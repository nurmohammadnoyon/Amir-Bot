"""
scraper2.py — Method 2 panel scraper for bot.py

Uses httpx.AsyncClient with follow_redirects=True — the proven approach from
the backup bot. httpx correctly handles all panel login redirects including IMS
which previously had CDR redirect issues with requests.Session.

No panels are hardcoded. All panels come from bot_settings["panels"] via get_settings().
Runs in a dedicated background thread with its own asyncio event loop.

Called by bot.py:
    import scraper2
    scraper2.start(on_otp_found=callback, get_settings=lambda: bot_settings)

Callback signature:
    def on_otp_found(num: str, otp: str, msg_text: str, panel_name: str, cli: str = "", received_ts: str = ""): ...
"""

import asyncio
import hashlib
import re
import threading
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

# ─── Globals ─────────────────────────────────────────────────────────────────

_on_otp_found  = None
_get_settings  = None
_processed     = set()
_processed_order = deque()   # FIFO eviction order, paired with _processed
_proc_lock     = threading.Lock()
_loop          = None
_FETCH_INTERVAL = 1     # seconds between polls per panel (was 3 → faster OTP pickup)

# Panels that have already completed their initial "mark existing OTPs as
# seen" pass, at least once in this process's lifetime. This is intentionally
# module-level (NOT a local variable inside _panel_worker) — if the worker's
# asyncio task dies (e.g. an unhandled exception in session.login()) and the
# supervisor spawns a brand-new _panel_worker for the same panel index, a
# local `first_run = True` would silently re-mark every currently-visible
# record as "seen" WITHOUT forwarding it, permanently losing any real OTP
# that happened to be sitting on the panel at that moment. Tracking this
# per-idx at module scope means a respawn is treated as a normal resumed
# fetch cycle — genuinely new OTPs still get forwarded via the persistent
# _processed dedup set below.
_panel_first_run_done: set = set()

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── OTP extraction (mirrors bot.py's extract_otp_code) ──────────────────────

def _extract_otp(text: str):
    if not text:
        return None
    clean = re.sub(r"[\u200B-\u200D\uFEFF]", "", str(text))

    # BUG FIX: Strip date/timestamp patterns FIRST — before ANY digit-pattern
    # matching.  Previously this was only done inside the digit-fallback branch
    # (step 4), so the multi-part OTP rules (step 2) could misread a timestamp
    # like "08:13:13" as the OTP code "081313" (three 2-digit segments joined).
    # Stripping real dates/times up front removes the false-positive at the
    # source for every branch — mirrors what bot.py's extract_otp_code does.
    clean = re.sub(r"\d{4}[-/]\d{2}[-/]\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", " ", clean)
    clean = re.sub(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?", " ", clean)
    clean = re.sub(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)", " ", clean)

    # 1. Keyword-based — HIGHEST PRIORITY
    # Broad match: keyword + up to 60 non-digit/non-newline chars (lazy) + number.
    # Handles all forms:
    #   "Your code is 04870"            keyword → connector → number
    #   "Votre code est 1759227"         French "est" connector
    #   "Code Snapchat : 121059"         word between keyword and ":"
    #   "OTP: 1234"  "رمز: 9999"         direct separator
    kws = [
        "your code", "votre code", "code secret", "code",
        "otp", "pin", "verification", "auth",
        "secret", "رمز", "كود", "كد", "код",
    ]
    kp  = "|".join(re.escape(k) for k in kws)
    m = re.search(rf"(?:{kp})\b[^0-9\n]{{0,60}}?([0-9]{{4,10}})(?!\d)", clean, re.I)
    if m:
        return m.group(1)
    # Reverse form: "08076 is your code / OTP / account"
    m_rev = re.search(r"([0-9]{4,10})\s+is\s+(?:your|the)\b", clean, re.I)
    if m_rev:
        return m_rev.group(1)

    # 2. Multi-part OTPs (e.g. 123-456 or 809-761) — date patterns explicitly excluded
    # 2-part: 123-456 or 536 714
    two = re.search(r"(?<!\d)(\d{3})[-\s](\d{3})(?!\d)", clean)
    if two:
        return two.group(1) + two.group(2)
    # 3-part: 80-97-61 — skip if middle segment is 01-12 (date month)
    for cand in re.finditer(r"(?<!\d)\d{2}[-\s]\d{2}[-\s]\d{2}(?!\d)", clean):
        parts = re.split(r"[-\s]+", cand.group(0))
        try:
            if 1 <= int(parts[1]) <= 12:
                continue
        except (ValueError, IndexError):
            pass
        return cand.group(0).replace("-", "").replace(" ", "")

    # 3. Google OTP
    gm = re.search(r"G-(\d{6})", clean, re.IGNORECASE)
    if gm:
        return gm.group(1)

    # 4. Digit fallback (date/time already stripped above at the top)
    clean_fb = re.sub(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?", "", clean)
    clean_fb = re.sub(r"\d{2}/\d{2}/\d{4}", "", clean_fb)
    digits = re.findall(r"(?<!\d)\d{4,8}(?!\d)", clean_fb)
    if digits:
        return digits[0]
    return None

# ─── Dedup ───────────────────────────────────────────────────────────────────

def _msg_norm(text: str) -> str:
    """Normalize message text for dedup keys.
    Strips HTML tags and normalises whitespace so minor panel formatting
    differences don't produce different keys for the same underlying SMS.
    Capped at 120 chars — long messages are uniquely identified by their
    first chunk; truncation avoids unbounded key growth."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", str(text))
    t = " ".join(t.split())
    return t[:120]

def _dedup_key(tag: str, num: str, otp: str, dt: str = "", msg: str = "") -> str:
    # Dedup rule (matches user requirement exactly):
    #   • Same number + same OTP + same message + same received time  → forward ONCE
    #   • Same number + same OTP + same message + different time       → forward BOTH
    #   • Same number + same time + different OTP                      → forward BOTH
    # Including the message prevents two truly different SMSs that happen to
    # carry the same OTP code at the same second from being collapsed into one.
    # Including the datetime string (not a rounded bucket) means a 1-second
    # difference in received time always produces a different key.
    # When no datetime is available (HTML panels) dt="" — any exact duplicate
    # (same num+otp+msg) within the same poll window is still blocked.
    return hashlib.md5(f"{tag}|{num}|{otp}|{_msg_norm(msg)}|{dt}".encode()).hexdigest()

def _is_processed(key: str) -> bool:
    with _proc_lock:
        return key in _processed

def _mark_processed(key: str):
    with _proc_lock:
        if key in _processed:
            return
        _processed.add(key)
        _processed_order.append(key)
        # Evict oldest entries once we exceed the cap, instead of wiping the
        # whole set — a bulk .clear() forgot every OTP ever seen in one shot,
        # which meant older (still-valid-looking) rows on a panel could be
        # treated as "new" again and re-forwarded as a duplicate.
        while len(_processed_order) > 10000:
            old = _processed_order.popleft()
            _processed.discard(old)

# ─── Login page detection ─────────────────────────────────────────────────────

def _is_login_page(html: str, url: str = "") -> bool:
    if re.search(r"/(login|signin|sign-in|logon)(/|$|\?)", url.lower()):
        return True
    soup = BeautifulSoup(html, "html.parser")
    if soup.find("input", {"type": "password"}):
        return True
    title = soup.find("title")
    if title and any(w in title.get_text().lower() for w in ["login", "sign in", "log in"]):
        return True
    body = html.lower()
    for phrase in ["session expired", "please login", "please log in",
                   "please sign in", "unauthorized", "login required"]:
        if phrase in body:
            return True
    return False

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _solve_math_captcha(expr: str) -> str:
    expr = expr.replace("×", "*").replace("x", "*").replace("÷", "/")
    try:
        return str(int(eval(expr)))  # noqa: S307
    except Exception:
        return "0"

def _extract_csrf(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    hidden = soup.find("input", {"name": re.compile(r"_token|csrf|authenticity_token", re.I)})
    if hidden and hidden.get("value"):
        return hidden["value"]
    return ""

def _build_ajax_url(base: str, role: str, records: int = 200) -> str:
    today    = datetime.now().strftime("%Y-%m-%d 00:00:00").replace(" ", "%20")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 23:59:59").replace(" ", "%20")
    api_path = f"/{role}/res/data_smscdr.php"
    return (
        f"{base}{api_path}?fdate1={today}&fdate2={tomorrow}&"
        "frange=&fnum=&fcli=&fgdate=&fgmonth=&fgrange=&fgnumber=&fgcli=&fg=0&"
        f"sEcho=1&iColumns=7&sColumns=%2C%2C%2C%2C%2C%2C&iDisplayStart=0&iDisplayLength={records}&"
        "mDataProp_0=0&sSearch_0=&bRegex_0=false&bSearchable_0=true&bSortable_0=true&"
        "mDataProp_1=1&sSearch_1=&bRegex_1=false&bSearchable_1=true&bSortable_1=true&"
        "mDataProp_2=2&sSearch_2=&bRegex_2=false&bSearchable_2=true&bSortable_2=true&"
        "mDataProp_3=3&sSearch_3=&bRegex_3=false&bSearchable_3=true&bSortable_3=true&"
        "mDataProp_4=4&sSearch_4=&bRegex_4=false&bSearchable_4=true&bSortable_4=true&"
        "mDataProp_5=5&sSearch_5=&bRegex_5=false&bSearchable_5=true&bSortable_5=true&"
        "mDataProp_6=6&sSearch_6=&bRegex_6=false&bSearchable_6=true&bSortable_6=true&"
        "sSearch=&bRegex=false&iSortCol_0=0&sSortDir_0=desc&iSortingCols=1"
    )

# ─── Record parsers ───────────────────────────────────────────────────────────

_SKIP_VALS = {"", "none", "0", "1", "null", "undefined", "n/a", "-"}
# NOTE: this must only match actual currency/price/status values, never a bare
# OTP code. A plain digit string like "63191" used to match the old pattern
# (all currency-symbol/decimal parts are optional, so `\d*\.?\d*` alone matched
# any bare number) and got silently skipped — meaning any panel that returns
# the raw code with no surrounding text (no "your code is..." wrapper) lost
# that OTP entirely, regardless of digit count. Now a match requires an actual
# currency symbol or a decimal point, so bare integers of any length fall
# through to the CLI/message classification below instead of being discarded.
_SKIP_RE   = re.compile(
    r"^[\$€£₹¥₩₺₽]\s*\d*\.?\d*$|^\d*\.\d+[\$€£₹¥₩₺₽]?$"
    r"|^(delivered|sent|failed|pending|rejected|received|success|error)$",
    re.I,
)

_CLI_KEYS   = ["cli", "client", "service", "app", "provider", "application", "sender_id", "source"]
_NUM_KEYS   = ["destination", "number", "num", "msisdn", "phone", "mobile", "to"]
_MSG_KEYS   = ["message", "msg", "sms", "text", "content", "body"]

def _extract_cli_from_dict(row: dict) -> str:
    """Extract CLI/service name from a dict row, ignoring purely numeric values."""
    lower = {str(k).lower(): v for k, v in row.items()}
    for k in _CLI_KEYS:
        val = str(lower.get(k, "") or "").strip()
        if val and not re.match(r'^\+?[\d\s\-]+$', val):
            return val
    return ""

def _parse_ajax_records(data: dict, p: dict) -> list:
    n_idx = max(0, int(p.get("num_col_idx", 2)) - 1)
    rows  = data.get("aaData") or data.get("data") or []
    out   = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            dt_str = str(row[0]).strip()
            number = re.sub(r"[^\d]", "", str(row[n_idx] if n_idx < len(row) else row[min(2, len(row)-1)]))
            msg    = ""
            cli    = ""
            for i in range(len(row) - 1, 1, -1):
                v = re.sub(r"<[^>]+>", "", str(row[i])).strip()
                if not v or v.lower() in _SKIP_VALS:
                    continue
                if _SKIP_RE.match(v) or len(v) < 3:
                    continue
                # If it looks like a service name (short, no OTP digits) treat as CLI
                if not cli and len(v) <= 30 and not re.search(r'\d{4,}', v):
                    cli = v
                    continue
                msg = v
                break
            if number and msg:
                out.append({"number": number, "message": msg, "datetime": dt_str, "cli": cli})
        elif isinstance(row, dict):
            lower_row = {str(k).lower(): v for k, v in row.items()}
            number = re.sub(r"[^\d]", "", str(
                next((lower_row[k] for k in _NUM_KEYS if k in lower_row and lower_row[k]), "") or ""))
            message = re.sub(r"<[^>]+>", "", str(
                next((lower_row[k] for k in _MSG_KEYS if k in lower_row and lower_row[k]), "") or "")).strip()
            dt_str  = str(row.get("datetime") or row.get("date") or "").strip()
            cli     = _extract_cli_from_dict(row)
            if number and message:
                out.append({"number": number, "message": message, "datetime": dt_str, "cli": cli})
    return out

_CLI_COL_NAMES = ["cli", "client", "service", "app", "provider", "application", "sender", "source"]

def _parse_html_records(html: str, p: dict) -> list:
    n_col = p.get("num_col_name", "number").lower()
    m_col = p.get("msg_col_name", "message").lower()
    n_idx = max(0, int(p.get("num_col_idx", 2)) - 1)
    m_idx = max(0, int(p.get("msg_col_idx", 4)) - 1)
    soup  = BeautifulSoup(html, "html.parser")
    out   = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        fn, fm, fc = n_idx, m_idx, -1  # fc = cli column index (-1 = not found)
        header_cells = rows[0].find_all(["th", "td"])
        for i, cell in enumerate(header_cells):
            ct = cell.get_text(strip=True).lower()
            if n_col in ct or "number" in ct or "phone" in ct or "msisdn" in ct:
                fn = i
            if m_col in ct or "message" in ct or "sms" in ct or "text" in ct:
                fm = i
            # Detect CLI/service column
            if any(c in ct for c in _CLI_COL_NAMES):
                fc = i
        for row in rows[1:]:
            cols = row.find_all(["td", "th"])
            if len(cols) <= max(fn, fm):
                continue
            number  = re.sub(r"[^\d]", "", cols[fn].get_text(strip=True))
            message = cols[fm].get_text(separator=" ", strip=True)
            # Extract CLI from dedicated column if detected
            cli = ""
            if fc >= 0 and fc < len(cols):
                cli_raw = cols[fc].get_text(strip=True)
                if cli_raw and not re.match(r'^\+?[\d\s\-]+$', cli_raw):
                    cli = cli_raw
            if number and 5 <= len(number) <= 18 and message:
                out.append({"number": number, "message": message, "datetime": "", "cli": cli})
    return out

# ─── Panel session (httpx.AsyncClient — backup-bot proven approach) ───────────

class _PanelSession:
    def __init__(self, idx: int, p: dict):
        self.idx      = idx
        self.p        = p
        self.tag      = (p.get("name") or p.get("type") or f"Panel{idx}").strip()
        self.username = (p.get("username") or p.get("user") or "").strip()
        self.password = (p.get("password") or p.get("pass") or "").strip()
        self.login_url = (p.get("login_url") or "").strip()
        self._client: httpx.AsyncClient | None = None
        self._role    = "client"
        self._sesskey = None
        self._csrf    = None
        self._skip_sesskey = False

    def _base(self) -> str:
        url = self.login_url
        for suffix in ["/login", "/signin", "/sign-in", "/logon", "/auth"]:
            idx = url.lower().find(suffix)
            if idx != -1:
                return url[:idx]
        return url.rstrip("/")

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=_BROWSER_HEADERS.copy(),
        )

    async def login(self) -> bool:
        if not self.login_url or not self.username or not self.password:
            print(f"[S2/{self.tag}] Missing login_url / credentials — skipping")
            return False

        base = self._base()
        login_paths = list(dict.fromkeys(filter(None, [
            self.login_url,
            f"{base}/login",
            f"{base}/signin",
            f"{base}/sign-in",
            f"{base}/client/login",
            f"{base}/agent/login",
        ])))

        client     = self._new_client()
        login_url  = None
        login_resp = None

        try:
            for lpath in login_paths:
                try:
                    resp = await client.get(lpath, timeout=15)
                    if resp.status_code == 200:
                        login_url  = lpath
                        login_resp = resp
                        if _is_login_page(resp.text, str(resp.url)):
                            break
                except Exception:
                    continue

            if login_resp is None:
                print(f"[S2/{self.tag}] ⚠️ Cannot reach panel")
                await client.aclose()
                return False

            soup = BeautifulSoup(login_resp.text, "html.parser")
            form_data: dict = {}
            form_action_url = None

            form   = soup.find("form", {"method": re.compile("post", re.I)}) or soup.find("form")
            inputs = form.find_all("input") if form else soup.find_all("input")

            if form:
                action = form.get("action", "")
                if action:
                    form_action_url = (
                        action if action.startswith("http")
                        else urljoin(base + "/", action.lstrip("/"))
                    )

            # Math captcha
            captcha_answer = None
            mm = re.search(r"(\d+)\s*([\+\-\*×x])\s*(\d+)\s*=\s*\?",
                           login_resp.text, re.I)
            if mm:
                captcha_answer = _solve_math_captcha(
                    f"{mm.group(1)} {mm.group(2)} {mm.group(3)}")
                print(f"[S2/{self.tag}] Captcha: {mm.group(0)} = {captcha_answer}")

            # CSRF
            csrf_inp = soup.find("input",
                                 {"name": re.compile(r"_token|csrf|authenticity_token", re.I)})
            if csrf_inp and csrf_inp.get("value"):
                form_data[csrf_inp["name"]] = csrf_inp["value"]

            USER_F    = ["user", "email", "username", "login", "user_id", "phone", "mobile"]
            PASS_F    = ["pass", "password", "pwd", "passwd"]
            CAPT_F    = ["capt", "ans", "code", "result", "captcha", "verification"]

            for inp in inputs:
                name = inp.get("name")
                if not name:
                    continue
                nl = name.lower()
                if csrf_inp and name == csrf_inp.get("name"):
                    continue
                if any(f in nl for f in USER_F):
                    form_data[name] = self.username
                elif any(f in nl for f in PASS_F):
                    form_data[name] = self.password
                elif any(f in nl for f in CAPT_F):
                    form_data[name] = captcha_answer or inp.get("value", "")
                else:
                    form_data[name] = inp.get("value", "")

            if not any(any(f in k.lower() for f in USER_F) for k in form_data):
                form_data["username"] = self.username
            if not any(any(f in k.lower() for f in PASS_F) for k in form_data):
                form_data["password"] = self.password

            signin_candidates = list(dict.fromkeys(filter(None, [
                form_action_url,
                f"{base}/signin",
                f"{base}/login",
                login_url,
                f"{base}/auth/login",
            ])))

            OK_WORDS  = ["dashboard", "logout", "cdr", "smscdr", "inbox",
                         "/client/", "/agent/", "welcome", "sms report"]
            ERR_WORDS = ["invalid", "wrong", "error", "failed", "incorrect",
                         "unauthorized", "gagal", "salah"]

            await asyncio.sleep(0.8)

            for su in signin_candidates:
                try:
                    post = await client.post(
                        su, data=form_data,
                        headers={
                            "Referer":      login_url or su,
                            "Origin":       base,
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        timeout=30,
                    )
                    fl        = str(post.url).lower()
                    bl        = post.text.lower()
                    not_login = not re.search(r"/(login|signin|sign-in)(/|$|\?)", fl)
                    has_ok    = any(w in bl for w in OK_WORDS)
                    still_pw  = bool(
                        BeautifulSoup(post.text, "html.parser")
                        .find("input", {"type": "password"})
                    )
                    has_error = any(w in bl for w in ERR_WORDS) and not has_ok

                    if has_error:
                        print(f"[S2/{self.tag}] Error response from {su} — trying next")
                        continue

                    if (not_login and not still_pw) or has_ok:
                        print(f"[S2/{self.tag}] ✅ Login OK via {su}")
                        self._role  = "agent" if "/agent" in fl else "client"
                        self._csrf  = _extract_csrf(post.text) or None
                        self._sesskey = None
                        self._skip_sesskey = False
                        if self._client:
                            await self._client.aclose()
                        self._client = client
                        return True
                except Exception:
                    continue

            print(f"[S2/{self.tag}] ❌ All login attempts failed (wrong credentials?)")
            await client.aclose()
            return False

        except Exception as e:
            print(f"[S2/{self.tag}] Login exception: {e}")
            try:
                await client.aclose()
            except Exception:
                pass
            return False

    async def _get_sesskey(self) -> str:
        if self._sesskey:
            return self._sesskey
        if self._skip_sesskey:
            return ""
        base  = self._base()
        roles = (["agent", "client"] if self._role == "agent" else ["client", "agent"])
        for role in roles:
            for path in (f"/{role}/SMSCDRStats", f"/{role}/dashboard", f"/{role}/"):
                try:
                    r = await self._client.get(f"{base}{path}", timeout=20)
                    if r.status_code != 200:
                        continue
                    if re.search(r"/(login|signin|sign-in|logon)(/|$|\?)",
                                 str(r.url).lower()):
                        continue
                    m = re.search(r"sesskey=([a-zA-Z0-9+/=]+)", r.text) or \
                        re.search(r"['\"]?sesskey['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]",
                                  r.text)
                    if m:
                        self._sesskey = m.group(1)
                        print(f"[S2/{self.tag}] sesskey: {self._sesskey[:10]}...")
                        return self._sesskey
                except Exception:
                    continue
        self._skip_sesskey = True
        return ""

    async def fetch_records(self) -> list | None:
        if not self._client:
            return None
        base    = self._base()
        sesskey = await self._get_sesskey()
        # BUG FIX: do NOT reset _sesskey = None here. Doing so forced a fresh
        # dashboard/SMSCDRStats page fetch on every single poll cycle (every 1-2 s)
        # just to re-extract the same sesskey — wasted one HTTP round-trip per
        # poll, slowed OTP pickup, and increased server load. The sesskey is
        # already automatically cleared on re-login (login() sets it to None),
        # so it stays valid until a session expiry triggers a fresh login.

        p = self.p

        # Try DataTables AJAX for both roles
        for role in ([self._role, "agent" if self._role == "client" else "client"]):
            ajax_url = _build_ajax_url(base, role)
            if sesskey:
                ajax_url += f"&sesskey={sesskey}"
            ref_url = f"{base}/{role}/SMSCDRStats"
            hdrs = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer":          ref_url,
                "Accept":           "application/json, text/javascript, */*; q=0.01",
            }
            if self._csrf:
                hdrs["X-CSRF-TOKEN"] = self._csrf
            try:
                resp = await self._client.get(ajax_url, headers=hdrs, timeout=60)
                if resp.status_code in (401, 403, 502, 503, 504):
                    return None
                if _is_login_page(resp.text, str(resp.url)):
                    return None
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and ("aaData" in data or "data" in data):
                            recs = _parse_ajax_records(data, p)
                            if role != self._role:
                                print(f"[S2/{self.tag}] Role switch → {role}")
                                self._role = role
                            print(f"[S2/{self.tag}] AJAX [{role}] — {len(recs)} rows")
                            return recs
                    except Exception:
                        if _is_login_page(resp.text, str(resp.url)):
                            return None
            except httpx.ConnectError:
                return []
            except Exception as e:
                print(f"[S2/{self.tag}] AJAX error: {e}")

        # Fallback: fetch CDR HTML page and parse table
        msg_link = (p.get("msg_link") or "").strip()
        if not msg_link:
            msg_link = f"{base}/client/SMSCDRStats"
        if not msg_link.startswith("http"):
            msg_link = "http://" + msg_link
        try:
            r = await self._client.get(msg_link, timeout=30)
            if _is_login_page(r.text, str(r.url)):
                return None
            recs = _parse_html_records(r.text, p)
            print(f"[S2/{self.tag}] HTML fallback — {len(recs)} rows")
            return recs
        except Exception as e:
            print(f"[S2/{self.tag}] HTML fallback error: {e}")
            return []

    async def close(self):
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


# ─── Worker per panel ─────────────────────────────────────────────────────────

async def _panel_worker(idx: int, p: dict):
    session    = _PanelSession(idx, p)
    tag        = session.tag
    fail_count = 0
    # NOTE: do not use a local `first_run` variable here — see the
    # _panel_first_run_done module comment above for why that silently lost
    # real OTPs whenever this task was respawned after a crash.

    print(f"[S2/{tag}] Worker started | user={session.username}")

    while True:
        if not _get_settings:
            await asyncio.sleep(5)
            continue

        settings = _get_settings()
        panels   = settings.get("panels", [])
        if idx >= len(panels):
            print(f"[S2/{tag}] Panel removed — stopping worker")
            await session.close()
            return

        if panels[idx].get("status") != "ON":
            # Stopped from the admin panel — don't even attempt to log in
            # until it's switched back "ON".
            await asyncio.sleep(3)
            continue

        try:
            logged_in = await session.login()
        except Exception as e:
            # An uncaught exception here used to crash this whole asyncio
            # task. The supervisor would then spawn a brand-new worker with
            # first_run reset to True, which silently re-marked every
            # currently-visible OTP as "seen" without ever forwarding it —
            # the actual root cause of OTPs randomly going missing.
            print(f"[S2/{tag}] login() raised {e} — treating as failed login")
            logged_in = False
        if not logged_in:
            fail_count += 1
            wait = 5   # always retry quickly — no long exponential backoff
            print(f"[S2/{tag}] Login failed (attempt {fail_count}) — retry in {wait}s")
            await asyncio.sleep(wait)
            continue

        fail_count = 0
        consec     = 0

        while True:
            # Verify panel still present
            settings = _get_settings()
            panels   = settings.get("panels", [])
            if idx >= len(panels):
                print(f"[S2/{tag}] Panel removed — closing worker")
                await session.close()
                return

            # Admin "Stop" on a panel only flips its status flag — the panel
            # entry stays in the list, so the removed-panel check above never
            # triggers. Previously nothing here looked at status, so a
            # stopped panel kept fetching/forwarding OTPs in the background.
            # Pause here (without closing the session) until it's turned
            # back "ON", then resume right where we left off.
            if panels[idx].get("status") != "ON":
                await asyncio.sleep(3)
                continue

            try:
                records = await session.fetch_records()

                if records is None:
                    print(f"[S2/{tag}] Session expired — re-login")
                    await session.close()
                    break

                if idx not in _panel_first_run_done:
                    # Mark all existing OTPs as seen so we don't re-forward them.
                    # This module-level flag only fires once per panel index
                    # for the whole process lifetime — a worker respawn (after
                    # a crash/re-login) must NOT hit this branch again, or any
                    # real OTP sitting on the panel at that moment gets marked
                    # seen without ever being forwarded.
                    count = 0
                    for rec in (records or []):
                        otp = _extract_otp(rec.get("message", ""))
                        if not otp:
                            continue
                        # Pass message so the startup key matches the forwarding key exactly.
                        _mark_processed(_dedup_key(tag, rec["number"], otp, rec.get("datetime", ""), rec.get("message", "")))
                        count += 1
                    print(f"[S2/{tag}] Startup: {count} existing OTP(s) marked as seen")
                    _panel_first_run_done.add(idx)
                else:
                    new_count = 0
                    for rec in (records or []):
                        num = rec.get("number", "")
                        msg = rec.get("message", "")
                        if not num or not msg:
                            continue
                        otp = _extract_otp(msg)
                        if not otp:
                            continue
                        rec_dt  = rec.get("datetime", "")
                        # Key includes message so that same OTP code + different message
                        # text at the same timestamp → different key → both forwarded.
                        key = _dedup_key(tag, num, otp, rec_dt, msg)
                        if _is_processed(key):
                            continue
                        _mark_processed(key)
                        # cli from scraped table (may be empty string if not detected)
                        rec_cli = rec.get("cli", "")
                        print(f"[S2/{tag}] 🔔 OTP {otp} | +{num} | CLI={rec_cli!r} | ts={rec_dt!r} | {msg[:50]!r}")
                        if _on_otp_found:
                            try:
                                _on_otp_found(num, otp, msg, tag, rec_cli, rec_dt)
                            except Exception as cb_err:
                                print(f"[S2/{tag}] Callback error: {cb_err}")
                        new_count += 1
                        # BUG FIX: removed asyncio.sleep(0.05) per OTP.
                        # The callback only enqueues to _otp_forward_queue
                        # (non-blocking), so no inter-OTP delay is needed.
                        # 200 OTPs × 50ms = 10-second drain window during
                        # which new panel records pile up and fall off the
                        # server's visible list → permanent OTP loss under
                        # high load. Rate-limiting is handled by
                        # _otp_wait_global_slot() in the sender threads.
                    if new_count:
                        print(f"[S2/{tag}] ✅ {new_count} new OTP(s) forwarded")

                consec = 0

            except Exception as e:
                print(f"[S2/{tag}] Worker error: {e}")
                consec += 1
                if consec > 10:
                    print(f"[S2/{tag}] Too many consecutive errors — re-login")
                    await session.close()
                    break
                await asyncio.sleep(min(2 ** consec, 60))
                continue

            # Default stays fast (near-instant OTP pickup). A specific panel
            # can be slowed down individually via its own "fetch_interval"
            # setting (e.g. 6-7s) if that provider's API only allows 1
            # request every 5s — other panels are not affected.
            await asyncio.sleep(panels[idx].get("fetch_interval", _FETCH_INTERVAL) if idx < len(panels) else _FETCH_INTERVAL)

        await asyncio.sleep(5)


# ─── Supervisor: watches panels list, spawns/kills workers dynamically ────────

_worker_tasks: dict = {}

async def _supervisor():
    print("[S2] Supervisor started — watching bot_settings['panels']")
    while True:
        try:
            if _get_settings:
                panels = _get_settings().get("panels", [])
                for idx, p in enumerate(panels):
                    # scraper2 only handles Auto Captcha Panels (login-based).
                    # API panels (Konekta, Number Panel, etc.) are handled by
                    # bot.py's panel_monitor_thread — spawning a scraper2
                    # worker for them just causes repeated "Missing login_url"
                    # failures with no benefit.
                    if p.get("type", "API Panel") != "Auto Captcha Panel":
                        # Cancel any leftover worker if panel type was changed
                        stale = _worker_tasks.pop(idx, None)
                        if stale and not stale.done():
                            stale.cancel()
                        continue

                    task = _worker_tasks.get(idx)
                    if task is None or task.done():
                        name = (p.get("name") or p.get("type") or f"Panel{idx}").strip()
                        print(f"[S2] Spawning worker for panel #{idx}: {name}")
                        t = asyncio.create_task(
                            _panel_worker(idx, p),
                            name=f"s2-worker-{idx}",
                        )
                        _worker_tasks[idx] = t

                # Cancel workers whose panels were removed
                for idx in list(_worker_tasks.keys()):
                    if idx >= len(panels):
                        task = _worker_tasks.pop(idx, None)
                        if task and not task.done():
                            task.cancel()
                            print(f"[S2] Cancelled worker for removed panel #{idx}")

        except Exception as e:
            print(f"[S2] Supervisor error: {e}")

        await asyncio.sleep(10)


# ─── Public API ───────────────────────────────────────────────────────────────

def start(on_otp_found, get_settings):
    """
    Start scraper2 in a background daemon thread.

    on_otp_found(num, otp, msg_text, panel_name) — called for each new OTP.
    get_settings()                                — returns live bot_settings dict.
    """
    global _on_otp_found, _get_settings, _loop

    _on_otp_found = on_otp_found
    _get_settings = get_settings

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(_supervisor())
        except Exception as e:
            print(f"[S2] Event loop crashed: {e}")
        finally:
            _loop.close()

    t = threading.Thread(target=_run, daemon=True, name="scraper2-loop")
    t.start()
    print("[S2] scraper2 background thread started ✅")
