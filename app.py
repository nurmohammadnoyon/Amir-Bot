import requests
import time
import json
import os
import uuid
import threading
import random
import re
import html
import csv
import io
import hashlib
import pyotp
import traceback
from collections import Counter 
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from datetime import datetime 
from urllib.parse import urljoin

# ==========================================
# Configuration (Token & Owner ID)
# ==========================================
# Fill these in directly (simplest way to run on your own server), OR set
# BOT_TOKEN / BOT_OWNER_ID as environment variables — env vars win if set.
BOT_TOKEN_HARDCODED = "8667546285:AAHLSXHsBRP8kex5fNY4G7D4JBFrfaNY0s0"  # Set BOT_TOKEN in the environment.
BOT_OWNER_ID_HARDCODED = "8896123901"  # Set BOT_OWNER_ID in the environment.

TOKEN = os.environ.get("BOT_TOKEN") or BOT_TOKEN_HARDCODED
if not TOKEN or TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
    raise RuntimeError(
        "Bot token is not set. Either edit BOT_TOKEN_HARDCODED near the top of "
        "bot.py, or set the BOT_TOKEN environment variable, before starting the bot."
    )
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# ── Portable high-throughput profile ────────────────────────────────────────
# 10,000 is the bounded logical queue capacity, not 10,000 OS threads.
# Spawning 10,000 native threads would exhaust memory and destabilize Telegram.
LOGICAL_WORKER_CAP = 10_000
REAL_MESSAGE_WORKERS = 256
REAL_CALLBACK_WORKERS = 128
OTP_SENDER_THREADS = 50
FILE_URL = f"https://api.telegram.org/file/bot{TOKEN}/"

_owner_id_raw = os.environ.get("BOT_OWNER_ID") or BOT_OWNER_ID_HARDCODED
if not _owner_id_raw or _owner_id_raw == "PUT_YOUR_TELEGRAM_USER_ID_HERE":
    raise RuntimeError(
        "Owner/admin ID is not set. Either edit BOT_OWNER_ID_HARDCODED near the "
        "top of bot.py, or set the BOT_OWNER_ID environment variable, to your "
        "Telegram numeric user ID before starting the bot."
    )
try:
    OWNER_ID = int(_owner_id_raw)
except ValueError:
    raise RuntimeError(
        f"Owner/admin ID must be numeric, got: {_owner_id_raw!r}. Fix "
        "BOT_OWNER_ID_HARDCODED (or the BOT_OWNER_ID environment variable)."
    )
BOT_USERNAME = ""
BOT_NAME = ""
DB_PATH = "data/bot.db"

# ==========================================
# Premium Emoji Database
# ==========================================
PEM = {
    "ok": '<tg-emoji emoji-id="5352694861990501856">✅</tg-emoji>',
    "no": '<tg-emoji emoji-id="5420130255174145507">❌</tg-emoji>',
    "warn": '<tg-emoji emoji-id="5336944168944047463">⚠️</tg-emoji>',
    "admin": '<tg-emoji emoji-id="5949327894567195412">📊</tg-emoji>',
    "user": '<tg-emoji emoji-id="5352861489541714456">👤</tg-emoji>',
    "file": '<tg-emoji emoji-id="5352721946054268944">📁</tg-emoji>',
    "rocket": '<tg-emoji emoji-id="5352597830089347330">🚀</tg-emoji>',
    "graph": '<tg-emoji emoji-id="5352877703043258544">📊</tg-emoji>',
    "money": '<tg-emoji emoji-id="5409048419211682843">💲</tg-emoji>',
    "gift": '<tg-emoji emoji-id="5332724926216428039">🎁</tg-emoji>',
    "msg": '<tg-emoji emoji-id="5337302974806922068">💬</tg-emoji>',
    "gear": '<tg-emoji emoji-id="5420155432272438703">⚙️</tg-emoji>',
    "link": '<tg-emoji emoji-id="5839375134061761681">🔗</tg-emoji>',
    "trash": '<tg-emoji emoji-id="5422557736330106570">🗑</tg-emoji>',
    "upload": '<tg-emoji emoji-id="5445355530111437729">📤</tg-emoji>',
    "world": '<tg-emoji emoji-id="5336972142066047577">🌐</tg-emoji>',
    "lock": '<tg-emoji emoji-id="6068830682359010545">🔐</tg-emoji>',
    "phone": '<tg-emoji emoji-id="5337132498965010628">📱</tg-emoji>',
    "num": '<tg-emoji emoji-id="5841276284155467413">🔢</tg-emoji>',
    "pin": '<tg-emoji emoji-id="5352922460897452503">📍</tg-emoji>',
    "star": '✨',
    "hi": '<tg-emoji emoji-id="5353027129250453493">👋</tg-emoji>',
    "tether": '<tg-emoji emoji-id="5359437015752401733">💵</tg-emoji>',
    "binance": '<tg-emoji emoji-id="5888561507557447441">🪙</tg-emoji>',
    "card": '<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji>',
    "id": '<tg-emoji emoji-id="5841276284155467413">🆔</tg-emoji>',
    "group": '<tg-emoji emoji-id="5841494459904168607">👥</tg-emoji>',
    "owner": '<tg-emoji emoji-id="5951518619945931024">👑</tg-emoji>'
}

GLOBAL_BODY_EMOJIS = {
    "➖": "5870818207383686839", "🚫": "5334807341109908955", "😒": "5334763399299506604",
    "🖥": "5334880948259427772", "🌐": "5334590977837403844", "🌟": "5337102391244263212",
    "🕓": "5336983442125001376", "⌛": "5337172996211648018", "💬": "5337302974806922068",
    "🔐": "5337255927735163754", "🍏": "5337132498965010628", "❔": "5336850036145823599",
    "⚠️": "5336944168944047463", "🔥": "5337267511261960341", "💸": "5348469219761626211",
    "🥚": "5348390922507817684", "👨‍⚖": "5334763399299506604", "🐁": "5348494358205207761",
    "🧻": "5348486915026884464", "⚗": "5346311574221000149", "🛴": "5348075478634766440",
    "📊": "5353032893096567467", "🔢": "5352862640592949843", "👤": "5352861489541714456",
    "📁": "5352721946054268944", "🚀": "5352597830089347330", "💎": "5352838545826420397",
    "📍": "5352922460897452503", "👋": "5353027129250453493", "✅": "5352694861990501856",
    "1️⃣": "5352651766288652742", "2️⃣": "5355186458418257716", "3️⃣": "5352867219028091093",
    "4️⃣": "5352566657216714037", "5️⃣": "5353086880835474989", "6️⃣": "5354859211975071385",
    "7️⃣": "5352859127309707652", "8️⃣": "5352957533600389988", "9️⃣": "5353060913463204207",
    "🔤": "5352727417842606016", "📣": "5352980533150259581", "📤": "5445355530111437729",
    "✨": "5352552689983067014", "🔹": "5352638632278660622", "🎙": "5355102594886833928",
    "💴": "5352985330628730418", "📅": "5352585194295564660", "📴": "5352974971167611327",
    "✏️": "5395444784611480792", "📱": "5337132498965010628", "🔗": "5420517437885943844",
    "❌": "5420130255174145507", "⚙️": "5420155432272438703", "🫂": "5420145051336485498",
    "➕": "5420323438508155202", "🗑": "5422557736330106570", "🎁": "5332724926216428039",
    "➤": "5420618897898381296", "🏢": "5420156334215565595", "💳": "5190899075968441286",
    "📝": "5192739271886282680", "🛡": "5190447043545438788", "🤝": "5192805934073685937",
    "💰": "5190576863226933563", "👀": "5190645917711114179", "🕹": "5193100774988617665",
    "🟢": "5192812028632274956", "🧪": "5190781475468915802", "🎨": "5190751148704833975",
    "📂": "5257969839313526622", "🌍": "5780471598922337683", "📌": "5318986077455795572",
    "📢": "5789428375261023681", "🆔": "5352862640592949843", "📈": "5352877703043258544",
    "🔔": "5352980533150259581", "🏦": "5348469219761626211", "🧾": "5192739271886282680",
    "👨‍⚖️": "5334763399299506604", "🔍": "5463352748751753567",
    "🔑": "5197288647275071607",
    "👥": "5841494459904168607",
    # ── Leaderboard / award emojis ──────────────────────────────────────────
    # These appear in daily-leaderboard announcements and rank displays.
    # Without tg-emoji IDs they rendered as plain Unicode on all clients;
    # now they show as Telegram premium animated emoji where supported.
    "🏆": "5361409666476013371", "🥇": "5361607641706451754",
    "🥈": "5361498674855269181", "🥉": "5361554452416003460",
    "🎉": "5354024891729614858", "🎖": "5357765700278574874"
}

DEFAULT_CUSTOM_MESSAGES = {
    "start": {"text": "━━━━━━━━━━━━━━━\n👋 Hello <b>{name}</b>!\n━━━━━━━━━━━━━━━\n\n🚀 Welcome to <b>Amir OTP Bot</b>\n\n✨ Get instant OTP codes &amp; earn money with every verification!\n\n💎 <b>Fast • Reliable • Premium Service</b>\n\n━━━━━━━━━━━━━━━\n📱 Bot: @{bot_username}", "buttons": []},
    "get_number": {"text": f"{PEM['pin']} Select a service:", "buttons": []},
    "select_country": {"text": f"📌 Select a country for {{service}}:", "buttons": []}, 

    "traffic": {"text": f"{PEM['graph']} <b>Traffic Overview</b>\n\n{PEM['ok']} Available Numbers: {{avail}}\n{PEM['rocket']} Assigned Numbers: {{assigned}}", "buttons": []},
    "refer": {"text": f"➖➖➖➖➖➖➖\n« {PEM['gift']} REFER & EARN »\n➖➖➖➖➖➖➖\n{PEM['link']} YOUR LINK:\n<code>{{ref_link}}</code>\n➖➖➖➖➖➖➖\n{PEM['user']} TOTAL REFERS: <b>{{total_ref}}</b>\n➖➖➖➖➖➖➖\n{PEM['tether']} PER REFER: <b>{{ref_reward}}</b>\n➖➖➖➖➖➖➖", "buttons": []},
    "withdrawal": {"text": f"➖➖➖➖➖➖➖\n《 {PEM['card']} WITHDRAWAL 》\n➖➖➖➖➖➖➖\n{PEM['msg']} Total OTP: {{total_otp}}\n➖➖➖➖➖➖➖\n{PEM['gift']} Total Refers: {{total_ref}}\n➖➖➖➖➖➖➖\n{PEM['tether']} BALANCE: {{bal}}\n➖➖➖➖➖➖➖\n{PEM['lock']} MINIMUM: {{min_w}}\n➖➖➖➖➖➖➖\nSELECT METHOD:", "buttons": []},

    "support": {"text": f"{PEM['msg']} Contact us for any help:", "buttons": []}
}

# ==========================================
# Database Setup (SQLite)
# ==========================================
import sqlite3

os.makedirs("data", exist_ok=True)

# ==========================================
# Local Numbers Folder (human-readable file backup, per service+country)
# e.g. numbers/egypt_whatsapp.txt — survives restarts even if the DB is reset.
# ==========================================
NUMBERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "numbers")
os.makedirs(NUMBERS_DIR, exist_ok=True)

db_lock = threading.Lock()
number_batches_lock = threading.Lock()  # guards number_batches mutations (select + delete must be atomic)

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode lets readers run while a write is in progress instead of
    # locking the whole file (default rollback-journal mode serializes
    # every connection against every other one). Under thousands of
    # concurrent workers this was a major source of the 3-4s reply delay.
    # busy_timeout makes a connection wait for a released lock instead of
    # raising "database is locked" immediately.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass
    return conn

def init_db():
    with db_lock:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            total_refers INTEGER DEFAULT 0,
            total_otps INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            ref_paid INTEGER DEFAULT 0,
            username TEXT DEFAULT NULL,
            first_name TEXT DEFAULT NULL
        )""")
        # Migrate existing DBs — add columns if missing
        for col, typ in [("username", "TEXT"), ("first_name", "TEXT"), ("language", "TEXT")]:
            try: c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT NULL")
            except: pass
        c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            account TEXT,
            request_id TEXT,
            status TEXT DEFAULT 'Pending',
            timestamp REAL
        )""")
        # Older databases were created before request_id was stored.  Keep
        # those databases readable so the original admin message can still be
        # matched to its durable withdrawal row after a restart.
        try:
            c.execute("ALTER TABLE withdrawals ADD COLUMN request_id TEXT")
        except Exception:
            pass
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_withdrawals_request_id "
            "ON withdrawals(request_id)"
        )
        c.execute("""CREATE TABLE IF NOT EXISTS bot_settings_store (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        # Persistent dedup table — survives bot restarts so old OTPs are
        # never re-forwarded hours later after a crash/redeploy.
        c.execute("""CREATE TABLE IF NOT EXISTS otp_dedup (
            uid TEXT PRIMARY KEY,
            ts  REAL NOT NULL
        )""")
        # Daily leaderboard — one row per (user, date). Survives restarts.
        # This is the source of truth for Today & Weekly leaderboards.
        c.execute("""CREATE TABLE IF NOT EXISTS daily_leaderboard (
            user_id INTEGER NOT NULL,
            date    TEXT    NOT NULL,
            count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )""")
        # Persistent OTP retry queue — stores sends that exhausted normal retries
        # so they survive a bot restart and are re-attempted with longer backoff.
        c.execute("""CREATE TABLE IF NOT EXISTS otp_retry_queue (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id       INTEGER NOT NULL,
            text          TEXT    NOT NULL,
            reply_markup  TEXT,
            parse_mode    TEXT    DEFAULT 'HTML',
            retry_count   INTEGER DEFAULT 0,
            created_at    REAL    NOT NULL,
            next_retry_at REAL    NOT NULL
        )""")
        conn.commit()
        conn.close()
    print("✅ SQLite Database Ready! (data/bot.db)")

init_db()


bot_settings = {
    "admins": [OWNER_ID],
    "panels": [], 
    "fw_groups": [],

    "otp_link": "https://t.me/your_otp_group",
    "fw_channel_link": "",
    "withdraw_on": True,
    "auto_withdraw": False,
    "min_withdraw": 30.0,
    "otp_reward": 0.1,
    "refer_reward": 0.2,
    "ref_commission": 0.0,   # per-OTP commission paid to inviter (internal base unit, shown as BDT), admin-set
    "service_otp_prices": {},
    "cooldown": 10,
    "num_req": 3,
    "num_share": 1, 
    "support_link": "https://t.me/your_support",
    "w_methods": [],
    "w_group": "", 
    
    "fj_on": False,
    "fj_channels": [],
    "refer_on": True,
    "numbers_broadcast_on": True,
    "voltx_keys": [],
    "voltx_services": {},
    "voltx_search_countries": [],
    "stex_keys": [],
    "stex_services": {},
    "stex_search_countries": [],
    "locked_countries": {},
    "maintenance_mode": False,
    "num_expiry": 0,
    "old_num_window": 0,
    "leaderboard_on": True,
    "currency": "BDT",
    "currency_rates": {"BDT": 110},
    "premium_flags": {
        "93": {"char": "🇦🇫", "iso": "AF", "name": "Afghanistan", "id": "5291937511591925566"},
        "62": {"char": "🇮🇩", "iso": "ID", "name": "Indonesia", "id": "5224405893960969756"},
        "211": {"char": "🇸🇸", "iso": "SS", "name": "South Sudan"},
        "35818": {"char": "🇦🇽", "iso": "AX", "name": "Aland Islands", "id": "5294077418917616055"},
        "355": {"char": "🇦🇱", "iso": "AL", "name": "Albania", "id": "5294202819077756005"},
        "213": {"char": "🇩🇿", "iso": "DZ", "name": "Algeria", "id": "5294048127240655242"},
        "1684": {"char": "🇦🇸", "iso": "AS", "name": "American Samoa", "id": "5291994273879709721"},
        "376": {"char": "🇦🇩", "iso": "AD", "name": "Andorra", "id": "5294215205763434181"},
        "244": {"char": "🇦🇴", "iso": "AO", "name": "Angola", "id": "5294516785482062829"},
        "1264": {"char": "🇦🇮", "iso": "AI", "name": "Anguilla", "id": "5292186323342350940"},
        "1268": {"char": "🇦🇬", "iso": "AG", "name": "Antigua & Barbuda", "id": "5294005972136647964"},
        "54": {"char": "🇦🇷", "iso": "AR", "name": "Argentina", "id": "5292208210495689627"},
        "374": {"char": "🇦🇲", "iso": "AM", "name": "Armenia", "id": "5291978717508164018"},
        "297": {"char": "🇦🇼", "iso": "AW", "name": "Aruba", "id": "5294007002928798927"},
        "61": {"char": "🇦🇺", "iso": "AU", "name": "Australia", "id": "5294444247779399477"},
        "43": {"char": "🇦🇹", "iso": "AT", "name": "Austria", "id": "5291975174160145850"},
        "994": {"char": "🇦🇿", "iso": "AZ", "name": "Azerbaijan", "id": "5294323533428579078"},
        "1242": {"char": "🇧🇸", "iso": "BS", "name": "Bahamas", "id": "5294031587321600012"},
        "973": {"char": "🇧🇭", "iso": "BH", "name": "Bahrain", "id": "5294108398516720753"},
        "880": {"char": "🇧🇩", "iso": "BD", "name": "Bangladesh", "id": "5291824687096027834"},
        "1246": {"char": "🇧🇧", "iso": "BB", "name": "Barbados", "id": "5294526187165471742"},
        "375": {"char": "🇧🇾", "iso": "BY", "name": "Belarus", "id": "5294134426018536120"},
        "32": {"char": "🇧🇪", "iso": "BE", "name": "Belgium", "id": "5291774466043435275"},
        "501": {"char": "🇧🇿", "iso": "BZ", "name": "Belize", "id": "5294171848068584842"},
        "229": {"char": "🇧🇯", "iso": "BJ", "name": "Benin", "id": "5293984969746566866"},
        "975": {"char": "🇧🇹", "iso": "BT", "name": "Bhutan", "id": "5294121983498277263"},
        "591": {"char": "🇧🇴", "iso": "BO", "name": "Bolivia", "id": "5294201479047957700"},
        "267": {"char": "🇧🇼", "iso": "BW", "name": "Botswana", "id": "5294026179957772585"},
        "55": {"char": "🇧🇷", "iso": "BR", "name": "Brazil", "id": "5291892229751723900"},
        "673": {"char": "🇧🇳", "iso": "BN", "name": "Brunei", "id": "5292098293692650297"},
        "359": {"char": "🇧🇬", "iso": "BG", "name": "Bulgaria", "id": "5294308947719640437"},
        "226": {"char": "🇧🇫", "iso": "BF", "name": "Burkina Faso", "id": "5294153164960848949"},
        "257": {"char": "🇧🇮", "iso": "BI", "name": "Burundi", "id": "5294051631933967760"},
        "855": {"char": "🇰🇭", "iso": "KH", "name": "Cambodia", "id": "5294225191562400452"},
        "237": {"char": "🇨🇲", "iso": "CM", "name": "Cameroon", "id": "5291997306126626950"},
        "238": {"char": "🇨🇻", "iso": "CV", "name": "Cape Verde", "id": "5292203503211535593"},
        "236": {"char": "🇨🇫", "iso": "CF", "name": "Central African Republic", "id": "5294210571493724819"},
        "235": {"char": "🇹🇩", "iso": "TD", "name": "Chad", "id": "5291780728105753403"},
        "56": {"char": "🇨🇱", "iso": "CL", "name": "Chile", "id": "5294231037012888049"},
        "86": {"char": "🇨🇳", "iso": "CN", "name": "China", "id": "5294068833277990704"},
        "57": {"char": "🇨🇴", "iso": "CO", "name": "Colombia", "id": "5294010206974397371"},
        "269": {"char": "🇰🇲", "iso": "KM", "name": "Comoros", "id": "5294351381996521508"},
        "242": {"char": "🇨🇬", "iso": "CG", "name": "Congo", "id": "5294035229453865597"},
        "682": {"char": "🇨🇰", "iso": "CK", "name": "Cook Islands", "id": "5292098684534675100"},
        "506": {"char": "🇨🇷", "iso": "CR", "name": "Costa Rica", "id": "5292063805105263554"},
        "225": {"char": "🇨🇮", "iso": "CI", "name": "Cote d Ivoire", "id": "5293991322003200135"},
        "385": {"char": "🇭🇷", "iso": "HR", "name": "Croatia", "id": "5291999676948569127"},
        "53": {"char": "🇨🇺", "iso": "CU", "name": "Cuba", "id": "5291963947115631526"},
        "357": {"char": "🇨🇾", "iso": "CY", "name": "Cyprus", "id": "5294062721539526918"},
        "420": {"char": "🇨🇿", "iso": "CZ", "name": "Czech Republic", "id": "5294242852467923382"},
        "45": {"char": "🇩🇰", "iso": "DK", "name": "Denmark", "id": "5294531860817268837"},
        "253": {"char": "🇩🇯", "iso": "DJ", "name": "Djibouti", "id": "5294127214768468283"},
        "1767": {"char": "🇩🇲", "iso": "DM", "name": "Dominica", "id": "5294485513825178032"},
        "1809": {"char": "🇩🇴", "iso": "DO", "name": "Dominican Republic", "id": "5294522197140857947"},
        "593": {"char": "🇪🇨", "iso": "EC", "name": "Ecuador", "id": "5292083733753517221"},
        "20": {"char": "🇪🇬", "iso": "EG", "name": "Egypt", "id": "5293992082212409502"},
        "503": {"char": "🇸🇻", "iso": "SV", "name": "El Salvador", "id": "5294337307388695687"},
        "240": {"char": "🇬🇶", "iso": "GQ", "name": "Equatorial Guinea", "id": "5292170045416297012"},
        "291": {"char": "🇪🇷", "iso": "ER", "name": "Eritrea", "id": "5291922054004625949"},
        "372": {"char": "🇪🇪", "iso": "EE", "name": "Estonia", "id": "5291951143818123103"},
        "268": {"char": "🇸🇿", "iso": "SZ", "name": "Eswatini", "id": "5294312482477724867"},
        "251": {"char": "🇪🇹", "iso": "ET", "name": "Ethiopia", "id": "5292245976143124155"},
        "388": {"char": "🇪🇺", "iso": "EU", "name": "European Union", "id": "5291992809295861098"},
        "358": {"char": "🇫🇮", "iso": "FI", "name": "Finland", "id": "5294049961191690629"},
        "33": {"char": "🇫🇷", "iso": "FR", "name": "France", "id": "5291817660529533837"},
        "241": {"char": "🇬🇦", "iso": "GA", "name": "Gabon", "id": "5294321325815389139"},
        "220": {"char": "🇬🇲", "iso": "GM", "name": "Gambia", "id": "5294399820637688352"},
        "995": {"char": "🇬🇪", "iso": "GE", "name": "Georgia", "id": "5294349389131697267"},
        "49": {"char": "🇩🇪", "iso": "DE", "name": "Germany", "id": "5292013274815028523"},
        "233": {"char": "🇬🇭", "iso": "GH", "name": "Ghana", "id": "5294347396266873249"},
        "350": {"char": "🇬🇮", "iso": "GI", "name": "Gibraltar", "id": "5292055799286224027"},
        "30": {"char": "🇬🇷", "iso": "GR", "name": "Greece", "id": "5291948395039054764"},
        "299": {"char": "🇬🇱", "iso": "GL", "name": "Greenland", "id": "5292014752283774878"},
        "502": {"char": "🇬🇹", "iso": "GT", "name": "Guatemala", "id": "5294336633078831209"},
        "224": {"char": "🇬🇳", "iso": "GN", "name": "Guinea", "id": "5291892096607739008"},
        "245": {"char": "🇬🇼", "iso": "GW", "name": "Guinea-Bissau", "id": "5294409819321550432"},
        "592": {"char": "🇬🇾", "iso": "GY", "name": "Guyana", "id": "5292062692708736193"},
        "509": {"char": "🇭🇹", "iso": "HT", "name": "Haiti", "id": "5292045130587462814"},
        "504": {"char": "🇭🇳", "iso": "HN", "name": "Honduras", "id": "5291901034434682297"},
        "852": {"char": "🇭🇰", "iso": "HK", "name": "Hong Kong", "id": "5292166459118606932"},
        "36": {"char": "🇭🇺", "iso": "HU", "name": "Hungary", "id": "5294229581018975260"},
        "354": {"char": "🇮🇸", "iso": "IS", "name": "Iceland", "id": "5294354358408859664"},
        "91": {"char": "🇮🇳", "iso": "IN", "name": "India", "id": "5291933173674957761"},
        "98": {"char": "🇮🇷", "iso": "IR", "name": "Iran", "id": "5294220170745630736"},
        "964": {"char": "🇮🇶", "iso": "IQ", "name": "Iraq", "id": "5294325010897327367"},
        "353": {"char": "🇮🇪", "iso": "IE", "name": "Ireland", "id": "5294471971793293647"},
        "972": {"char": "🇮🇱", "iso": "IL", "name": "Israel", "id": "5294069056616289553"},
        "39": {"char": "🇮🇹", "iso": "IT", "name": "Italy", "id": "5291826830284709120"},
        "1876": {"char": "🇯🇲", "iso": "JM", "name": "Jamaica", "id": "5294505107465982830"},
        "81": {"char": "🇯🇵", "iso": "JP", "name": "Japan", "id": "5291799063321139445"},
        "962": {"char": "🇯🇴", "iso": "JO", "name": "Jordan", "id": "5291988613112814801"},
        "254": {"char": "🇰🇪", "iso": "KE", "name": "Kenya", "id": "5292111852904416801"},
        "686": {"char": "🇰🇮", "iso": "KI", "name": "Kiribati", "id": "5294538934628405146"},
        "965": {"char": "🇰🇼", "iso": "KW", "name": "Kuwait", "id": "5292066437920218075"},
        "996": {"char": "🇰🇬", "iso": "KG", "name": "Kyrgyzstan", "id": "5292091954320922577"},
        "856": {"char": "🇱🇦", "iso": "LA", "name": "Laos", "id": "5291981530711746037"},
        "371": {"char": "🇱🇻", "iso": "LV", "name": "Latvia", "id": "5292236016113966127"},
        "961": {"char": "🇱🇧", "iso": "LB", "name": "Lebanon", "id": "5294193108156699621"},
        "266": {"char": "🇱🇸", "iso": "LS", "name": "Lesotho", "id": "5292040693886247604"},
        "231": {"char": "🇱🇷", "iso": "LR", "name": "Liberia", "id": "5291793810576137439"},
        "218": {"char": "🇱🇾", "iso": "LY", "name": "Libya", "id": "5291858711826946840"},
        "423": {"char": "🇱🇮", "iso": "LI", "name": "Liechtenstein", "id": "5292048742654957785"},
        "370": {"char": "🇱🇹", "iso": "LT", "name": "Lithuania", "id": "5294343084119708700"},
        "352": {"char": "🇱🇺", "iso": "LU", "name": "Luxembourg", "id": "5294423709245787718"},
        "389": {"char": "🇲🇰", "iso": "MK", "name": "Macedonia", "id": "5294023611567332075"},
        "261": {"char": "🇲🇬", "iso": "MG", "name": "Madagascar", "id": "5291991568050312348"},
        "265": {"char": "🇲🇼", "iso": "MW", "name": "Malawi", "id": "5294241881805312589"},
        "60": {"char": "🇲🇾", "iso": "MY", "name": "Malaysia", "id": "5291858351049696702"},
        "960": {"char": "🇲🇻", "iso": "MV", "name": "Maldives", "id": "5292004203844097218"},
        "223": {"char": "🇲🇱", "iso": "ML", "name": "Mali", "id": "5292086972158858331"},
        "356": {"char": "🇲🇹", "iso": "MT", "name": "Malta", "id": "5294532213004588353"},
        "692": {"char": "🇲🇭", "iso": "MH", "name": "Marshall Islands", "id": "5294180730060954484"},
        "222": {"char": "🇲🇷", "iso": "MR", "name": "Mauritania", "id": "5294429743674840973"},
        "230": {"char": "🇲🇺", "iso": "MU", "name": "Mauritius", "id": "5294127824653797277"},
        "52": {"char": "🇲🇽", "iso": "MX", "name": "Mexico", "id": "5294535073452809778"},
        "691": {"char": "🇫🇲", "iso": "FM", "name": "Micronesia", "id": "5291838156113470124"},
        "373": {"char": "🇲🇩", "iso": "MD", "name": "Moldova", "id": "5294158486425325375"},
        "377": {"char": "🇲🇨", "iso": "MC", "name": "Monaco", "id": "5294378161117614233"},
        "976": {"char": "🇲🇳", "iso": "MN", "name": "Mongolia", "id": "5294316532631883496"},
        "212": {"char": "🇲🇦", "iso": "MA", "name": "Morocco", "id": "5292108962391414885"},
        "258": {"char": "🇲🇿", "iso": "MZ", "name": "Mozambique", "id": "5294086708931874940"},
        "95": {"char": "🇲🇲", "iso": "MM", "name": "Myanmar", "id": "5294254478944393569"},
        "264": {"char": "🇳🇦", "iso": "NA", "name": "Namibia", "id": "5292021761670404922"},
        "674": {"char": "🇳🇷", "iso": "NR", "name": "Nauru", "id": "5294463274484521342"},
        "977": {"char": "🇳🇵", "iso": "NP", "name": "Nepal", "id": "5294458756178924088"},
        "31": {"char": "🇳🇱", "iso": "NL", "name": "Netherlands", "id": "5291917797692042265"},
        "64": {"char": "🇳🇿", "iso": "NZ", "name": "New Zealand", "id": "5294189019347833274"},
        "505": {"char": "🇳🇮", "iso": "NI", "name": "Nicaragua", "id": "5294240825243358100"},
        "227": {"char": "🇳🇪", "iso": "NE", "name": "Niger", "id": "5291809418487290691"},
        "234": {"char": "🇳🇬", "iso": "NG", "name": "Nigeria", "id": "5294456308047563965"},
        "683": {"char": "🇳🇺", "iso": "NU", "name": "Niue", "id": "5294471336138134209"},
        "850": {"char": "🇰🇵", "iso": "KP", "name": "North Korea", "id": "5294193812531333564"},
        "47": {"char": "🇳🇴", "iso": "NO", "name": "Norway", "id": "5291761718580502030"},
        "968": {"char": "🇴🇲", "iso": "OM", "name": "Oman", "id": "5291813666209946812"},
        "92": {"char": "🇵🇰", "iso": "PK", "name": "Pakistan", "id": "5291825606219029010"},
        "970": {"char": "🇵🇸", "iso": "PS", "name": "Palestine", "id": "5294289826525238172"},
        "507": {"char": "🇵🇦", "iso": "PA", "name": "Panama", "id": "5291959935616178405"},
        "675": {"char": "🇵🇬", "iso": "PG", "name": "Papua New Guinea", "id": "5291917995260533077"},
        "595": {"char": "🇵🇾", "iso": "PY", "name": "Paraguay", "id": "5294525611639852679"},
        "51": {"char": "🇵🇪", "iso": "PE", "name": "Peru", "id": "5292099427564018941"},
        "63": {"char": "🇵🇭", "iso": "PH", "name": "Philippines", "id": "5291798075478661634"},
        "48": {"char": "🇵🇱", "iso": "PL", "name": "Poland", "id": "5292190970496963836"},
        "351": {"char": "🇵🇹", "iso": "PT", "name": "Portugal", "id": "5294436555492973610"},
        "1787": {"char": "🇵🇷", "iso": "PR", "name": "Puerto Rico", "id": "5292121516580820347"},
        "974": {"char": "🇶🇦", "iso": "QA", "name": "Qatar", "id": "5292166360334357676"},
        "40": {"char": "🇷🇴", "iso": "RO", "name": "Romania", "id": "5294107724206856227"},
        "7": {"char": "🇷🇺", "iso": "RU", "name": "Russia", "id": "5294335323113807278"},
        "250": {"char": "🇷🇼", "iso": "RW", "name": "Rwanda", "id": "5294191265615729158"},
        "378": {"char": "🇸🇲", "iso": "SM", "name": "San Marino", "id": "5292147350809106831"},
        "239": {"char": "🇸🇹", "iso": "ST", "name": "Sao Tome & Principe", "id": "5292183188016222701"},
        "966": {"char": "🇸🇦", "iso": "SA", "name": "Saudi Arabia", "id": "5294163983983463099"},
        "221": {"char": "🇸🇳", "iso": "SN", "name": "Senegal", "id": "5292087023698466689"},
        "381": {"char": "🇷🇸", "iso": "RS", "name": "Serbia", "id": "5294458584380230360"},
        "248": {"char": "🇸🇨", "iso": "SC", "name": "Seychelles", "id": "5291891186074672309"},
        "232": {"char": "🇸🇱", "iso": "SL", "name": "Sierra Leone", "id": "5294494314213167952"},
        "65": {"char": "🇸🇬", "iso": "SG", "name": "Singapore", "id": "5294451304410663668"},
        "421": {"char": "🇸🇰", "iso": "SK", "name": "Slovakia", "id": "5294538440707166931"},
        "386": {"char": "🇸🇮", "iso": "SI", "name": "Slovenia", "id": "5294279359689938006"},
        "677": {"char": "🇸🇧", "iso": "SB", "name": "Solomon Islands", "id": "5294283890880433237"},
        "252": {"char": "🇸🇴", "iso": "SO", "name": "Somalia", "id": "5294058817414255960"},
        "27": {"char": "🇿🇦", "iso": "ZA", "name": "South Africa", "id": "5294325281480266304"},
        "82": {"char": "🇰🇷", "iso": "KR", "name": "South Korea", "id": "5294408281723262763"},
        "34": {"char": "🇪🇸", "iso": "ES", "name": "Spain", "id": "5294513087515216901"},
        "94": {"char": "🇱🇰", "iso": "LK", "name": "Sri Lanka", "id": "5292102670264328257"},
        "249": {"char": "🇸🇩", "iso": "SD", "name": "Sudan", "id": "5294177148058228060"},
        "597": {"char": "🇸🇷", "iso": "SR", "name": "Suriname", "id": "5294396668131692138"},
        "46": {"char": "🇸🇪", "iso": "SE", "name": "Sweden", "id": "5291737091238026321"},
        "41": {"char": "🇨🇭", "iso": "CH", "name": "Switzerland", "id": "5291791748991835084"},
        "963": {"char": "🇸🇾", "iso": "SY", "name": "Syria", "id": "5294013428199869487"},
        "886": {"char": "🇹🇼", "iso": "TW", "name": "Taiwan", "id": "5294095745543069603"},
        "992": {"char": "🇹🇯", "iso": "TJ", "name": "Tajikistan", "id": "5294120269806328883"},
        "255": {"char": "🇹🇿", "iso": "TZ", "name": "Tanzania", "id": "5292146096678658977"},
        "66": {"char": "🇹🇭", "iso": "TH", "name": "Thailand", "id": "5293994384314882755"},
        "228": {"char": "🇹🇬", "iso": "TG", "name": "Togo", "id": "5294097669688415562"},
        "676": {"char": "🇹🇴", "iso": "TO", "name": "Tonga", "id": "5294283689016973348"},
        "1868": {"char": "🇹🇹", "iso": "TT", "name": "Trinidad & Tobago", "id": "5294362935458548705"},
        "216": {"char": "🇹🇳", "iso": "TN", "name": "Tunisia", "id": "5294484680601521871"},
        "90": {"char": "🇹🇷", "iso": "TR", "name": "Turkey", "id": "5293993400767367408"},
        "993": {"char": "🇹🇲", "iso": "TM", "name": "Turkmenistan", "id": "5294098958178603764"},
        "1649": {"char": "🇹🇨", "iso": "TC", "name": "Turks & Caicos", "id": "5294320866253884749"},
        "971": {"char": "🇦🇪", "iso": "AE", "name": "UAE", "id": "5294314831824835370"},
        "256": {"char": "🇺🇬", "iso": "UG", "name": "Uganda", "id": "5294192317882716626"},
        "380": {"char": "🇺🇦", "iso": "UA", "name": "Ukraine", "id": "5294263837678131580"},
        "44": {"char": "🇬🇧", "iso": "GB", "name": "United Kingdom", "id": "5293993521026453119"},
        "1": {"char": "🇺🇸", "iso": "US", "name": "United States", "id": "5294244076533600593"},
        "598": {"char": "🇺🇾", "iso": "UY", "name": "Uruguay", "id": "5291928449210932974"},
        "1340": {"char": "🇻🇮", "iso": "VI", "name": "US Virgin Islands", "id": "5294228039125718124"},
        "998": {"char": "🇺🇿", "iso": "UZ", "name": "Uzbekistan", "id": "5294217645304864345"},
        "678": {"char": "🇻🇺", "iso": "VU", "name": "Vanuatu", "id": "5294448585696368047"},
        "58": {"char": "🇻🇪", "iso": "VE", "name": "Venezuela", "id": "5294476442854247878"},
        "84": {"char": "🇻🇳", "iso": "VN", "name": "Vietnam", "id": "5294235963340379688"},
        "967": {"char": "🇾🇪", "iso": "YE", "name": "Yemen", "id": "5294058972033076492"},
        "260": {"char": "🇿🇲", "iso": "ZM", "name": "Zambia", "id": "5294100109229838880"},
        "263": {"char": "🇿🇼", "iso": "ZW", "name": "Zimbabwe", "id": "5294422158762592930"},
    },
    "premium_apps": {
        "FACEBOOK": {"char": "📘", "id": "5323261730283863478", "name": "Facebook"},
        "INSTAGRAM": {"char": "📸", "id": "5319160079465857105", "name": "Instagram"},
        "MESSENGER": {"char": "💬", "id": "5323687726615119535", "name": "Messenger"},
        "META": {"char": "🌐", "id": "5321447183910716259", "name": "Meta"},
        "DISCORD": {"char": "🎮", "id": "5325612636467903082", "name": "Discord"},
        "SIGNAL": {"char": "🔒", "id": "5328050550099427291", "name": "Signal"},
        "TELEGRAM": {"char": "✈️", "id": "5330237710655306682", "name": "Telegram"},
        "THREADS": {"char": "🧵", "id": "5334592721594105691", "name": "Threads"},
        "REDNOTE": {"char": "📝", "id": "5334707727933390944", "name": "Rednote"},
        "VK": {"char": "🔵", "id": "5334853932915114338", "name": "VK"},
        "WECHAT": {"char": "💬", "id": "5332524123610430820", "name": "WeChat"},
        "TIKTOK": {"char": "🎵", "id": "5280662183057825163", "name": "TikTok"},
        "SNAPCHAT": {"char": "👻", "id": "5330248916224983855", "name": "Snapchat"},
        "REDDIT": {"char": "🤖", "id": "5330321861949539755", "name": "Reddit"},
        "APPLE": {"char": "🍎", "id": "5307884768111631358", "name": "Apple"},
        "TWITTER": {"char": "🐦", "id": "5330337435500951363", "name": "X/Twitter"},
        "X": {"char": "✖️", "id": "5330337435500951363", "name": "X/Twitter"},
        "NETFLIX": {"char": "🎬", "id": "5296258364655805333", "name": "Netflix"},
        "WHATSAPP": {"char": "📞", "id": "5334998226636390258", "name": "WhatsApp"},
        "BOLT": {"char": "🚗", "id": "5346188613602263703", "name": "Bolt"},
        "SPOTIFY": {"char": "🎶", "id": "5346074681004801565", "name": "Spotify"},
        "PAYPAL": {"char": "💰", "id": "5364111181415996352", "name": "PayPal"},
        "MASTERCARD": {"char": "💳", "id": "5364036341610858181", "name": "Mastercard"},
        "TETHER": {"char": "💵", "id": "5359437015752401733", "name": "Tether"},
        "CHATGPT": {"char": "🤖", "id": "5359726582447487916", "name": "ChatGPT"},
        "MICROSOFT": {"char": "🪟", "id": "5370857634440170316", "name": "Microsoft"},
        "STEAM": {"char": "🎮", "id": "5298975451161565553", "name": "Steam"},
        "BINANCE": {"char": "💹", "id": "5888561507557447441", "name": "Binance"},
        "TEAMS": {"char": "💼", "id": "5453866707888152017", "name": "Teams"},
        "GMAIL": {"char": "📧", "id": "5303416490295304868", "name": "Gmail"},
        "GOOGLEDRIVE": {"char": "📁", "id": "5303051181851943323", "name": "Google Drive"},
        "UBER": {"char": "🚖", "id": "5298715455316303708", "name": "Uber"},
        "GROKAI": {"char": "🤖", "id": "5454065032298009119", "name": "Grok AI"},
        "GITHUB": {"char": "💻", "id": "5303382121967001310", "name": "GitHub"},
        "CANVA": {"char": "🎨", "id": "5429229538527690282", "name": "Canva"},
    },
    "custom_messages": DEFAULT_CUSTOM_MESSAGES.copy()
}

CURRENCY_SYMBOLS = {"BDT": "BDT"}

CURRENCY_EMOJI_IDS = {
    "BDT": "5291824687096027834",
}

def _bdt_rate():
    """Internal balance unit -> BDT multiplier. The bot now shows BDT only."""
    try:
        return float(bot_settings.get("currency_rates", {}).get("BDT", 110)) or 110.0
    except (TypeError, ValueError):
        return 110.0
SETTINGS_EMOJI_ID = "5226961519761199044"
OTP_EMOJI_ID = "6068830682359010545"

def format_currency(amount):
    """Format a balance/price (always stored internally in USDT) into the
    admin-selected display currency using bot_settings['currency_rates'].
    Always displays in BDT (Bangladeshi Taka).

    Uses a *dynamic* number of decimal places instead of a hard-coded
    ``.2f`` — tiny OTP prices like 0.0001 used to round straight down to
    0.00 and look like a free/zero reward. Amounts of 1 or more still show
    the usual 2 decimals; smaller amounts show as many decimals as needed
    (up to 8) to keep the value visibly non-zero, with trailing zeros
    trimmed."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    # BDT only: ignore any old saved currency (USDT/PKR/INR) from the database.
    rate = _bdt_rate()
    symbol = "BDT"
    converted = amount * rate

    if converted == 0:
        return f"0.00 {symbol}"

    if abs(converted) >= 1:
        formatted = f"{converted:.2f}"
    else:
        # Small value: show enough decimals to keep it non-zero (up to 8),
        # then trim trailing zeros but always keep at least 2 decimals.
        formatted = f"{converted:.8f}".rstrip("0")
        if formatted.endswith("."):
            formatted += "00"
        else:
            dec_len = len(formatted.split(".")[1])
            if dec_len < 2:
                formatted += "0" * (2 - dec_len)

    return f"{formatted} {symbol}"

def parse_currency_input(entered_amount):
    """Convert a price the admin typed in the currently-selected display
    currency back into the internal USDT base unit, so it round-trips
    correctly through format_currency() later (avoids double conversion)."""
    try:
        entered_amount = float(entered_amount)
    except (TypeError, ValueError):
        return 0.0
    return entered_amount / _bdt_rate()

def format_bdt(amount):
    """Always show an internal (USDT-based) amount in BDT (Bangladeshi Taka),
    regardless of the global display-currency setting. Used by User Management."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    rate = bot_settings.get("currency_rates", {}).get("BDT", 110)
    return f"{amount * rate:.2f} BDT"

def bdt_to_internal(entered_bdt):
    """Convert an amount typed in BDT back to the internal USDT base unit."""
    try:
        entered_bdt = float(entered_bdt)
    except (TypeError, ValueError):
        return 0.0
    rate = bot_settings.get("currency_rates", {}).get("BDT", 110) or 1
    return entered_bdt / rate


number_batches = {}
used_numbers_list = []
voltx_assigned_numbers = {}
VOLTX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
stex_assigned_numbers = {}
STEX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tness/@public/api"
total_uploaded_stats = 0
total_assigned_stats = 0
import collections as _collections

# ─── Thread-safe bounded OTP dedup set ───────────────────────────────────────
# Uses deque to evict OLDEST entries instead of clearing everything at once.
# Clearing all at once (the old approach) caused already-seen OTPs to be
# re-forwarded immediately after the clear — the primary source of missed /
# duplicate OTPs.
_otp_dedup_lock = threading.Lock()
_otp_dedup_deque = _collections.deque(maxlen=20000)  # keeps last 20 k unique IDs
_otp_dedup_set   = set()

def _otp_seen(uid: str) -> bool:
    with _otp_dedup_lock:
        return uid in _otp_dedup_set

def _otp_mark(uid: str):
    with _otp_dedup_lock:
        if uid in _otp_dedup_set:
            return False
        if len(_otp_dedup_deque) == _otp_dedup_deque.maxlen:
            oldest = _otp_dedup_deque[0]
            _otp_dedup_set.discard(oldest)
        _otp_dedup_deque.append(uid)
        _otp_dedup_set.add(uid)
        # Push to background writer — NO per-OTP thread spawn
        _dedup_write_queue.append(uid)
        _dedup_write_queue_event.set()
        return True

# ── Background dedup writer (single thread, batched SQLite writes) ────────────
# Previously a new thread was spawned per OTP. Under high volume (thousands of
# OTPs/hour) that created thousands of short-lived threads → OS scheduler
# thrash → gradual speed degradation. One persistent writer thread eliminates
# all that overhead.
_dedup_write_queue       = _collections.deque()   # thread-safe append/popleft
_dedup_write_queue_event = threading.Event()

def _dedup_writer_thread():
    """Drain _dedup_write_queue and batch-insert into SQLite every 2 s."""
    while True:
        _dedup_write_queue_event.wait(timeout=2.0)
        _dedup_write_queue_event.clear()
        batch = []
        while True:
            try:
                batch.append(_dedup_write_queue.popleft())
            except IndexError:
                break
        if not batch:
            continue
        ts = time.time()
        try:
            conn = get_db_conn()
            conn.executemany(
                "INSERT OR IGNORE INTO otp_dedup (uid, ts) VALUES (?,?)",
                [(u, ts) for u in batch]
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

threading.Thread(target=_dedup_writer_thread, daemon=True, name="dedup-writer").start()

def _load_dedup_from_db():
    """On startup: load last 24h of dedup UIDs from SQLite into memory.
    This prevents re-forwarding old OTPs that were already sent before a restart."""
    try:
        cutoff = time.time() - 86400  # keep last 24 hours
        conn = get_db_conn()
        rows = conn.execute(
            "SELECT uid FROM otp_dedup WHERE ts > ?", (cutoff,)
        ).fetchall()
        # Also clean up entries older than 24h to keep table small
        conn.execute("DELETE FROM otp_dedup WHERE ts <= ?", (cutoff,))
        conn.commit()
        conn.close()
        with _otp_dedup_lock:
            for (uid,) in rows:
                if uid not in _otp_dedup_set:
                    if len(_otp_dedup_deque) == _otp_dedup_deque.maxlen:
                        oldest = _otp_dedup_deque[0]
                        _otp_dedup_set.discard(oldest)
                    _otp_dedup_deque.append(uid)
                    _otp_dedup_set.add(uid)
        print(f"✅ Dedup restored: {len(rows)} OTP IDs loaded from DB (no re-forwarding on restart)")
    except Exception as e:
        print(f"[dedup] DB load failed: {e}")

# ── Speed tracker (shared across all panel worker threads) ───────────────────
_speed_tracker = {
    "count":       0,      # total OTPs forwarded since last reset
    "last_otp_ts": 0.0,    # time.time() of last forwarded OTP
}

# ── Timestamp extraction helper ───────────────────────────────────────────────
_DT_PATTERN = re.compile(
    r'\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]\d{1,2}:\d{2}(:\d{2})?'
)

def _parse_row_timestamp(row_val) -> float | None:
    """Extract a Unix timestamp from a panel row (list, dict, or string).
    Returns None if no recognisable datetime is found."""
    from datetime import datetime as _dt
    candidates = []
    if isinstance(row_val, str):
        # scraper2 passes received_ts as a raw datetime string — handle it directly.
        candidates = [row_val]
    elif isinstance(row_val, list):
        candidates = [str(v) for v in row_val]
    elif isinstance(row_val, dict):
        # Check common timestamp key names first
        for k in ["datetime", "date", "time", "created_at", "timestamp",
                   "received_at", "created", "receive_time", "sms_time"]:
            v = row_val.get(k) or row_val.get(k.upper())
            if v:
                candidates = [str(v)]
                break
        if not candidates:
            candidates = [str(v) for v in row_val.values()]
    for s in candidates:
        m = _DT_PATTERN.search(s)
        if m:
            dt_str = m.group(0).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
                        "%Y-%m-%d %H:%M",    "%Y/%m/%d %H:%M",
                        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
                try:
                    return _dt.strptime(dt_str, fmt).timestamp()
                except ValueError:
                    pass
    return None

# ── Message normaliser for dedup keys ────────────────────────────────────────
def _msg_dedup_key(text: str) -> str:
    """Return a normalised, length-capped representation of an SMS message
    suitable for embedding in a dedup UID.

    Why: two different delivery paths for the *same* SMS (e.g. an API panel
    and scraper2) may produce slightly different whitespace or HTML wrapping.
    Stripping HTML and collapsing whitespace makes the key stable across paths
    so cross-source dedup still works.  Capping at 120 chars keeps UIDs short
    while preserving enough signal to distinguish genuinely different messages.
    """
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", str(text))   # strip HTML tags
    t = " ".join(t.split())                  # collapse whitespace
    return t[:120]

# Keep the old name as an alias so existing code that checks `unique_id not in processed_otps`
# still works — we shadow it with the real set but add/remove via the safe helpers above.
processed_otps = _otp_dedup_set

# Bounded deque — auto-evicts oldest entries; never grows unbounded
recent_traffic = _collections.deque(maxlen=1000)

# ─── OTP Forwarding Queue ─────────────────────────────────────────────────────
# All send_message / send_inbox calls are pushed here so monitoring threads
# are NEVER blocked waiting for Telegram.  16 dedicated sender threads drain
# the queue in parallel.
import queue as _otp_q_mod
_otp_forward_queue = _otp_q_mod.Queue(maxsize=0)

def _otp_sender_worker():
    """Drain _otp_forward_queue and execute each forwarding task.
    25 of these threads are started in main() so all OTP sends are
    fully non-blocking to the panel-poller and scraper2 threads."""
    while True:
        try:
            task = _otp_forward_queue.get()
            fn   = task[0]
            args = task[1:]
            fn(*args)
        except Exception as e:
            # Was silently swallowed before — a failure here (e.g. inside
            # _dispatch_otp_to_users) meant an OTP vanished with zero trace.
            # Log it so a real delivery failure is visible instead of hidden.
            print(f"[OTP-SEND] task failed: {e}")
        finally:
            try:
                _otp_forward_queue.task_done()
            except Exception:
                pass

def _enqueue_otp_send(fn, *args):
    """Non-blocking push to OTP forward queue."""
    try:
        _otp_forward_queue.put_nowait((fn, *args))
    except Exception as _eq_err:
        # BUG FIX: was `except: pass` — silent swallow meant OTPs could be
        # permanently lost without any trace. Log so failures are visible.
        print(f"[OTP-QUEUE] ❌ enqueue failed ({fn.__name__ if callable(fn) else fn}): {_eq_err}")

# ─── OTP Persistent Retry Queue ───────────────────────────────────────────────
# When send_otp_message exhausts all 8 normal rapid retries (e.g. during heavy
# panel load causing sustained 429 flood), the OTP is NOT dropped. Instead it
# is written to SQLite and placed in _otp_retry_q. A dedicated retry worker
# thread re-attempts with exponential backoff (30s → 60s → 120s → 300s → 600s).
# On bot restart, all pending rows are loaded back from DB so nothing is lost.
_otp_retry_q = _otp_q_mod.Queue(maxsize=0)

def _push_to_retry_queue(chat_id, text, reply_markup, parse_mode):
    """Save a failed OTP send to the persistent retry queue (SQLite + memory).
    Called only when send_otp_message has exhausted all rapid-retry attempts.

    BUG FIX: previously the in-memory _otp_retry_q.put() ran INSIDE the same
    try block as the SQLite INSERT, AFTER it. Under high load db_lock contention
    can cause the INSERT to fail → the except fires → _otp_retry_q.put() is
    NEVER called → OTP silently dropped forever.

    Fix: enqueue in-memory FIRST (guaranteed, never skipped), then attempt the
    SQLite write as a best-effort persistence step. row_id=None signals the
    retry worker to skip SQLite update/delete for these in-memory-only entries.
    """
    rm_json = json.dumps(reply_markup) if reply_markup else None
    now = time.time()
    next_retry = now + 1   # first retry after 1 second

    # ── Step 1: in-memory enqueue — ALWAYS succeeds (unbounded queue) ─────────
    # row_id=None → _otp_retry_worker skips SQLite update/delete calls.
    _otp_retry_q.put((None, chat_id, text, rm_json, parse_mode, 0, next_retry))
    print(f"[OTP-RETRY] 📥 chat_id={chat_id} queued for retry in 1s")

    # ── Step 2: SQLite persistence — best-effort, for restart recovery only ───
    try:
        with db_lock:
            conn = get_db_conn()
            conn.execute(
                """INSERT INTO otp_retry_queue
                   (chat_id, text, reply_markup, parse_mode, retry_count, created_at, next_retry_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (chat_id, text, rm_json, parse_mode, 0, now, next_retry)
            )
            conn.commit()
            conn.close()
    except Exception as e:
        # OTP is still safe in the in-memory queue above — log only.
        print(f"[OTP-RETRY] ⚠️ SQLite persist skipped (OTP still in memory queue): {e}")

def _retry_queue_update(row_id, retry_count, next_retry_at):
    """Update a retry row with new count and next-attempt timestamp."""
    try:
        with db_lock:
            conn = get_db_conn()
            conn.execute(
                "UPDATE otp_retry_queue SET retry_count=?, next_retry_at=? WHERE id=?",
                (retry_count, next_retry_at, row_id)
            )
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[OTP-RETRY] ❌ update failed: {e}")

def _retry_queue_remove(row_id):
    """Delete a completed/failed row from the persistent retry queue."""
    try:
        with db_lock:
            conn = get_db_conn()
            conn.execute("DELETE FROM otp_retry_queue WHERE id=?", (row_id,))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[OTP-RETRY] ❌ remove failed: {e}")

def _load_retry_queue_from_db():
    """On startup, reload any pending retry rows from SQLite back into memory
    so OTPs that were queued before a bot restart are not permanently lost."""
    try:
        with db_lock:
            conn = get_db_conn()
            rows = conn.execute(
                """SELECT id, chat_id, text, reply_markup, parse_mode,
                          retry_count, next_retry_at
                   FROM otp_retry_queue"""
            ).fetchall()
            conn.close()
        for row in rows:
            _otp_retry_q.put(tuple(row))
        if rows:
            print(f"[OTP-RETRY] 🔄 Restored {len(rows)} pending retry items from DB")
    except Exception as e:
        print(f"[OTP-RETRY] ❌ load from DB failed: {e}")

# Retry interval — every attempt waits exactly 1 second before re-sending
_RETRY_BACKOFF = [1, 1, 1, 1, 1]
_RETRY_MAX_ROUNDS = len(_RETRY_BACKOFF)   # 5 rounds of 1s each → then discard

def _otp_retry_worker():
    """Single dedicated thread that drains _otp_retry_q with exponential
    backoff. Keeps its own rate-limiting via _otp_wait_global_slot so it
    plays nicely with the 25 normal sender threads and does not hammer
    Telegram when it is already flood-controlling."""
    while True:
        try:
            item = _otp_retry_q.get(timeout=5)
        except _otp_q_mod.Empty:
            continue
        try:
            row_id, chat_id, text, rm_json, parse_mode, retry_count, next_retry_at = item

            # Honour the scheduled delay — sleep only the remaining gap
            gap = next_retry_at - time.time()
            if gap > 0:
                time.sleep(gap)

            reply_markup = json.loads(rm_json) if rm_json else None

            # Call send_message directly (not send_otp_message) to avoid
            # re-entering the retry queue recursively on a second failure.
            _otp_wait_global_slot()
            result = send_message(chat_id, text, reply_markup, parse_mode) or {}

            if result.get("ok"):
                # row_id=None → in-memory-only entry (no SQLite row to delete)
                if row_id is not None:
                    _retry_queue_remove(row_id)
                print(f"[OTP-RETRY] ✅ Delivered to chat_id={chat_id} (round {retry_count + 1})")
            else:
                err_code = result.get("error_code")
                if err_code in (400, 403):
                    # Permanent failure — bot blocked or chat gone; no point retrying
                    if row_id is not None:
                        _retry_queue_remove(row_id)
                    print(f"[OTP-RETRY] ❌ Permanent {err_code} for chat_id={chat_id}, discarded")
                elif retry_count + 1 >= _RETRY_MAX_ROUNDS:
                    # Exhausted all backoff rounds
                    if row_id is not None:
                        _retry_queue_remove(row_id)
                    print(f"[OTP-RETRY] ❌ Max rounds reached for chat_id={chat_id}, discarded")
                else:
                    # Schedule next backoff round
                    new_count = retry_count + 1
                    backoff   = _RETRY_BACKOFF[new_count]
                    new_next  = time.time() + backoff
                    # row_id=None → in-memory-only entry, skip SQLite update
                    if row_id is not None:
                        _retry_queue_update(row_id, new_count, new_next)
                    _otp_retry_q.put((row_id, chat_id, text, rm_json, parse_mode, new_count, new_next))
                    print(f"[OTP-RETRY] ⏳ chat_id={chat_id} re-queued, next in {backoff}s (round {new_count + 1})")
        except Exception as e:
            print(f"[OTP-RETRY] ❌ worker error: {e}")
        finally:
            try:
                _otp_retry_q.task_done()
            except Exception:
                pass
user_banned_cache = {}

# Active HTTP sessions for Auto Captcha Panels
panel_sessions = {}


def _is_session_expired(html_text: str) -> bool:
    """
    Return True ONLY when the server has redirected us to the login page.
    Uses multiple signals to avoid false positives (e.g. a page that contains
    the word 'login' in a nav link or footer while the user IS logged in).
    """
    lower = html_text.lower()

    # Strong signals — a login <form> is present on the page
    has_login_form = bool(re.search(
        r'<form[^>]*(?:action|id|class)[^>]*login',
        html_text, re.I
    ))
    has_password_field = bool(re.search(
        r'<input[^>]*type=["\']password["\']',
        html_text, re.I
    ))

    # Definitive "you are not logged in" phrases
    hard_phrases = [
        "sign in to your account", "please sign in",
        "invalid username", "invalid password",
        "authentication required", "you must log in",
        "please login to continue", "session expired",
        "your session has expired"
    ]
    has_hard_phrase = any(ph in lower for ph in hard_phrases)

    # A login form WITH a password field = definitely logged out
    if has_login_form and has_password_field:
        return True

    # Hard phrase alone (without a form) is also conclusive
    if has_hard_phrase:
        return True

    return False


# Zero-payout rows: unique_id -> time first seen with payout 0.
# A row that stays at 0 longer than the grace period is marked "seen" for good,
# so a payout the panel fills in much later can never forward an OLD OTP.
_cpt_zero_first_seen = {}
_CPT_ZERO_GRACE_SECS = 90

def _cpt_note_zero_row(uid):
    now = time.time()
    first = _cpt_zero_first_seen.get(uid)
    if first is None:
        if len(_cpt_zero_first_seen) > 20000:
            for k in sorted(_cpt_zero_first_seen, key=_cpt_zero_first_seen.get)[:5000]:
                _cpt_zero_first_seen.pop(k, None)
        _cpt_zero_first_seen[uid] = now
    elif now - first > _CPT_ZERO_GRACE_SECS:
        _otp_mark(uid)               # never forward this row, even if payout appears later
        _cpt_zero_first_seen.pop(uid, None)

def fetch_cpt_panel_cdrs(p, session, check_url):
    res = session.get(check_url, timeout=15)
    html_text = res.text

    if _is_session_expired(html_text):
        raise Exception("Session expired")

    soup = BeautifulSoup(html_text, 'html.parser')
    s_ajax_source = ""
    for script in soup.find_all("script"):
        script_text = script.string or ""
        match = re.search(r'sAjaxSource":\s*"([^"]+)"', script_text)
        if match:
            s_ajax_source = match.group(1)
            break
    # Header titles of the page's CDR table — used to find the "My Payout" column.
    _page_headers = []
    for _th in soup.find_all("th"):
        _page_headers.append(_th.get_text(strip=True).lower())
    soup.decompose()  # BUG FIX: free parsed HTML tree — large panels held MBs in memory per poll

    results = []

    def _find_payout_idx(col_names):
        """Index of the "My Payout" column (revenue paid for the OTP), or -1.
        Prefers 'my payout'; falls back to any 'payout' column that isn't the client's."""
        names = [str(n).lower().strip() for n in col_names]
        for i, nm in enumerate(names):
            if "my payout" in nm:
                return i
        for i, nm in enumerate(names):
            if "payout" in nm and "client" not in nm:
                return i
        return -1

    def _zero_payout(cell):
        """True only when the payout cell is a number that is 0 (or blank 0-like)."""
        txt = re.sub(r"<[^>]*>", "", str(cell)).strip()
        txt = re.sub(r"[^0-9.\-]", "", txt)
        if not txt or txt in (".", "-"):
            return False
        try:
            return float(txt) <= 0
        except ValueError:
            return False

    n_col_name = p.get("num_col_name", "number").lower()
    m_col_name = p.get("msg_col_name", "message").lower()
    # Convert 1-based user config to 0-based; None/0 means "auto-detect"
    _nu = p.get("num_col_idx")
    _mu = p.get("msg_col_idx")
    n_idx_cfg = int(_nu) - 1 if _nu and str(_nu).isdigit() and int(_nu) > 0 else None
    m_idx_cfg = int(_mu) - 1 if _mu and str(_mu).isdigit() and int(_mu) > 0 else None

    _N_WORDS = ["number", "num", "phone", "msisdn", "mobile", "destination", "dest", "caller"]
    _M_WORDS = ["message", "msg", "sms", "text", "content", "body"]
    _C_WORDS = ["cli", "client", "service", "app", "provider", "application", "sender", "source"]

    def _auto_detect_cols(col_names):
        """Given a list of column name strings, return (n_idx, m_idx, c_idx)."""
        n_i = m_i = c_i = -1
        for i, name in enumerate(col_names):
            nl = str(name).lower().strip()
            if n_i == -1 and any(w in nl for w in _N_WORDS):
                n_i = i
            if m_i == -1 and any(w in nl for w in _M_WORDS):
                m_i = i
            if c_i == -1 and any(w in nl for w in _C_WORDS):
                c_i = i
        return n_i, m_i, c_i

    def _smart_detect_from_data(rows_sample):
        """Scan first few data rows to guess number and message column indices."""
        if not rows_sample:
            return -1, -1, -1
        n_i = m_i = c_i = -1
        num_counts = {}
        msg_len = {}
        for row_val in rows_sample[:10]:
            if not isinstance(row_val, list):
                continue
            for ci, cell in enumerate(row_val):
                s = str(cell).strip()
                digits = re.sub(r'\D', '', s)
                if 7 <= len(digits) <= 15 and len(digits) == len(s.replace('+', '').replace(' ', '')):
                    num_counts[ci] = num_counts.get(ci, 0) + 1
                if len(s) > 15:
                    msg_len[ci] = msg_len.get(ci, 0) + len(s)
        if num_counts:
            n_i = max(num_counts, key=num_counts.get)
        if msg_len:
            m_i = max(msg_len, key=msg_len.get)
        return n_i, m_i, c_i

    if s_ajax_source:
        baseUrl = p.get("login_url", "").split("/client")[0].split("/login")[0].strip()
        if not baseUrl.startswith("http"):
            baseUrl = "http://" + baseUrl

        full_ajax_url = ""
        if s_ajax_source.startswith("http"):
            full_ajax_url = s_ajax_source
        elif s_ajax_source.startswith("/"):
            full_ajax_url = f"{baseUrl}{s_ajax_source}"
        else:
            last_slash_idx = check_url.rfind("/")
            current_dir = check_url[:last_slash_idx]
            full_ajax_url = f"{current_dir}/{s_ajax_source}"

        if "iDisplayLength" not in full_ajax_url:
            query_params = "sEcho=1&iColumns=10&iDisplayStart=0&iDisplayLength=250&sSearch=&iSortingCols=1&iSortCol_0=0&sSortDir_0=desc"
            divider = "&" if "?" in full_ajax_url else "?"
            full_ajax_url += f"{divider}{query_params}"

        ajax_headers = {"Referer": check_url, "X-Requested-With": "XMLHttpRequest"}
        ajax_res = session.get(full_ajax_url, headers=ajax_headers, timeout=15)
        data_dict = ajax_res.json()
        rows = data_dict.get("aaData", [])

        # Detect columns from aoColumns or sColumns in AJAX response
        n_i = n_idx_cfg if n_idx_cfg is not None else -1
        m_i = m_idx_cfg if m_idx_cfg is not None else -1
        c_i = -1
        pay_i = -1
        _ao_all = data_dict.get("aoColumns", data_dict.get("columns", []))
        if _ao_all:
            _names_all = []
            for col in _ao_all:
                if isinstance(col, dict):
                    _names_all.append(col.get("sTitle", col.get("title", col.get("data", ""))))
                else:
                    _names_all.append(str(col))
            if rows and isinstance(rows[0], list) and len(rows[0]) == len(_names_all):
                pay_i = _find_payout_idx(_names_all)
        if pay_i == -1 and rows and isinstance(rows[0], list) and len(rows[0]) == len(_page_headers):
            # Only trust the page's <th> titles when they line up with the data columns.
            pay_i = _find_payout_idx(_page_headers)

        if n_i == -1 or m_i == -1:
            ao_cols = data_dict.get("aoColumns", data_dict.get("columns", []))
            if ao_cols:
                col_names = []
                for col in ao_cols:
                    if isinstance(col, dict):
                        col_names.append(col.get("sTitle", col.get("title", col.get("data", ""))))
                    else:
                        col_names.append(str(col))
                dn, dm, dc = _auto_detect_cols(col_names)
                if n_i == -1 and dn >= 0: n_i = dn
                if m_i == -1 and dm >= 0: m_i = dm
                if c_i == -1 and dc >= 0: c_i = dc

            # Still not found → smart scan data rows
            if n_i == -1 or m_i == -1:
                dn, dm, dc = _smart_detect_from_data(rows)
                if n_i == -1 and dn >= 0: n_i = dn
                if m_i == -1 and dm >= 0: m_i = dm
                if c_i == -1 and dc >= 0: c_i = dc

            # Final fallback defaults (Number=col0, SMS=col3 for typical CDR panels)
            if n_i == -1: n_i = 0
            if m_i == -1: m_i = 3

        # Sanity: the chosen payout column must hold plain numbers in every sampled
        # row. Anything else means the column index is misaligned → don't filter.
        if pay_i >= 0:
            _num_re = re.compile(r"^\s*\$?\s*-?\d*\.?\d+\s*\$?\s*$")
            for _r in rows[:30]:
                if isinstance(_r, list) and pay_i < len(_r):
                    _c = re.sub(r"<[^>]*>", "", str(_r[pay_i])).strip()
                    if _c and not _num_re.match(_c):
                        print(f"[CPT] '{p.get('name')}': payout col #{pay_i + 1} not numeric ({_c[:20]!r}) — payout filter disabled")
                        pay_i = -1
                        break
        _skipped_zero = 0

        for row_val in rows:
            if not isinstance(row_val, list) or len(row_val) <= max(n_i, m_i):
                continue

            # "My Payout" = 0 → panel earned nothing for this OTP → skip it.
            if 0 <= pay_i < len(row_val) and _zero_payout(row_val[pay_i]):
                _skipped_zero += 1
                try:
                    _zn = re.sub(r'\D', '', str(row_val[n_i])) if 0 <= n_i < len(row_val) else ""
                    _zm = str(row_val[m_i]) if 0 <= m_i < len(row_val) else ""
                    _zo = extract_otp_code(_zm)
                    if _zn and _zo:
                        _zts = _parse_row_timestamp(row_val)
                        _zk = _msg_dedup_key(_zm)
                        _zuid = (f"{_zn}_{_zo}_{_zk}_{int(_zts)}" if _zts is not None
                                 else f"{_zn}_{_zo}_{_zk}")
                        _cpt_note_zero_row(_zuid)
                except Exception as _ze:
                    print(f"[CPT] zero-row tracking failed: {_ze}")
                continue

            num_val = str(row_val[n_i]) if 0 <= n_i < len(row_val) else ""
            msg_val = str(row_val[m_i]) if 0 <= m_i < len(row_val) else ""
            cli_val = ""
            if 0 <= c_i < len(row_val):
                raw_c = str(row_val[c_i]).strip()
                if raw_c and not re.match(r'^\+?[\d\s\-]+$', raw_c):
                    cli_val = raw_c

            clean_num = re.sub(r'\D', '', num_val)
            if clean_num and 5 <= len(clean_num) <= 18:
                otp = extract_otp_code(msg_val)
                if otp and len(msg_val) > 4:
                    if not cli_val:
                        cli_val = detect_service(msg_val) or ""
                    received_ts = _parse_row_timestamp(row_val)
                    results.append({"number": clean_num, "message": msg_val, "otp": otp, "cli": cli_val, "received_ts": received_ts})

        if pay_i >= 0 and _skipped_zero:
            print(f"[CPT] '{p.get('name')}': payout col #{pay_i + 1} — skipped {_skipped_zero} zero-payout row(s), kept {len(results)}")

    else:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if not rows:
                continue

            final_n_idx = n_idx_cfg if n_idx_cfg is not None else 0
            final_m_idx = m_idx_cfg if m_idx_cfg is not None else 3
            final_c_idx = -1

            # Auto-detect from header row
            header_cells = rows[0].find_all(['th', 'td'])
            for i, cell in enumerate(header_cells):
                c_text = cell.get_text(strip=True).lower()
                if n_idx_cfg is None and any(w in c_text for w in [n_col_name] + _N_WORDS):
                    final_n_idx = i
                if m_idx_cfg is None and any(w in c_text for w in [m_col_name] + _M_WORDS):
                    final_m_idx = i
                if any(w in c_text for w in _C_WORDS):
                    final_c_idx = i

            for row in rows:
                cols = row.find_all(['td', 'th'])
                if all(c.name == 'th' for c in cols):
                    continue
                if len(cols) <= max(final_n_idx, final_m_idx):
                    continue

                num_text = cols[final_n_idx].get_text(separator=" ", strip=True)
                msg_text = cols[final_m_idx].get_text(separator=" ", strip=True)
                cli_val = ""
                if 0 <= final_c_idx < len(cols):
                    raw_c = cols[final_c_idx].get_text(strip=True)
                    if raw_c and not re.match(r'^\+?[\d\s\-]+$', raw_c):
                        cli_val = raw_c

                clean_num = re.sub(r'\D', '', num_text)
                if clean_num and 5 <= len(clean_num) <= 18:
                    otp = extract_otp_code(msg_text)
                    if otp and len(msg_text) > 4:
                        if not cli_val:
                            cli_val = detect_service(msg_text) or ""
                        row_cells = [c.get_text(separator=" ", strip=True) for c in cols]
                        received_ts = _parse_row_timestamp(row_cells)
                        results.append({"number": clean_num, "message": msg_text, "otp": otp, "cli": cli_val, "received_ts": received_ts})

    return results, html_text

# Track active number sessions to expire them automatically
user_active_sessions = {}


def load_db():
    global bot_settings, total_uploaded_stats, total_assigned_stats, pending_withdrawals, number_batches
    import json as _json
    # ── Load all bot_settings from DB ──────────────────────────────────────
    with db_lock:
        conn = get_db_conn()
        rows = conn.execute("SELECT key, value FROM bot_settings_store").fetchall()
        conn.close()
    RESERVED = {"__stats__", "__number_batches__"}
    # NOTE: premium_flags/premium_apps used to be force-skipped here (and in
    # save_local_db's SKIP set below) on the assumption they're static
    # code-only defaults. They aren't — the "Add Single Emoji" admin flow and
    # the bulk .txt upload both write directly into these dicts at runtime.
    # Skipping them meant every admin-added emoji (flags or apps) was silently
    # wiped back to the hardcoded defaults on the next restart. Now persisted
    # like every other setting; the hardcoded literals above still act as the
    # first-run default before any DB row exists.
    PROTECTED_DEFAULTS = set()
    for key, val in rows:
        if key in RESERVED or key in PROTECTED_DEFAULTS:
            continue
        try:
            bot_settings[key] = _json.loads(val)
        except Exception:
            bot_settings[key] = val
    # ── Load number_batches (uploaded numbers survive restarts) ─────────────
    with db_lock:
        conn = get_db_conn()
        nb_row = conn.execute("SELECT value FROM bot_settings_store WHERE key='__number_batches__'").fetchone()
        conn.close()
    if nb_row:
        try:
            loaded_batches = _json.loads(nb_row[0])
            if isinstance(loaded_batches, dict):
                number_batches = loaded_batches
                print(f"✅ Loaded {len(number_batches)} number batch(es) from DB")
        except Exception:
            pass
    # ── Restore user_active_sessions (so Add CC / Change Number work after restart) ──
    with db_lock:
        conn = get_db_conn()
        ses_row = conn.execute("SELECT value FROM bot_settings_store WHERE key='__user_sessions__'").fetchone()
        conn.close()
    if ses_row:
        try:
            loaded_sessions = _json.loads(ses_row[0])
            if isinstance(loaded_sessions, dict):
                # JSON keys are always strings; restore as int chat_ids
                user_active_sessions.update({int(k): v for k, v in loaded_sessions.items()})
                print(f"✅ Restored {len(user_active_sessions)} active user session(s) from DB")
        except Exception:
            pass
    # ── Restore recent_traffic so OTP history survives restarts ────────────────
    with db_lock:
        conn = get_db_conn()
        rt_row = conn.execute("SELECT value FROM bot_settings_store WHERE key='__recent_traffic__'").fetchone()
        conn.close()
    if rt_row:
        try:
            loaded_traffic = _json.loads(rt_row[0])
            if isinstance(loaded_traffic, list):
                _tw_sec = bot_settings.get("traffic_window", 60) * 60
                _now = time.time()
                for entry in loaded_traffic:
                    if isinstance(entry, dict) and _now - entry.get("time", 0) <= _tw_sec:
                        recent_traffic.append(entry)
                print(f"✅ Restored {len(recent_traffic)} traffic entry/entries from DB")
        except Exception:
            pass
    # ── Restore any stock backed up in numbers/*.txt (survives even a DB reset) ──
    load_numbers_from_folder()
    # Always ensure OWNER_ID is in admins list after loading
    if OWNER_ID not in bot_settings.get("admins", []):
        bot_settings.setdefault("admins", []).insert(0, OWNER_ID)
    # ── Load stats ─────────────────────────────────────────────────────────
    with db_lock:
        conn = get_db_conn()
        stats_row = conn.execute("SELECT value FROM bot_settings_store WHERE key='__stats__'").fetchone()
        # ── Reload pending withdrawals from DB ──────────────────────────────
        pending_rows = conn.execute(
            "SELECT id, user_id, amount, method, account, request_id "
            "FROM withdrawals WHERE status='pending'"
        ).fetchall()
        conn.close()
    if stats_row:
        try:
            parsed = _json.loads(stats_row[0])
            total_uploaded_stats = parsed.get("uploaded", 0)
            total_assigned_stats = parsed.get("assigned", 0)
        except Exception:
            pass
    for row in pending_rows:
        db_id, uid, amt, method, account, stored_req_id = row
        req_id = stored_req_id or f"DB_{db_id}"
        pending_withdrawals[req_id] = {
            "user_id": uid, "amount": amt,
            "method": method, "number": account,
            "full_name": "", "db_id": db_id
        }
    print("✅ SQLite DB Loaded!")

def save_local_db():
    import json as _json
    # Persist everything, including premium_flags/premium_apps — see the
    # matching note in load_db() for why those must not be skipped.
    SKIP = set()
    with db_lock:
        conn = get_db_conn()
        for k, v in bot_settings.items():
            if k in SKIP:
                continue
            try:
                serialised = _json.dumps(v)
                conn.execute(
                    "INSERT INTO bot_settings_store (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                    (k, serialised, serialised)
                )
            except Exception:
                pass
        # Save number_batches so uploaded numbers survive bot restarts
        try:
            nb_json = _json.dumps(number_batches)
            conn.execute("INSERT INTO bot_settings_store (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                         ("__number_batches__", nb_json, nb_json))
        except Exception:
            pass
        # Save user_active_sessions so "Add CC / Change Number" buttons still
        # work after a bot restart — without this, any restart wipes all sessions
        # and users get "Session expired" on their existing number cards.
        try:
            # Convert int keys to str for JSON serialisation; restored as int below.
            ses_json = _json.dumps({str(k): v for k, v in user_active_sessions.items()})
            conn.execute("INSERT INTO bot_settings_store (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                         ("__user_sessions__", ses_json, ses_json))
        except Exception:
            pass
        # Stats (uploaded/assigned counts)
        try:
            st_json = _json.dumps({"uploaded": total_uploaded_stats, "assigned": total_assigned_stats})
            conn.execute("INSERT INTO bot_settings_store (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                         ("__stats__", st_json, st_json))
        except Exception:
            pass
        # Save recent_traffic so OTP history survives restarts
        try:
            _tw_sec = bot_settings.get("traffic_window", 60) * 60
            _now = time.time()
            # Only save entries within the window (no point saving stale data)
            rt_snapshot = [e for e in recent_traffic if _now - e.get("time", 0) <= _tw_sec]
            rt_json = _json.dumps(rt_snapshot)
            conn.execute("INSERT INTO bot_settings_store (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?",
                         ("__recent_traffic__", rt_json, rt_json))
        except Exception:
            pass
        conn.commit()
        conn.close()
    # Write users.txt for backup/export
    try:
        with db_lock:
            conn2 = get_db_conn()
            user_rows = conn2.execute("SELECT user_id, username, first_name FROM users").fetchall()
            conn2.close()
        os.makedirs("data", exist_ok=True)
        with open("data/users.txt", "w", encoding="utf-8") as uf:
            uf.write("user_id|username|first_name\n")
            for row in user_rows:
                uid2, uname2, fname2 = row[0], row[1] or "", row[2] or ""
                uf.write(f"{uid2}|{uname2}|{fname2}\n")
    except Exception:
        pass

_save_db_running = threading.Event()

def save_db():
    """Fire-and-forget DB save — skip if one is already in flight."""
    if _save_db_running.is_set():
        return  # previous save still running; skip to avoid thread pile-up
    # BUG FIX: set the flag HERE (before spawning) to close the race window
    # between the is_set() check above and the .set() that was previously
    # inside _run(). Two concurrent callers could both pass is_set()=False
    # before either thread had a chance to call .set(), starting two parallel
    # save threads and corrupting the DB. Setting it synchronously here
    # eliminates that window entirely.
    _save_db_running.set()
    def _run():
        try:
            save_local_db()
        finally:
            _save_db_running.clear()
    threading.Thread(target=_run, daemon=True, name="save-db").start()

def _fs_sanitize(s):
    """Turn a service/country label into a safe lowercase filename fragment."""
    s = re.sub(r'[^a-z0-9]+', '_', str(s or "unknown").strip().lower())
    return s.strip('_') or "unknown"

def _fs_batch_id(service, country):
    """Deterministic batch id so every upload for the same service+country
    merges into ONE local backup file instead of scattering across many."""
    return f"fs_{_fs_sanitize(country)}_{_fs_sanitize(service)}"

def _fs_file_path(service, country):
    return os.path.join(NUMBERS_DIR, f"{_fs_sanitize(country)}_{_fs_sanitize(service)}.txt")

def _fs_sync_batch(batch_id):
    """Rewrite (or remove) the local numbers/*.txt backup file so it always
    mirrors the current numbers actually left in that batch. Called after
    every add/remove so a bot restart can restore stock straight from disk."""
    b = number_batches.get(batch_id)
    try:
        if not b:
            return
        service, country = b.get("service", "UNKNOWN"), b.get("country", "UNKNOWN")
        path = _fs_file_path(service, country)
        nums = [str(n.get("num", "")) for n in b.get("numbers", []) if n.get("num")]
        if nums:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(nums) + "\n")
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def _fs_remove_file_for(service, country):
    try:
        path = _fs_file_path(service, country)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def load_numbers_from_folder():
    """On startup, restore any stock found in numbers/*.txt that isn't
    already loaded from the DB (e.g. DB was wiped/reset). Files are named
    <country>_<service>.txt and use the same deterministic fs_ batch id, so
    re-running this is always safe/idempotent."""
    restored_files = 0
    try:
        for fname in os.listdir(NUMBERS_DIR):
            if not fname.endswith(".txt"):
                continue
            fpath = os.path.join(NUMBERS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    file_nums = [line.strip() for line in f if line.strip()]
            except Exception:
                continue
            if not file_nums:
                continue
            # Find any existing batch (fs_-based or legacy) already covering
            # this exact file so we don't duplicate numbers already in DB.
            existing_nums_all = set()
            for b in number_batches.values():
                for n in b.get("numbers", []):
                    existing_nums_all.add(str(n.get("num", "")).replace("+", "").replace(" ", "").replace("-", "").strip())
            base = fname[:-4]
            # base is "<country>_<service>" (both sanitized) — recover a
            # best-effort display service/country by matching sanitized parts
            # against premium_apps/premium_flags, falling back to raw text.
            service_guess, country_guess = "UNKNOWN", "UNKNOWN"
            for app_key, app_data in bot_settings.get("premium_apps", {}).items():
                if _fs_sanitize(app_key) and base.endswith("_" + _fs_sanitize(app_key)):
                    service_guess = app_key
                    country_guess = base[: -(len(_fs_sanitize(app_key)) + 1)]
                    break
            if service_guess == "UNKNOWN":
                # Fall back: split on last underscore
                if "_" in base:
                    country_guess, service_guess = base.rsplit("_", 1)
                else:
                    service_guess = base
            new_nums = [n for n in file_nums if n.replace("+", "").replace(" ", "").replace("-", "").strip() not in existing_nums_all]
            if not new_nums:
                continue
            b_id = _fs_batch_id(service_guess, country_guess)
            with number_batches_lock:
                if b_id in number_batches:
                    number_batches[b_id]["numbers"].extend({"num": n, "shares": 0, "used_by": []} for n in new_nums)
                else:
                    number_batches[b_id] = {
                        "filename": fname, "service": service_guess, "country": country_guess,
                        "numbers": [{"num": n, "shares": 0, "used_by": []} for n in new_nums]
                    }
            restored_files += 1
        if restored_files:
            print(f"✅ Restored stock from {restored_files} local numbers/*.txt file(s)")
    except Exception as e:
        print(f"⚠️ load_numbers_from_folder error: {e}")

def _numbers_match(a, b):
    """
    True if `a` and `b` are the SAME phone number, allowing for one side
    missing its country code (a common formatting inconsistency between the
    number-stock list and the OTP panel's own record of the number).

    This intentionally does NOT use a blind "last 8 digits match" check.
    At high concurrency (thousands of numbers active at once) a bare
    last-8-digit comparison collides by pure chance between two totally
    different numbers (birthday-paradox math: with ~10k concurrent numbers
    sharing an 8-digit suffix space of 10^8, a collision is likely, not
    rare) — that caused OTPs meant for one user's number to be delivered to
    a different user whose number merely happened to share the same last 8
    digits. Requiring the ENTIRE shorter number to match as a suffix, with
    only a small (<=4 digit) length gap reserved for a country code,
    removes that collision risk.
    """
    a = str(a).replace("+", "").replace(" ", "").replace("-", "").strip()
    b = str(b).replace("+", "").replace(" ", "").replace("-", "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    diff = len(long_) - len(short)
    return len(short) >= 6 and 0 < diff <= 4 and long_.endswith(short)


def remove_number_after_otp(raw_num):
    """
    Called only when an OTP has actually been received for a number.
    Removes the matching number from stock (number_batches) and records it in
    used_numbers_list (with service/country) so it can be restocked later.
    Numbers that were merely assigned/shared to a user but never received an
    OTP are left untouched in stock.
    """
    clean_target = str(raw_num).replace("+", "").replace(" ", "").replace("-", "").strip()
    if not clean_target:
        return False
    for b_id, b_data in list(number_batches.items()):
        numbers = b_data.get("numbers", [])
        for idx, n_obj in enumerate(numbers):
            n_clean = str(n_obj.get("num", "")).replace("+", "").replace(" ", "").replace("-", "").strip()
            if _numbers_match(n_clean, clean_target):
                used_numbers_list.append({
                    "num": n_obj.get("num"),
                    "service": b_data.get("service"),
                    "country": b_data.get("country")
                })
                del numbers[idx]
                save_db()
                _fs_sync_batch(b_id)
                return True
    return False

class _TimestampedDict(dict):
    """dict subclass that auto-records a timestamp on every __setitem__ so
    housekeeping can evict stale entries without touching 60+ call sites."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._ts = {}
    def __setitem__(self, key, value):
        self._ts[key] = time.time()
        super().__setitem__(key, value)
    def __delitem__(self, key):
        self._ts.pop(key, None)
        super().__delitem__(key)
    def pop(self, key, *args):
        self._ts.pop(key, None)
        return super().pop(key, *args)
    def get_ts(self, key):
        return self._ts.get(key, 0)

user_states = _TimestampedDict()
temp_data = {}
user_cooldowns = {}

# --- Callback debounce (fixes "single click opens double menu") ---
# 4 dispatcher threads pull updates off the same queue concurrently. A fast
# double-tap (or a client resending a callback while the previous one is
# still animating) produces two callback_query updates with the SAME
# chat_id+data within a fraction of a second, and two threads can process
# them in parallel — some menu actions call send_message (a new message)
# rather than edit_message, so this visibly stacks two menus in the chat.
# Guard against it by dropping a repeat of the same (chat_id, data) that
# arrives within a short window of the first.
_recent_callbacks = {}
_recent_callbacks_lock = threading.Lock()
_CALLBACK_DEBOUNCE_SEC = 0.8

def _is_duplicate_callback(chat_id, data, message_id=None):
    now = time.time()
    # Include the message id.  The same callback data is intentionally reused
    # by refreshed menus and pagination buttons; debouncing only identical
    # clicks on the same message prevents a real click from being discarded.
    key = (chat_id, message_id, data)
    with _recent_callbacks_lock:
        last = _recent_callbacks.get(key, 0)
        _recent_callbacks[key] = now
        if now - last < _CALLBACK_DEBOUNCE_SEC:
            return True
        # Occasionally prune old entries so this dict doesn't grow forever.
        if len(_recent_callbacks) > 5000:
            cutoff = now - 60
            for k, v in list(_recent_callbacks.items()):
                if v < cutoff:
                    del _recent_callbacks[k]
    return False
pending_withdrawals = {}
daily_otps = {}  # {user_id: {"date": "YYYY-MM-DD", "count": N}}  ← kept for OTP Status panel
today_stats = {"date": "", "earned": 0.0, "by_service": {}}  # {service: {iso: count}} — reset each day

def lb_record_otp(user_id):
    """Persist one OTP for user_id into the daily_leaderboard DB table.
    This is the single source of truth for Today and Weekly leaderboards —
    it survives bot restarts unlike the in-memory daily_otps dict.
    Also mirrors the count into daily_otps for the OTP Status panel.
    """
    _today = datetime.now().strftime("%Y-%m-%d")
    # ── DB write ──────────────────────────────────────────────────────────
    try:
        with db_lock:
            _c = get_db_conn()
            _c.execute(
                """INSERT INTO daily_leaderboard (user_id, date, count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1""",
                (user_id, _today)
            )
            _c.commit()
            _c.close()
    except Exception as _e:
        print(f"[lb_record_otp] DB error: {_e}")
    # ── In-memory mirror (OTP Status panel uses this) ─────────────────────
    if daily_otps.get(user_id, {}).get("date") != _today:
        daily_otps[user_id] = {"date": _today, "count": 0}
    daily_otps[user_id]["count"] = daily_otps[user_id].get("count", 0) + 1

load_db()
_load_dedup_from_db()        # restore seen-OTP dedup from SQLite → prevents re-forwarding after restart
_load_retry_queue_from_db()  # restore any OTPs that failed delivery before last restart

def _load_daily_otps_from_db():
    """Load today's per-user OTP counts and today_stats from DB so OTP Status
    and Today leaderboard survive restarts."""
    global daily_otps, today_stats
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with db_lock:
            conn = get_db_conn()
            row_otps  = conn.execute("SELECT value FROM bot_settings_store WHERE key='daily_otps'").fetchone()
            row_stats = conn.execute("SELECT value FROM bot_settings_store WHERE key='today_stats'").fetchone()
            conn.close()

        if row_otps and row_otps[0]:
            data = json.loads(row_otps[0])
            cleaned = {int(uid): v for uid, v in data.items() if v.get("date") == today_str}
            daily_otps.update(cleaned)
            print(f"✅ daily_otps restored: {len(cleaned)} users for today")

        if row_stats and row_stats[0]:
            data = json.loads(row_stats[0])
            if data.get("date") == today_str:
                today_stats.update(data)
                print(f"✅ today_stats restored: earned={data.get('earned', 0):.4f}, services={len(data.get('by_service', {}))}")
    except Exception as e:
        print(f"[daily_otps load] error: {e}")

_load_daily_otps_from_db()

def _housekeeping_thread():
    """Runs every 30 minutes — cleans up all unbounded in-memory structures so
    the bot never degrades in speed after hours of uptime."""
    while True:
        time.sleep(300)    # every 5 min — was 1800 (30 min); long interval lets user_states,
                           # temp_data, user_cooldowns, daily_otps grow unboundedly between runs
        try:
            now = time.time()

            # 1. daily_otps — remove keys from previous days (they never auto-delete)
            today = datetime.now().strftime("%Y-%m-%d")
            stale_users = [uid for uid, v in list(daily_otps.items())
                           if v.get("date") != today]
            for uid in stale_users:
                daily_otps.pop(uid, None)

            # 2. otp_dedup SQLite table — delete rows older than 24 h
            cutoff = now - 86400
            try:
                conn = get_db_conn()
                deleted = conn.execute(
                    "DELETE FROM otp_dedup WHERE ts <= ?", (cutoff,)
                ).rowcount
                conn.commit()
                conn.close()
            except Exception:
                deleted = 0

            # 2b. otp_retry_queue — purge rows older than 24 h that are still
            # sitting in the DB (should not happen normally, but guards against
            # a stuck item never being cleaned up).
            try:
                conn = get_db_conn()
                purged = conn.execute(
                    "DELETE FROM otp_retry_queue WHERE created_at <= ?", (cutoff,)
                ).rowcount
                conn.commit()
                conn.close()
                if purged:
                    print(f"[OTP-RETRY] 🗑️ Purged {purged} stale retry rows (>24h old)")
            except Exception:
                pass

            # 3. user_cache — trim if too large
            trimmed = 0
            while len(user_cache) > 8000:
                try:
                    user_cache.pop(next(iter(user_cache)))
                    trimmed += 1
                except (StopIteration, RuntimeError):
                    break

            # 4. recent_traffic — trim entries older than the configured window
            _tw_sec = bot_settings.get("traffic_window", 60) * 60
            while recent_traffic and now - recent_traffic[0].get("time", 0) > _tw_sec:
                recent_traffic.popleft()

            # 5. user_states / temp_data — evict abandoned flows (>30 min old)
            #    Users who close the bot mid-flow leave stale state forever;
            #    this is the main long-running memory leak.
            STATE_TTL = 1800  # 30 minutes
            stale_states = [uid for uid in list(user_states.keys())
                            if now - user_states.get_ts(uid) > STATE_TTL]
            for uid in stale_states:
                user_states.pop(uid, None)
                temp_data.pop(uid, None)

            # 6. user_cooldowns — remove entries older than 10 minutes
            stale_cd = [uid for uid, ts in list(user_cooldowns.items())
                        if now - ts > 600]
            for uid in stale_cd:
                user_cooldowns.pop(uid, None)

            # 7. Persist daily_otps + today_stats → DB so OTP Status / Today leaderboard survive restarts
            try:
                with db_lock:
                    _conn_hk = get_db_conn()
                    _conn_hk.execute(
                        "INSERT OR REPLACE INTO bot_settings_store (key, value) VALUES ('daily_otps', ?)",
                        (json.dumps({str(k): v for k, v in list(daily_otps.items())}),)
                    )
                    _conn_hk.execute(
                        "INSERT OR REPLACE INTO bot_settings_store (key, value) VALUES ('today_stats', ?)",
                        (json.dumps(today_stats),)
                    )
                    _conn_hk.commit()
                    _conn_hk.close()
            except Exception as _hk_e:
                print(f"[housekeeping] persist error: {_hk_e}")

            print(f"[housekeeping] daily_otps={len(stale_users)} | "
                  f"dedup_deleted={deleted} | cache_trimmed={trimmed} | "
                  f"stale_states={len(stale_states)} | stale_cd={len(stale_cd)} | "
                  f"user_cache={len(user_cache)} | traffic={len(recent_traffic)}")
        except Exception as e:
            print(f"[housekeeping] error: {e}")

threading.Thread(target=_housekeeping_thread, daemon=True, name="housekeeping").start()

# ── Daily Leaderboard Midnight Announcement ────────────────────────────────
def _daily_leaderboard_thread():
    """Fires at midnight every day — reads winners from DB, broadcasts announcement,
    then the new day automatically starts fresh (DB rows keyed by date)."""
    from datetime import timedelta
    while True:
        # ── Sleep until next midnight ────────────────────────────────────────
        try:
            _now = datetime.now()
            _target = _now.replace(hour=0, minute=0, second=5, microsecond=0)
            if _target <= _now:
                _target += timedelta(days=1)
            time.sleep((_target - _now).total_seconds())
        except Exception as _e:
            print(f"[daily_lb] sleep error: {_e}")
            time.sleep(86400)
            continue

        try:
            if not bot_settings.get("leaderboard_on", True):
                continue

            # Yesterday's date (we just crossed midnight so "yesterday" = finished day)
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # Read top-3 from DB
            try:
                with db_lock:
                    _c = get_db_conn()
                    _rows = _c.execute(
                        "SELECT user_id, count FROM daily_leaderboard "
                        "WHERE date = ? AND count > 0 ORDER BY count DESC LIMIT 3",
                        (yesterday,)
                    ).fetchall()
                    _c.close()
            except Exception as _de:
                print(f"[daily_lb] DB read error: {_de}")
                continue

            if not _rows:
                print(f"[daily_lb] No winners for {yesterday} — skipping announcement.")
                continue

            _MEDALS = ["🥇", "🥈", "🥉"]
            winner_lines = ""
            for rank, row in enumerate(_rows):
                medal = _MEDALS[rank] if rank < len(_MEDALS) else f"{rank+1}."
                name  = _lb_get_name(row["user_id"])
                winner_lines += f"{medal} <b>{name}</b> — <code>{row['count']}</code> OTPs\n"

            announcement = (
                "━━━━━━━━━━━━━━━━━━\n"
                "🏆 <b>DAILY LEADERBOARD RESULTS</b> 🏆\n"
                f"📅 <i>{yesterday}</i>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"{winner_lines}\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎉 Congratulations to today's top performers!\n"
                "<i>Daily leaderboard resets at midnight. Good luck tomorrow!</i>"
            )
            ann_text = render_body_text(announcement)

            # Send to admin/withdrawal group if configured
            w_group = bot_settings.get("w_group")
            if w_group:
                try:
                    send_message(w_group, ann_text)
                except Exception as _ge:
                    print(f"[daily_lb] group send error: {_ge}")

            # Broadcast to all active users
            try:
                with db_lock:
                    _lb_conn = get_db_conn()
                    user_rows = _lb_conn.execute(
                        "SELECT user_id FROM users WHERE banned=0"
                    ).fetchall()
                    _lb_conn.close()
                sent_count = 0
                for _urow in user_rows:
                    try:
                        send_message(_urow[0], ann_text)
                        sent_count += 1
                        time.sleep(0.05)   # ~20 msgs/sec — stay within Telegram limits
                    except Exception:
                        pass
                print(f"[daily_lb] Announced to {sent_count} users.")
            except Exception as _be:
                print(f"[daily_lb] broadcast error: {_be}")

        except Exception as e:
            print(f"[daily_lb] error: {e}")

threading.Thread(target=_daily_leaderboard_thread, daemon=True, name="daily-leaderboard").start()

# Numbers a user released by pressing "Change Number": clean_num -> list of
# {"uid", "service", "released_at"}.  Used so an OTP that still arrives on the
# old number within the admin-set window ("old_num_window", minutes) goes to
# the user who had it.
_released_numbers = {}
_released_numbers_lock = threading.Lock()

def _clean_num_str(n):
    return str(n).replace("+", "").replace(" ", "").replace("-", "").strip()

def _record_released_numbers(uid, nums, service, country=None):
    if not nums or int(bot_settings.get("old_num_window", 0) or 0) <= 0:
        return
    now = time.time()
    with _released_numbers_lock:
        for n in nums:
            cn = _clean_num_str(n)
            if not cn:
                continue
            lst = [e for e in _released_numbers.get(cn, []) if e["uid"] != uid]
            lst.append({"uid": uid, "service": service, "country": country, "released_at": now})
            _released_numbers[cn] = lst

def _find_released_owner(clean_num):
    """Latest user who released `clean_num` within the admin-set window, or None."""
    window = int(bot_settings.get("old_num_window", 0) or 0)
    if window <= 0:
        return None
    limit = window * 60
    now = time.time()
    best = None
    with _released_numbers_lock:
        for cn in list(_released_numbers.keys()):
            fresh = [e for e in _released_numbers[cn] if now - e["released_at"] <= limit]
            if fresh:
                _released_numbers[cn] = fresh
            else:
                del _released_numbers[cn]
                continue
            if _numbers_match(cn, clean_num):
                cand = max(fresh, key=lambda e: e["released_at"])
                if best is None or cand["released_at"] > best["released_at"]:
                    best = cand
    return best

def _number_expiry_thread():
    """Checks every 30 seconds for expired number sessions and returns them to stock."""
    while True:
        time.sleep(30)
        try:
            expiry_min = bot_settings.get("num_expiry", 0)
            if not expiry_min or expiry_min <= 0:
                continue
            expiry_sec = expiry_min * 60
            now = time.time()
            expired_users = [
                uid for uid, sess in list(user_active_sessions.items())
                if sess.get("assigned_at") and (now - sess["assigned_at"]) >= expiry_sec
            ]
            for uid in expired_users:
                try:
                    print(f"[expiry] Auto-expiring number for user {uid} (limit={expiry_min}min)")
                    expire_previous_number(uid, return_to_stock=True)
                except Exception as ex:
                    print(f"[expiry] Error expiring user {uid}: {ex}")
        except Exception as e:
            print(f"[expiry] Thread error: {e}")

threading.Thread(target=_number_expiry_thread, daemon=True, name="num-expiry").start()

# ==========================================
# Telegram API & Helpers
# ==========================================
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as _Retry

# ─── Thread-local sessions ────────────────────────────────────────────────────
# Each worker thread gets its own Session so there is ZERO lock contention on
# the shared connection pool — the single biggest throughput bottleneck at high
# concurrency.  Each session keeps its own small pool (4 conns) which is plenty
# because one thread can only be in one api_call at a time.
_tl = threading.local()

def _get_session() -> requests.Session:
    if not hasattr(_tl, "session"):
        s = requests.Session()
        a = HTTPAdapter(
            pool_connections=4,
            pool_maxsize=8,
            max_retries=_Retry(total=0),  # retries handled in api_call below
        )
        s.mount("https://", a)
        s.mount("http://", a)
        _tl.session = s
    return _tl.session

# Keep a single shared session ONLY for the main polling thread (getUpdates).
# This session uses a large pool so the poller itself never stalls.
tg_session = requests.Session()
_poll_adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=_Retry(total=0))
tg_session.mount("https://", _poll_adapter)
tg_session.mount("http://", _poll_adapter)

def api_call(method, payload=None, _retry=3):
    url = f"{BASE_URL}/{method}"
    sess = _get_session()
    for attempt in range(_retry):
        try:
            res = sess.post(url, json=payload, timeout=10)
            data = res.json()
            # Handle Telegram rate-limit (429) — wait then retry
            if not data.get("ok") and data.get("error_code") == 429:
                wait = min(data.get("parameters", {}).get("retry_after", 2), 10)
                if attempt < _retry - 1:
                    time.sleep(wait)
                    continue
            return data
        except Exception:
            if attempt < _retry - 1:
                time.sleep(0.5)
                continue
            return {}
    return {}

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_call("sendMessage", payload)

# ─── OTP delivery: instant-send + guaranteed retry ────────────────────────────
# Telegram enforces about 30 messages/second bot-wide, and a stricter ceiling
# on any single chat (private OR group) if you sustain a high rate to it for
# too long. Previously the 16 OTP sender threads hammered Telegram
# concurrently for the SAME group/user; when Telegram flood-controlled a
# send (HTTP 429), `api_call()` only retried 3 times with short waits and
# then returned silently — nothing re-checked that result, so the OTP was
# just lost. That silent loss is the "OTP skip" bug.
#
# `send_otp_message()` replaces direct `send_message()` calls in every OTP
# forwarding path (group forwards + user inbox). Per the requested behaviour,
# it does NOT pre-emptively delay a send that might succeed — every OTP is
# forwarded instantly the moment it's picked up:
#   1. It only waits for a global token-bucket slot (~25 msgs/sec, safely
#      under Telegram's ~30/sec bot-wide ceiling) — this is a hard Telegram
#      rule for the whole bot, not an artificial slowdown for one chat.
#   2. It sends immediately — no forced per-chat gap.
#   3. If Telegram actually rejects the send (429 flood-control or a network
#      hiccup), it is automatically RE-QUEUED to fire ~1 second later instead
#      of being dropped — a "skipped" OTP lands in the very next available
#      second rather than never arriving. Permanent failures (bot blocked by
#      the user, chat not found) are not retried.

_otp_global_rate_lock = threading.Lock()
_otp_global_tokens = 25.0
_otp_global_last_refill = time.time()
_OTP_GLOBAL_RATE = 25.0    # tokens refilled per second
_OTP_GLOBAL_BURST = 25.0   # max tokens banked at once

def _otp_wait_global_slot():
    global _otp_global_tokens, _otp_global_last_refill
    while True:
        with _otp_global_rate_lock:
            now = time.time()
            elapsed = now - _otp_global_last_refill
            _otp_global_last_refill = now
            _otp_global_tokens = min(_OTP_GLOBAL_BURST, _otp_global_tokens + elapsed * _OTP_GLOBAL_RATE)
            if _otp_global_tokens >= 1:
                _otp_global_tokens -= 1
                return
            deficit = 1 - _otp_global_tokens
        time.sleep(min(max(deficit / _OTP_GLOBAL_RATE, 0.01), 0.5))

def send_otp_message(chat_id, text, reply_markup=None, parse_mode="HTML", _attempt=1, _max_attempts=8):
    """Instant-send OTP forwarding (group forwards + user inbox) with
    guaranteed next-second retry on failure. See module notes above
    _otp_wait_global_slot."""
    _otp_wait_global_slot()
    result = send_message(chat_id, text, reply_markup, parse_mode) or {}

    if result.get("ok"):
        return result

    err_code = result.get("error_code")
    # Permanent failures (bot blocked / chat not found / bad request) — retrying
    # would never succeed, so stop here instead of looping forever.
    if err_code in (400, 403):
        return result

    if _attempt >= _max_attempts:
        # All rapid retries exhausted — hand off to the persistent retry queue
        # so the OTP is NOT lost. The retry worker will re-attempt with longer
        # backoff (30s → 60s → 120s → 300s → 600s) and survives a bot restart.
        _push_to_retry_queue(chat_id, text, reply_markup, parse_mode)
        return result

    # Transient failure (429 flood-control or a dropped connection) — hand it
    # back to the OTP queue a little over a second later so it goes out in
    # the next available slot instead of being lost.
    delay = 1.1 * _attempt
    timer = threading.Timer(
        delay, _enqueue_otp_send,
        args=(send_otp_message, chat_id, text, reply_markup, parse_mode, _attempt + 1, _max_attempts)
    )
    timer.daemon = True
    timer.start()
    return result


def send_photo(chat_id, photo_url_or_file_id, caption="", reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "photo": photo_url_or_file_id, "caption": caption, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_call("sendPhoto", payload)

def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    return api_call("editMessageText", payload)

def delete_message(chat_id, message_id):
    return api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def answer_callback(callback_id, text="", show_alert=False):
    api_call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": show_alert})

def _edit_or_send(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    """Edit an inline-menu message, falling back to a new message.

    Telegram can reject an edit when the original message is stale, already
    edited, or contains a payload it no longer accepts.  A menu must not leave
    the user on an endless loading screen in that case.
    """
    result = edit_message(
        chat_id,
        message_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    if result.get("ok"):
        return result
    print(
        f"[menu] edit failed method=editMessageText "
        f"error={result.get('description', 'unknown')}"
    )
    fallback = send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    if not fallback.get("ok"):
        print(
            f"[menu] fallback send failed "
            f"error={fallback.get('description', 'unknown')}"
        )
    return fallback

def send_document(chat_id, filename, text_content):
    url = f"{BASE_URL}/sendDocument"
    files = {'document': (filename, text_content)}
    data = {'chat_id': chat_id}
    try: requests.post(url, data=data, files=files)
    except: pass

all_known_users = set()

def sync_users_list():
    global all_known_users
    with db_lock:
        conn = get_db_conn()
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()
    all_known_users = set(str(r[0]) for r in rows)

threading.Thread(target=sync_users_list, daemon=True).start()

_user_write_q     = _collections.deque()
_user_write_event = threading.Event()

def _bg_user_writer():
    """Drain _user_write_q and batch-insert into SQLite every 2 s."""
    while True:
        _user_write_event.wait(timeout=2.0)
        _user_write_event.clear()
        batch = []
        while _user_write_q:
            try: batch.append(_user_write_q.popleft())
            except IndexError: break
        if not batch: continue
        try:
            with db_lock:
                conn = get_db_conn()
                for _uid, _uname, _fname in batch:
                    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (_uid,))
                    if _uname or _fname:
                        conn.execute(
                            "UPDATE users SET username=COALESCE(?,username), first_name=COALESCE(?,first_name) WHERE user_id=?",
                            (_uname or None, _fname or None, _uid)
                        )
                conn.commit()
                conn.close()
        except Exception as _e:
            print(f"[bg_user_writer] DB error: {_e}")

threading.Thread(target=_bg_user_writer, daemon=True, name="bg-user-writer").start()

def register_user_local(uid, username=None, first_name=None):
    uid_str = str(uid)
    all_known_users.add(uid_str)
    # Non-blocking: push to background queue so callers (button handlers) return instantly.
    _user_write_q.append((uid, username, first_name))
    _user_write_event.set()

def broadcast_copymessage(from_chat_id, msg_id):
    users = list(all_known_users)
    url = f"{BASE_URL}/copyMessage"
    results = {"success": 0, "failed": 0}
    lock = threading.Lock()

    def _send_one(user_id):
        payload = {"chat_id": user_id, "from_chat_id": from_chat_id, "message_id": msg_id}
        try:
            res = requests.post(url, json=payload, timeout=10).json()
            with lock:
                if res.get("ok"): results["success"] += 1
                else: results["failed"] += 1
        except:
            with lock:
                results["failed"] += 1

    # 🚀 ULTRA FAST: 20 concurrent workers, 25 dispatched/sec to respect Telegram limits
    with ThreadPoolExecutor(max_workers=20) as executor:
        for i, user_id in enumerate(users):
            executor.submit(_send_one, user_id)
            if i % 25 == 24:   # every 25 dispatches wait 1 sec → ~25 msg/sec rate
                time.sleep(1.0)

    send_message(from_chat_id, render_body_text(
        f"📢 <b>Broadcast Completed!</b>\n✅ Success: {results['success']}\n"
        f"❌ Failed: {results['failed']}\n👥 Total Sent: {len(users)}"
    ))

def render_body_text(text):
    if not text: return str(text)
    parts = re.split(r'(<tg-emoji.*?</tg-emoji>)', str(text))
    for i in range(len(parts)):
        if not parts[i].startswith('<tg-emoji'):
            for normal_emj, prem_id in GLOBAL_BODY_EMOJIS.items():
                if normal_emj in parts[i]:
                    parts[i] = parts[i].replace(normal_emj, f'<tg-emoji emoji-id="{prem_id}">{normal_emj}</tg-emoji>')
    return "".join(parts)

def extract_premium_html(msg):
    text = msg.get("text", msg.get("caption", ""))
    entities = msg.get("entities", msg.get("caption_entities", []))
    if not entities: return text
    try:
        b_text = text.encode('utf-16-le')
        c_entities = [e for e in entities if e.get("type") == "custom_emoji"]
        c_entities.sort(key=lambda x: x["offset"], reverse=True)
        for ent in c_entities:
            offset = ent["offset"] * 2
            length = ent["length"] * 2
            eid = ent["custom_emoji_id"]
            emoji_char = b_text[offset:offset+length].decode('utf-16-le')
            html_tag = f'<tg-emoji emoji-id="{eid}">{emoji_char}</tg-emoji>'
            replacement = html_tag.encode('utf-16-le')
            b_text = b_text[:offset] + replacement + b_text[offset+length:]
        return b_text.decode('utf-16-le')
    except Exception as e:
        return text 

def _normalize_number_digits(num):
    """Strip everything except digits, then drop a leading international-dial
    prefix ('00') so numbers like '00447700900000', '(44) 7700-900000' or
    '+44 7700 900000' all normalize to the same digit string for matching."""
    digits = re.sub(r"\D", "", str(num or ""))
    if digits.startswith("00") and len(digits) > 2:
        digits = digits[2:]
    return digits

def get_flag_info_from_num(num):
    clean = _normalize_number_digits(num)
    flags_db = bot_settings.get("premium_flags", {})
    sorted_codes = sorted(flags_db.keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            data = flags_db[code]
            return data["char"], data.get("iso", "XX"), data.get("id")
    return "🌍", "XX", None

def get_flag_and_code(num):
    char, iso, _ = get_flag_info_from_num(num)
    return char, iso

def _get_phone_prefix(num):
    """Return the phone-country-prefix code (e.g. '880') that matches num, or '' if unknown."""
    clean = _normalize_number_digits(num)
    flags_db = bot_settings.get("premium_flags", {})
    sorted_codes = sorted(flags_db.keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            return code
    return ""

def get_flag_info_html(num_or_iso):
    if len(num_or_iso) == 2:
        for code, data in bot_settings.get("premium_flags", {}).items():
            if data.get("iso") == num_or_iso:
                eid = data.get("id")
                char = data.get("char")
                if eid: return f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
                return char
        return "🌍"
        
    char, _, eid = get_flag_info_from_num(num_or_iso)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
    return char

def generate_emoji_txt(mode):
    if mode == "flags":
        flags_db = bot_settings.get("premium_flags", {})
        if not flags_db:
            return None
        lines = []
        for code, data in flags_db.items():
            char = data.get("char", "")
            iso = data.get("iso", "XX")
            name = data.get("name", "")
            eid = data.get("id", "")
            json_part = json.dumps({"emoji": char, "id": eid}, ensure_ascii=False)
            lines.append(f"{name} ({code}) ({iso}) {char} {json_part}")
        return "\n".join(lines)
    else:
        apps_db = bot_settings.get("premium_apps", {})
        if not apps_db:
            return None
        lines = []
        for key, data in apps_db.items():
            char = data.get("char", "")
            name = data.get("name", key)
            eid = data.get("id", "")
            json_part = json.dumps({"emoji": char, "id": eid}, ensure_ascii=False)
            lines.append(f"{name} {char} {json_part}")
        return "\n".join(lines)

def mask_number(num):
    clean = num.replace("+", "").replace(" ", "")
    if len(clean) > 7:
        return f"+{clean[:4]}••{clean[-3:]}"
    elif len(clean) > 4:
        return f"+{clean[:2]}••{clean[-2:]}"
    return f"+{clean}"

# ==========================================
# 🌟 ADVANCED SERVICE & LANGUAGE DETECTION
# ==========================================

SERVICE_SMS_KEYWORDS = {
    # 🟢 Social Media & Chat
    "whatsapp":      ["whatsapp", "wa.me", "whatsapp business", "wa code", "واتساب", "واتساپ", "واٹس ایپ", "व्हाट्सएप", "వాట్సాప్", "왓츠앱", "whatsapp验证码", "וואטסאפ"],
    "facebook":      ["facebook", "fb", "fbook", "fb code", "facebook code", "facebook verification", "facebook account", "فيسبوك", "فيس بوك", "فیسبوک"],
    "instagram":     ["instagram", "insta", "ig code", "instagram code", "instagram confirmation", "انستغرام", "انستقرام", "اینستاگرام"],
    "telegram":      ["telegram", "tg", "tele", "telegram code", "tg code", "t.me", "تيليجرام", "تليجرام", "تلگرام"],
    "tiktok":        ["tiktok", "tik tok", "tikvideo", "tiktok code", "تيك توك", "تیک توک"],
    "snapchat":      ["snapchat", "snap code", "سناب شات", "سناپ چت"],
    "twitter":       ["twitter", "x.com", "twitter code", "تويتر", "توییتر"],
    "discord":       ["discord", "discord code", "ديسكورد"],
    "viber":         ["viber", "viber code", "فايبر", "وایبر"],
    "line":          ["line app", "line code", "line verification", "لاين"],
    "wechat":        ["wechat", "we chat", "wechat code", "微信", "وي تشات"],
    "signal":        ["signal app", "signal code", "سيجنال"],
    "linkedin":      ["linkedin", "linked in", "linkedin code", "لينكد إن"],
    "imo":           ["imo", "imo code", "imo verification", "ايمو"],
    "kakaotalk":     ["kakao", "kakaotalk", "kakao code", "كاكاو"],
    "qq":            ["tencent qq", "qq验证码"],
    "vk":            ["vkontakte", "vk code", "vk verification"],
    "messenger":     ["messenger", "fb messenger", "facebook messenger"],
    "meta":          ["meta code", "meta verification", "meta account", "meta platforms"],
    "threads":       ["threads", "threads code", "threads app", "threads verification"],
    "rednote":       ["rednote", "xiaohongshu", "red note", "小红书"],
    "reddit":        ["reddit", "redd.it", "reddit code", "reddit verification"],
    "skype":         ["skype", "skype code", "skype verification", "سكايب"],
    "zoom":          ["zoom", "zoom code", "zoom meeting", "zoom verification"],
    "pinterest":     ["pinterest", "pinterest code", "pinterest verification"],
    "twitch":        ["twitch", "twitch code", "twitch verification"],
    "likee":         ["likee", "likee code", "likee verification"],
    "zalo":          ["zalo", "zalo code", "zalo verification"],
    "kik":           ["kik messenger", "kik code"],
    "tumblr":        ["tumblr", "tumblr code"],
    "clubhouse":     ["clubhouse", "clubhouse code"],
    "bigo":          ["bigo", "bigo live", "bigo code"],
    "kwai":          ["kwai", "kwai code"],
    "hike":          ["hike messenger", "hike code"],

    # 🔵 Tech & Mail
    "teams":         ["microsoft teams", "ms teams", "teams code", "teams verification"],
    "gmail":         ["gmail", "google mail", "gmail code", "gmail verification"],
    "googledrive":   ["google drive", "googledrive", "gdrive", "drive.google"],
    "grokai":        ["grok", "grok ai", "xai", "grok code"],
    "github":        ["github", "git hub", "github code", "gh code"],
    "canva":         ["canva", "canva code", "canva verification"],
    "chatgpt":       ["chatgpt", "chat gpt", "openai", "chatgpt code", "openai code"],
    "google":        ["google account", "google voice", "جوجل", "غوغل"],
    "microsoft":     ["microsoft", "outlook", "live.com", "hotmail", "msn"],
    "apple":         ["apple", "icloud", "itunes", "apple id", "apple account"],
    "yahoo":         ["yahoo", "yahoo code", "ymail", "yahoo mail"],
    "protonmail":    ["proton", "protonmail", "proton mail"],
    "dropbox":       ["dropbox", "dropbox code"],
    "slack":         ["slack", "slack code", "slack verification"],
    "notion":        ["notion", "notion code"],
    "adobe":         ["adobe", "adobe id", "adobe code"],
    "cloudflare":    ["cloudflare", "cloudflare code"],
    "shopify":       ["shopify", "shopify code"],
    "netflix":       ["netflix", "netflix code", "netflix verification"],
    "spotify":       ["spotify", "spotify code", "spotify verification"],
    "youtube":       ["youtube", "youtube code", "youtube premium"],
    "disneyplus":    ["disney", "disney+", "disneyplus", "disney plus"],
    "hbo":           ["hbo", "hbo max", "hbo code"],
    "hulu":          ["hulu", "hulu code"],
    "amazonprime":   ["prime video", "amazon prime", "primevideo"],
    "deezer":        ["deezer", "deezer code"],
    "soundcloud":    ["soundcloud", "sound cloud"],

    # 💰 Crypto & Trading
    "binance":       ["binance", "bnb", "binance code", "binance verification"],
    "coinbase":      ["coinbase", "coinbase code"],
    "okx":           ["okx", "okex", "okx code"],
    "kucoin":        ["kucoin", "kucoin code"],
    "bybit":         ["bybit", "bybit code"],
    "huobi":         ["huobi", "htx", "huobi code"],
    "mexc":          ["mexc", "mexc code"],
    "trustwallet":   ["trust wallet", "trustwallet"],
    "kraken":        ["kraken", "kraken code"],
    "gateio":        ["gate.io", "gateio", "gate code"],
    "bitfinex":      ["bitfinex", "bitfinex code"],
    "crypto":        ["crypto.com", "crypto code", "crypto verification"],
    "metamask":      ["metamask", "meta mask", "metamask code"],
    "bitget":        ["bitget", "bitget code"],
    "pionex":        ["pionex", "pionex code"],
    "phemex":        ["phemex", "phemex code"],
    "bitmex":        ["bitmex", "bitmex code"],
    "etoro":         ["etoro", "etoro code"],

    # 💳 Finance & Wallets
    "bkash":         ["bkash", "b-kash", "bkash code", "bkash verification"],
    "nagad":         ["nagad", "nagad code", "nagad verification"],
    "rocket":        ["dutch bangla", "dutch-bangla"],
    "upay":          ["upay", "upay code"],
    "paypal":        ["paypal", "pay pal", "paypal code", "paypal verification"],
    "paytm":         ["paytm", "paytm code"],
    "cashapp":       ["cash app", "cashapp", "cash app code"],
    "wise":          ["wise", "transferwise", "wise transfer"],
    "mastercard":    ["mastercard", "master card", "mastercard code"],
    "tether":        ["tether", "usdt", "tether code"],
    "bolt":          ["bolt food", "bolt ride", "bolt driver", "bolt verification"],
    "gpay":          ["google pay", "gpay", "g pay", "google payment"],
    "applepay":      ["apple pay", "applepay"],
    "stripe":        ["stripe", "stripe code"],
    "skrill":        ["skrill", "skrill code"],
    "neteller":      ["neteller", "neteller code"],
    "revolut":       ["revolut", "revolut code"],
    "monzo":         ["monzo", "monzo code"],
    "chime":         ["chime", "chime code"],
    "zelle":         ["zelle", "zelle code"],
    "venmo":         ["venmo", "venmo code"],
    "payoneer":      ["payoneer", "payoneer code"],
    "momo":          ["mtn momo", "momo code"],
    "mpesa":         ["m-pesa", "mpesa", "safaricom"],
    "dana":          ["dana", "dana code", "dana verification"],
    "ovo":           ["ovo", "ovo code", "ovo verification"],
    "gopay":         ["gopay", "go-pay", "gojek pay"],
    "grab":          ["grabpay", "grab code"],
    "truemoney":     ["truemoney", "true money", "truewallet"],
    "alipay":        ["alipay", "ali pay", "alipay code", "支付宝"],
    "jazzcash":      ["jazzcash", "jazz cash", "jazzcash code"],
    "easypaisa":     ["easypaisa", "easy paisa", "easypaisa code"],
    "sadapay":       ["sadapay", "sada pay"],
    "nayapay":       ["nayapay", "naya pay"],
    "interac":       ["interac", "interac code"],
    "pix":           ["pix code", "pix verification"],
    "hsbc":          ["hsbc", "hsbc bank", "hsbc code", "hsbc verification"],

    # 🛒 E-commerce & Delivery
    "amazon":        ["amazon", "amzn", "amazon code", "amazon verification"],
    "ebay":          ["ebay", "ebay code"],
    "aliexpress":    ["aliexpress", "ali express", "aliexpress code"],
    "alibaba":       ["alibaba", "alibaba code"],
    "daraz":         ["daraz", "daraz code", "daraz verification"],
    "foodpanda":     ["foodpanda", "food panda"],
    "uber":          ["uber", "uber code", "uber verification", "uber eats"],
    "pathao":        ["pathao", "pathao ride"],
    "shein":         ["shein", "shein code", "shein verification"],
    "lazada":        ["lazada", "lazada code"],
    "shopee":        ["shopee", "shopee code", "shopee verification"],
    "tokopedia":     ["tokopedia", "tokopedia code"],
    "flipkart":      ["flipkart", "flipkart code"],
    "meesho":        ["meesho", "meesho code"],
    "noon":          ["noon code", "noon verification"],
    "temu":          ["temu", "temu code", "temu verification"],
    "olx":           ["olx", "olx code", "olx verification"],
    "careem":        ["careem", "careem code", "careem verification"],
    "zomato":        ["zomato", "zomato code"],
    "swiggy":        ["swiggy", "swiggy code"],
    "doordash":      ["doordash", "door dash"],
    "lyft":          ["lyft", "lyft code"],
    "instacart":     ["instacart", "instacart code"],
    "gojek":         ["gojek", "go-jek"],
    "rappi":         ["rappi", "rappi code"],

    # 🎮 Gaming
    "steam":         ["steam", "steam guard", "steam code"],
    "epicgames":     ["epic games", "epicgames", "epic code"],
    "roblox":        ["roblox", "roblox code"],
    "riotgames":     ["riot games", "valorant", "league of legends"],
    "garena":        ["garena", "free fire", "freefire"],
    "playstation":   ["playstation", "psn", "ps4", "ps5", "playstation code"],
    "xbox":          ["xbox", "xbox live", "xbox code", "xbox verification"],
    "nintendo":      ["nintendo", "nintendo code", "nintendo switch"],
    "pubg":          ["pubg", "pubg mobile", "battlegrounds"],
    "mobilelegends": ["mobile legends", "mobilelegends", "mlbb"],
    "codm":          ["call of duty", "codm", "cod mobile"],
    "apex":          ["apex legends", "apex code"],

    # 🎲 Betting & Casino
    "1xbet":         ["1xbet", "1x bet", "1xbet code"],
    "melbet":        ["melbet", "melbet code"],
    "linebet":       ["linebet", "linebet code"],
    "bet365":        ["bet365", "bet 365"],
    "megapari":      ["megapari", "megapari code"],
    "betwinner":     ["betwinner", "bet winner"],
    "mostbet":       ["mostbet", "most bet"],
    "pinup":         ["pin-up bet", "pinup bet", "pin up casino"],
    "parimatch":     ["parimatch", "pari match"],
    "betway":        ["betway", "betway code"],
    "draftkings":    ["draftkings", "draft kings"],
    "fanduel":       ["fanduel", "fan duel"],

    # ❤️ Dating
    "tinder":        ["tinder", "tinder code"],
    "bumble":        ["bumble", "bumble code"],
    "badoo":         ["badoo", "badoo code"],
    "hinge":         ["hinge", "hinge code"],
    "okcupid":       ["okcupid", "ok cupid"],
    "grindr":        ["grindr", "grindr code"],

    # 🚗 Ride & Transport
    "indriver":      ["indriver", "indrive", "in driver"],
    "yandex":        ["yandex", "yandex go", "yandex taxi"],
    "ola":           ["ola cab", "ola code"],
}


def _country_code_matches(c, iso, name):
    """Match a stored country code/name (e.g. voltx country key) against a flag
    entry's iso/name. Always requires an EXACT match (after normalizing case
    and separators) — substring matching is unsafe for country names because
    many real country names contain another real country name as a substring,
    e.g. 'GUINEA' is inside both 'EQUATORIAL GUINEA' and 'GUINEA-BISSAU',
    'NIGER' is inside 'NIGERIA', 'SUDAN' is inside 'SOUTH SUDAN', 'KOREA' is
    inside both 'NORTH KOREA' and 'SOUTH KOREA', and short ISO codes like 'SL'
    are literally contained inside unrelated words like 'ISLANDS'. Any of
    these previously caused the wrong flag/country to be shown."""
    c_up = re.sub(r"[\s\-_]+", " ", str(c).upper().strip())
    if not c_up:
        return False
    name_up = re.sub(r"[\s\-_]+", " ", str(name).upper().strip())
    iso_up = str(iso).upper().strip()
    return c_up == iso_up or c_up == name_up

def _kw_matches(kw, text_lower):
    """Match keyword against lowercase text. Short keywords (≤3 chars) require word boundaries
    to prevent false positives like 'wa' matching 'was', 'want', 'swap' etc."""
    if len(kw) <= 3:
        return bool(re.search(r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9])', text_lower))
    return kw in text_lower

def detect_service(text):
    text_lower = str(text).lower()
    for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
        for kw in keywords:
            if _kw_matches(kw, text_lower):
                return service_key.upper()
    return None

def _e(name, char, eid):
    return (name, f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>')

def _eu(name, char):
    """Unknown/generic service emoji using the default unknown emoji ID."""
    return name, f'<tg-emoji emoji-id="5253742260054409879">{char}</tg-emoji>'

_GENERIC_EMOJI_ID = "5253742260054409879"

def _format_svc(app_full_name: str, prem_app_html: str) -> str:
    """Return the correct service display string.
    If the service has a real specific premium emoji ID → show the emoji AND
    the service name next to it so users see both the icon and the label.
    If it uses the generic placeholder ID or has no tg-emoji tag at all → the
    service is "unknown", so show the bold service name instead of an emoji.
    """
    if ('<tg-emoji emoji-id="' in prem_app_html
            and _GENERIC_EMOJI_ID not in prem_app_html):
        return f"{prem_app_html} <b>{app_full_name}</b>"
    return f"<b>{app_full_name}</b>"

def _normalize_svc_name(name: str) -> str:
    """Normalize a service name for loose matching.
    Strips spaces, underscores, and hyphens, then uppercases.
    e.g. "TIK TOK" → "TIKTOK", "HSBC_UK" → "HSBCUK"
    """
    return re.sub(r'[\s_\-]+', '', name).upper()

def _svc_name_matches(service_key: str, app_key: str) -> bool:
    """Return True if service_key and app_key refer to the same service.
    Tries both raw substring matching AND normalized (space-stripped) matching
    so names like 'TIK TOK' match the 'TIKTOK' key, and 'HSBC UK' matches 'HSBC'.
    """
    su = service_key.upper()
    ak = app_key.upper()
    if su == ak or su in ak or ak in su:
        return True
    sn = _normalize_svc_name(service_key)
    an = _normalize_svc_name(app_key)
    return sn == an or sn in an or an in sn

def _get_svc_icon_info(service_key: str) -> tuple:
    """Return (emoji_id, emoji_char) for a service.

    emoji_id  — custom-emoji ID to use as icon_custom_emoji_id (any pack).
                None only if the service has the generic placeholder or no match.
    emoji_char — plain Unicode fallback character (e.g. '📞'), or '' if unknown.

    Matching is done with _svc_name_matches() so names with spaces/underscores
    (e.g. 'TIK TOK', 'HSBC UK', 'MARI BANK') correctly find their premium_apps
    entry regardless of whether the key uses spaces or not.
    """
    # 1. Check admin-configured premium_apps DB first (highest priority)
    apps_db = bot_settings.get("premium_apps", {})
    for app_key, app_data in apps_db.items():
        if _svc_name_matches(service_key, app_key):
            eid = app_data.get("id", "")
            char = app_data.get("char", "")
            if eid and eid != _GENERIC_EMOJI_ID:
                return eid, char
            # Found the service but only has generic/no emoji ID — return char only
            return None, char

    # 2. Fall back to built-in _DEFAULT_SERVICE_EMOJIS
    s_upper = service_key.upper()
    entry = _DEFAULT_SERVICE_EMOJIS.get(s_upper)
    if not entry:
        # Try normalized lookup in case the built-in key differs slightly
        s_norm = _normalize_svc_name(service_key)
        for key, val in _DEFAULT_SERVICE_EMOJIS.items():
            if _normalize_svc_name(key) == s_norm:
                entry = val
                break
    if entry:
        _, html_str = entry
        m_id = re.search(r'emoji-id="(\d+)"', html_str)
        m_ch = re.search(r'>(.*?)</tg-emoji>', html_str)
        char = m_ch.group(1) if m_ch else ""
        if m_id:
            eid = m_id.group(1)
            if eid != _GENERIC_EMOJI_ID:
                return eid, char
        return None, char

    return None, ""

def _get_svc_icon_id(service_key: str) -> str | None:
    """Return the custom-emoji ID for a service button icon (backwards compat).
    Use _get_svc_icon_info() when you also need the fallback char.
    """
    eid, _ = _get_svc_icon_info(service_key)
    return eid

def _svc_btn(service_key: str, callback_data: str, style: str = "primary") -> dict:
    """Build an inline keyboard button for a service.
    Uses icon_custom_emoji_id when a real emoji ID is found (any pack).
    Falls back to prepending the plain Unicode char to the button text when no
    compatible icon ID exists, so users always see *some* emoji for the service.
    """
    icon_id, icon_char = _get_svc_icon_info(service_key)
    if icon_id:
        return {"text": service_key, "icon_custom_emoji_id": icon_id,
                "callback_data": callback_data, "style": style}
    elif icon_char:
        return {"text": f"{icon_char} {service_key}", "callback_data": callback_data, "style": style}
    else:
        return {"text": service_key, "callback_data": callback_data, "style": style}

_DEFAULT_SERVICE_EMOJIS = {
    # Social & Chat
    "WHATSAPP":      _e("WhatsApp",        "💬", "5334998226636390258"),
    "FACEBOOK":      _e("Facebook",        "📘", "5323261730283863478"),
    "INSTAGRAM":     _e("Instagram",       "📸", "5319160079465857105"),
    "MESSENGER":     _e("Messenger",       "💬", "5323687726615119535"),
    "META":          _e("Meta",            "🔵", "5321447183910716259"),
    "TELEGRAM":      _e("Telegram",        "✈️", "5330237710655306682"),
    "TIKTOK":        _e("TikTok",          "🎵", "5327982530702359565"),
    "SNAPCHAT":      _e("Snapchat",        "👻", "5330248916224983855"),
    "TWITTER":       _e("Twitter/X",       "🐦", "5330337435500951363"),
    "DISCORD":       _e("Discord",         "🎮", "5325612636467903082"),
    "SIGNAL":        _e("Signal",          "🔵", "5328050550099427291"),
    "THREADS":       _e("Threads",         "🔗", "5334592721594105691"),
    "REDNOTE":       _e("RedNote",         "📕", "5334707727933390944"),
    "VK":            _e("VK",              "💙", "5334853932915114338"),
    "WECHAT":        _e("WeChat",          "🟢", "5332524123610430820"),
    "REDDIT":        _e("Reddit",          "🔴", "5330321861949539755"),
    "VIBER":         _eu("Viber",          "📳"),
    "LINE":          _eu("Line",           "💚"),
    "LINKEDIN":      _eu("LinkedIn",       "💼"),
    "IMO":           _e("Imo",              "📞", "5226479577185949100"),
    "KAKAOTALK":     _eu("KakaoTalk",      "💛"),
    "SKYPE":         _eu("Skype",          "🔵"),
    "ZOOM":          _eu("Zoom",           "🎦"),
    "PINTEREST":     _eu("Pinterest",      "📌"),
    "TWITCH":        _eu("Twitch",         "🟣"),
    "LIKEE":         _eu("Likee",          "🎬"),
    "ZALO":          _eu("Zalo",           "🔵"),
    "KIK":           _eu("Kik",            "🟢"),
    "TUMBLR":        _eu("Tumblr",         "🔵"),
    "CLUBHOUSE":     _eu("Clubhouse",      "🟢"),
    "BIGO":          _eu("Bigo Live",      "🎥"),
    "KWAI":          _eu("Kwai",           "🎵"),
    "QQ":            _eu("QQ",             "🐧"),
    # Tech & Mail
    "GMAIL":         _e("Gmail",           "📧", "5303416490295304868"),
    "GOOGLEDRIVE":   _e("Google Drive",    "📁", "5303051181851943323"),
    "GROKAI":        _e("Grok AI",         "🤖", "5454065032298009119"),
    "GITHUB":        _e("GitHub",          "🐙", "5303382121967001310"),
    "CANVA":         _e("Canva",           "🎨", "5429229538527690282"),
    "CHATGPT":       _e("ChatGPT",         "🤖", "5359726582447487916"),
    "MICROSOFT":     _e("Microsoft",       "🪟", "5370857634440170316"),
    "APPLE":         _e("Apple",           "🍎", "5334955749409834455"),
    "TEAMS":         _e("Teams",           "🟦", "5453866707888152017"),
    "GOOGLE":        _eu("Google",         "🔍"),
    "YAHOO":         _eu("Yahoo",          "🟣"),
    "PROTONMAIL":    _eu("ProtonMail",     "🟣"),
    "SLACK":         _eu("Slack",          "💬"),
    "NOTION":        _eu("Notion",         "📝"),
    "ADOBE":         _eu("Adobe",          "🔴"),
    "DROPBOX":       _eu("Dropbox",        "🔵"),
    # Entertainment
    "NETFLIX":       _e("Netflix",         "🎬", "5318911503938634641"),
    "SPOTIFY":       _e("Spotify",         "🎧", "5346074681004801565"),
    "YOUTUBE":       _eu("YouTube",        "▶️"),
    "DISNEYPLUS":    _eu("Disney+",        "🏰"),
    "HBO":           _eu("HBO Max",        "🎬"),
    "HULU":          _eu("Hulu",           "🟢"),
    "AMAZONPRIME":   _eu("Prime Video",    "📦"),
    "DEEZER":        _eu("Deezer",         "🎵"),
    "SOUNDCLOUD":    _eu("SoundCloud",     "🔶"),
    # Finance
    "PAYPAL":        _e("PayPal",          "💳", "5364111181415996352"),
    "MASTERCARD":    _e("Mastercard",      "💳", "5364036341610858181"),
    "TETHER":        _e("Tether",          "💵", "5359437015752401733"),
    "PAYTM":         _eu("Paytm",          "💰"),
    "CASHAPP":       _eu("Cash App",       "💵"),
    "WISE":          _eu("Wise",           "💸"),
    "BKASH":         _eu("bKash",          "🩷"),
    "NAGAD":         _eu("Nagad",          "🟠"),
    "ROCKET":        _eu("Rocket",         "🚀"),
    "UPAY":          _eu("Upay",           "💳"),
    "GPAY":          _eu("Google Pay",     "💳"),
    "APPLEPAY":      _eu("Apple Pay",      "💳"),
    "STRIPE":        _eu("Stripe",         "🔵"),
    "SKRILL":        _eu("Skrill",         "🟣"),
    "NETELLER":      _eu("Neteller",       "🔵"),
    "REVOLUT":       _eu("Revolut",        "🔵"),
    "MONZO":         _eu("Monzo",          "🔥"),
    "CHIME":         _eu("Chime",          "🟢"),
    "ZELLE":         _eu("Zelle",          "🔵"),
    "VENMO":         _eu("Venmo",          "🔵"),
    "PAYONEER":      _eu("Payoneer",       "🟠"),
    "MOMO":          _eu("MoMo",           "🟣"),
    "MPESA":         _eu("M-Pesa",         "🟢"),
    "DANA":          _eu("Dana",           "🔵"),
    "OVO":           _eu("OVO",            "🟣"),
    "GOPAY":         _eu("GoPay",          "🟢"),
    "GRAB":          _eu("GrabPay",        "🟢"),
    "TRUEMONEY":     _eu("TrueMoney",      "🔵"),
    "ALIPAY":        _eu("Alipay",         "💙"),
    "JAZZCASH":      _eu("JazzCash",       "🔴"),
    "EASYPAISA":     _eu("EasyPaisa",      "🟢"),
    "SADAPAY":       _eu("SadaPay",        "🟣"),
    "NAYAPAY":       _eu("NayaPay",        "🔵"),
    "INTERAC":       _eu("Interac",        "🔴"),
    "PIX":           _eu("Pix",            "🔵"),
    "HSBC":          _e("HSBC",            "🏦", "5161439019111810521"),
    # Crypto
    "BINANCE":       _e("Binance",         "🪙", "5888561507557447441"),
    "COINBASE":      _eu("Coinbase",       "🔵"),
    "OKX":           _eu("OKX",            "⬛"),
    "BYBIT":         _eu("Bybit",          "🟠"),
    "KUCOIN":        _eu("KuCoin",         "🟢"),
    "HUOBI":         _eu("Huobi",          "🔵"),
    "MEXC":          _eu("MEXC",           "🔵"),
    "TRUSTWALLET":   _eu("Trust Wallet",   "🔵"),
    "KRAKEN":        _eu("Kraken",         "🟣"),
    "GATEIO":        _eu("Gate.io",        "🔵"),
    "BITFINEX":      _eu("Bitfinex",       "🟢"),
    "CRYPTO":        _eu("Crypto.com",     "🔵"),
    "METAMASK":      _eu("MetaMask",       "🦊"),
    "BITGET":        _eu("Bitget",         "🔵"),
    "ETORO":         _eu("eToro",          "🟢"),
    # E-commerce & Delivery
    "UBER":          _e("Uber",            "🚗", "5298715455316303708"),
    "BOLT":          _e("Bolt",            "⚡", "5346188613602263703"),
    "AMAZON":        _eu("Amazon",         "📦"),
    "EBAY":          _eu("eBay",           "🛒"),
    "ALIEXPRESS":    _eu("AliExpress",     "🛍️"),
    "ALIBABA":       _eu("Alibaba",        "🛒"),
    "DARAZ":         _eu("Daraz",          "🛍️"),
    "FOODPANDA":     _eu("foodpanda",      "🐼"),
    "PATHAO":        _eu("Pathao",         "🚗"),
    "SHEIN":         _eu("Shein",          "👗"),
    "LAZADA":        _eu("Lazada",         "🛒"),
    "SHOPEE":        _eu("Shopee",         "🛒"),
    "TOKOPEDIA":     _eu("Tokopedia",      "🟢"),
    "FLIPKART":      _eu("Flipkart",       "🛒"),
    "MEESHO":        _eu("Meesho",         "🛍️"),
    "NOON":          _eu("Noon",           "🛒"),
    "TEMU":          _eu("Temu",           "🛒"),
    "OLX":           _eu("OLX",            "🟢"),
    "CAREEM":        _eu("Careem",         "🚗"),
    "ZOMATO":        _eu("Zomato",         "🔴"),
    "SWIGGY":        _eu("Swiggy",         "🟠"),
    "DOORDASH":      _eu("DoorDash",       "🔴"),
    "LYFT":          _eu("Lyft",           "🩷"),
    "INSTACART":     _eu("Instacart",      "🟢"),
    "GOJEK":         _eu("GoJek",          "🟢"),
    "RAPPI":         _eu("Rappi",          "🟡"),
    # Gaming
    "STEAM":         _e("Steam",           "🎮", "5373144051690258848"),
    "ROBLOX":        _eu("Roblox",         "🎲"),
    "GARENA":        _eu("Garena",         "🔥"),
    "PLAYSTATION":   _eu("PlayStation",    "🎮"),
    "EPICGAMES":     _eu("Epic Games",     "🎮"),
    "RIOTGAMES":     _eu("Riot Games",     "⚔️"),
    "XBOX":          _eu("Xbox",           "🟢"),
    "NINTENDO":      _eu("Nintendo",       "🔴"),
    "PUBG":          _eu("PUBG",           "🎯"),
    "MOBILELEGENDS": _eu("Mobile Legends", "⚔️"),
    "CODM":          _eu("Call of Duty",   "🎮"),
    "APEX":          _eu("Apex Legends",   "🎯"),
    # Betting
    "1XBET":         _eu("1xBet",          "🎲"),
    "MELBET":        _eu("Melbet",         "🎲"),
    "LINEBET":       _eu("LineBet",        "🎲"),
    "BET365":        _eu("Bet365",         "🎲"),
    "MEGAPARI":      _eu("Megapari",       "🎲"),
    "BETWINNER":     _eu("BetWinner",      "🎲"),
    "MOSTBET":       _eu("Mostbet",        "🎲"),
    "PINUP":         _eu("Pin-Up",         "🎲"),
    "PARIMATCH":     _eu("Parimatch",      "🎲"),
    "BETWAY":        _eu("Betway",         "🎲"),
    "DRAFTKINGS":    _eu("DraftKings",     "🏈"),
    "FANDUEL":       _eu("FanDuel",        "🏈"),
    # Dating
    "TINDER":        _eu("Tinder",         "🔥"),
    "BUMBLE":        _eu("Bumble",         "🐝"),
    "BADOO":         _eu("Badoo",          "❤️"),
    "HINGE":         _eu("Hinge",          "❤️"),
    "OKCUPID":       _eu("OkCupid",        "❤️"),
    "GRINDR":        _eu("Grindr",         "🟡"),
    # Transport
    "INDRIVER":      _eu("inDriver",       "🚗"),
    "YANDEX":        _eu("Yandex Go",      "🚖"),
    "OLA":           _eu("Ola",            "🚖"),
}


def get_service_info_html(service_text, msg_text=""):
    s = str(service_text).upper().strip()
    m = str(msg_text).lower().strip()
    apps = bot_settings.get("premium_apps", {})

    # Is service_text purely numeric? (e.g. CLI="372828") → not a service name
    _is_numeric = bool(re.match(r'^\+?[\d\s\-]+$', s.strip())) if s else True

    detected_service = s

    if s and not _is_numeric:
        # Priority 1: CLI/service_text is a real name — try to match against known services
        cli_mapped = None
        s_lower = s.lower()
        for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
            for kw in keywords:
                if _kw_matches(kw, s_lower):
                    cli_mapped = service_key.upper()
                    break
            if cli_mapped:
                break
        if cli_mapped:
            detected_service = cli_mapped
        else:
            # CLI name not found in keywords (e.g. "Panel 1", unknown panel name)
            # → Priority 2: try message body
            if m:
                for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
                    for kw in keywords:
                        if _kw_matches(kw, m):
                            detected_service = service_key.upper()
                            break
                    if detected_service != s:
                        break
    else:
        # CLI is numeric or empty → Priority 2: detect from message body
        if m:
            for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
                for kw in keywords:
                    if _kw_matches(kw, m):
                        detected_service = service_key.upper()
                        break
                if detected_service != s:
                    break

    clean_s = re.sub(r'[^\w\s]', '', detected_service).strip()

    # 1. Check admin-configured premium_apps first
    for app_name, data in apps.items():
        if app_name == detected_service or app_name == clean_s or app_name in detected_service or detected_service in app_name:
            full_name = data.get("name", app_name.title())
            char = data.get("char", "📱")
            eid = data.get("id")
            if eid: return full_name, f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
            return full_name, char

    # 2. Fall back to built-in emoji map for common services
    if clean_s in _DEFAULT_SERVICE_EMOJIS:
        return _DEFAULT_SERVICE_EMOJIS[clean_s]
    for key, val in _DEFAULT_SERVICE_EMOJIS.items():
        if key in clean_s or clean_s in key:
            return val

    if len(detected_service) > 20:
        return "Message", '<tg-emoji emoji-id="5253742260054409879">💬</tg-emoji>'

    # Empty detected_service means no CLI and no keyword match — show "SMS"
    # instead of a blank name (callers now pass "" instead of panel_name).
    if not detected_service.strip():
        return "SMS", '<tg-emoji emoji-id="5253742260054409879">📱</tg-emoji>'

    return detected_service.title(), '<tg-emoji emoji-id="5253742260054409879">📱</tg-emoji>'

def detect_language(text):
    if not text: return "#EN"
    text_str = str(text)


    if any('\u0600' <= c <= '\u06ff' for c in text_str): return "#AR" # Arabic / Persian / Urdu
    if any('\u0980' <= c <= '\u09ff' for c in text_str): return "#BN" # Bengali
    if any('\u0900' <= c <= '\u097f' for c in text_str): return "#HI" # Hindi / Marathi / Nepali
    if any('\u0a00' <= c <= '\u0a7f' for c in text_str): return "#PA" # Punjabi (Gurmukhi)
    if any('\u0a80' <= c <= '\u0aff' for c in text_str): return "#GU" # Gujarati
    if any('\u0b00' <= c <= '\u0b7f' for c in text_str): return "#OR" # Odia
    if any('\u0b80' <= c <= '\u0bff' for c in text_str): return "#TA" # Tamil
    if any('\u0c00' <= c <= '\u0c7f' for c in text_str): return "#TE" # Telugu
    if any('\u0c80' <= c <= '\u0cff' for c in text_str): return "#KN" # Kannada
    if any('\u0d00' <= c <= '\u0d7f' for c in text_str): return "#ML" # Malayalam
    if any('\u0d80' <= c <= '\u0dff' for c in text_str): return "#SI" # Sinhala
    if any('\u0e00' <= c <= '\u0e7f' for c in text_str): return "#TH" # Thai
    if any('\u0e80' <= c <= '\u0eff' for c in text_str): return "#LO" # Lao
    if any('\u0f00' <= c <= '\u0fff' for c in text_str): return "#BO" # Tibetan
    if any('\u1000' <= c <= '\u109f' for c in text_str): return "#MY" # Burmese (Myanmar)
    if any('\u1200' <= c <= '\u137f' for c in text_str): return "#AM" # Amharic (Ethiopic)
    if any('\u1780' <= c <= '\u17ff' for c in text_str): return "#KM" # Khmer
    if any('\u10a0' <= c <= '\u10ff' for c in text_str): return "#KA" # Georgian
    if any('\u0530' <= c <= '\u058f' for c in text_str): return "#HY" # Armenian
    if any('\u0590' <= c <= '\u05ff' for c in text_str): return "#HE" # Hebrew
    if any('\u0370' <= c <= '\u03ff' for c in text_str): return "#EL" # Greek
    if any('\u0400' <= c <= '\u04ff' for c in text_str): return "#RU" # Russian / Ukrainian (Cyrillic)
    if any('\u4e00' <= c <= '\u9fff' for c in text_str): return "#ZH" # Chinese
    if any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text_str): return "#JA" # Japanese
    if any('\uac00' <= c <= '\ud7af' for c in text_str): return "#KO" # Korean


    text_lower = text_str.lower()
    
    # Asian / Pacific
    if any(w in text_lower for w in ["kode verifikasi", "jangan bagikan", "rahasia"]): return "#ID" # Indonesian
    if any(w in text_lower for w in ["kod pengesahan", "jangan kongsi"]): return "#MS" # Malay
    if any(w in text_lower for w in ["mã của bạn", "không chia sẻ", "mã xác minh"]): return "#VN" # Vietnamese
    if any(w in text_lower for w in ["ang iyong code", "huwag ibahagi"]): return "#TL" # Tagalog / Filipino
    
    # European / Americas
    if any(w in text_lower for w in ["código", "tu código", "verificación", "no compartas"]): return "#ES" # Spanish
    if any(w in text_lower for w in ["seu código", "código de verificação", "não compartilhe"]): return "#PT" # Portuguese
    if any(w in text_lower for w in ["code secret", "ne partagez pas", "votre code"]): return "#FR" # French
    if any(w in text_lower for w in ["dein code", "bestätigungscode", "nicht teilen"]): return "#DE" # German
    if any(w in text_lower for w in ["il tuo codice", "codice di verifica", "non condividere"]): return "#IT" # Italian
    if any(w in text_lower for w in ["twój kod", "nie udostępniaj", "kod weryfikacyjny"]): return "#PL" # Polish
    if any(w in text_lower for w in ["doğrulama kodu", "paylaşmayın", "onay kodu"]): return "#TR" # Turkish
    if any(w in text_lower for w in ["jouw code", "verificatiecode", "niet delen"]): return "#NL" # Dutch
    if any(w in text_lower for w in ["din kod", "verifieringskod", "dela inte"]): return "#SV" # Swedish
    if any(w in text_lower for w in ["bekræftelseskode", "del ikke"]): return "#DA" # Danish
    if any(w in text_lower for w in ["bekreftelseskode", "ikke del"]): return "#NO" # Norwegian
    if any(w in text_lower for w in ["vahvistuskoodi", "älä jaa"]): return "#FI" # Finnish
    if any(w in text_lower for w in ["váš kód", "ověřovací kód", "nesdílejte"]): return "#CS" # Czech
    if any(w in text_lower for w in ["overovací kód", "nezdieľajte"]): return "#SK" # Slovak
    if any(w in text_lower for w in ["ellenőrző kód", "ne oszd meg"]): return "#HU" # Hungarian
    if any(w in text_lower for w in ["codul tău", "codul de verificare", "nu partaja"]): return "#RO" # Romanian
    if any(w in text_lower for w in ["kontrolni kod", "kod za potvrdu", "ne delite"]): return "#HR" # Croatian/Serbian
    if any(w in text_lower for w in ["код за потвърждение", "не споделяйте"]): return "#BG" # Bulgarian
    if any(w in text_lower for w in ["ваш код", "код підтвердження"]): return "#UK" # Ukrainian
    
    # African
    if any(w in text_lower for w in ["msimbo wako", "usishiriki"]): return "#SW" # Swahili
    if any(w in text_lower for w in ["verifikasiekode", "moenie deel nie"]): return "#AF" # Afrikaans
    

    return "#EN"

def parse_chat_id(text):
    text = text.strip()
    if text.startswith("-100") or (text.startswith("-") and text[1:].isdigit()):
        return text
    if "t.me/" in text:
        parts = text.split("/")
        username = parts[-1]
        if username: return "@" + username if not username.startswith("@") else username
    if text.startswith("@"):
        return text
    return "@" + text

def is_admin(user_id):
    return user_id in bot_settings["admins"] or user_id == OWNER_ID

def is_country_locked(service: str, country: str) -> bool:
    """Return True if this service+country combination is locked by admin."""
    locked = bot_settings.get("locked_countries", {})
    return country in locked.get(service, [])

def _service_visible_to_users(service: str) -> bool:
    """Return True if this service has at least one unlocked country visible to users."""
    local_cnts = set(b["country"] for b in number_batches.values() if b["service"] == service and b["numbers"])
    voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
    stex_cnts  = set(bot_settings.get("stex_services",  {}).get(service, {}).keys())
    all_cnts = local_cnts.union(voltx_cnts).union(stex_cnts)
    # Service is visible only if at least one country is NOT locked
    return any(not is_country_locked(service, c) for c in all_cnts)

_fj_cache = {}      # {user_id: (result_bool, timestamp)}
_FJ_CACHE_TTL = 120  # seconds — avoid live API call on every button press

def check_force_join(user_id):
    if not bot_settings["fj_on"] or not bot_settings["fj_channels"]: return True
    if is_admin(user_id): return True
    _now = time.time()
    cached = _fj_cache.get(user_id)
    if cached and (_now - cached[1] < _FJ_CACHE_TTL):
        return cached[0]
    for ch in bot_settings["fj_channels"]:
        try:
            res = api_call("getChatMember", {"chat_id": ch, "user_id": user_id})
            if res.get("ok"):
                status = res["result"].get("status", "left")
                if status in ["left", "kicked"]:
                    _fj_cache[user_id] = (False, _now)
                    return False
                # status is "member", "administrator", or "creator" — OK, continue
            else:
                # API returned not-ok for any reason (bot not in channel, chat not
                # found, user not found, network error, etc.).  Previously only a
                # small set of hardcoded keywords triggered a False return; any
                # other error silently fell through and returned True (joined) —
                # so Force Join was invisible when the bot wasn't a member of the
                # channel, or when Telegram returned an unexpected error description.
                # Conservative fix: treat ANY not-ok response as "not verified" →
                # show Force Join so the user can explicitly confirm.
                _fj_cache[user_id] = (False, _now)
                return False
        except Exception:
            # Network / timeout error — can't verify; treat conservatively.
            _fj_cache[user_id] = (False, _now)
            return False
    _fj_cache[user_id] = (True, _now)
    return True

def _get_fj_invite_link(ch):
    ch = str(ch)
    if ch.startswith("@"):
        return f"https://t.me/{ch.lstrip('@')}"
    inv = api_call("exportChatInviteLink", {"chat_id": ch})
    if inv.get("ok"):
        return inv["result"]
    chat_info = api_call("getChat", {"chat_id": ch})
    return chat_info.get("result", {}).get("invite_link", "")

def _get_chat_title(ch):
    """Fetch the title/name of a channel or group from Telegram.
    Prefers username (handle) over title — title can be arbitrary short text.
    For private channels/groups with no username, falls back to title."""
    try:
        ch_info = api_call("getChat", {"chat_id": ch})
        result = ch_info.get("result", {})
        username = result.get("username")   # e.g. "AmirXOtp"
        title = result.get("title")         # e.g. "ه"
        if username:
            return username  # prefer handle — always matches what admin added
        if title:
            return title     # private channel/group — no username, use title
    except:
        pass
    # Safe fallback: strip @ for usernames, keep numeric IDs as-is
    ch_str = str(ch)
    if ch_str.startswith("@"):
        return ch_str[1:]
    return ch_str

def send_force_join_msg(chat_id):
    kb = []
    for ch in bot_settings["fj_channels"]:
        url = _get_fj_invite_link(ch)
        if url and str(url).startswith("http"):
            ch_name = _get_chat_title(ch)
            btn_label = ch_name if ch_name else "Join Channel"
            kb.append([{"text": btn_label, "icon_custom_emoji_id": "5789428375261023681", "url": url, "style": "primary"}])
    kb.append([{"text": "I Joined — Check Now", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "check_fj", "style": "success"}])
    send_message(chat_id, render_body_text(f"{PEM['warn']} <b>Join our channel(s) first to use the bot!</b>\n\n{PEM['link']} Click the button below, join, then press <b>I Joined</b>."), reply_markup={"inline_keyboard": kb})

def is_user_banned(user_id):
    if is_admin(user_id): return False
    if user_id in user_banned_cache and time.time() - user_banned_cache[user_id]['time'] < 60:
        return user_banned_cache[user_id]['banned']
    with db_lock:
        conn = get_db_conn()
        row = conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
    banned = bool(row[0]) if row else False
    user_banned_cache[user_id] = {'banned': banned, 'time': time.time()}
    return banned


# ==========================================
# Captcha Auto Login & Parsing Core
# ==========================================
def extract_otp_code(text):
    clean_text = re.sub(r'[\u200B-\u200D\uFEFF]', '', str(text))

    # 0. Strip date/timestamp patterns FIRST — before ANY digit-pattern
    # matching. Without this, a plain timestamp like "2026-07-13 08:13:13"
    # gets misread by the 2-part/3-part rules below as a multi-segment OTP
    # (e.g. "07-13 08" -> "071308"), because those rules only ran the
    # date-exclusion check for a month-like middle segment (01-12) — a day
    # segment like "13" slipped right past it. Stripping real dates/times
    # up front removes the false-positive at the source, for every branch.
    clean_text = re.sub(r'\d{4}[-/]\d{2}[-/]\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?', ' ', clean_text)
    clean_text = re.sub(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?', ' ', clean_text)
    clean_text = re.sub(r'(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)', ' ', clean_text)

    # 1. Keyword-based — HIGHEST PRIORITY
    # Broad match: keyword + up to 60 non-digit/non-newline chars (lazy) + number.
    # Handles all forms:
    #   "Your code is 04870"            keyword → connector → number
    #   "Votre code est 1759227"         French "est" connector
    #   "Code Snapchat : 121059"         word between keyword and ":"
    #   "OTP: 1234"  "رمز: 9999"         direct separator
    otp_keywords = [
        'your code', 'votre code', 'code secret', 'code',
        'otp', 'pin', 'verification', 'auth',
        'secret', 'رمز', 'كود', 'كد', 'код',
    ]
    keywords_pattern = '|'.join(re.escape(k) for k in otp_keywords)
    keyword_match = re.search(
        rf'(?:{keywords_pattern})\b[^0-9\n]{{0,60}}?([0-9]{{4,10}})(?!\d)',
        clean_text, re.I
    )
    if keyword_match:
        return keyword_match.group(1)

    # Reverse form: "08076 is your code / OTP / account"
    keyword_match_rev = re.search(r'([0-9]{4,10})\s+is\s+(?:your|the)\b', clean_text, re.I)
    if keyword_match_rev:
        return keyword_match_rev.group(1)

    # 2. Multi-part OTPs (e.g. 123-456 or 809-761) — date patterns explicitly excluded
    # 2-part: 123-456 or 536 714
    two_part = re.search(r'(?<!\d)(\d{3})[-\s](\d{3})(?!\d)', clean_text)
    if two_part:
        return two_part.group(1) + two_part.group(2)
    # 3-part: 80-97-61 — skip if middle segment is 01-12 (date month)
    for cand in re.finditer(r'(?<!\d)\d{2}[-\s]\d{2}[-\s]\d{2}(?!\d)', clean_text):
        parts = re.split(r'[-\s]+', cand.group(0))
        try:
            if 1 <= int(parts[1]) <= 12:
                continue
        except (ValueError, IndexError):
            pass
        return cand.group(0).replace('-', '').replace(' ', '')

    # 3. Google OTP
    g_match = re.search(r'G-(\d{6})', clean_text, re.IGNORECASE)
    if g_match: return g_match.group(1)

    # 4. Digit fallback — strip date/time stamps first to avoid extracting year (e.g. "2026")
    clean_fallback = re.sub(r'\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?', '', clean_text)
    clean_fallback = re.sub(r'\d{2}/\d{2}/\d{4}', '', clean_fallback)
    digit_matches = re.findall(r'(?<!\d)\d{4,8}(?!\d)', clean_fallback)
    if digit_matches: return digit_matches[0]

    return None

def parse_panel_response(response_text, p_config=None):
    results = []
    p_type = p_config.get("type", "API Panel") if p_config else "API Panel"
    
    n_col_name = p_config.get("num_col_name", "number").lower() if p_config else "number"
    m_col_name = p_config.get("msg_col_name", "message").lower() if p_config else "message"
    n_idx = int(p_config.get("num_col_idx", 1)) - 1 if p_config and p_config.get("num_col_idx") else 1
    m_idx = int(p_config.get("msg_col_idx", 2)) - 1 if p_config and p_config.get("msg_col_idx") else 2

    _CLI_HDR_WORDS = ["cli", "client", "service", "app", "provider", "application", "sender", "source"]

    if p_type == "Auto Captcha Panel":
        try:
            soup = BeautifulSoup(response_text, 'html.parser')
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                if not rows: continue

                final_n_idx = n_idx
                final_m_idx = m_idx
                final_c_idx = -1  # CLI column index; -1 = not found

                header_cells = rows[0].find_all(['th', 'td'])
                for i, cell in enumerate(header_cells):
                    c_text = cell.get_text(strip=True).lower()
                    if n_col_name in c_text or "number" in c_text or "phone" in c_text or "msisdn" in c_text:
                        final_n_idx = i
                    if m_col_name in c_text or "message" in c_text or "sms" in c_text or "text" in c_text:
                        final_m_idx = i
                    if any(w in c_text for w in _CLI_HDR_WORDS):
                        final_c_idx = i

                for row in rows:
                    cols = row.find_all(['td', 'th'])

                    if all(c.name == 'th' for c in cols): continue
                    
                    if len(cols) > max(final_n_idx, final_m_idx):

                        num_text = cols[final_n_idx].get_text(separator=" ", strip=True)
                        msg_text = cols[final_m_idx].get_text(separator=" ", strip=True)
                        clean_num = re.sub(r'\D', '', num_text)

                        # Extract CLI from dedicated column if detected
                        cli_val = ""
                        if final_c_idx >= 0 and final_c_idx < len(cols):
                            raw_cli = cols[final_c_idx].get_text(strip=True)
                            if raw_cli and not re.match(r'^\+?[\d\s\-]+$', raw_cli):
                                cli_val = raw_cli

                        # If no CLI column, detect service from message body
                        if not cli_val:
                            cli_val = detect_service(msg_text) or ""

                        if clean_num and 5 <= len(clean_num) <= 18:
                            otp = extract_otp_code(msg_text)
                            if otp and len(msg_text) > 4:
                                row_cells2 = [c.get_text(separator=" ", strip=True) for c in cols]
                                results.append({"number": clean_num, "message": msg_text, "otp": otp, "cli": cli_val, "received_ts": _parse_row_timestamp(row_cells2)})
        except Exception as e:
            pass
        finally:
            soup.decompose()  # BUG FIX: free BeautifulSoup tree — prevents memory growth per poll cycle
    else:
        try:
            data = json.loads(response_text)
            temp_results = []
            
            def process_item(item):
                pot_nums_list = []
                pot_msg = None
                pot_msg_is_bare = False
                values = []
                cli_hint = None  # initialised here so it's always defined

                if isinstance(item, dict):
                    lower_keys = {str(k).lower(): v for k, v in item.items()}
                    for k in ["number", "num", "phone", "msisdn", "sender", "to", "destination", "dest", "receiver", "mobile"]:
                        if k in lower_keys:
                            clean_val = re.sub(r'\D', '', str(lower_keys[k]))
                            if 5 <= len(clean_val) <= 18:
                                if clean_val not in pot_nums_list: pot_nums_list.append(clean_val)
                    for k in ["message", "msg", "sms", "content", "text", "body", "sms_text", "otp_message"]:
                        if k in lower_keys:
                            val = str(lower_keys[k])
                            # BUG FIX: was `> 4` which silently dropped valid 4-digit OTP
                            # messages like "1234" or "Your code: 1234" with short text.
                            # Changed to `>= 1` — the OTP extractor (extract_otp_code)
                            # decides whether the string contains a usable OTP; we must
                            # not pre-filter by length here.
                            if len(val) >= 1:
                                pot_msg = val
                                break
                    for k in ["cli", "client", "service", "app", "provider", "application"]:
                        if k in lower_keys and str(lower_keys[k]).strip():
                            cli_hint = str(lower_keys[k]).strip()
                            break
                    values = list(item.values())
                elif isinstance(item, list):
                    values = item
                    # Format 1: [CLI, NUMBER, MESSAGE, DATETIME]
                    # e.g. ["HSBC", "966558961415", "Your one-time code...", "2026-07-13 06:42:52"]
                    # Detect CLI from first element if it looks like a service name
                    if values:
                        v0 = str(values[0]).strip()
                        # Service name: non-empty, ≤40 chars, no pure-digit sequence (4+),
                        # not a phone number (no string of 5+ digits)
                        if (v0 and 1 <= len(v0) <= 40
                                and not re.match(r'^\+?[\d\s\-]+$', v0)
                                and not re.search(r'\d{5,}', v0)):
                            cli_hint = v0


                for v in values:
                    if isinstance(v, (dict, list)) or v is None: continue
                    v_str = str(v).strip()
                    

                    clean_v = re.sub(r'\D', '', v_str)
                    if 7 <= len(clean_v) <= 18 and not re.search(r'[a-zA-Z]', v_str):

                        if not re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', v_str) and not re.search(r'\d{2}:\d{2}:\d{2}', v_str) and "." not in v_str:
                            if clean_v not in pot_nums_list:
                                pot_nums_list.append(clean_v)
                    

                    # A message candidate is either normal text containing an OTP
                    # (len > 4, has non-digit chars) OR a BARE digit-only value that
                    # is itself the OTP (some panels return the raw code with no
                    # surrounding text at all, e.g. "63191"). Bare candidates must be
                    # OTP-length (4-8 digits) — anything 7+ digits could collide with
                    # a phone number, so only accept those if they weren't already
                    # captured as a phone-number candidate above.
                    is_bare_otp = (v_str.isdigit() and 4 <= len(v_str) <= 8
                                   and v_str not in pot_nums_list)
                    if (len(v_str) > 4 and not v_str.isdigit()) or is_bare_otp:
                        if extract_otp_code(v_str):
                            # A bare digit-only field (e.g. a time value with its
                            # colons stripped, like "17:13:13" -> "171313") is
                            # indistinguishable from a real bare OTP by pattern
                            # alone, and used to win here purely on string length.
                            # A real message WITH context (has "code"/keyword,
                            # non-digit chars, etc.) is always more trustworthy
                            # than a bare digit run, so it must never be displaced
                            # by one — only fall back to a bare candidate when no
                            # contextual message was found at all.
                            if pot_msg is None:
                                pot_msg = v_str
                                pot_msg_is_bare = is_bare_otp
                            elif is_bare_otp:
                                pass  # never override an existing candidate with a bare one
                            elif pot_msg_is_bare or len(v_str) > len(pot_msg):
                                pot_msg = v_str
                                pot_msg_is_bare = False
                                

                pot_num = None
                if pot_nums_list:
                    # Try to find a number that is actually assigned to an active
                    # user session.  The old loop was broken — it always did
                    # `matched_user_num = n; break` on the first iteration, making
                    # the session-match attempt a no-op and leaving the
                    # `elif len >= 2: pot_nums_list[1]` branch permanently dead.
                    # That caused panels whose JSON puts the SENDER number first
                    # (e.g. [sender, destination, message, datetime]) to always
                    # deliver the OTP to the sender's number instead of the
                    # user's rented destination number.
                    matched_user_num = None
                    for n in pot_nums_list:
                        n_clean = str(n).replace("+", "").replace(" ", "").replace("-", "").strip()
                        for _uid, _sess in list(user_active_sessions.items()):
                            for _act in _sess.get("nums", []):
                                _act_c = str(_act).replace("+", "").replace(" ", "").replace("-", "").strip()
                                if _numbers_match(_act_c, n_clean):
                                    matched_user_num = n
                                    break
                            if matched_user_num:
                                break
                        if matched_user_num:
                            break

                    if matched_user_num:
                        pot_num = matched_user_num
                    elif len(pot_nums_list) >= 2:
                        # No active-session match — prefer index 1 since many
                        # panels put a CLI/sender at index 0 and the destination
                        # (the rented number) at index 1.
                        pot_num = pot_nums_list[1]
                    else:
                        pot_num = pot_nums_list[0]
                            
                if pot_num and pot_msg:
                    otp = extract_otp_code(pot_msg)
                    if otp:
                        # cli_hint may come from dict keys OR list[0] (Format 1).
                        # Fall back to message-body detection if still empty.
                        final_cli = cli_hint or detect_service(pot_msg) or ""
                        received_ts = _parse_row_timestamp(item)
                        temp_results.append({"number": pot_num, "message": pot_msg, "otp": otp, "cli": final_cli, "received_ts": received_ts})
                        
            def traverse_json(node):
                if isinstance(node, list):
                    if len(node) > 0 and not isinstance(node[0], (dict, list)):
                        # It's a flat list representing one record
                        process_item(node)
                    for child in node:
                        if isinstance(child, (dict, list)):
                            traverse_json(child)
                elif isinstance(node, dict):
                    process_item(node)
                    for val in node.values():
                        if isinstance(val, (dict, list)):
                            traverse_json(val)

            traverse_json(data)
            
            # Remove duplicates that arise when traverse_json visits the same
            # record via multiple paths (e.g., a top-level list AND a nested
            # object within the same response).  The key intentionally does NOT
            # include CLI — the same JSON record may be reached once with a CLI
            # value and once without, producing different keys and two identical
            # OTP deliveries.  CLI is NOT a distinguishing identity field here;
            # it is enrichment data.  Two genuinely different OTPs from the same
            # number with the same code but different message text DO get different
            # keys because message is included.
            #
            # BUG FIX: received_ts MUST be included when available so that two
            # legitimately different OTPs (same number, same code, same message
            # text) that arrive at different seconds are NOT collapsed into one.
            # Example: number X sends OTP 1234 at 12:55:10 and again at 12:55:11
            # — previously both had the same uid and only the first was forwarded.
            # Now the per-second timestamp makes each uid unique, so both forward.
            # When received_ts is None (panel provides no timestamps) the old
            # ts-less key is used — two truly identical records with no timestamp
            # cannot be distinguished, so deduping them is still correct.
            seen = set()
            for r in temp_results:
                _r_ts = r.get("received_ts")
                uid = (
                    f"{r['number']}_{r['otp']}_{_msg_dedup_key(r.get('message', ''))}_{ int(_r_ts)}"
                    if _r_ts is not None
                    else f"{r['number']}_{r['otp']}_{_msg_dedup_key(r.get('message', ''))}"
                )
                if uid not in seen:
                    seen.add(uid)
                    results.append(r)
        except Exception as _parse_err:
            print(f"[parse_panel_response] JSON parse/traverse error — OTPs may be lost: {_parse_err}")
        
    return results

# 🌟 Advanced Automated Background Captcha Solver 🌟
def attempt_auto_login(p, idx):
    login_url = p.get("login_url", "").strip()
    if not login_url.startswith("http"):
        login_url = "http://" + login_url
        
    if not login_url.lower().endswith('/login') and not login_url.lower().endswith('.php'):
        login_url = f"{login_url.rstrip('/')}/login"
        
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    })
    
    try:
        res = session.get(login_url, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        all_text = res.text
        
        # 1. SOLVE CAPTCHA (Exact bot 3.py logic)
        captcha_match = re.search(r'(\d+\s*[\+\-\*]\s*\d+)\s*[=\?:]', all_text)
        if not captcha_match:
            captcha_match = re.search(r'what is\s*(\d+\s*[\+\-\*]\s*\d+)', all_text, re.I)
        if not captcha_match:
            elements = soup.find_all(["label", "div", "span", "p", "strong"])
            for el in elements:
                txt = el.get_text(separator=" ", strip=True)
                if any(op in txt for op in ["+", "-", "*"]):
                    m = re.search(r'(\d+\s*[\+\-\*]\s*\d+)', txt)
                    if m:
                        captcha_match = m
                        break
                        
        captcha_text = captcha_match.group(1) if captcha_match else "0 + 0"
        answer = "0"
        m2 = re.search(r'(\d+)\s*([\+\-\*])\s*(\d+)', captcha_text)
        if m2:
            a, op, b = int(m2.group(1)), m2.group(2), int(m2.group(3))
            if op == '+': answer = str(a + b)
            elif op == '-': answer = str(a - b)
            elif op == '*': answer = str(a * b)

        # 2. FIND FORM
        form = soup.find("form")
        if not form:
            p["login_status"] = "❌ No login form found"
            return False
            
        action = form.get("action")
        from urllib.parse import urljoin
        post_url = urljoin(login_url, action) if action else login_url

        form_data = {}
        for hidden in form.find_all("input", type="hidden"):
            name = hidden.get("name")
            if name: form_data[name] = hidden.get("value") or ""
        
        user_input = form.find("input", {"name": re.compile(r"user|email|id", re.I)}) or \
                     form.find("input", {"type": "text", "placeholder": re.compile(r"user|email", re.I)}) or \
                     form.find("input", {"type": "text"})
                     
        pass_input = form.find("input", {"name": re.compile(r"pass", re.I)}) or \
                     form.find("input", {"type": "password"})
                     
        captcha_input = form.find("input", {"placeholder": re.compile(r"answer|ans|code|verification|value|captcha", re.I)}) or \
                        form.find("input", {"name": re.compile(r"ans|captcha|ver|code", re.I)})
        
        user_field = user_input.get("name") if user_input else "username"
        pass_field = pass_input.get("name") if pass_input else "password"
        captcha_field = captcha_input.get("name") if captcha_input else "answer"

        form_data[user_field] = p.get("username", "")
        form_data[pass_field] = p.get("password", "")
        if captcha_field:
            form_data[captcha_field] = answer
        soup.decompose()  # BUG FIX: free login-page HTML tree — last use of soup is above

        # 3. SUBMIT
        login_req = session.post(post_url, data=form_data, allow_redirects=True, timeout=15)
        
        # 4. VERIFY (Exact bot 3.py check logic)
        msg_link = p.get("msg_link", "").strip()
        if not msg_link.startswith("http") and msg_link != "":
            msg_link = "http://" + msg_link
            
        check_url = msg_link if msg_link else f"{login_url.split('/login')[0]}/client/SMSCDRStats"
        
        check_res = session.get(check_url, timeout=10)
        
        if 'logout' in login_req.text.lower() or 'logout' in check_res.text.lower() or 'sms reports' in check_res.text.lower() or 'dashboard' in check_res.text.lower() or 'cdrs' in check_res.text.lower():
            panel_sessions[idx] = session
            p["login_status"] = "✅ Active & Fetching"
            return True
        else:

            p["login_status"] = f"❌ Login Failed (Math: {captcha_text} = {answer})"
            return False
            
    except Exception as e:
        p["login_status"] = f"❌ Error: {str(e)[:20]}"
        
    return False

def _dispatch_otp_to_users(num, otp, msg_text, app_full_name, prem_app_html, panel_name="Panel", received_ts=None):
    """
    Find owners of `num`, send inbox OTP message, credit balance, update DB.
    Called via _enqueue_otp_send so it NEVER blocks the polling/monitor threads.
    received_ts: float Unix timestamp of the OTP record (used in inbox dedup key
    so that the same OTP code re-sent at a different time is still delivered).
    """
    display_num = f"+{num}" if not str(num).startswith("+") else str(num)
    lang = detect_language(msg_text)
    clean_api_num = str(num).replace("+", "").replace(" ", "").replace("-", "").strip()
    # `iso` (country code, used below in the inbox message) was never computed
    # in this function — every call raised a silent NameError inside the OTP
    # sender thread, so the inbox message was never built/sent at all. This
    # was the actual cause of "inbox OTPs not arriving".
    _char, iso = get_flag_and_code(num)

    remove_number_after_otp(clean_api_num)

    owners = []
    owner_assigned_service = {}
    owner_assigned_country = {}
    owner_assigned_at = {}
    for uid, session_data in list(user_active_sessions.items()):
        for act_num in session_data.get("nums", []):
            act_clean = str(act_num).replace("+", "").replace(" ", "").replace("-", "").strip()
            if _numbers_match(act_clean, clean_api_num):
                owners.append(uid)
                owner_assigned_service[uid] = session_data.get("service")
                owner_assigned_country[uid] = session_data.get("country")
                owner_assigned_at[uid] = session_data.get("assigned_at", 0)
                break

    # If the same number somehow ended up in multiple sessions, only forward
    # to the latest owner (highest assigned_at). Normal case = 1 owner.
    if len(owners) > 1:
        owners = [max(owners, key=lambda uid: owner_assigned_at.get(uid, 0))]
    else:
        owners = list(set(owners))

    # Nobody holds this number right now: if a user changed away from it within
    # the admin-set window, deliver the OTP to that user's inbox.
    if not owners:
        _old = _find_released_owner(clean_api_num)
        if _old:
            owners = [_old["uid"]]
            owner_assigned_service[_old["uid"]] = _old.get("service")
            owner_assigned_country[_old["uid"]] = _old.get("country")
    for owner_id in owners:
        # One owner's send/DB failure must never stop the inbox OTP from
        # reaching the other owners of the same number.
        try:
            # Per-user inbox dedup: blocks the same OTP arriving via two
            # different paths (API panel + scraper2) from being delivered
            # twice to the same user's inbox.  Key includes the normalised
            # message text so that two distinct SMS messages that happen to
            # carry the same OTP code at the same second (different message
            # body, different sender) are still delivered separately.
            # A genuine re-send at a different timestamp always produces a
            # different key and is delivered correctly.
            _inbox_msg_key = _msg_dedup_key(msg_text)
            inbox_uid = (
                f"inbox_{owner_id}_{num}_{otp}_{_inbox_msg_key}_{int(received_ts)}"
                if received_ts is not None
                else f"inbox_{owner_id}_{num}_{otp}_{_inbox_msg_key}"
            )
            if not _otp_mark(inbox_uid):
                continue

            assigned_service = owner_assigned_service.get(owner_id)
            if assigned_service:
                owner_app_full_name, owner_prem_app_html = get_service_info_html(assigned_service)
            else:
                owner_app_full_name, owner_prem_app_html = app_full_name, prem_app_html

            inbox_msg = render_body_text(
                f"╔═══════════════╗\n║ {get_flag_info_html(display_num)} <b>{iso}</b> <b>{display_num}</b> {lang}\n╚═══════════════╝"
            )
            inbox_kb = [[{"text": f"{otp}", "icon_custom_emoji_id": "6068830682359010545",
                          "copy_text": {"text": otp}, "style": "success"}]]

            reward = get_service_otp_reward(owner_app_full_name, owner_assigned_country.get(owner_id), assigned_service)
            if reward > 0:
                update_balance(owner_id, reward)
                inbox_kb.append([{"text": f"Added {format_currency(reward)}",
                                   "icon_custom_emoji_id": "5409048419211682843",
                                   "callback_data": "ignore", "style": "primary"}])
            pay_ref_commission(owner_id, reward)

            send_otp_message(owner_id, inbox_msg, reply_markup={"inline_keyboard": inbox_kb})

            with db_lock:
                conn = get_db_conn()
                conn.execute("UPDATE users SET total_otps=total_otps+1 WHERE user_id=?", (owner_id,))
                conn.commit()
                conn.close()
            if owner_id in user_cache:
                user_cache[owner_id]["total_otps"] = user_cache[owner_id].get("total_otps", 0) + 1
            lb_record_otp(owner_id)   # ← DB-backed leaderboard entry
            _today = datetime.now().strftime("%Y-%m-%d")
            # Track today's total earned (by_service already counted above for all OTPs)
            if today_stats.get("date") != _today:
                today_stats.update({"date": _today, "earned": 0.0, "by_service": {}})
            today_stats["earned"] = today_stats.get("earned", 0.0) + reward
        except Exception as e:
            print(f"[OTP] inbox dispatch failed for owner {owner_id}: {e}")


def _process_otp_item(item, panel_name="Panel"):
    """
    Panel-worker HOT PATH — ONLY dedup + enqueue. Returns in microseconds.

    Under high panel load (50-200 new OTPs per poll cycle) the old approach
    blocked the panel worker thread for every OTP doing synchronous enrichment
    (flag lookup, service detect, regex, string formatting).  100 OTPs × 5ms
    each = 500 ms the panel cannot poll again — OTPs pile up on the server and
    the next cycle gets even more, compounding the delay.

    Fix: dedup here (fast — just a set lookup + lock), then hand the raw item
    to a sender thread via _enqueue_otp_send.  All enrichment runs in
    _enrich_and_forward_otp which executes in one of the 25 sender threads,
    completely independent of the panel poller.
    """
    num      = item["number"]
    otp      = item["otp"]
    msg_text = item["message"]
    # Dedup key — see full rule comment in _enrich_and_forward_otp below.
    _recv_ts  = item.get("received_ts")
    _msg_key  = _msg_dedup_key(msg_text)
    unique_id = (f"{num}_{otp}_{_msg_key}_{int(_recv_ts)}"
                 if _recv_ts is not None else f"{num}_{otp}_{_msg_key}")
    if not _otp_mark(unique_id):
        return  # already seen — panel worker done in ~1 µs
    # All heavy work delegated — panel worker is back to polling immediately
    _enqueue_otp_send(_enrich_and_forward_otp, item, panel_name, _recv_ts)


def _enrich_and_forward_otp(item, panel_name, _recv_ts):
    """
    Runs in a sender thread (one of 25). Performs all enrichment and forwards
    to fw_groups + owner inbox. Panel worker never touches this code.

    Dedup key rules (for reference — the actual check is done in _process_otp_item):
      • Same number + same OTP + same message + different received time
        → different key → BOTH forwarded  ✅
      • Same number + same OTP + same message + same received time
        (true duplicate / same SMS seen from two sources) → forward ONCE  ✅
      • Same number + same time + different OTP or different message
        → different key → BOTH forwarded  ✅
    """
    num      = item["number"]
    otp      = item["otp"]
    msg_text = item["message"]

    # ── Flag + ISO ──────────────────────────────────────────────────────────
    try:
        char, iso = get_flag_and_code(num)
    except Exception as e:
        print(f"[OTP] get_flag_and_code failed: {e}")
        char, iso = "🌐", "??"

    # ── Service detection ────────────────────────────────────────────────────
    try:
        _cli        = (item.get("cli") or "").strip()
        _is_numeric = bool(re.match(r'^\+?[\d\s\-]+$', _cli)) if _cli else True
        # Never fall back to panel_name — it shows the panel's own name
        # ("Its Sms", "Panel 1", etc.) instead of the actual app/service.
        _svc_hint   = _cli if (_cli and not _is_numeric) else (detect_service(msg_text) or "")
        app_full_name, prem_app_html = get_service_info_html(_svc_hint, msg_text)
    except Exception as e:
        print(f"[OTP] service detection failed: {e}")
        app_full_name, prem_app_html = "SMS", "SMS"

    # ── Traffic + today_stats ────────────────────────────────────────────────
    try:
        recent_traffic.append({"service": app_full_name, "iso": iso,
                                "flag": char, "number": num, "time": time.time()})
        _rt_today = datetime.now().strftime("%Y-%m-%d")
        if today_stats.get("date") != _rt_today:
            today_stats.update({"date": _rt_today, "earned": 0.0, "by_service": {}})
        _rt_svc = (app_full_name or "Unknown").strip()
        _rt_iso = iso or "??"
        today_stats["by_service"].setdefault(_rt_svc, {})
        today_stats["by_service"][_rt_svc][_rt_iso] = today_stats["by_service"][_rt_svc].get(_rt_iso, 0) + 1
    except Exception:
        pass

    # ── Build forwarding message ─────────────────────────────────────────────
    display_num = f"+{num}" if not str(num).startswith("+") else str(num)
    try:
        masked = mask_number(display_num)
    except Exception:
        masked = display_num
    try:
        lang = detect_language(msg_text)
    except Exception:
        lang = ""
    try:
        display_msg = render_body_text(
            f"╔═════════════════╗\n║ {_format_svc(app_full_name, prem_app_html)} {get_flag_info_html(display_num)} <b>{iso}</b> <b>{masked}</b> {lang}\n╚═════════════════╝"
        )
    except Exception as e:
        print(f"[OTP] display_msg build failed, using plain fallback: {e}")
        display_msg = f"🔔 OTP: {otp}\n{display_num}"

    # ── Forward to fw_groups — each isolated so one broken config can't
    # stop others or the inbox dispatch below ────────────────────────────────
    for fw in bot_settings.get("fw_groups", []):
        try:
            kb = build_otp_fw_kb(otp, fw)
            _enqueue_otp_send(send_otp_message, fw["chat_id"], display_msg, {"inline_keyboard": kb})
        except Exception as e:
            print(f"[OTP] fw_group send failed ({fw.get('chat_id')}): {e}")

    # ── Enqueue owner inbox dispatch — non-blocking ──────────────────────────
    _enqueue_otp_send(_dispatch_otp_to_users, num, otp, msg_text, app_full_name, prem_app_html, panel_name, _recv_ts)


# ─── Per-panel worker: each panel runs in its own thread ─────────────────────
# Previously ALL panels ran sequentially in one loop.  A single slow panel
# (e.g. 15 s network timeout on login) would freeze every other panel for the
# same duration.  Now each panel is fully independent.

def _single_panel_worker(idx_ref):
    """
    idx_ref is a list [idx] so we can update the index if panels are reordered.
    (We key off idx for panel_sessions compatibility.)
    """
    # Stagger startup so all panels don't hammer the server at the same second.
    time.sleep(idx_ref[0] * 0.3)

    _api_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    _last_save_ts = [0.0]   # mutable so inner logic can update it

    while True:
        # BUG FIX: initialize dispatched BEFORE try: so the adaptive sleep
        # logic (outside the try block) never raises NameError when an exception
        # occurs before the inner "dispatched = 0" is reached.  Without this,
        # any early exception (panel OFF, index out of range, network error)
        # would crash the sleep block → panel sleeps for the full base interval
        # instead of hot-mode 0.2 s, delaying the next poll under load.
        dispatched = 0
        p = {}
        try:
            panels = bot_settings.get("panels", [])
            idx    = idx_ref[0]
            if idx >= len(panels):
                time.sleep(5)
                continue

            p = panels[idx]
            if p.get("status") != "ON":
                time.sleep(3)
                continue

            parsed_data = []

            # ── Auto Captcha Panel ──────────────────────────────────────────
            if p.get("type") == "Auto Captcha Panel":
                sess = panel_sessions.get(idx)

                if not sess:
                    now = time.time()
                    # Cooldown only applies between repeated login FAILURES.
                    # A fresh expiry (last_login_attempt reset to 0) bypasses it.
                    cooldown_remaining = 30 - (now - p.get("last_login_attempt", 0))
                    if cooldown_remaining > 0:
                        time.sleep(min(cooldown_remaining, 3))
                        continue

                    p["last_login_attempt"] = now
                    p["login_status"] = "⏳ Logging in..."

                    success = attempt_auto_login(p, idx)
                    save_db()

                    if not success:
                        # Failed login — wait before retry
                        time.sleep(10)
                        continue

                    sess = panel_sessions.get(idx)
                    if not sess:
                        time.sleep(10)
                        continue

                    p["login_status"] = "✅ Logged In — Fetching..."

                try:
                    parsed_data, _ = fetch_cpt_panel_cdrs(p, sess, p.get("msg_link", ""))
                    p["login_status"] = "✅ Active & Fetching"

                except Exception as _sess_err:
                    # ── Session expired: clean up and re-login immediately ──
                    p["login_status"] = "🔄 Session Expired — Re-logging in..."

                    # Close old session (releases connections)
                    old_sess = panel_sessions.pop(idx, None)
                    if old_sess:
                        try:
                            old_sess.close()
                        except Exception:
                            pass

                    # Reset cooldown so re-login starts on NEXT iteration
                    # without waiting 30 s unnecessarily.
                    p["last_login_attempt"] = 0

                    save_db()
                    # Brief pause — server may need a moment after expiry
                    time.sleep(2)
                    continue

            # ── API Panel ───────────────────────────────────────────────────
            elif p.get("api_url") or p.get("full_api_url"):
                full_url = p.get("full_api_url", "").strip()
                url      = p.get("api_url", "").strip()
                token    = p.get("token", "").strip()
                if not full_url and not url:
                    time.sleep(5)
                    continue

                urls_to_try = []
                if full_url:
                    urls_to_try.append(full_url)
                else:
                    if "{token}" in url or "{key}" in url:
                        urls_to_try.append(url.replace("{token}", token).replace("{key}", token))
                    elif "token=" in url or "key=" in url:
                        urls_to_try.append(url)
                    else:
                        sep = '&' if '?' in url else '?'
                        urls_to_try.append(f"{url}{sep}token={token}")
                        urls_to_try.append(f"{url}{sep}key={token}&start=0")
                        urls_to_try.append(f"{url}{sep}key={token}")

                for try_url in urls_to_try:
                    try:
                        res = requests.get(try_url, headers=_api_headers, timeout=10)
                        parsed_data = parse_panel_response(res.text, p)
                        if parsed_data:
                            if not full_url and try_url != url and token:
                                p["api_url"] = try_url.replace(token, "{token}")
                                save_db()
                            break
                    except Exception:
                        continue
            else:
                time.sleep(5)
                continue

            # ── Apply record limit (API panels only) ────────────────────────
            # IMPORTANT: filter already-seen OTPs BEFORE applying the limit.
            # Without this, when a number receives 2 different OTPs and the
            # panel returns them newest-first, the already-seen OTP at
            # position 1 permanently blocks the unprocessed OTP at position 2
            # because the limit slices the list before the new OTP is reached.
            # Pre-filtering ensures the limit only counts UNSEEN records, so
            # every new OTP eventually gets forwarded regardless of limit size.
            if p.get("type") != "Auto Captcha Panel":
                limit = p.get("records", 0)
                if limit > 0:
                    unseen_data = [
                        item for item in parsed_data
                        if not _otp_seen(
                            # Key MUST match _process_otp_item exactly:
                            # num + otp + normalised_msg + int(ts) (per-second).
                            # Previously used // 10 (10-s bucket) which NEVER
                            # matched what _process_otp_item stored (1-s bucket),
                            # making this filter silently useless.
                            f"{item['number']}_{item['otp']}_{_msg_dedup_key(item.get('message',''))}_{int(item['received_ts'])}"
                            if item.get("received_ts") is not None
                            else f"{item['number']}_{item['otp']}_{_msg_dedup_key(item.get('message',''))}"
                        )
                    ]
                    parsed_data = unseen_data[:limit]

            # ── Dispatch each new OTP immediately ───────────────────────────
            panel_name = p.get("name", f"Panel{idx}")
            dispatched = 0  # NOTE: also initialised before try: — see below
            for item in parsed_data:
                _process_otp_item(item, panel_name)
                dispatched += 1

            # ── Speed tracker: rolling 60-s OTP counter ──────────────────────
            if dispatched > 0:
                _speed_tracker["count"] += dispatched
                _speed_tracker["last_otp_ts"] = time.time()

            # Batch-save traffic every 30 s instead of on every OTP
            now = time.time()
            if now - _last_save_ts[0] >= 30:
                _last_save_ts[0] = now
                threading.Thread(target=save_local_db, daemon=True).start()

        except Exception as e:
            print(f"[Panel#{idx_ref[0]}] fetch cycle error: {e}")

        # ── Adaptive hot-polling ──────────────────────────────────────────────
        # If we just forwarded OTPs → poll again in 0.2 s (hot mode).
        # If OTPs came in the last 30 s → stay fast at 1 s.
        # Otherwise fall back to the configured interval (default 2 s).
        # Captcha panels always use 4 s (login is expensive).
        if p.get("type") == "Auto Captcha Panel":
            sleep_secs = 4
        else:
            base_interval = p.get("fetch_interval", 2)
            since_last = time.time() - _speed_tracker.get("last_otp_ts", 0)
            if dispatched > 0:
                sleep_secs = 0.2          # hot: OTPs just found → re-poll instantly
            elif since_last < 30:
                sleep_secs = min(1.0, base_interval)   # warm: active recently
            else:
                sleep_secs = base_interval             # idle: normal pace
        time.sleep(sleep_secs)


def panel_monitor_thread():
    """
    Supervisor: watches bot_settings['panels'] and spawns/kills per-panel threads.
    Replaces the old single-threaded sequential loop.
    """
    _panel_threads = {}   # idx -> (thread, idx_ref)
    while True:
        try:
            panels = bot_settings.get("panels", [])
            for idx in range(len(panels)):
                entry = _panel_threads.get(idx)
                if entry is None or not entry[0].is_alive():
                    idx_ref = [idx]
                    t = threading.Thread(
                        target=_single_panel_worker,
                        args=(idx_ref,),
                        daemon=True,
                        name=f"panel-worker-{idx}"
                    )
                    t.start()
                    _panel_threads[idx] = (t, idx_ref)

            # Clean up threads for removed panels
            for idx in list(_panel_threads.keys()):
                if idx >= len(panels):
                    del _panel_threads[idx]
        except Exception:
            pass
        time.sleep(5)

# ==========================================
# User Data (SQLite)
# ==========================================
user_cache = {}

def get_user(user_id):
    if user_id in user_cache: return user_cache[user_id]
    with db_lock:
        conn = get_db_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            data = dict(row)
        else:
            conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            data = {"user_id": user_id, "balance": 0.0, "total_refers": 0, "total_otps": 0,
                    "banned": 0, "verified": 0, "referred_by": None, "ref_paid": 0}
        conn.close()
    data["banned"] = bool(data.get("banned", 0))
    data["verified"] = bool(data.get("verified", 0))
    user_cache[user_id] = data
    # Evict oldest entry when cache exceeds limit (prevents unbounded growth)
    if len(user_cache) > 8000:
        try:
            user_cache.pop(next(iter(user_cache)))
        except (StopIteration, RuntimeError):
            pass
    return data

def _get_batch_price(service, country_key=""):
    """Return OTP rate for a specific service+country batch.
    Lookup order:
      1. service_country_prices[service][country_key]  ← per-batch (e.g. "58 1", "58 2")
      2. service_otp_prices[service]                   ← per-service fallback
      3. global otp_reward                             ← bot-wide default
    This ensures suffixed batches like Venezuela 1 / Venezuela 2 each keep
    their own rate and don't overwrite each other.
    """
    if country_key:
        per_country = bot_settings.get("service_country_prices", {}).get(service, {})
        if country_key in per_country:
            return float(per_country[country_key])
    svc_price = bot_settings.get("service_otp_prices", {}).get(service)
    if svc_price is not None:
        return float(svc_price)
    return float(bot_settings.get("otp_reward", 0.1))

def get_service_otp_reward(app_full_name, country_key=None, service=None):
    # Per-batch rate first: "Venezuela 1" and "Venezuela 2" each keep their own
    # rate. Only when this country has NO rate of its own do we fall back to the
    # service-level / global rate below.
    if country_key:
        _names = {str(app_full_name or "").strip().upper(), str(service or "").strip().upper()}
        _names.discard("")
        for _svc_key, _per_country in bot_settings.get("service_country_prices", {}).items():
            if str(_svc_key).strip().upper() in _names and country_key in _per_country:
                try:
                    return float(_per_country[country_key])
                except (TypeError, ValueError):
                    pass
    prices = bot_settings.get("service_otp_prices", {})
    name   = (app_full_name or "").strip()
    # BUG FIX 1: case-insensitive lookup — admin panel stores keys in their
    # original case (e.g. "WhatsApp") but callers pass the resolved full name
    # which may have different casing.  Uppercasing only the lookup key and
    # comparing against uppercased dict keys ensures a match regardless of how
    # the admin typed the service name.
    name_upper = name.upper()
    for k, v in prices.items():
        if str(k).upper() == name_upper:
            return float(v)
    # BUG FIX 2: was returning 0.0 as default, ignoring the global `otp_reward`
    # setting configured by the admin.  Now correctly falls back to that value
    # (default 0.1) so users always receive at least the configured base reward.
    return float(bot_settings.get("otp_reward", 0.1))

def update_balance(user_id, amount):
    if user_id in user_cache:
        user_cache[user_id]["balance"] = user_cache[user_id].get("balance", 0.0) + float(amount)
    with db_lock:
        conn = get_db_conn()
        conn.execute(
            "INSERT INTO users (user_id, balance) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+?",
            (user_id, float(amount), float(amount))
        )
        conn.commit()
        conn.close()

# Commission tiers: (min_refs, rate_per_otp, short_name, long_name, emoji_html, emoji_id_next)
REF_TIERS = [
    (0,   0.0002, "L1", "Level 1", '<tg-emoji emoji-id="5294205834144795719">🥇</tg-emoji>', "6206222099132978580"),
    (50,  0.0004, "L2", "Level 2", '<tg-emoji emoji-id="6206222099132978580">🥈</tg-emoji>', "5453902265922376865"),
    (100, 0.0006, "L3", "Level 3", '<tg-emoji emoji-id="5453902265922376865">🥉</tg-emoji>', "5039999772300149658"),
    (150, 0.0008, "L4", "Level 4", '<tg-emoji emoji-id="5039999772300149658">💎</tg-emoji>', "6125115309650089324"),
    (200, 0.0010, "L5", "Level 5", '<tg-emoji emoji-id="6125115309650089324">👑</tg-emoji>', ""),
]

def get_ref_tier(total_refers):
    """Return the current tier tuple for a user with total_refers referrals."""
    tier = REF_TIERS[0]
    for t in REF_TIERS:
        if total_refers >= t[0]:
            tier = t
    return tier  # (min_refs, rate, short, long, icon)

def pay_ref_commission(owner_id, otp_reward):
    """Pay the admin-set per-OTP referral commission to the inviter of owner_id."""
    try:
        rate = float(bot_settings.get("ref_commission", 0.0) or 0.0)
        if rate <= 0:
            return
        inviter_id = get_user(owner_id).get("referred_by")
        if not inviter_id:
            return
        update_balance(inviter_id, rate)
    except Exception as _ref_err:
        print(f"[ref_commission] failed for owner={owner_id}: {_ref_err}")

def add_referral(inviter_id, new_user_id):
    existing = get_user(new_user_id)
    if existing.get("ref_paid"): return
    with db_lock:
        conn = get_db_conn()
        conn.execute("UPDATE users SET total_refers=total_refers+1 WHERE user_id=?", (inviter_id,))
        conn.commit()
        conn.close()
    if inviter_id in user_cache:
        user_cache[inviter_id]["total_refers"] = user_cache[inviter_id].get("total_refers", 0) + 1
    total_refs = get_user(inviter_id).get("total_refers", 0)
    ref_msg = (
        f"🎉 <b>New Referral!</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Referrals:</b> {total_refs}\n"
        f"💰 <b>Commission:</b> {format_currency(bot_settings.get('ref_commission', 0.0))}/OTP\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Every OTP your referral receives earns you commission!"
    )
    send_message(inviter_id, render_body_text(ref_msg))


# ==========================================
# External Backup Importer (key-value "docs" format -> this bot's tables)
# ==========================================
def is_docs_backup(path):
    """True if `path` is a key-value backup (table `docs`) instead of this
    bot's native SQLite file (table `users`)."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        c.close()
        return "docs" in names and "users" not in names
    except Exception:
        return False

def import_docs_backup(path):
    """Merge a docs-format backup into the live DB.

    Imports: users (balance, total_refers, total_otps, banned, verified,
    referred_by, name/username), withdrawals and the daily OTP leaderboard.
    Users already in the live DB are updated from the backup; users that exist
    only in the live DB are left untouched. Nothing is deleted.
    The backup stores money in BDT, but this bot stores it internally in USDT
    (shown to users as internal * BDT-rate), so balances and withdrawal amounts
    are divided by the BDT rate here. Re-importing the same file is safe and
    also repairs rows imported earlier with the wrong unit.
    Returns a dict of counts (stats["balance"] is the total in BDT).
    """
    import json as _json
    rate = _bdt_rate()
    if not rate or rate <= 0:
        rate = 110.0
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    def _docs(coll):
        out = []
        for _id, _data in src.execute("SELECT id, data FROM docs WHERE collection=?", (coll,)):
            try:
                out.append((_id, _json.loads(_data)))
            except Exception:
                pass
        return out

    users = _docs("users")
    wds = _docs("withdrawals")
    otp_daily = _docs("otp_daily")
    src.close()

    def _int(v, d=None):
        try: return int(v)
        except (TypeError, ValueError): return d
    def _flt(v, d=0.0):
        try: return float(v)
        except (TypeError, ValueError): return d

    stats = {"users": 0, "balance": 0.0, "referred": 0, "withdrawals": 0, "leaderboard": 0}
    with db_lock:
        conn = get_db_conn()
        # Safety copy of the live DB (sqlite backup API is WAL-safe)
        try:
            bk = sqlite3.connect(DB_PATH + ".backup")
            conn.backup(bk)
            bk.close()
        except Exception as _e:
            print(f"[IMPORT] backup copy failed: {_e}")
        try:
            for _id, u in users:
                uid = _int(u.get("user_id"), _int(_id))
                if uid is None:
                    continue
                ref_by = _int(u.get("referred_by"))
                if ref_by == uid:
                    ref_by = None
                # ref_paid=1 when there is an inviter: the backup's total_refers
                # already counts this user, so add_referral() must not run again
                # on their next /start (that would double-count the referral).
                ref_paid = 1 if ref_by else 0
                conn.execute(
                    "INSERT INTO users (user_id,balance,total_refers,total_otps,banned,verified,"
                    "referred_by,ref_paid,username,first_name) VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance,"
                    "total_refers=excluded.total_refers,total_otps=excluded.total_otps,"
                    "banned=excluded.banned,verified=excluded.verified,"
                    "referred_by=excluded.referred_by,ref_paid=excluded.ref_paid,"
                    "username=COALESCE(excluded.username,users.username),"
                    "first_name=COALESCE(excluded.first_name,users.first_name)",
                    (uid, _flt(u.get("balance")) / rate, _int(u.get("total_refers"), 0),
                     _int(u.get("total_otps"), 0), 1 if u.get("banned") else 0,
                     1 if u.get("verified") else 0, ref_by, ref_paid,
                     (u.get("username") or None), (u.get("first_name") or None))
                )
                stats["users"] += 1
                stats["balance"] += _flt(u.get("balance"))
                if ref_by: stats["referred"] += 1

            for req_id, w in wds:
                uid = _int(w.get("user_id"))
                if uid is None:
                    continue
                if conn.execute("SELECT 1 FROM withdrawals WHERE request_id=?", (req_id,)).fetchone():
                    # already imported earlier -> just fix its amount unit
                    conn.execute("UPDATE withdrawals SET amount=? WHERE request_id=?",
                                 (_flt(w.get("amount")) / rate, req_id))
                    continue
                conn.execute(
                    "INSERT INTO withdrawals (user_id,amount,method,account,request_id,status,timestamp) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (uid, _flt(w.get("amount")) / rate, w.get("method"), w.get("number"), req_id,
                     str(w.get("status") or "pending").lower(), _flt(w.get("timestamp")))
                )
                stats["withdrawals"] += 1

            for _id, d in otp_daily:
                uid = _int(d.get("user_id")); day = d.get("day")
                if uid is None or not day:
                    continue
                conn.execute(
                    "INSERT INTO daily_leaderboard (user_id,date,count) VALUES (?,?,?) "
                    "ON CONFLICT(user_id,date) DO UPDATE SET count=excluded.count",
                    (uid, day, _int(d.get("count"), 0))
                )
                stats["leaderboard"] += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    user_cache.clear()
    return stats


# ==========================================
# UI Keyboards & Menu Builders
# ==========================================
def get_cancel_kb():
    return {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]]}

def main_menu(user_id):
    kb = [
        [
            {"text": "GET NUMBER", "icon_custom_emoji_id": "5895343514320899727", "style": "primary"},
            {"text": "TRAFFIC", "icon_custom_emoji_id": "5429278861932124623", "style": "success"}
        ],
    ]
    if bot_settings.get("refer_on", True):
        kb.append([
            {"text": "Refer", "icon_custom_emoji_id": "5332724926216428039", "style": "success"},
            {"text": "PROFILE", "icon_custom_emoji_id": "5352861489541714456", "style": "primary"}
        ])
    else:
        kb.append([
            {"text": "PROFILE", "icon_custom_emoji_id": "5352861489541714456", "style": "primary"}
        ])
    if bot_settings.get("leaderboard_on", True):
        kb.append([
            {"text": "SUPPORT", "icon_custom_emoji_id": "5307746710682869587", "style": "primary"},
            {"text": "LEADERBOARD", "icon_custom_emoji_id": "5440539497383087970", "style": "success"}
        ])
    else:
        kb.append([{"text": "SUPPORT", "icon_custom_emoji_id": "5307746710682869587", "style": "primary"}])
    if is_admin(user_id):
        kb.append([{"text": "Admin Panel", "icon_custom_emoji_id": "5420155432272438703", "style": "danger"}])
    return {"keyboard": kb, "resize_keyboard": True}

def get_admin_text():
    users_count = len(all_known_users) # 🌟 Zero Cost User Count!
    total_files = len(number_batches)
    # Live counts (not stale lifetime counters) so numbers/available drop to 0
    # once their batches are actually deleted from stock.
    numbers_in_stock = sum(len(b["numbers"]) for b in number_batches.values())
    available_nums = sum(
        1 for b in number_batches.values()
        for n in b.get("numbers", []) if not n.get("exhausted")
    )

    txt = f"""
{PEM['admin']} <b>ADMIN CONTROL PANEL</b> {PEM['admin']}
━━━━━━━━━━━━━━━━━━

{PEM['graph']} <b>DATABASE OVERVIEW</b>
— — — — — — — — — —
{PEM['user']} Users      » {users_count}
{PEM['file']} Files      » {total_files}
{PEM['num']} Numbers    » {numbers_in_stock}
{PEM['ok']} Assigned   » {total_assigned_stats}
{PEM['rocket']} Available  » {available_nums}

{PEM['graph']} <b>STOCK LEVEL</b>
— — — — — — — — — —
[██████░░░░░░░░░] {available_nums} free
"""
    return render_body_text(txt)

def admin_panel_keyboard():
    return {"inline_keyboard": [
        [{"text": "LEADER BOARD SYSTEM", "icon_custom_emoji_id": "5353032893096567467", "callback_data": "lb_main", "style": "success"}],
        [{"text": "NUMBER Mgmt", "icon_custom_emoji_id": "5271837459783638319", "callback_data": "num_mgmt", "style": "primary"},
         {"text": "Stock", "icon_custom_emoji_id": "5352877703043258544", "callback_data": "view_stock", "style": "primary"}],
        [{"text": "Broadcast", "icon_custom_emoji_id": "5789428375261023681", "callback_data": "broadcast_msg", "style": "success"},
         {"text": "System", "icon_custom_emoji_id": "5420155432272438703", "callback_data": "system_settings", "style": "primary"}],
        [{"text": "Used number", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "show_used", "style": "success"},
         {"text": "Unused number", "icon_custom_emoji_id": "5352597830089347330", "callback_data": "show_unused", "style": "success"}],
        [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]
    ]}

def num_mgmt_keyboard():
    return {"inline_keyboard": [
        [{"text": "Upload Number", "icon_custom_emoji_id": "5445355530111437729", "callback_data": "upload_num", "style": "primary"},
         {"text": "Delete Files", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "delete_files", "style": "danger"}],
        [{"text": "Update Number", "icon_custom_emoji_id": "5395444784611480792", "callback_data": "update_num", "style": "success"},
         {"text": "Number Lock", "icon_custom_emoji_id": "6068830682359010545", "callback_data": "num_lock", "style": "danger"}],
        [{"text": "Manage Rate", "icon_custom_emoji_id": "5431456208487716895", "callback_data": "manage_rate", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]
    ]}


def build_total_balance_text():
    """Sum of every user's balance (admin-only view, shown in BDT)."""
    try:
        with db_lock:
            conn = get_db_conn()
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance),0), "
                "COALESCE(SUM(CASE WHEN balance>0 THEN 1 ELSE 0 END),0) FROM users"
            ).fetchone()
            conn.close()
        total_users, total_bal, funded_users = row[0], float(row[1] or 0.0), row[2]
    except Exception as e:
        return f"{PEM['no']} <b>Failed to calculate total balance:</b> <code>{html.escape(str(e))}</code>"
    return (
        f"{PEM['money']} <b>TOTAL BALANCE (All Users)</b>\n"
        f"➖➖➖➖➖➖➖\n"
        f"{PEM['group']} Total Users: <b>{total_users}</b>\n"
        f"{PEM['user']} Users with Balance: <b>{funded_users}</b>\n"
        f"➖➖➖➖➖➖➖\n"
        f"{PEM['card']} Total Balance: <b>{total_bal * _bdt_rate():.2f} BDT</b>\n"
        f"➖➖➖➖➖➖➖"
    )

# ==========================================
# Low Stock Alert
# ==========================================
LOW_STOCK_DEFAULT_THRESHOLD = 50     # alert when a service+country has <= this many numbers
LOW_STOCK_CHECK_INTERVAL = 60        # seconds between background checks
_low_stock_alerted = set()           # (service, country) already alerted; cleared once restocked

def get_low_stock_items(threshold=None):
    """Return [(service, country, count)] for every service+country whose
    remaining stock is <= threshold, lowest stock first."""
    if threshold is None:
        try:
            threshold = int(bot_settings.get("low_stock_threshold", LOW_STOCK_DEFAULT_THRESHOLD))
        except (TypeError, ValueError):
            threshold = LOW_STOCK_DEFAULT_THRESHOLD
    agg = {}
    with number_batches_lock:
        for b in number_batches.values():
            key = (b.get("service", "UNKNOWN"), b.get("country", "UNKNOWN"))
            agg[key] = agg.get(key, 0) + len(b.get("numbers", []))
    items = [(svc, cnt, n) for (svc, cnt), n in agg.items() if n <= threshold]
    items.sort(key=lambda x: (x[2], str(x[0]), str(x[1])))
    return items

def _low_stock_lines(items, limit=20):
    lines = []
    for svc, cnt, n in items[:limit]:
        tag = "🚫 OUT OF STOCK" if n == 0 else f"⚠️ {n} left"
        lines.append(f"• <b>{html.escape(str(svc))}</b> — {html.escape(str(cnt))}: {tag}")
    if len(items) > limit:
        lines.append(f"… and {len(items) - limit} more")
    return "\n".join(lines)

def build_low_stock_text():
    on = bot_settings.get("low_stock_alert_on", True)
    th = int(bot_settings.get("low_stock_threshold", LOW_STOCK_DEFAULT_THRESHOLD))
    items = get_low_stock_items(th)
    body = _low_stock_lines(items) if items else f"{PEM['ok']} All stocks are above the limit."
    return (
        f"{PEM['warn']} <b>LOW STOCK ALERT</b>\n"
        f"➖➖➖➖➖➖➖\n"
        f"Status: <b>{'ON 🟢' if on else 'OFF 🔴'}</b>\n"
        f"Alert when stock ≤ <b>{th}</b> numbers\n"
        f"➖➖➖➖➖➖➖\n"
        f"{body}"
    )

def low_stock_keyboard():
    on = bot_settings.get("low_stock_alert_on", True)
    th = int(bot_settings.get("low_stock_threshold", LOW_STOCK_DEFAULT_THRESHOLD))
    return {"inline_keyboard": [
        [{"text": f"Alert: {'ON' if on else 'OFF'}", "icon_custom_emoji_id": "5336944168944047463",
          "callback_data": "low_stock_toggle", "style": "success" if on else "danger"},
         {"text": f"Limit: {th}", "icon_custom_emoji_id": "5420155432272438703",
          "callback_data": "low_stock_set", "style": "primary"}],
        [{"text": "🔄 Refresh", "icon_custom_emoji_id": "5395444784611480792",
          "callback_data": "low_stock_alert", "style": "success"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176",
          "callback_data": "system_settings", "style": "danger"}]
    ]}

def low_stock_monitor_thread():
    """Background checker: DMs every admin when a service+country drops to the
    limit. Each one alerts once and re-arms after it is restocked above the limit."""
    time.sleep(30)
    while True:
        try:
            if bot_settings.get("low_stock_alert_on", True):
                items = get_low_stock_items()
                current = {(s, c) for s, c, n in items}
                _low_stock_alerted.intersection_update(current)   # restocked -> re-arm
                new_items = [(s, c, n) for s, c, n in items if (s, c) not in _low_stock_alerted]
                if new_items:
                    th = int(bot_settings.get("low_stock_threshold", LOW_STOCK_DEFAULT_THRESHOLD))
                    text = render_body_text(
                        f"{PEM['warn']} <b>LOW STOCK ALERT</b>\n"
                        f"Stock is at or below <b>{th}</b>:\n\n"
                        f"{_low_stock_lines(new_items)}\n\n"
                        f"Please upload more numbers."
                    )
                    admins = set(bot_settings.get("admins", [])) | {OWNER_ID}
                    for adm in admins:
                        try:
                            send_message(adm, text)
                        except Exception:
                            pass
                    _low_stock_alerted.update((s, c) for s, c, n in new_items)
        except Exception as e:
            print(f"[low-stock-monitor] error: {e}")
        time.sleep(LOW_STOCK_CHECK_INTERVAL)

def system_settings_keyboard():
    maint_on = bot_settings.get("maintenance_mode", False)
    cur = bot_settings.get("currency", "USDT")
    return {"inline_keyboard": [
        [{"text": "Voltx Control", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "voltx_control", "style": "primary"},
         {"text": "STEX SMS Control", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "stex_control", "style": "success"}],
        [{"text": "Panel MANAGEMENT", "icon_custom_emoji_id": "5336879280578138635", "callback_data": "manage_panels", "style": "danger"},
         {"text": "DEV Control", "icon_custom_emoji_id": "5193100774988617665", "callback_data": "dxa_control", "style": "primary"}],
        [{"text": "Force Join System", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "manage_fj", "style": "primary"},
         {"text": "Admin Management", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "manage_admins", "style": "danger"}],
        [{"text": "OTP Group", "icon_custom_emoji_id": "5190447043545438788", "callback_data": "manage_otp_groups", "style": "danger"},
         {"text": "User Management", "icon_custom_emoji_id": "5193063022226086560", "callback_data": "user_management", "style": "primary"}],
        [{"text": "Premium Emoji", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "manage_emojis", "style": "success"},
         {"text": "Database", "icon_custom_emoji_id": "5800835941543186089", "callback_data": "database_management", "style": "primary"}],
        [{"text": "Settings", "icon_custom_emoji_id": SETTINGS_EMOJI_ID, "callback_data": "open_settings", "style": "primary"},
         {"text": "OTP Status", "icon_custom_emoji_id": "5190447043545438788", "callback_data": "otp_status", "style": "success"}],
        [{"text": "Total Balance", "icon_custom_emoji_id": "5190576863226933563", "callback_data": "total_balance", "style": "success"},
         {"text": "Low Stock Alert", "icon_custom_emoji_id": "5336944168944047463", "callback_data": "low_stock_alert", "style": "danger"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275166", "callback_data": "back_to_admin", "style": "danger"}]
    ]}

def settings_keyboard():
    maint_on  = bot_settings.get("maintenance_mode", False)
    cur       = bot_settings.get("currency", "USDT")
    num_bc_on = bot_settings.get("numbers_broadcast_on", True)
    return {"inline_keyboard": [
        [{"text": f"Maintenance: {'ON' if maint_on else 'OFF'}", "icon_custom_emoji_id": "5336944168944047463", "callback_data": "toggle_maintenance", "style": "danger" if maint_on else "success"},
         {"text": f"Broadcast: {'ON' if num_bc_on else 'OFF'}", "icon_custom_emoji_id": "5789428375261023681", "callback_data": "toggle_numbers_broadcast", "style": "success" if num_bc_on else "danger"}],
        [{"text": "Test", "icon_custom_emoji_id": "5190781475468915802", "callback_data": "test_message_flow", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": SETTINGS_EMOJI_ID, "callback_data": "system_settings", "style": "danger"}]
    ]}

def currency_select_keyboard():
    cur = bot_settings.get("currency", "USDT")
    rows = []
    for c in ["BDT"]:
        mark = " ✅" if c == cur else ""
        rows.append([{"text": f"{c}{mark}", "icon_custom_emoji_id": CURRENCY_EMOJI_IDS.get(c), "callback_data": f"set_currency_{c}", "style": "success" if c == cur else "primary"}])
    rows.append([{"text": "Back", "icon_custom_emoji_id": SETTINGS_EMOJI_ID, "callback_data": "open_settings", "style": "danger"}])
    return {"inline_keyboard": rows}

def build_otp_status_text():
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_str   = datetime.now().strftime("%H:%M:%S")

    # ── Today's total OTPs — sum from today_stats["by_service"] which counts
    # ALL received OTPs (not just ones dispatched to a matched user).  This
    # is the same source used for the "by service / country" breakdown below,
    # so both numbers are always consistent.
    today_total = 0
    if today_stats.get("date") == today_str:
        for _svc_counts in today_stats.get("by_service", {}).values():
            today_total += sum(_svc_counts.values())
    # Fallback to DB leaderboard if today_stats hasn't been populated yet
    if today_total == 0:
        _lr = None
        try:
            with db_lock:
                _lc = get_db_conn()
                _lr = _lc.execute(
                    "SELECT COALESCE(SUM(count),0) FROM daily_leaderboard WHERE date=?",
                    (today_str,)
                ).fetchone()
                _lc.close()
            today_total = int(_lr[0]) if _lr else 0
        except Exception:
            today_total = sum(
                v.get("count", 0) for v in daily_otps.values()
                if v.get("date") == today_str
            )

    # ── Active sessions ─────────────────────────────────────────────────
    active_count = len(user_active_sessions)

    lines = [
        "━━━━━━━━━━━━━━━━━━",
        "《 📊 OTP STATUS 》",
        "━━━━━━━━━━━━━━━━━━",
        f"📩 <b>Today OTPs:</b> {today_total:,}",
        f"🟢 <b>Active Sessions:</b> {active_count}",
        "━━━━━━━━━━━━━━━━━━",
    ]

    # ── OTPs by Service / Country (today_stats now counts ALL received OTPs) ─
    by_svc = today_stats.get("by_service", {}) if today_stats.get("date") == today_str else {}
    if by_svc:
        lines.append("📡 <b>TODAY OTPs BY SERVICE / COUNTRY:</b>")
        # Sort services alphabetically; within each service sort countries by count desc
        for srv in sorted(by_svc):
            # Use _format_svc so we show EITHER the specific premium emoji OR the
            # bold service name — never both (which caused double-emoji display).
            _svc_fn, _svc_html = get_service_info_html(srv)
            svc_display = _format_svc(_svc_fn, _svc_html)
            country_counts = by_svc[srv]
            for iso_key, cnt in sorted(country_counts.items(), key=lambda x: -x[1]):
                # Use get_flag_info_html so premium flag tg-emoji tags are used
                # instead of plain Unicode chars (fixes "premium flags not showing").
                flag = get_flag_info_html(iso_key)
                lines.append(
                    f"  {svc_display}  ·  {flag} <b>{iso_key}</b>  —  <b>{cnt:,}</b> OTPs"
                )
        lines.append("━━━━━━━━━━━━━━━━━━")
    else:
        lines.append("📡 <i>No OTPs received today yet</i>")
        lines.append("━━━━━━━━━━━━━━━━━━")

    # ── Voltx services ───────────────────────────────────────────────────
    voltx_srvs = bot_settings.get("voltx_services", {})
    if voltx_srvs:
        lines.append("⚡ <b>VOLTX SERVICES:</b>")
        for srv, srv_data in voltx_srvs.items():
            countries = srv_data.get("countries", {})
            _vfn, _vhtml = get_service_info_html(srv)
            svc_disp = _format_svc(_vfn, _vhtml)
            for ckey in sorted(countries):
                cname, fhtml = _flag_display(ckey)
                parts = ckey.strip().split(" ")
                sfx = f"  <i>suffix #{parts[-1]}</i>" \
                    if len(parts) > 1 and parts[-1].isdigit() else ""
                lines.append(f"  {svc_disp} · {fhtml}{cname}{sfx}")
        lines.append("━━━━━━━━━━━━━━━━━━")

    # ── STEX services ────────────────────────────────────────────────────
    stex_srvs = bot_settings.get("stex_services", {})
    if stex_srvs:
        lines.append("🌐 <b>STEX SERVICES:</b>")
        for srv, srv_data in stex_srvs.items():
            _sfn, _shtml = get_service_info_html(srv)
            svc_disp = _format_svc(_sfn, _shtml)
            rngs  = srv_data.get("ranges", {})
            lines.append(f"  {svc_disp} — {len(rngs)} range(s)")
        lines.append("━━━━━━━━━━━━━━━━━━")

    lines.append(f"🕐 <b>Updated:</b> {now_str}")
    return "\n".join(lines)

def get_user_management_text():
    # 🌟 Fast & Free User Management Stats!
    total = len(all_known_users)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt = f"""➖➖➖➖➖➖➖➖
《 👋 USER VIEW 》
➖➖➖➖➖➖➖➖
📊 LIVE STATISTICS:
➖➖➖➖➖➖➖➖
🫂 TOTAL USERS: {total}
✅ VERIFIED USERS: (Hidden to save DB Cost)
🚫 BANNED USERS: (Hidden to save DB Cost)
➖➖➖➖➖➖➖➖
⌛ UPDATED: {now_str}"""
    return render_body_text(txt)

def user_management_keyboard():
    return {"inline_keyboard": [
        [{"text": "Manage Balance", "icon_custom_emoji_id": "5190576863226933563", "callback_data": "um_manage_balance", "style": "primary"},
         {"text": "Ban/Unban User", "icon_custom_emoji_id": "5334807341109908955", "callback_data": "um_ban_unban", "style": "danger"}],
        [{"text": "User Profile", "icon_custom_emoji_id": "5352861489541714456", "callback_data": "um_user_profile", "style": "success"},
         {"text": "User List", "icon_custom_emoji_id": "5193063022226086560", "callback_data": "um_user_list_0", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "primary"}]
    ]}

def database_management_keyboard():
    return {"inline_keyboard": [
        [{"text": "Download Database", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_database", "style": "success"},
         {"text": "Upload Database", "icon_custom_emoji_id": "5445355530111437729", "callback_data": "upload_database", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}]
    ]}

def emoji_settings_keyboard():
    return {"inline_keyboard": [
        [{"text": "Upload Flags (TXT)", "icon_custom_emoji_id": "5445355530111437729", "callback_data": "up_flags_txt", "style": "primary"},
         {"text": "Download Flags", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_flags_txt", "style": "success"}],
        [{"text": "Upload Services (TXT)", "icon_custom_emoji_id": "5445355530111437729", "callback_data": "up_apps_txt", "style": "primary"},
         {"text": "Download Services", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_apps_txt", "style": "success"}],
        [{"text": "Delete All Flags", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "del_all_flags", "style": "danger"},
         {"text": "Add Single Emoji", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_single_emoji", "style": "success"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}]
    ]}

def fj_settings_keyboard():
    status_text = 'ON' if bot_settings['fj_on'] else 'OFF'
    status_icon = "5352694861990501856" if bot_settings['fj_on'] else "5318840353510408444"
    kb = [[{"text": f"STATUS: {status_text}", "icon_custom_emoji_id": status_icon, "callback_data": "toggle_fj", "style": "primary"}]]
    for idx, ch in enumerate(bot_settings["fj_channels"]):
        kb.append([{"text": f"Delete: {ch}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_fj_{idx}", "style": "danger"}])
    kb.append([{"text": "Add Channel", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_fj", "style": "success"}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "primary"}])
    return {"inline_keyboard": kb}

def admin_settings_keyboard():
    kb = []
    for idx, adm in enumerate(bot_settings["admins"]):
        text_btn = f"Owner: {adm}" if adm == OWNER_ID else f"Delete: {adm}"
        icon_id = "5353032893096567467" if adm == OWNER_ID else "5420130255174145507"
        cb_data = "ignore" if adm == OWNER_ID else f"del_adm_{idx}"
        kb.append([{"text": text_btn, "icon_custom_emoji_id": icon_id, "callback_data": cb_data, "style": "danger" if adm != OWNER_ID else "primary"}])
    kb.append([{"text": "Add Admin", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_adm", "style": "success"}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "primary"}])
    return {"inline_keyboard": kb}

def otp_groups_list_keyboard():
    ch_set = "✅" if bot_settings.get("fw_channel_link") else "❌"
    kb = [
        [{"text": "Edit OTP Group Link", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "edit_otp_link", "style": "primary"}],
        [{"text": f"Edit Channel Link {ch_set}", "icon_custom_emoji_id": "5429405838345265327", "callback_data": "edit_fw_channel_link", "style": "primary"}],
    ]
    for idx, fg in enumerate(bot_settings["fw_groups"]):
        group_label = fg.get("name") or fg["chat_id"]
        kb.append([{"text": f"Group: {group_label}", "icon_custom_emoji_id": "5193063022226086560", "callback_data": f"manage_fw_{idx}", "style": "primary"}])
    kb.append([{"text": "Add Forward Group", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_fw", "style": "success"}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}])
    return {"inline_keyboard": kb}

def build_otp_fw_kb(otp: str, fw: dict) -> list:
    """Build the inline keyboard for an OTP forward group message.
    Row 1: OTP copy button (green)
    Row N: any custom buttons configured for this group
    Last row: [Number BOT | Channel] side-by-side (auto from BOT_USERNAME + otp_link)
    """
    kb = [[{"text": f"{otp}", "icon_custom_emoji_id": "6068830682359010545", "copy_text": {"text": otp}, "style": "success"}]]
    for btn in fw.get("buttons", []):
        # A malformed/incomplete custom button (missing text or url) used to
        # raise a KeyError here. Since this keyboard is built BEFORE the
        # inbox OTP is dispatched, that single bad button silently killed
        # the entire OTP — no group message AND no inbox message. Skip a
        # broken button instead of crashing the whole OTP delivery.
        btn_text = btn.get("text")
        btn_url  = btn.get("url")
        if not btn_text or not btn_url:
            continue
        b_obj = {"text": btn_text, "url": btn_url, "style": "primary"}
        if "icon_custom_emoji_id" in btn:
            b_obj["icon_custom_emoji_id"] = btn["icon_custom_emoji_id"]
        kb.append([b_obj])
    # Bottom row: Channel (left) + Get Number/BOT (right) — side by side
    bottom_row = []
    fw_channel = bot_settings.get("fw_channel_link", "")
    if fw_channel and fw_channel.strip():
        bottom_row.append({"text": "𝗖𝗵𝗮𝗻𝗻𝗲𝗹", "url": fw_channel.strip(), "style": "primary", "icon_custom_emoji_id": "5839406384243807787"})
    if BOT_USERNAME:
        bottom_row.append({"text": "𝗕𝗢𝗧", "url": f"https://t.me/{BOT_USERNAME}", "style": "primary", "icon_custom_emoji_id": "5352597830089347330"})
    if bottom_row:
        kb.append(bottom_row)
    return kb

def voltx_control_keyboard():
    return {"inline_keyboard": [
        [{"text": "Add Voltx Key", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_voltx_key", "style": "success"},
         {"text": "View/Del Keys", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "view_voltx_keys", "style": "danger"}],
        [{"text": "Manage Services", "icon_custom_emoji_id": "5192739271886282680", "callback_data": "manage_voltx_srv", "style": "success"},
         {"text": "Search Country", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "voltx_search_country", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "primary"}]
    ]}

def stex_control_keyboard():
    return {"inline_keyboard": [
        [{"text": "Add STEX Key", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_stex_key", "style": "success"},
         {"text": "View/Del Keys", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "view_stex_keys", "style": "danger"}],
        [{"text": "Manage Services", "icon_custom_emoji_id": "5192739271886282680", "callback_data": "manage_stex_srv", "style": "success"},
         {"text": "Allowed Ranges", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "stex_search_country", "style": "primary"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "primary"}]
    ]}

def specific_fw_group_keyboard(idx):
    group = bot_settings["fw_groups"][idx]
    kb = []
    for b_idx, btn in enumerate(group.get("buttons", [])):
        kb.append([{"text": f"Del: {btn['text']}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_fwbtn_{idx}_{b_idx}", "style": "danger"}])
    
    kb.append([{"text": "Add Inline Button", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"add_fwbtn_{idx}", "style": "success"}])
    kb.append([{"text": "Delete Entire Group", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"del_fw_{idx}", "style": "danger"}])
    kb.append([{"text": "Back to Groups", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": "primary"}])
    return {"inline_keyboard": kb}

def dxa_control_keyboard():
    w_status = "ON" if bot_settings["withdraw_on"] else "OFF"
    sup_status = "ON" if bot_settings.get("support_link") else "OFF"
    grp_status = "ON" if bot_settings.get("w_group") else "OFF"
    try:
        with db_lock:
            conn = get_db_conn()
            pending_count = conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
            conn.close()
    except:
        pending_count = 0
    req_label = f"W. REQUESTS ({pending_count})" if pending_count else "W. REQUESTS"
    refer_status = "ON" if bot_settings.get("refer_on", True) else "OFF"
    return {"inline_keyboard": [
        [{"text": f"WITHDRAW: {w_status}", "icon_custom_emoji_id": "5888561507557447441", "callback_data": "dxa_toggle_w", "style": "primary"},
         {"text": f"REFER & EARN: {refer_status}", "icon_custom_emoji_id": "5332724926216428039", "callback_data": "dxa_toggle_refer", "style": "success" if bot_settings.get("refer_on", True) else "danger"}],
        [{"text": f"MIN WITHDRAW: {format_currency(bot_settings['min_withdraw'])}", "icon_custom_emoji_id": "5352877703043258544", "callback_data": "dxa_min_w", "style": "success"},
         {"text": f"OTP REWARD: {bot_settings['otp_reward']}", "icon_custom_emoji_id": "5190576863226933563", "callback_data": "dxa_otp_r", "style": "primary"}],
        [{"text": f"NUM/REQ: {bot_settings['num_req']}", "icon_custom_emoji_id": "5337132498965010628", "callback_data": "dxa_num_req", "style": "success"},
         {"text": f"COOLDOWN: {bot_settings['cooldown']}s", "icon_custom_emoji_id": "5337172996211648018", "callback_data": "dxa_cool", "style": "primary"}],
        [{"text": f"TRAFFIC WINDOW: {bot_settings.get('traffic_window', 60)}min", "icon_custom_emoji_id": "5465368548702446780", "callback_data": "dxa_traffic_w", "style": "success"},
         {"text": f"SUPPORT LINK: {sup_status}", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "dxa_sup_link", "style": "primary"}],
        [{"text": f"NUM EXPIRY: {'OFF' if not bot_settings.get('num_expiry', 0) else str(bot_settings.get('num_expiry', 0)) + 'min'}", "icon_custom_emoji_id": "5337172996211648018", "callback_data": "dxa_num_expiry", "style": "danger" if not bot_settings.get('num_expiry', 0) else "success"},
         {"text": "W. METHODS", "icon_custom_emoji_id": "5190899075968441286", "callback_data": "manage_w_methods", "style": "primary"}],
        [{"text": req_label, "icon_custom_emoji_id": "5472250091332993630", "callback_data": "view_w_requests", "style": "success"},
         {"text": f"LEADERBOARD: {'ON' if bot_settings.get('leaderboard_on', True) else 'OFF'}", "icon_custom_emoji_id": "5440539497383087970", "callback_data": "dxa_toggle_lb", "style": "success" if bot_settings.get("leaderboard_on", True) else "danger"}],
        [{"text": f"AUTO WITHDRAW: {'ON' if bot_settings.get('auto_withdraw', False) else 'OFF'}", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "dxa_toggle_auto_w", "style": "success" if bot_settings.get("auto_withdraw", False) else "danger"},
         {"text": f"OLD NUM OTP: {'OFF' if not bot_settings.get('old_num_window', 0) else str(bot_settings.get('old_num_window', 0)) + 'min'}", "icon_custom_emoji_id": "5337172996211648018", "callback_data": "dxa_old_num", "style": "danger" if not bot_settings.get('old_num_window', 0) else "success"}],
        [{"text": f"REF COMMISSION: {format_currency(bot_settings.get('ref_commission', 0.0))}", "icon_custom_emoji_id": "5332724926216428039", "callback_data": "dxa_ref_comm", "style": "success"}],
        [{"text": "BACK", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}]
    ]}

def get_payment_emoji_id(method_name):
    key = method_name.upper().replace(" ", "").replace("/", "").replace("-", "")
    apps = bot_settings.get("premium_apps", {})
    for app_key, app_data in apps.items():
        clean_key = app_key.replace(" ", "").replace("/", "").replace("-", "")
        if clean_key in key or key in clean_key:
            return app_data.get("id", "5472250091332993630")
    return "5472250091332993630"

def withdrawal_requests_list_keyboard(requests):
    kb = []
    for row in requests:
        db_id, user_id, amount, method, account, status, ts = row
        account_preview = str(account or "")[:8]
        label = f"#{db_id} | {method or 'Unknown'} | {format_currency(amount)} | {account_preview}..."
        kb.append([{"text": label, "icon_custom_emoji_id": "5472250091332993630", "callback_data": f"wreq_detail_{db_id}", "style": "primary"}])
    kb.append([{"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": "view_w_requests", "style": "success"},
               {"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "dxa_control", "style": "danger"}])
    return {"inline_keyboard": kb}

def w_methods_keyboard():
    kb = []
    for idx, m in enumerate(bot_settings["w_methods"]):
        emoji_id = get_payment_emoji_id(m)
        kb.append([{"text": f"{m}", "icon_custom_emoji_id": emoji_id, "callback_data": f"del_wm_{idx}", "style": "danger"}])
    kb.append([{"text": "Add Method", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_wm", "style": "success"}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "dxa_control", "style": "primary"}])
    return {"inline_keyboard": kb}

def typed_panels_list_keyboard(p_type):
    kb = []
    for idx, p in enumerate(bot_settings["panels"]):
        if p.get("type", "API Panel") != p_type: continue
        action_text = f"Turn OFF {p['name']}" if p['status'] == 'ON' else f"Turn ON {p['name']}"
        action_icon = "5318840353510408444" if p['status'] == 'ON' else "5192812028632274956"
        icon_id = "5420155432272438703" 
        kb.append([
            {"text": action_text, "icon_custom_emoji_id": action_icon, "callback_data": f"tog_pnl_{idx}", "style": "danger" if p['status'] == 'ON' else "success"},
            {"text": f"{p['name']}", "icon_custom_emoji_id": icon_id, "callback_data": f"conf_pnl_{idx}", "style": "primary"}
        ])
    add_cb = "add_api_panel" if p_type == "API Panel" else "add_cpt_panel"
    kb.append([{"text": "Add New Provider", "icon_custom_emoji_id": "5420323438508155202", "callback_data": add_cb, "style": "success"}])
    kb.append([{"text": "Delete Provider", "icon_custom_emoji_id": "5336944168944047463", "callback_data": f"list_del_{'api' if p_type=='API Panel' else 'cpt'}", "style": "danger"}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_panels", "style": "primary"}])
    return {"inline_keyboard": kb}

def panel_config_keyboard(idx):
    p = bot_settings["panels"][idx]
    
    kb = []
    action_text = "Turn OFF" if p['status'] == 'ON' else "Turn ON"
    action_icon = "5318840353510408444" if p['status'] == 'ON' else "5192812028632274956"
    kb.append([{"text": action_text, "icon_custom_emoji_id": action_icon, "callback_data": f"tog_pnl_{idx}", "style": "danger" if p['status'] == 'ON' else "success"}])
    
    if p["type"] != "Auto Captcha Panel":
        rec_count_text = "All (Unlimited)" if p.get('records', 0) == 0 else str(p.get('records'))
        kb.append([{"text": "Set API URL", "icon_custom_emoji_id": "5420517437885943844", "callback_data": f"set_p_api_{idx}", "style": "primary"}])
        kb.append([{"text": "Set Token", "icon_custom_emoji_id": "6068830682359010545", "callback_data": f"set_p_tok_{idx}", "style": "primary"}])
        kb.append([{"text": "Full API (URL+Token)", "icon_custom_emoji_id": "5420517437885943844", "callback_data": f"set_p_fapi_{idx}", "style": "primary"}])
        kb.append([{"text": f"Set Records Count: {rec_count_text}", "icon_custom_emoji_id": "5192739271886282680", "callback_data": f"set_p_rec_{idx}", "style": "primary"}])
        fetch_int_text = f"{p.get('fetch_interval', 2)}s"
        kb.append([{"text": f"Set Fetch Delay: {fetch_int_text}", "icon_custom_emoji_id": "5192739271886282680", "callback_data": f"set_p_int_{idx}", "style": "primary"}])
        
    kb.append([{"text": "Test Connection", "icon_custom_emoji_id": "5352694861990501856", "callback_data": f"test_p_conn_{idx}", "style": "success"}])
        
    back_data = "manage_api_panels" if p.get("type", "API Panel") == "API Panel" else "manage_cpt_panels"
    kb.append([{"text": "Back to Providers", "icon_custom_emoji_id": "5267490665117275176", "callback_data": back_data, "style": "danger"}])
    return {"inline_keyboard": kb}

def build_traffic_ui():
    current_time = time.time()
    # In-place cleanup — drop entries older than 1 h from the left
    # (deque is time-ordered: oldest at index 0)
    _tw = bot_settings.get("traffic_window", 60) * 60
    while recent_traffic and current_time - recent_traffic[0].get("time", 0) > _tw:
        recent_traffic.popleft()

    # Build aggregated stats: (service, iso) -> {count, flag, c_name}
    stats = {}
    for t in recent_traffic:
        srv = t.get("service", "Unknown")
        iso = t.get("iso", "XX")
        flag = t.get("flag", "🌍")
        key = (srv, iso)
        if key not in stats:
            # Resolve country name
            c_name = iso
            for code, fdata in bot_settings.get("premium_flags", {}).items():
                if fdata.get("iso") == iso:
                    c_name = fdata.get("name", iso)
                    break
            stats[key] = {"count": 0, "flag": flag, "c_name": c_name, "srv": srv, "iso": iso}
        stats[key]["count"] += 1

    _tw_min = bot_settings.get("traffic_window", 60)
    txt = f"🔴 <b>Live Traffic (Last {_tw_min} Min)</b>\n\n"

    kb = []
    if not stats:
        txt += f"<i>No recent traffic found in the last {_tw_min} min...</i>\n"
    else:
        total_all = sum(v["count"] for v in stats.values())

        # Sort by count descending so highest OTP sources appear first (highest % auto-first)
        sorted_entries = sorted(stats.values(), key=lambda x: x["count"], reverse=True)

        for entry in sorted_entries:
            srv = entry["srv"]
            iso = entry["iso"]
            c_name = entry["c_name"]
            count = entry["count"]
            pct = (count / total_all * 100) if total_all else 0.0

            app_full_name, prem_app_html = get_service_info_html(srv)
            prem_flag_html = get_flag_info_html(iso)

            txt += f"{_format_svc(app_full_name, prem_app_html)} | {prem_flag_html} {c_name} | <b>{pct:.1f}%</b>\n"

        txt += f"\n<i>Total OTPs: {total_all}</i>\n"

    txt = render_body_text(txt)
    kb.append([{"text": "Refresh", "icon_custom_emoji_id": "5465368548702446780", "callback_data": "refresh_traffic", "style": "primary"}])
    kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])

    return txt, {"inline_keyboard": kb}

# ==========================================
# Leaderboard Builder  (DB-backed — scratch rewrite)
# ==========================================
_LB_RANK_ICONS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

def _lb_get_name(user_id):
    """Return display name for a user_id: first_name only (no @username)."""
    udata = user_cache.get(user_id) or {}
    fname = udata.get("first_name")
    if not fname:
        try:
            with db_lock:
                _c = get_db_conn()
                _row = _c.execute(
                    "SELECT first_name FROM users WHERE user_id=?", (user_id,)
                ).fetchone()
                _c.close()
            if _row:
                fname = _row["first_name"]
        except Exception:
            pass
    return html.escape(str(fname)) if fname else f"User {user_id}"

def _lb_fetch_today():
    """Return list of (user_id, count) sorted desc for today from DB."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with db_lock:
            conn = get_db_conn()
            rows = conn.execute(
                "SELECT user_id, count FROM daily_leaderboard "
                "WHERE date = ? AND count > 0 ORDER BY count DESC LIMIT 10",
                (today_str,)
            ).fetchall()
            conn.close()
        return [(r["user_id"], r["count"]) for r in rows]
    except Exception as e:
        print(f"[lb_fetch_today] {e}")
        return []

def _lb_fetch_weekly():
    """Return list of (user_id, total_count) for last 7 days sorted desc."""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    try:
        with db_lock:
            conn = get_db_conn()
            rows = conn.execute(
                "SELECT user_id, SUM(count) AS total FROM daily_leaderboard "
                "WHERE date >= ? GROUP BY user_id HAVING total > 0 "
                "ORDER BY total DESC LIMIT 10",
                (cutoff,)
            ).fetchall()
            conn.close()
        return [(r["user_id"], r["total"]) for r in rows]
    except Exception as e:
        print(f"[lb_fetch_weekly] {e}")
        return []

def _lb_fetch_alltime():
    """Return list of (user_id, total_otps, username, first_name) sorted desc."""
    try:
        with db_lock:
            conn = get_db_conn()
            rows = conn.execute(
                "SELECT user_id, total_otps, username, first_name FROM users "
                "WHERE total_otps > 0 ORDER BY total_otps DESC LIMIT 10"
            ).fetchall()
            conn.close()
        return [(r["user_id"], r["total_otps"], r["username"], r["first_name"]) for r in rows]
    except Exception as e:
        print(f"[lb_fetch_alltime] {e}")
        return []

def build_leaderboard_ui(mode="today"):
    from datetime import timedelta
    now = datetime.now()

    if mode == "today":
        rows    = _lb_fetch_today()
        entries = [(uid, cnt, _lb_get_name(uid)) for uid, cnt in rows]
        header  = f"{PEM['graph']}  <b>TODAY'S LEADERBOARD</b>  ✨"
        sub     = f"<i>📅 {now.strftime('%A, %d %b %Y')} — Top OTP earners</i>"
        empty_msg = (
            f"{PEM['msg']} <i>No OTP activity yet today.</i>\n"
            "<i>Be the first to receive an OTP and claim the top spot!</i>"
        )

    elif mode == "weekly":
        rows    = _lb_fetch_weekly()
        entries = [(uid, cnt, _lb_get_name(uid)) for uid, cnt in rows]
        start   = (now - timedelta(days=6)).strftime("%d %b")
        end     = now.strftime("%d %b %Y")
        header  = f"{PEM['graph']}  <b>WEEKLY LEADERBOARD</b>  ✨"
        sub     = f"<i>📅 {start} → {end} — Last 7 days</i>"
        empty_msg = f"{PEM['msg']} <i>No OTP activity recorded this week yet.</i>"

    else:  # alltime
        rows    = _lb_fetch_alltime()
        # Use _lb_get_name() — same as today/weekly — so usernames and first
        # names are always html.escape()'d before being embedded in HTML.
        # The previous inline `f"@{uname}"` path skipped escaping entirely,
        # meaning a username containing "<", ">", or "&" would break the HTML
        # or (in a worst case) inject arbitrary tags into the message.
        entries = [(uid, cnt, _lb_get_name(uid)) for uid, cnt, _, _ in rows]
        header  = f"{PEM['rocket']}  <b>ALL-TIME LEADERBOARD</b>  ✨"
        sub     = f"<i>💎 The greatest OTP earners of all time</i>"
        empty_msg = f"{PEM['msg']} <i>No OTP data has been recorded yet.</i>"

    # ── Render ──────────────────────────────────────────────────────────────
    DIVIDER = "━━━━━━━━━━━━━━━━━━━━━"
    txt = f"{header}\n{sub}\n{DIVIDER}\n"

    if not entries:
        txt += f"\n{empty_msg}\n\n"
    else:
        for i, (uid, cnt, name) in enumerate(entries):
            rank = _LB_RANK_ICONS[i] if i < len(_LB_RANK_ICONS) else f"<b>{i+1}.</b>"
            cnt_fmt = f"{cnt:,}"
            txt += f"{rank}  <b>{name}</b>  —  <code>{cnt_fmt}</code> OTPs\n"
        txt += "\n"

    txt += DIVIDER

    # render_body_text converts plain emojis (📅 💎 ✨ 1️⃣–9️⃣ etc.) to
    # <tg-emoji> premium tags; PEM values are already tags and pass through.
    txt = render_body_text(txt)

    # ── Keyboard — icon_custom_emoji_id adds the premium icon; the text label
    # must NOT also start with a plain emoji or Telegram renders both the icon
    # AND the emoji character — showing the emoji twice on every button.
    s_today   = "primary" if mode == "today"   else "success"
    s_weekly  = "primary" if mode == "weekly"  else "success"
    s_alltime = "primary" if mode == "alltime" else "success"
    kb = [
        [
            {"text": "Refresh",
             "icon_custom_emoji_id": "5798596554184986461",
             "callback_data": f"lb_{mode}", "style": "primary"},
        ],
        [
            {"text": "Today",
             "icon_custom_emoji_id": "5413879192267805083",
             "callback_data": "lb_today",   "style": s_today},
            {"text": "Weekly",
             "icon_custom_emoji_id": "5440539497383087970",
             "callback_data": "lb_weekly",  "style": s_weekly},
        ],
        [
            {"text": "All Time",
             "icon_custom_emoji_id": "5998897065613071275",
             "callback_data": "lb_alltime", "style": s_alltime},
        ],
        [
            {"text": "Close",
             "icon_custom_emoji_id": "5420130255174145507",
             "callback_data": "close_msg",  "style": "danger"},
        ],
    ]
    return txt, {"inline_keyboard": kb}

# ==========================================
# /leaderboard  (Owner/Admin only — separate from the menu LEADERBOARD button)
# Lists EVERY user who received OTPs today, split across messages if needed.
# ==========================================
def _lb_cmd_fetch_all_today():
    """[(user_id, count, username, first_name)] for everyone with OTPs today, desc."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        with db_lock:
            conn = get_db_conn()
            rows = conn.execute(
                "SELECT d.user_id AS uid, d.count AS cnt, u.username AS uname, u.first_name AS fname "
                "FROM daily_leaderboard d LEFT JOIN users u ON u.user_id = d.user_id "
                "WHERE d.date = ? AND d.count > 0 ORDER BY d.count DESC, d.user_id ASC",
                (today_str,)
            ).fetchall()
            conn.close()
        return [(r["uid"], r["cnt"], r["uname"], r["fname"]) for r in rows]
    except Exception as e:
        print(f"[lb_cmd] fetch failed: {e}")
        return []

def build_leaderboard_cmd_messages():
    """Return a list of HTML message texts (each < Telegram's 4096-char limit)."""
    now = datetime.now()
    hours_left = max(1, int((86400 - (now.hour * 3600 + now.minute * 60 + now.second) + 3599) // 3600))
    title = "🏆 <b>Daily OTP Leaderboard</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    footer = f"\n⏳ <i>{hours_left} ঘন্টা পর রিসেট হবে</i>"

    rows = _lb_cmd_fetch_all_today()
    if not rows:
        return [title + "<i>আজ এখনো কোনো OTP আসেনি।</i>" + footer]

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, cnt, uname, fname) in enumerate(rows):
        label = f"@{uname}" if uname else (fname or f"User {uid}")
        label = html.escape(str(label))
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {label} — <b>{cnt} OTP</b>")

    msgs, cur = [], title
    for ln in lines:
        if len(cur) + len(ln) + 1 > 3700:
            msgs.append(cur.rstrip())
            cur = ""
        cur += ln + "\n"
    msgs.append(cur.rstrip())
    msgs[-1] += "\n" + footer
    return msgs

# ==========================================
# Number Upload Finalizer (shared by wait_for_otp_price + skip_otp_price)
# ==========================================
# ==========================================
# Ask-before-broadcast for newly added numbers
# ==========================================
_pending_stock_broadcasts = {}   # token -> {"txt": str, "kb": dict}

def _run_stock_broadcast(txt, kb):
    """Send the 'New Stock Added' message to every known user (rate-limited)."""
    url = f"{BASE_URL}/sendMessage"

    def _bc_one(u_id):
        try:
            requests.post(url, json={"chat_id": u_id, "text": txt, "parse_mode": "HTML",
                                      "disable_web_page_preview": True, "reply_markup": kb}, timeout=10)
        except Exception:
            pass

    # 20 concurrent workers, 25/sec rate limit
    with ThreadPoolExecutor(max_workers=20) as ex:
        for i, u_id in enumerate(list(all_known_users)):
            ex.submit(_bc_one, u_id)
            if i % 25 == 24:
                time.sleep(1.0)

def _ask_stock_broadcast(chat_id, summary_html, broadcast_txt, broadcast_kb):
    """Tell the admin the numbers were added and ask whether to broadcast."""
    token = uuid.uuid4().hex[:10]
    _pending_stock_broadcasts[token] = {"txt": broadcast_txt, "kb": broadcast_kb}
    # keep memory bounded
    while len(_pending_stock_broadcasts) > 50:
        try:
            _pending_stock_broadcasts.pop(next(iter(_pending_stock_broadcasts)))
        except (StopIteration, RuntimeError):
            break
    send_message(chat_id, render_body_text(
        f"{summary_html}\n\n📢 <b>Broadcast this to all users?</b>\n"
        f"👥 Users: <b>{len(all_known_users)}</b>"
    ), reply_markup={"inline_keyboard": [[
        {"text": "Yes, Broadcast", "icon_custom_emoji_id": "5352694861990501856",
         "callback_data": f"sbc_yes_{token}", "style": "success"},
        {"text": "No, Skip", "icon_custom_emoji_id": "5420130255174145507",
         "callback_data": f"sbc_no_{token}", "style": "danger"}
    ]]})

def _finalize_number_upload(chat_id):
    global total_uploaded_stats
    try:
        td = temp_data.get(chat_id)
        if not td:
            send_message(chat_id, render_body_text("❌ Session expired. Please upload the file again."))
            return
        service = td.get("service", "UNKNOWN")
        raw_numbers = td.get("numbers", [])
        filename = td.get("filename", "")

        clean_nums = []
        for num in raw_numbers:
            num = str(num).strip()
            if num:
                if not num.startswith("+"): num = "+" + num
                clean_nums.append(num)

        if not clean_nums:
            send_message(chat_id, render_body_text("❌ No valid numbers found in the file. Please upload again."))
            if chat_id in user_states: del user_states[chat_id]
            if chat_id in temp_data: del temp_data[chat_id]
            return

        flags_db_up = bot_settings.get("premium_flags", {})
        prem_flag_html = f"{PEM['world']} "

        # Use country pre-detected during service entry (may include suffix), else auto-detect
        if td.get("auto_country_key"):
            auto_country_key = td["auto_country_key"]
            auto_country_name = td.get("auto_country_name", auto_country_key)
            base_code = auto_country_key.split(" ")[0]
            fd = flags_db_up.get(base_code, {})
            flag_char_up = fd.get("char", "🏳️")
            flag_eid_up = fd.get("id")
            prem_flag_html = f'<tg-emoji emoji-id="{flag_eid_up}">{flag_char_up}</tg-emoji>' if flag_eid_up else flag_char_up
        else:
            auto_country_key = "UNKNOWN"
            auto_country_name = "Unknown"
            first_num = clean_nums[0].replace("+", "").replace(" ", "") if clean_nums else ""
            sorted_codes = sorted(flags_db_up.keys(), key=len, reverse=True)
            for code in sorted_codes:
                if first_num.startswith(code):
                    fd = flags_db_up[code]
                    auto_country_key = code
                    auto_country_name = fd.get("name", code)
                    flag_char_up = fd.get("char", "🏳️")
                    flag_eid_up = fd.get("id")
                    prem_flag_html = f'<tg-emoji emoji-id="{flag_eid_up}">{flag_char_up}</tg-emoji>' if flag_eid_up else flag_char_up
                    break

        batch_id = _fs_batch_id(service, auto_country_key)
        with number_batches_lock:
            if batch_id in number_batches:
                number_batches[batch_id]["numbers"].extend({"num": n, "shares": 0, "used_by": []} for n in clean_nums)
                number_batches[batch_id]["filename"] = filename
            else:
                number_batches[batch_id] = {
                    "filename": filename, "service": service, "country": auto_country_key,
                    "numbers": [{"num": n, "shares": 0, "used_by": []} for n in clean_nums]
                }
            total_uploaded_stats += len(clean_nums)
        save_db()
        _fs_sync_batch(batch_id)

        app_full_name, prem_app_html = get_service_info_html(service)
        otp_price = _get_batch_price(service, auto_country_key)

        new_tag_html  = '<tg-emoji emoji-id="6271473763439612077">🆕</tg-emoji>'
        up_arrow_html = '<tg-emoji emoji-id="5118734498590098251">⬆️</tg-emoji>'
        total_html    = '<tg-emoji emoji-id="5444856076954520455">🧾</tg-emoji>'
        card_html     = '<tg-emoji emoji-id="5445353829304387411">💳</tg-emoji>'
        price_line = f"\n{card_html} OTP Rate: <b>{format_currency(otp_price)}</b>" if float(otp_price) > 0 else f"\n{card_html} OTP Rate: <b>No reward</b>"
        broadcast_txt = render_body_text(
            f"{new_tag_html} <b>New Stock Added</b> {up_arrow_html}\n\n"
            f"{prem_flag_html} | {_format_svc(app_full_name, prem_app_html)}\n"
            f"{total_html} TOTALL : <b>{len(clean_nums)}</b> Numbers{price_line}"
        )
        broadcast_kb = {"inline_keyboard": [[{
            "text": "  Get Number", "icon_custom_emoji_id": "5460907099884104609",
            "callback_data": f"ntf_get_{service}||{auto_country_key}", "style": "success"
        }]]}

        num_bc_on = bot_settings.get("numbers_broadcast_on", True)
        if num_bc_on:
            _ask_stock_broadcast(chat_id,
                f"{PEM['ok']} <b>{len(clean_nums)} numbers added!</b>\n"
                f"📍 Country: <b>{auto_country_name}</b>\n"
                f"📦 Service: <b>{service}</b>\n"
                f"💰 OTP Price: <b>{format_currency(otp_price)}</b>",
                broadcast_txt, broadcast_kb)
        else:
            send_message(chat_id, render_body_text(
                f"{PEM['ok']} <b>{len(clean_nums)} numbers added!</b>\n"
                f"📍 Country: <b>{auto_country_name}</b>\n"
                f"📦 Service: <b>{service}</b>\n"
                f"💰 OTP Price: <b>{format_currency(otp_price)}</b>\n\n"
                f"🔕 Numbers Broadcast is OFF — no notification sent to users."
            ))

    except Exception as e:
        try:
            send_message(chat_id, render_body_text(f"❌ <b>Upload Error:</b> <code>{e}</code>\nPlease try again."))
        except: pass
    finally:
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]

# ==========================================
# Update Number Flow Helpers (admin: service -> country -> upload -> price)
# ==========================================
def _all_stocked_numbers_set():
    """Set of all normalized (digits-only) numbers currently in stock across every batch."""
    existing = set()
    for b in number_batches.values():
        for n in b.get("numbers", []):
            existing.add(str(n.get("num", "")).replace("+", "").replace(" ", "").replace("-", "").strip())
    return existing

def _flag_display(code):
    """Return (display_name, flag_html) for a country/phone-code key.
    Handles suffixed keys like '966 1' by looking up base code '966' and
    appending the suffix to the display name → 'Saudi Arabia 1'.
    """
    flags_db = bot_settings.get("premium_flags", {})

    # Split off numeric suffix if present (e.g. "966 1" → base="966", suffix=" 1")
    parts = code.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base_code, suffix = parts[0], f" {parts[1]}"
    else:
        base_code, suffix = code, ""

    for fc, fd in flags_db.items():
        iso = fd.get("iso", "").upper()
        name = fd.get("name", "").upper()
        # Try exact match on full code first, then on base_code
        if fc == code or _country_code_matches(code, iso, name) or \
           (suffix and (fc == base_code or _country_code_matches(base_code, iso, name))):
            fchar = fd.get("char", "🏳️")
            feid = fd.get("id")
            fhtml = f'<tg-emoji emoji-id="{feid}">{fchar}</tg-emoji>' if feid else fchar
            return fd.get("name", code) + suffix, fhtml

    return code, "🏳️"

def _num_display(num, country, cc_on):
    """Return display string for a number with or without country code prefix.

    CC-stripping strategies (applied in order, first match wins):
      S1 — numeric country key  : "966" / "966 1"  → strip "966"
      S2 — premium_flags lookup : use the flag dict's numeric keys as an
           authoritative dial-code database; pick the longest matching prefix
           so "966" beats "9" and "92" beats "9".
      S3 — range-ID fallback    : for any remaining non-numeric country key,
           check the configured STEX/Voltx range IDs (capped at 3 digits to
           avoid stripping area-code digits from longer ranges like "96601").
    """
    clean = re.sub(r'[^\d]', '', str(num))
    if cc_on:
        return f"+{clean}"

    # ── S1: country key is itself a numeric dial code ─────────────────────────
    cc = re.sub(r'[^\d]', '', str(country).split()[0]) if country else ""
    if cc and clean.startswith(cc):
        return clean[len(cc):]

    # ── S2: premium_flags as CC database ─────────────────────────────────────
    # The flag dict keys ARE dial codes ("966", "971", "92", "44", …).
    # Pick the longest key that is a prefix of the number — longest wins so
    # "971" (UAE) beats a hypothetical single-digit match.
    best_cc = ""
    for flag_code in bot_settings.get("premium_flags", {}):
        trial = re.sub(r'[^\d]', '', str(flag_code))
        if trial and clean.startswith(trial) and len(trial) > len(best_cc):
            best_cc = trial
    if best_cc:
        return clean[len(best_cc):]

    # ── S3: range-ID fallback ─────────────────────────────────────────────────
    # Ranges may be longer than the CC (e.g. "96601").  Cap at 3 digits so we
    # never strip area-code digits; if the range itself is ≤3 digits use it whole.
    for cfg_key in ("voltx_services", "stex_services"):
        for srv_countries in bot_settings.get(cfg_key, {}).values():
            for rng in srv_countries.get(country, []):
                trial = re.sub(r'[^\d]', '', str(rng))[:3]
                if trial and clean.startswith(trial):
                    return clean[len(trial):]

    return clean

def _user_cc_on(uid):
    """True if this user wants country codes shown (default). Persists across number changes."""
    # Country code is never shown or copied now (no Add CC / Remove CC button).
    return False

def _set_user_cc(uid, on):
    lst = bot_settings.setdefault("cc_off_users", [])
    key = str(uid)
    if on and key in lst:
        lst.remove(key)
    elif not on and key not in lst:
        lst.append(key)
    save_db()

def _cc_button_row(cc_on):
    if cc_on:
        return [{"text": "Remove CC", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "toggle_cc", "style": "danger"}]
    return [{"text": "Add CC", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "toggle_cc", "style": "success"}]

def _build_num_card_kb(nums, service, country, emoji_id_srv, cc_on):
    """Build inline keyboard rows for the number assignment card (number rows + CC toggle)."""
    kb = []
    for num in nums:
        display_num = _num_display(num, country, cc_on)
        kb.append([{"text": display_num, "icon_custom_emoji_id": emoji_id_srv,
                    "copy_text": {"text": display_num}, "style": "primary"}])
    c_btns = bot_settings["custom_messages"].get("get_number", {}).get("buttons", [])
    for c_b in c_btns:
        b_copy = c_b.copy()
        if "style" not in b_copy:
            b_copy["style"] = "primary"
        kb.append([b_copy])
    return kb

def _finalize_update_number_upload(chat_id):
    global total_uploaded_stats
    try:
        td = temp_data.get(chat_id)
        if not td:
            send_message(chat_id, render_body_text("❌ Session expired. Please start again."))
            return
        service = td.get("upd_service", "UNKNOWN")
        country = td.get("upd_country", "UNKNOWN")
        raw_numbers = td.get("numbers", [])
        filename = td.get("filename", "")

        existing = _all_stocked_numbers_set()
        clean_nums = []
        seen_in_file = set()
        duplicate_count = 0
        for num in raw_numbers:
            num = str(num).strip()
            if not num:
                continue
            digits = num.replace("+", "").replace(" ", "").replace("-", "").strip()
            if not digits:
                continue
            if digits in existing or digits in seen_in_file:
                duplicate_count += 1
                continue
            seen_in_file.add(digits)
            if not num.startswith("+"):
                num = "+" + digits
            clean_nums.append(num)

        country_name, flag_html = _flag_display(country)

        if not clean_nums:
            send_message(chat_id, render_body_text(
                f"{PEM['no']} <b>No new numbers added.</b>\n"
                f"All {duplicate_count} number(s) in this file were duplicates or already in stock."
            ))
            if chat_id in user_states: del user_states[chat_id]
            if chat_id in temp_data: del temp_data[chat_id]
            return

        batch_id = _fs_batch_id(service, country)
        with number_batches_lock:
            if batch_id in number_batches:
                number_batches[batch_id]["numbers"].extend({"num": n, "shares": 0, "used_by": []} for n in clean_nums)
                number_batches[batch_id]["filename"] = filename
            else:
                number_batches[batch_id] = {
                    "filename": filename, "service": service, "country": country,
                    "numbers": [{"num": n, "shares": 0, "used_by": []} for n in clean_nums]
                }
            total_uploaded_stats += len(clean_nums)
        save_db()
        _fs_sync_batch(batch_id)

        otp_price = _get_batch_price(service, country)
        dup_line = f"\n{PEM['warn']} Duplicates skipped: <b>{duplicate_count}</b>" if duplicate_count else ""

        upd_summary = (
            f"{PEM['ok']} <b>Numbers Updated!</b>\n"
            f"📦 Service: <b>{service}</b>\n"
            f"{flag_html} Country: <b>{country_name}</b>\n"
            f"➕ New numbers added: <b>{len(clean_nums)}</b>{dup_line}\n"
            f"💰 OTP Price: <b>{format_currency(otp_price)}</b>"
        )
        if bot_settings.get("numbers_broadcast_on", True):
            app_full_name, prem_app_html = get_service_info_html(service)
            new_tag_html  = '<tg-emoji emoji-id="6271473763439612077">🆕</tg-emoji>'
            up_arrow_html = '<tg-emoji emoji-id="5118734498590098251">⬆️</tg-emoji>'
            total_html    = '<tg-emoji emoji-id="5444856076954520455">🧾</tg-emoji>'
            card_html     = '<tg-emoji emoji-id="5445353829304387411">💳</tg-emoji>'
            price_line = f"\n{card_html} OTP Rate: <b>{format_currency(otp_price)}</b>" if float(otp_price) > 0 else f"\n{card_html} OTP Rate: <b>No reward</b>"
            upd_bc_txt = render_body_text(
                f"{new_tag_html} <b>New Stock Added</b> {up_arrow_html}\n\n"
                f"{flag_html} | {_format_svc(app_full_name, prem_app_html)}\n"
                f"{total_html} TOTALL : <b>{len(clean_nums)}</b> Numbers{price_line}"
            )
            upd_bc_kb = {"inline_keyboard": [[{
                "text": "  Get Number", "icon_custom_emoji_id": "5460907099884104609",
                "callback_data": f"ntf_get_{service}||{country}", "style": "success"
            }]]}
            _ask_stock_broadcast(chat_id, upd_summary, upd_bc_txt, upd_bc_kb)
        else:
            send_message(chat_id, render_body_text(upd_summary),
                reply_markup={"inline_keyboard": [[{"text": "Back to Admin", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]})
    except Exception as e:
        try:
            send_message(chat_id, render_body_text(f"❌ <b>Update Error:</b> <code>{e}</code>\nPlease try again."))
        except: pass
    finally:
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]

# ==========================================
# Message Handler
# ==========================================
def handle_message(msg):
    try:
        _handle_message_inner(msg)
    except Exception as _hm_exc:
        try:
            cid = msg.get("chat", {}).get("id", "?")
            print(f"[handle_message ERROR] chat={cid} | {type(_hm_exc).__name__}: {_hm_exc}")
        except Exception:
            pass

def _handle_message_inner(msg):
    global total_uploaded_stats
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    
    if chat_type != "private":
        return
        
    text = msg.get("text", "")
    _from = msg.get("from", {})
    register_user_local(chat_id, username=_from.get("username"), first_name=_from.get("first_name"))

    if is_user_banned(chat_id):
        send_message(chat_id, render_body_text("🚫 <b>You are banned from using this bot!</b>\nIf you think this is a mistake, please contact support."))
        return

    if bot_settings.get("maintenance_mode") and not is_admin(chat_id):
        send_message(chat_id, render_body_text(f"{PEM['warn']} <b>Bot is under maintenance!</b>\nPlease check back later. Sorry for the inconvenience."))
        return

    # /leaderboard — Owner/Admin only. Normal users get no reply at all.
    if text.split("@")[0].strip().lower() == "/leaderboard":
        if is_admin(chat_id):
            for _part in build_leaderboard_cmd_messages():
                send_message(chat_id, _part)
        return

    # --- REFERRAL FIX: Save inviter BEFORE Force Join ---
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            param = parts[1]
            # Support both ?start=ref_123 and legacy ?start=123
            inviter_str = param[4:] if param.startswith("ref_") else param
            if inviter_str.isdigit():
                inviter = int(inviter_str)
                if inviter != chat_id:
                    u = get_user(chat_id)
                    if not u.get("referred_by"):
                        with db_lock:
                            conn = get_db_conn()
                            conn.execute("UPDATE users SET referred_by=?, ref_paid=0 WHERE user_id=?", (inviter, chat_id))
                            conn.commit()
                            conn.close()
                        if chat_id in user_cache: user_cache[chat_id]["referred_by"] = inviter
                        
    if not check_force_join(chat_id):
        send_force_join_msg(chat_id)
        return
        
    MAIN_MENU_CMDS = ["GET NUMBER", "TRAFFIC", "Refer", "SUPPORT", "Admin Panel", "LEADERBOARD"]
    
    is_main_cmd = False
    if text in MAIN_MENU_CMDS or text.startswith("/start"):
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]
        is_main_cmd = True
    
    if chat_id in user_states and not is_main_cmd:
        state = user_states[chat_id]
        
        # 🌟 Auto Captcha Panel Setup Flow 
        if state == "wait_for_cpanel_url" and text:
            temp_data[chat_id]["p_data"]["login_url"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_user"
            send_message(chat_id, render_body_text("2️⃣ <b>Username</b>\n➡️ Enter panel username:"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_user" and text:
            temp_data[chat_id]["p_data"]["username"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_pass"
            send_message(chat_id, render_body_text("3️⃣ <b>Password</b>\n➡️ Enter panel password:"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_pass" and text:
            temp_data[chat_id]["p_data"]["password"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_msg_link"
            send_message(chat_id, render_body_text("4️⃣ <b>Message Link</b>\n➡️ Enter the SMS/OTP data link (JSON):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_msg_link" and text:
            temp_data[chat_id]["p_data"]["msg_link"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_num_col_name"
            send_message(chat_id, render_body_text("5️⃣ <b>Number Column Name</b>\n➡️ Number column name in data? (e.g.: number, phone):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_num_col_name" and text:
            temp_data[chat_id]["p_data"]["num_col_name"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_num_col_idx"
            send_message(chat_id, render_body_text("6️⃣ <b>Number Column Serial</b>\n➡️ Number column serial? (e.g.: 3, 5):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_num_col_idx" and text:
            if text.isdigit():
                temp_data[chat_id]["p_data"]["num_col_idx"] = int(text)
                user_states[chat_id] = "wait_for_cpanel_msg_col_name"
                send_message(chat_id, render_body_text("7️⃣ <b>Message Column Name</b>\n➡️ Message/OTP column name? (e.g.: message, sms):"), reply_markup=get_cancel_kb())
            else:
                 send_message(chat_id, render_body_text("❌ Please enter a valid number serial!"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_msg_col_name" and text:
            temp_data[chat_id]["p_data"]["msg_col_name"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_msg_col_idx"
            send_message(chat_id, render_body_text("8️⃣ <b>Message Column Serial</b>\n➡️ Message column serial? (e.g.: 5, 7):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_cpanel_msg_col_idx" and text:
            if text.isdigit():
                temp_data[chat_id]["p_data"]["msg_col_idx"] = int(text)
                temp_data[chat_id]["p_data"]["login_status"] = "⏳ Pending Auto-Login..."
                
                # Save the panel configuration
                bot_settings["panels"].append(temp_data[chat_id]["p_data"])
                save_db()
                
                send_message(chat_id, render_body_text(f"{PEM['ok']} <b>Auto Captcha Panel Added Successfully!</b>\n          ।"), reply_markup=main_menu(chat_id))
                
                msg_id = temp_data[chat_id]["msg_id"]
                handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_cpt_panels", "id": "internal"})
                
                del user_states[chat_id]
                del temp_data[chat_id]
            else:
                 send_message(chat_id, render_body_text("❌ Please enter a valid number serial!"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_low_stock_limit" and text:
            val = text.strip()
            if not val.isdigit():
                send_message(chat_id, render_body_text("❌ Please send a valid number (e.g. 50)."), reply_markup=get_cancel_kb())
                return
            bot_settings["low_stock_threshold"] = int(val)
            _low_stock_alerted.clear()
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(build_low_stock_text()), reply_markup=low_stock_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        # --- User Management Flows ---
        elif state == "wait_for_um_bal_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                send_message(chat_id, render_body_text("❌ Invalid ID! Please send a numeric User ID."), reply_markup=get_cancel_kb())
                return
            target_uid = int(target_uid_str)
            doc_data = get_user(target_uid)
            if not doc_data:
                send_message(chat_id, render_body_text("❌ User not found in database!"), reply_markup=get_cancel_kb())
                return
            current_bal = doc_data.get('balance', 0.0)
            temp_data[chat_id]["target_uid"] = target_uid
            user_states[chat_id] = "wait_for_um_bal_amt"
            send_message(chat_id, render_body_text(f"✅ User found!\n💰 Current Balance: {format_bdt(current_bal)} \n\n📝 Send the amount in BDT to ADD (e.g. 50) or REMOVE (e.g. -50):"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_um_bal_amt" and text:
            try:
                amt_bdt = float(text.strip())
                amt = bdt_to_internal(amt_bdt)
                target_uid = temp_data[chat_id]["target_uid"]
                update_balance(target_uid, amt)
                send_message(chat_id, render_body_text(f"{PEM['ok']} Balance updated successfully for {target_uid}!"), reply_markup=main_menu(chat_id))
                send_message(target_uid, render_body_text(f"🔔 Your balance has been adjusted by <b>{amt_bdt:.2f} BDT</b> by an Admin."))
                del user_states[chat_id]
                del temp_data[chat_id]
            except ValueError:
                send_message(chat_id, render_body_text("❌ Invalid amount! Please send a number."), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_um_ban_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                send_message(chat_id, render_body_text("❌ Invalid ID!"), reply_markup=get_cancel_kb())
                return
            target_uid = int(target_uid_str)
            u_data = get_user(target_uid)
            current_status = u_data.get("banned", False)
            new_status = not current_status
            with db_lock:
                conn = get_db_conn()
                conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if new_status else 0, target_uid))
                conn.commit()
                conn.close()
            if target_uid in user_cache: user_cache[target_uid]["banned"] = new_status
            user_banned_cache[target_uid] = {'banned': new_status, 'time': time.time()}
            status_text = "BANNED 🚫" if new_status else "UNBANNED ✅"
            send_message(chat_id, render_body_text(f"✅ User {target_uid} has been {status_text}!"), reply_markup=main_menu(chat_id))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_um_edit_bal" and text:
            t_uid = temp_data[chat_id].get("target_uid")
            raw = text.strip()
            try:
                if raw.startswith("+") or raw.startswith("-"):
                    delta = bdt_to_internal(float(raw))
                    update_balance(t_uid, delta)
                else:
                    new_bal = bdt_to_internal(float(raw))
                    with db_lock:
                        conn = get_db_conn()
                        conn.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, t_uid))
                        conn.commit()
                        conn.close()
                    if t_uid in user_cache: user_cache[t_uid]["balance"] = new_bal
                if t_uid in user_cache: user_cache.pop(t_uid, None)
                u_new = get_user(t_uid)
                del user_states[chat_id]
                del temp_data[chat_id]
                send_message(chat_id, render_body_text(
                    f"✅ <b>Balance Updated!</b>\n\n"
                    f"🆔 User: <code>{t_uid}</code>\n"
                    f"💰 New Balance: <b>{format_bdt(u_new.get('balance', 0.0))}</b>"
                ), reply_markup={"inline_keyboard": [[{"text": "◀ Back to User", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"um_view_user_{t_uid}", "style": "success"}]]})
            except:
                send_message(chat_id, render_body_text(
                    "❌ Invalid amount!\n\nSend a number like <code>10.5</code>, <code>+5</code>, or <code>-3</code>:"
                ), reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"um_view_user_{t_uid}", "style": "danger"}]]})
            return

        elif state == "wait_for_um_prof_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                send_message(chat_id, render_body_text("❌ Invalid ID!"), reply_markup=get_cancel_kb())
                return
            target_uid = int(target_uid_str)
            data = get_user(target_uid)
            if not data:
                send_message(chat_id, render_body_text("❌ User not found in database!"), reply_markup=get_cancel_kb())
                return
            is_verified = True if data.get('total_otps', 0) > 0 else data.get('verified', False)
            prof_text = f"""➖➖➖➖➖➖➖➖
👤 <b>USER PROFILE</b>
➖➖➖➖➖➖➖➖
🆔 ID: <code>{target_uid}</code>
💰 Balance: {format_bdt(data.get('balance', 0.0))}
🤝 Total Refers: {data.get('total_refers', 0)}
🔐 Total OTPs: {data.get('total_otps', 0)}
✅ Verified: {is_verified}
🚫 Banned: {data.get('banned', False)}
➖➖➖➖➖➖➖➖"""
            kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "user_management", "style": "primary"}]]}
            send_message(chat_id, render_body_text(prof_text), reply_markup=kb)
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        # --- Database Upload Flow ---
        elif state == "wait_for_db_upload" and "document" in msg:
            if not is_admin(chat_id):
                send_message(chat_id, render_body_text(f"{PEM['no']} This action is restricted to admins only."))
                if chat_id in user_states: del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
                return
            doc = msg["document"]
            fname_doc = doc.get("file_name", "")
            if not fname_doc.endswith(".db"):
                send_message(chat_id, render_body_text(f"{PEM['no']} Please upload a valid <b>.db</b> file."), reply_markup=get_cancel_kb())
                return
            file_id = doc["file_id"]
            fi_resp = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            if not fi_resp.get("ok") or "result" not in fi_resp:
                send_message(chat_id, render_body_text(f"{PEM['no']} Failed to fetch the file from Telegram."), reply_markup=database_management_keyboard())
                if chat_id in user_states: del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
                return
            file_path_tg = fi_resp["result"]["file_path"]
            db_bytes = requests.get(f"{FILE_URL}{file_path_tg}").content
            import shutil as _shutil
            backup_path = DB_PATH + ".backup"
            # ── Foreign (key-value "docs") backup → convert & merge instead of replace ──
            _tmp_imp = os.path.join("data", "_import_tmp.db")
            try:
                with open(_tmp_imp, "wb") as _tf:
                    _tf.write(db_bytes)
                _is_docs = is_docs_backup(_tmp_imp)
            except Exception:
                _is_docs = False
            if _is_docs:
                try:
                    _st = import_docs_backup(_tmp_imp)
                    load_db()
                    threading.Thread(target=sync_users_list, daemon=True).start()
                    send_message(chat_id, render_body_text(
                        f"{PEM['ok']} <b>Backup Imported!</b>\n\n"
                        f"👤 Users: <b>{_st['users']}</b>\n"
                        f"💰 Total balance: <b>{_st['balance']:.2f}</b>\n"
                        f"🤝 Referral links restored: <b>{_st['referred']}</b>\n"
                        f"🏧 Withdrawals added: <b>{_st['withdrawals']}</b>\n"
                        f"📊 Leaderboard rows: <b>{_st['leaderboard']}</b>\n\n"
                        f"Your previous database was saved as a backup."
                    ), reply_markup=database_management_keyboard())
                except Exception as e:
                    send_message(chat_id, render_body_text(f"{PEM['no']} Import failed: {e}"), reply_markup=database_management_keyboard())
                finally:
                    try: os.remove(_tmp_imp)
                    except Exception: pass
                    if chat_id in user_states: del user_states[chat_id]
                    if chat_id in temp_data: del temp_data[chat_id]
                return
            try: os.remove(_tmp_imp)
            except Exception: pass
            try:
                _shutil.copy2(DB_PATH, backup_path)
                os.makedirs("data", exist_ok=True)
                with open(DB_PATH, "wb") as dbf:
                    dbf.write(db_bytes)
                load_db()
                threading.Thread(target=sync_users_list, daemon=True).start()
                if chat_id in user_states: del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
                send_message(chat_id, render_body_text(f"{PEM['ok']} <b>Database Replaced Successfully!</b>\n\nThe old database has been saved as a backup."), reply_markup=database_management_keyboard())
            except Exception as e:
                try: _shutil.copy2(backup_path, DB_PATH)
                except: pass
                send_message(chat_id, render_body_text(f"{PEM['no']} Failed to replace database: {e}"), reply_markup=database_management_keyboard())
                if chat_id in user_states: del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
            return

        elif state == "wait_for_test_service" and text:
            temp_data[chat_id]["service"] = text.strip()
            user_states[chat_id] = "wait_for_test_number"
            send_message(chat_id, render_body_text("📝 Send the Number (e.g. +8801712345678):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_number" and text:
            temp_data[chat_id]["number"] = text.strip()
            user_states[chat_id] = "wait_for_test_otp"
            send_message(chat_id, render_body_text("📝 Send the OTP (e.g. 556677):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_otp" and text:
            temp_data[chat_id]["otp"] = text.strip()
            user_states[chat_id] = "wait_for_test_lang"
            send_message(chat_id, render_body_text("📝 Send the Language (e.g. EN, AR):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_lang" and text:
            lang = text.strip().upper()
            if not lang.startswith("#"):
                lang = "#" + lang
                
            srv = temp_data[chat_id]["service"]
            num = temp_data[chat_id]["number"]
            otp = temp_data[chat_id]["otp"]
            
            masked = mask_number(num)
            prem_flag_html = get_flag_info_html(num)
            char, iso = get_flag_and_code(num)
            app_full_name, prem_app_html = get_service_info_html(srv)
            
            msg_text = render_body_text(f"╔═══════════════╗\n║ {_format_svc(app_full_name, prem_app_html)} {prem_flag_html} <b>{masked}</b> {lang}\n╚═══════════════╝")
            
            for fw in bot_settings["fw_groups"]:
                kb = build_otp_fw_kb(otp, fw)
                send_message(fw["chat_id"], msg_text, reply_markup={"inline_keyboard": kb})
                
            send_message(chat_id, render_body_text(f"{PEM['ok']} Test message formatted and sent to all Forward Groups!"), reply_markup=main_menu(chat_id))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_emoji_extract":
            entities = msg.get("entities", [])
            custom_emoji_id = None
            emoji_text = ""
            for ent in entities:
                if ent.get("type") == "custom_emoji":
                    custom_emoji_id = ent.get("custom_emoji_id")
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 0)
                    b_text = msg.get("text", "").encode('utf-16-le')
                    emoji_text = b_text[offset*2:(offset+length)*2].decode('utf-16-le')
                    break
            
            if custom_emoji_id:
                temp_data[chat_id] = {"id": custom_emoji_id, "char": emoji_text}
                user_states[chat_id] = "wait_for_emoji_details"
                send_message(chat_id, render_body_text(f"{PEM['ok']} Emoji ID  : <code>{custom_emoji_id}</code>\n\n📌         ।\n\n<b>:</b>\n`FLAG | 880 | BD | Bangladesh`\n\n`APP | WhatsApp`"), reply_markup=get_cancel_kb())
            else:
                send_message(chat_id, render_body_text(f"{PEM['no']}  Premium Emoji  !   Custom Emoji  ।"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_emoji_details" and text:
            parts = [p.strip() for p in text.split("|")]
            mode = parts[0].upper()
            eid = temp_data[chat_id]["id"]
            char = temp_data[chat_id]["char"]
            
            if mode == "FLAG" and len(parts) == 4:
                code, iso, name = parts[1], parts[2], parts[3]
                bot_settings["premium_flags"][code] = {"char": char, "iso": iso.upper(), "name": name, "id": eid}
                save_db()
                send_message(chat_id, render_body_text(f"{PEM['ok']} Flag Emoji  !\nCode: {code} | Name: {name}"), reply_markup=emoji_settings_keyboard())
            elif mode == "APP" and len(parts) == 2:
                name = parts[1]
                bot_settings["premium_apps"][name.upper()] = {"char": char, "id": eid, "name": name.title()}
                save_db()
                send_message(chat_id, render_body_text(f"{PEM['ok']} App Emoji  !\nName: {name}"), reply_markup=emoji_settings_keyboard())
            else:
                send_message(chat_id, render_body_text(f"{PEM['no']}  !\n\n :\n`FLAG | 880 | BD | Bangladesh`\n`APP | WhatsApp`"))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state in ["wait_for_flag_txt", "wait_for_app_txt"] and "document" in msg:
            doc = msg["document"]
            if not doc["file_name"].endswith(".txt"):
                send_message(chat_id, render_body_text(f"{PEM['no']} Please upload a .txt file only."))
                return
            file_id = doc["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            content = requests.get(f"{FILE_URL}{file_path}").text
            
            mode = "flags" if state == "wait_for_flag_txt" else "apps"
            count = 0
            
            if mode == "flags":
                for line in content.splitlines():
                    json_match = re.search(r'(\{.*\})', line)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            char = data.get("emoji")
                            eid = data.get("id")
                            
                            prefix_str = line[:json_match.start()].strip()
                            code_match = re.search(r'\((\d+)\)', prefix_str)
                            iso_match = re.search(r'\(([A-Za-z]+)\)', prefix_str)
                            
                            if code_match and iso_match and char and eid:
                                code = code_match.group(1)
                                iso = iso_match.group(1).upper()
                                name = prefix_str.replace(f"({code})", "").replace(f"({iso_match.group(1)})", "").replace(char, "").strip()
                                bot_settings["premium_flags"][code] = {"char": char, "iso": iso, "name": name, "id": eid}
                                count += 1
                        except: pass
            else:
                for line in content.splitlines():
                    json_match = re.search(r'(\{.*\})', line)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            char = data.get("emoji")
                            eid = data.get("id")
                            
                            name_part = line[:json_match.start()].strip()
                            name = name_part.replace(char, '').strip() if char else name_part
                            
                            if char and eid and name:
                                bot_settings["premium_apps"][name.upper()] = {"char": char, "id": eid, "name": name}
                                count += 1
                        except: pass
            
            save_db()
            send_message(chat_id, render_body_text(f"{PEM['ok']} Successfully loaded {count} Emojis!"), reply_markup=emoji_settings_keyboard())
            del user_states[chat_id]
            return

        elif state == "wait_for_broadcast":
            msg_id = msg["message_id"]
            send_message(chat_id, render_body_text(f"{PEM['ok']} Broadcast started..."))
            threading.Thread(target=broadcast_copymessage, args=(chat_id, msg_id)).start()
            del user_states[chat_id]
            return

        elif state == "wait_for_txt" and "document" in msg:
            doc = msg["document"]
            if not doc["file_name"].endswith(".txt"):
                send_message(chat_id, render_body_text(f"{PEM['no']} Please upload a .txt file only."))
                return
            file_id = doc["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            file_content = requests.get(f"{FILE_URL}{file_path}").text
            
            temp_data[chat_id] = {"numbers": file_content.splitlines(), "filename": doc["file_name"]}
            user_states[chat_id] = "wait_for_service"
            send_message(chat_id, render_body_text(f"{PEM['ok']} File received.\n\n📌 Enter the service name (e.g., WHATSAPP):"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_service" and text:
            service = text.upper()
            temp_data[chat_id]["service"] = service

            # Auto-detect country from uploaded numbers to check for existing batch
            raw_nums = temp_data[chat_id].get("numbers", [])
            auto_country_key = "UNKNOWN"
            auto_country_name = "Unknown"
            flags_db_up = bot_settings.get("premium_flags", {})
            sorted_codes = sorted(flags_db_up.keys(), key=len, reverse=True)
            for line in raw_nums:
                first_num = line.strip().replace("+", "").replace(" ", "")
                if first_num:
                    for code in sorted_codes:
                        if first_num.startswith(code):
                            fd = flags_db_up[code]
                            auto_country_key = code
                            auto_country_name = fd.get("name", code)
                            break
                    break
            temp_data[chat_id]["auto_country_key"] = auto_country_key
            temp_data[chat_id]["auto_country_name"] = auto_country_name

            # If same service+country batch already exists, offer suffix option
            existing_bid = _fs_batch_id(service, auto_country_key)
            if existing_bid in number_batches:
                existing_count = len(number_batches[existing_bid].get("numbers", []))
                user_states[chat_id] = "wait_for_country_suffix"
                suffix_kb = {"inline_keyboard": [
                    [{"text": "⏭ Merge (no suffix)", "callback_data": "skip_country_suffix", "style": "success"}],
                    [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
                ]}
                send_message(chat_id, render_body_text(
                    f"⚠️ <b>{service} | {auto_country_name}</b> already has <b>{existing_count}</b> numbers in stock!\n\n"
                    f"Enter a suffix to create a <b>separate batch</b> (e.g. <code>1</code>, <code>2</code>, <code>3</code>)\n"
                    f"Users will see: <b>{auto_country_name} 1</b>\n\n"
                    f"Or tap <b>Merge</b> to add to the existing batch."
                ), reply_markup=suffix_kb)
                return

            # No existing batch — go straight to OTP price
            user_states[chat_id] = "wait_for_otp_price"
            default_rate = _get_batch_price(service, auto_country_key)
            price_kb = {"inline_keyboard": [
                [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_otp_price", "style": "success"}],
                [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
            ]}
            send_message(chat_id, render_body_text(
                f"💰 <b>OTP Price for {service}</b>\n\n"
                f"Enter OTP reward per code for this service (e.g. <code>0.5</code>)\n"
                f"Enter <code>0</code> for no reward\n"
                f"Or tap <b>Skip</b> to use default rate (<b>{format_currency(default_rate)}</b>)"
            ), reply_markup=price_kb)
            return

        elif state == "wait_for_country_suffix" and text:
            suffix = text.strip()
            td = temp_data.get(chat_id, {})
            base_key = td.get("auto_country_key", "UNKNOWN")
            base_name = td.get("auto_country_name", "Unknown")
            service = td.get("service", "")
            # Reject suffix if that new batch already exists too
            new_country_key = f"{base_key} {suffix}"
            if _fs_batch_id(service, new_country_key) in number_batches:
                existing_c = len(number_batches[_fs_batch_id(service, new_country_key)].get("numbers", []))
                suffix_kb_r = {"inline_keyboard": [
                    [{"text": "⏭ Merge (no suffix)", "callback_data": "skip_country_suffix", "style": "success"}],
                    [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
                ]}
                send_message(chat_id, render_body_text(
                    f"❌ <b>{service} | {base_name} {suffix}</b> already has <b>{existing_c}</b> numbers!\n\n"
                    f"Suffix <b>{suffix}</b> is taken. Enter a <b>different suffix</b> (e.g. <code>2</code>, <code>3</code>):\n\n"
                    f"Or tap <b>Merge</b> to add to the original batch."
                ), reply_markup=suffix_kb_r)
                return
            temp_data[chat_id]["auto_country_key"] = new_country_key
            temp_data[chat_id]["auto_country_name"] = f"{base_name} {suffix}"
            user_states[chat_id] = "wait_for_otp_price"
            default_rate = _get_batch_price(service, new_country_key)
            price_kb = {"inline_keyboard": [
                [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_otp_price", "style": "success"}],
                [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
            ]}
            send_message(chat_id, render_body_text(
                f"✅ Suffix set! Users will see: <b>{base_name} {suffix}</b>\n\n"
                f"💰 <b>OTP Price for {service}</b>\n\n"
                f"Enter OTP reward per code (e.g. <code>0.5</code>)\n"
                f"Or tap <b>Skip</b> to use default rate (<b>{format_currency(default_rate)}</b>)"
            ), reply_markup=price_kb)
            return

        elif state == "wait_for_otp_price":
            if not text: return
            try:
                otp_price = float(text.strip())
                if otp_price < 0: raise ValueError
            except (ValueError, AttributeError):
                send_message(chat_id, render_body_text("❌ Enter a valid number (e.g. <code>0.5</code> or <code>0</code>)"), reply_markup=get_cancel_kb())
                return
            service     = temp_data[chat_id].get("service", "")
            country_key = temp_data[chat_id].get("auto_country_key", "")
            parsed_price = parse_currency_input(otp_price)
            # Save per-batch so Venezuela 1 / Venezuela 2 keep independent rates
            if country_key:
                bot_settings.setdefault("service_country_prices", {}).setdefault(service, {})[country_key] = parsed_price
            # Only use the service-level rate when there is no country key at all.
            # (Writing it here made every other country of this service change too.)
            else:
                bot_settings.setdefault("service_otp_prices", {})[service] = parsed_price
            save_db()
            _finalize_number_upload(chat_id)
            return

        elif state == "wait_for_upd_txt" and "document" in msg:
            doc = msg["document"]
            if not doc["file_name"].endswith(".txt"):
                send_message(chat_id, render_body_text(f"{PEM['no']} Please upload a .txt file only."))
                return
            file_id = doc["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            file_content = requests.get(f"{FILE_URL}{file_path}").text

            td = temp_data.get(chat_id, {})
            td["numbers"] = file_content.splitlines()
            td["filename"] = doc["file_name"]
            temp_data[chat_id] = td
            service = td.get("upd_service", "")
            country = td.get("upd_country", "")
            default_rate = bot_settings.get("service_otp_prices", {}).get(service, bot_settings.get("otp_reward", 0.1))

            # Check if batch already exists — offer suffix option
            existing_bid = _fs_batch_id(service, country)
            if existing_bid in number_batches:
                existing_count = len(number_batches[existing_bid].get("numbers", []))
                country_name, _ = _flag_display(country)
                user_states[chat_id] = "wait_for_upd_country_suffix"
                suffix_kb = {"inline_keyboard": [
                    [{"text": "⏭ Merge (no suffix)", "callback_data": "skip_upd_country_suffix", "style": "success"}],
                    [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
                ]}
                send_message(chat_id, render_body_text(
                    f"✅ File received!\n\n"
                    f"⚠️ <b>{service} | {country_name}</b> already has <b>{existing_count}</b> numbers in stock!\n\n"
                    f"Enter a suffix to create a <b>separate batch</b> (e.g. <code>1</code>, <code>2</code>, <code>3</code>)\n"
                    f"Users will see: <b>{country_name} 1</b>\n\n"
                    f"Or tap <b>Merge</b> to add to the existing batch."
                ), reply_markup=suffix_kb)
                return

            user_states[chat_id] = "wait_for_upd_price"
            price_kb = {"inline_keyboard": [
                [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_upd_price", "style": "success"}],
                [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
            ]}
            send_message(chat_id, render_body_text(
                f"{PEM['ok']} File received.\n\n💰 <b>OTP Price for {service}</b>\n\n"
                f"Enter OTP reward per code for this batch (e.g. <code>0.5</code>)\n"
                f"Enter <code>0</code> for no reward\n"
                f"Or tap <b>Skip</b> to use current rate (<b>{format_currency(default_rate)}</b>)"
            ), reply_markup=price_kb)
            return

        elif state == "wait_for_upd_country_suffix" and text:
            suffix = text.strip()
            td = temp_data.get(chat_id, {})
            base_country = td.get("upd_country", "UNKNOWN")
            base_name, _ = _flag_display(base_country)
            service = td.get("upd_service", "")
            # Reject suffix if that new batch already exists too
            new_country_key = f"{base_country} {suffix}"
            if _fs_batch_id(service, new_country_key) in number_batches:
                existing_c = len(number_batches[_fs_batch_id(service, new_country_key)].get("numbers", []))
                suffix_kb_r = {"inline_keyboard": [
                    [{"text": "⏭ Merge (no suffix)", "callback_data": "skip_upd_country_suffix", "style": "success"}],
                    [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
                ]}
                send_message(chat_id, render_body_text(
                    f"❌ <b>{service} | {base_name} {suffix}</b> already has <b>{existing_c}</b> numbers!\n\n"
                    f"Suffix <b>{suffix}</b> is taken. Enter a <b>different suffix</b> (e.g. <code>2</code>, <code>3</code>):\n\n"
                    f"Or tap <b>Merge</b> to add to the original batch."
                ), reply_markup=suffix_kb_r)
                return
            temp_data[chat_id]["upd_country"] = new_country_key
            user_states[chat_id] = "wait_for_upd_price"
            default_rate = _get_batch_price(service, new_country_key)
            price_kb = {"inline_keyboard": [
                [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_upd_price", "style": "success"}],
                [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
            ]}
            send_message(chat_id, render_body_text(
                f"✅ Suffix set! Users will see: <b>{base_name} {suffix}</b>\n\n"
                f"💰 <b>OTP Price for {service}</b>\n\n"
                f"Enter OTP reward per code (e.g. <code>0.5</code>)\n"
                f"Or tap <b>Skip</b> to use current rate (<b>{format_currency(default_rate)}</b>)"
            ), reply_markup=price_kb)
            return

        elif state == "wait_for_upd_price":
            if not text: return
            try:
                otp_price = float(text.strip())
                if otp_price < 0: raise ValueError
            except (ValueError, AttributeError):
                send_message(chat_id, render_body_text("❌ Enter a valid number (e.g. <code>0.5</code> or <code>0</code>)"), reply_markup=get_cancel_kb())
                return
            service      = temp_data[chat_id].get("upd_service", "")
            country_key2 = temp_data[chat_id].get("upd_country", "")
            parsed_price2 = parse_currency_input(otp_price)
            if country_key2:
                bot_settings.setdefault("service_country_prices", {}).setdefault(service, {})[country_key2] = parsed_price2
            else:
                bot_settings.setdefault("service_otp_prices", {})[service] = parsed_price2
            save_db()
            _finalize_update_number_upload(chat_id)
            return

        elif state == "wait_for_mr_rate":
            if not text: return
            try:
                new_rate = float(text.strip())
                if new_rate < 0: raise ValueError
            except (ValueError, AttributeError):
                send_message(chat_id, render_body_text("❌ Enter a valid number (e.g. <code>0.5</code> or <code>0</code>)"), reply_markup=get_cancel_kb())
                return
            td = temp_data.get(chat_id, {})
            service = td.get("mr_service", "")
            country = td.get("mr_country", "")
            orig_msg_id = td.get("mr_msg_id")
            bot_settings.setdefault("service_country_prices", {}).setdefault(service, {})[country] = parse_currency_input(new_rate)
            save_db()
            del user_states[chat_id]
            del temp_data[chat_id]
            country_name, flag_html = _flag_display(country)
            delete_message(chat_id, msg["message_id"])
            if orig_msg_id:
                edit_message(chat_id, orig_msg_id, render_body_text(
                    f"✅ <b>Rate Updated!</b>\n━━━━━━━━━━━━━━━━━━\n"
                    f"Service: <b>{service}</b>\n"
                    f"Country: {flag_html} <b>{country_name}</b>\n"
                    f"New Rate: <b>{format_currency(parse_currency_input(new_rate))}</b>"
                ), reply_markup={"inline_keyboard": [
                    [{"text": "« Back to Countries", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"mr_svc_{service}", "style": "danger"}]
                ]})
            return

        elif state == "wait_for_add_voltx_key" and text:
            bot_settings["voltx_keys"].append(text.strip())
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"✅ Voltx API Key Added! Total Keys: {len(bot_settings.get('voltx_keys', []))}"), reply_markup=voltx_control_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_add_stex_key" and text:
            bot_settings["stex_keys"].append(text.strip())
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"✅ STEX API Key Added! Total Keys: {len(bot_settings.get('stex_keys', []))}"), reply_markup=stex_control_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_add_ssc" and text:
            code = text.strip().replace("+", "")
            if "stex_search_countries" not in bot_settings: bot_settings["stex_search_countries"] = []
            bot_settings["stex_search_countries"].append(code)
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "stex_search_country", "id": "internal"})
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_stx_srv_name" and text:
            srv = text.strip().upper()
            if "stex_services" not in bot_settings: bot_settings["stex_services"] = {}
            if srv not in bot_settings["stex_services"]: bot_settings["stex_services"][srv] = {}
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "manage_stex_srv", "id": "internal"})
            del user_states[chat_id]
            return

        elif state == "wait_stx_cnt_name" and text:
            cnt = text.strip()
            srv = temp_data[chat_id]["srv"]
            if cnt not in bot_settings["stex_services"][srv]: bot_settings["stex_services"][srv][cnt] = []
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"stx_srv_{srv}", "id": "internal"})
            del user_states[chat_id]
            return

        elif state == "wait_stx_addr" and text:
            srv, cnt = temp_data[chat_id]["srv"], temp_data[chat_id]["cnt"]
            new_range = text.strip().replace("+", "")
            if new_range not in bot_settings["stex_services"][srv][cnt]:
                bot_settings["stex_services"][srv][cnt].append(new_range)
                if "stex_search_countries" not in bot_settings:
                    bot_settings["stex_search_countries"] = []
                if new_range not in bot_settings["stex_search_countries"]:
                    bot_settings["stex_search_countries"].append(new_range)
                save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"stx_cnt_{srv}_{cnt}", "id": "internal"})
            del user_states[chat_id]
            return


        elif state == "wait_for_add_vsc" and text:
            code = text.strip().replace("+", "")
            if "voltx_search_countries" not in bot_settings: bot_settings["voltx_search_countries"] = []
            bot_settings["voltx_search_countries"].append(code)
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "voltx_search_country", "id": "internal"})
            del user_states[chat_id]
            del temp_data[chat_id]
            return




        elif state == "wait_vx_srv_name" and text:
            srv = text.strip().upper()
            if "voltx_services" not in bot_settings: bot_settings["voltx_services"] = {}
            if srv not in bot_settings["voltx_services"]: bot_settings["voltx_services"][srv] = {}
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "manage_voltx_srv", "id": "internal"})
            del user_states[chat_id]
            return

        elif state == "wait_vx_cnt_name" and text:
            cnt = text.strip()
            srv = temp_data[chat_id]["srv"]
            if cnt not in bot_settings["voltx_services"][srv]: bot_settings["voltx_services"][srv][cnt] = []
            save_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"vx_srv_{srv}", "id": "internal"})
            del user_states[chat_id]
            return

        elif state == "wait_vx_addr" and text:
            srv, cnt = temp_data[chat_id]["srv"], temp_data[chat_id]["cnt"]
            new_range = text.strip().replace("+", "")
            
            if new_range not in bot_settings["voltx_services"][srv][cnt]:
                bot_settings["voltx_services"][srv][cnt].append(new_range)
                
                if "voltx_search_countries" not in bot_settings:
                    bot_settings["voltx_search_countries"] = []
                if new_range not in bot_settings["voltx_search_countries"]:
                    bot_settings["voltx_search_countries"].append(new_range)
                    
                save_db()
                
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"vx_cnt_{srv}_{cnt}", "id": "internal"})
            del user_states[chat_id]
            return

        elif state == "wait_for_add_wm" and text:
            bot_settings["w_methods"].append(text.strip())
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("💳 <b>WITHDRAWAL METHODS</b>\n\nManage your withdrawal methods below:"), reply_markup=w_methods_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_add_fj" and text:
            bot_settings["fj_channels"].append(parse_chat_id(text))
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("🔗 <b>FORCE JOIN SYSTEM</b>\nManage channels below:\n<i>(Note: For private links, use numeric IDs like -100...)</i>"), reply_markup=fj_settings_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return
            
        elif state == "wait_for_add_adm" and text:
            if text.isdigit():
                bot_settings["admins"].append(int(text))
                save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("👥 <b>ADMIN MANAGEMENT</b>\nManage your bot admins below:"), reply_markup=admin_settings_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_add_fw_id" and text:
            parsed_cid = parse_chat_id(text.strip())
            group_name = _get_chat_title(parsed_cid)
            bot_settings["fw_groups"].append({"chat_id": parsed_cid, "name": group_name, "buttons": []})
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return
            
        elif state == "wait_for_add_fw_btn" and text:
            fw_idx = temp_data[chat_id]["fw_idx"]
            if "-" in text:
                parts = text.split("-", 1)
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                emoji_id = None
                emoji_char = ""
                for ent in msg.get("entities", []):
                    if ent.get("type") == "custom_emoji":
                        emoji_id = ent.get("custom_emoji_id")
                        offset = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        b_text = text.encode('utf-16-le')
                        emoji_char = b_text[offset*2:(offset+length)*2].decode('utf-16-le')
                        break
                
                if emoji_char:
                    btn_text = btn_text.replace(emoji_char, "").strip()
                    
                btn_data = {"text": btn_text, "url": btn_url}
                if emoji_id:
                    btn_data["icon_custom_emoji_id"] = emoji_id
                    
                bot_settings["fw_groups"][fw_idx]["buttons"].append(btn_data)
                save_db()
            delete_message(chat_id, msg["message_id"])
            fw_grp = bot_settings['fw_groups'][fw_idx]
            fw_grp_lbl = fw_grp.get("name") or fw_grp['chat_id']
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"🛡 <b>Manage Group:</b> {fw_grp_lbl}"), reply_markup=specific_fw_group_keyboard(fw_idx))
            del user_states[chat_id]
            del temp_data[chat_id]
            return
            
        elif state == "wait_for_otp_link" and text:
            bot_settings["otp_link"] = text.strip()
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_fw_channel_link" and text:
            bot_settings["fw_channel_link"] = text.strip()
            save_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_panel_name" and text:
            p_name = text.strip()
            t_key = temp_data[chat_id].get("add_type", "api")
            msg_id = temp_data[chat_id]["msg_id"]
            delete_message(chat_id, msg["message_id"])
            
            if t_key == "logc":
                user_states[chat_id] = "wait_for_cpanel_url"
                temp_data[chat_id] = {"msg_id": msg_id, "p_data": {
                    "name": p_name, "type": "Auto Captcha Panel", "status": "ON", "records": 0, "login_status": "⏳ Pending First Login"
                }}
                edit_message(chat_id, msg_id, render_body_text("1️⃣ <b>Login URL</b>\n➡️ Panel  Login Link :"), reply_markup=get_cancel_kb())
                return
            else:
                bot_settings["panels"].append({
                    "name": p_name, "type": "API Panel", "status": "OFF", "api_url": "", "token": "", "records": 0
                })
                save_db()
                handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_api_panels", "id": "internal"})
                if chat_id in user_states: del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
                return

        elif state == "wait_for_p_api" and text:
            idx = temp_data[chat_id]["p_idx"]
            bot_settings["panels"][idx]["api_url"] = text.strip()
            save_db()
            delete_message(chat_id, msg["message_id"])
            p = bot_settings["panels"][idx]
            ui_text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>"
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(ui_text), reply_markup=panel_config_keyboard(idx))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_p_tok" and text:
            idx = temp_data[chat_id]["p_idx"]
            bot_settings["panels"][idx]["token"] = text.strip()
            save_db()
            delete_message(chat_id, msg["message_id"])
            p = bot_settings["panels"][idx]
            ui_text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>"
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(ui_text), reply_markup=panel_config_keyboard(idx))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_p_fapi" and text:
            idx = temp_data[chat_id]["p_idx"]
            bot_settings["panels"][idx]["full_api_url"] = text.strip()
            save_db()
            delete_message(chat_id, msg["message_id"])
            p = bot_settings["panels"][idx]
            ui_text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Full API URL:</b> <code>{p.get('full_api_url', 'None')}</code>"
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(ui_text), reply_markup=panel_config_keyboard(idx))
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_p_rec" and text:
            if text.isdigit():
                idx = temp_data[chat_id]["p_idx"]
                bot_settings["panels"][idx]["records"] = int(text)
                save_db()
                delete_message(chat_id, msg["message_id"])
                p = bot_settings["panels"][idx]
                
                ui_text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>"
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(ui_text), reply_markup=panel_config_keyboard(idx))
            else:
                send_message(chat_id, render_body_text("❌ Please enter a valid number! Try again."), reply_markup=get_cancel_kb())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_p_int" and text:
            if text.isdigit() and 1 <= int(text) <= 30:
                idx = temp_data[chat_id]["p_idx"]
                bot_settings["panels"][idx]["fetch_interval"] = int(text)
                save_db()
                delete_message(chat_id, msg["message_id"])
                p = bot_settings["panels"][idx]
                ui_text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>\n<b>Fetch Delay:</b> {p.get('fetch_interval', 2)}s"
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(ui_text), reply_markup=panel_config_keyboard(idx))
            else:
                send_message(chat_id, render_body_text("❌ Please enter a number between 1 and 30 (seconds)! Try again."), reply_markup=get_cancel_kb())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "set_dxa":
            msg_id = temp_data[chat_id]["msg_id"]
            key = temp_data[chat_id]["key"]
            try:
                if key in ("min_withdraw", "ref_commission"): bot_settings[key] = parse_currency_input(float(text))
                elif key in ["otp_reward", "refer_reward"]: bot_settings[key] = float(text)
                elif key in ["cooldown", "num_req", "num_share", "traffic_window", "num_expiry", "old_num_window"]: bot_settings[key] = int(text)
                else: bot_settings[key] = text
                save_db()
                delete_message(chat_id, msg["message_id"])
                edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())
            except:
                delete_message(chat_id, msg["message_id"])
                edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>\n\n❌ Invalid value!"), reply_markup=dxa_control_keyboard())
            del user_states[chat_id]
            del temp_data[chat_id]
            return

        elif state == "wait_for_withdraw_amount" and text:
            msg_id_to_edit = temp_data[chat_id].get("msg_id")
            try:
                # The user types the amount in the displayed currency (e.g. 400 BDT);
                # convert to the internal USDT base unit used for balances.
                _typed = float(text.strip())
                bal = temp_data[chat_id]["balance"]
                min_w = bot_settings['min_withdraw']
                _rate = _bdt_rate()
                amount = parse_currency_input(_typed)
                # Balance is shown rounded to 2 decimals; typing the shown full
                # balance must not fail because of rounding.
                if _typed <= round(bal * _rate, 2) + 0.005:
                    amount = min(amount, bal)

                if amount < min_w - 1e-9:
                    if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text(f"❌ Minimum withdrawal is {format_currency(min_w)}!\n💰 Balance: {format_currency(bal)} \n\n📝 Enter again:"), reply_markup=get_cancel_kb())
                    return
                if amount > bal:
                    if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text(f"❌ You don't have enough balance!\n💰 Balance: {format_currency(bal)} \n\n📝 Enter again:"), reply_markup=get_cancel_kb())
                    return
                    
                temp_data[chat_id]["amount"] = amount
                user_states[chat_id] = "wait_for_withdraw_number"
                if msg_id_to_edit:
                    chosen_method = temp_data[chat_id]['method']
                    addr_prompt = f"✅ Amount: {format_currency(amount)} \n\n📱 Now send your <b>{chosen_method}</b> account number:"
                    edit_message(chat_id, msg_id_to_edit, render_body_text(addr_prompt), reply_markup=get_cancel_kb())
            except ValueError:
                if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text("❌ Invalid amount!\n\n📝 Please send a valid number:"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_2fa_key" and text:
            msg_id_to_edit = temp_data.get(chat_id, {}).get("msg_id")
            delete_message(chat_id, msg.get("message_id"))

            if not msg_id_to_edit:
                send_message(chat_id, render_body_text("❌ Error: Message not found. Try again."))
                del user_states[chat_id]
                return

            try:
                secret = text.strip().replace(" ", "")
                totp = pyotp.TOTP(secret)
                code = totp.now()
                remaining_time = 30 - (int(time.time()) % 30)
                
                success_txt = (
                    f"━━━━━━━━━━━━━━━\n"
                    f"《 🔐 <b>2FA CODE</b> 》\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🔐 <b>CODE:</b> <code>{code}</code>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🕓 <b>EXPIRES IN:</b> {remaining_time}s\n"
                    f"━━━━━━━━━━━━━━━"
                )
                kb = [[{"text": f"Click to copy {code}", "icon_custom_emoji_id": "6068830682359010545", "copy_text": {"text": code}, "style": "success"}],
                      [{"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": f"ref_2fa_{secret}", "style": "primary"},
                       {"text": "New Code", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "gen_2fa", "style": "danger"}],
                      [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]
                
                edit_message(chat_id, msg_id_to_edit, render_body_text(success_txt), reply_markup={"inline_keyboard": kb})
                del user_states[chat_id]
                if chat_id in temp_data: del temp_data[chat_id]
            except Exception:
                error_txt = "━━━━━━━━━━━━━━━\n《 🔑 <b>ENTER 2FA KEY</b> 》\n━━━━━━━━━━━━━━━\n📝 <b>SEND YOUR 2FA SECRET KEY</b>\n━━━━━━━━━━━━━━━\n❌ <b>Invalid Secret Key! Try again.</b>\n━━━━━━━━━━━━━━━"
                cancel_kb = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_2fa", "style": "danger"}]]}
                edit_message(chat_id, msg_id_to_edit, render_body_text(error_txt), reply_markup=cancel_kb)
            return

        elif state == "wait_for_withdraw_number":
            msg_id_to_edit = temp_data[chat_id].get("msg_id")

            method = temp_data[chat_id]["method"]
            amount = temp_data[chat_id]["amount"]
            number = text.strip()

            req_id = f"W_{str(uuid.uuid4())[:6].upper()}"

            first_name = msg.get("from", {}).get("first_name", "User")
            last_name  = msg.get("from", {}).get("last_name", "")
            # html.escape prevents names with <, >, &, " from breaking Telegram
            # HTML in the admin withdrawal notification messages.
            full_name  = html.escape(f"{first_name} {last_name}".strip())

            auto_w    = bot_settings.get("auto_withdraw", False)
            db_status = "approved" if auto_w else "pending"

            # The withdrawal row is the source of truth.  Persist it before
            # notifying the admin so a restart cannot lose the request.
            try:
                update_balance(chat_id, -amount)
                with db_lock:
                    conn = get_db_conn()
                    cursor = conn.execute(
                        "INSERT INTO withdrawals "
                        "(user_id,amount,method,account,request_id,status,timestamp) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (chat_id, amount, method, number, req_id, db_status, time.time())
                    )
                    conn.commit()
                    withdrawal_db_id = cursor.lastrowid
                    conn.close()
                pending_withdrawals[req_id] = {
                    "user_id": chat_id,
                    "amount": amount,
                    "method": method,
                    "number": number,
                    "full_name": full_name,
                    "db_id": withdrawal_db_id,
                }
            except Exception as db_error:
                # Never silently discard a withdrawal or keep the balance
                # deducted when SQLite cannot persist the request.
                try:
                    update_balance(chat_id, amount)
                except Exception:
                    pass
                pending_withdrawals.pop(req_id, None)
                user_states.pop(chat_id, None)
                temp_data.pop(chat_id, None)
                error_text = (
                    "❌ Could not save your withdrawal request.\n"
                    "Your balance was not changed. Please try again."
                )
                print(f"[withdrawal] persist error: {db_error}")
                if msg_id_to_edit:
                    edit_message(
                        chat_id,
                        msg_id_to_edit,
                        render_body_text(error_text),
                        reply_markup=kb if "kb" in locals() else None,
                    )
                else:
                    send_message(chat_id, render_body_text(error_text))
                return

            kb = {"inline_keyboard": [[{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]}
            method_eid        = get_payment_emoji_id(method)
            method_emoji_html = f'<tg-emoji emoji-id="{method_eid}">💳</tg-emoji>'

            if auto_w:
                if pending_withdrawals.get(req_id):
                    del pending_withdrawals[req_id]
                if bot_settings.get("w_group"):
                    masked_num = f"{number[:4]}❖AUTO❖{number[-3:]}" if len(number) >= 7 else number
                    admin_msg  = f"🤖 <b>AUTO WITHDRAWAL APPROVED</b>\n\n👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>{full_name}</a>\n💳 <b>AMOUNT:</b> {format_currency(amount)}\n🍏 <b>NUMBER:</b> <code>{masked_num}</code>\n🏦 <b>METHOD:</b> {method}\n\n🧾 <b>REQ ID:</b> {req_id}\n✅ <b>AUTO-APPROVED</b>"
                    send_message(bot_settings["w_group"], render_body_text(admin_msg))
                success_text = f"{PEM['ok']} <b>Withdrawal Approved!</b>\n\n🧾 <b>Req ID:</b> {req_id}\n💰 <b>Amount:</b> {format_currency(amount)}\n{method_emoji_html} <b>Method:</b> {method}\n📱 <b>Number:</b> <code>{number}</code>\n\n⚡ <b>Auto-processed. Payment will be sent shortly.</b>"

            else:
                # Manual approval — send to admin group
                if bot_settings["w_group"]:
                    admin_msg = f"🎙 <b>NEW WITHDRAWAL REQUEST</b>\n\n👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>{full_name}</a>\n💳 <b>WITHDRAWAL:</b> {format_currency(amount)}\n🍏 <b>NUMBER:</b> <code>{number}</code>\n🏦 <b>METHOD:</b> {method}\n\n🧾 <b>REQ ID:</b> {req_id}\n👨‍⚖️ <b>PROCESSED BY ADMIN</b>"
                    kb_admin  = {"inline_keyboard": [[{"text": "APPROVE", "icon_custom_emoji_id": "5352694861990501856", "callback_data": f"wapp_{req_id}", "style": "success"}, {"text": "REJECT", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"wrej_{req_id}", "style": "danger"}]]}
                    send_message(bot_settings["w_group"], render_body_text(admin_msg), reply_markup=kb_admin)
                success_text = f"{PEM['ok']} Your withdrawal request has been submitted!\n\n🧾 <b>Req ID:</b> {req_id}\n💰 <b>Amount:</b> {format_currency(amount)}\n{method_emoji_html} <b>Method:</b> {method}\n📱 <b>Number:</b> <code>{number}</code>"
            
            if msg_id_to_edit:
                edit_message(chat_id, msg_id_to_edit, render_body_text(success_text), reply_markup=kb)
            else:
                send_message(chat_id, render_body_text(success_text), reply_markup=kb)
                
            del user_states[chat_id]
            del temp_data[chat_id]
            return

    # --- Regular Commands ---
    if text.startswith("/start"):
        get_user(chat_id)

        # --- PROCESS PENDING REFERRAL ---
        u_data = get_user(chat_id)
        if u_data.get("referred_by") and not u_data.get("ref_paid"):
            inviter = u_data["referred_by"]
            add_referral(inviter, chat_id)
            with db_lock:
                conn = get_db_conn()
                conn.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (chat_id,))
                conn.commit()
                conn.close()
            if chat_id in user_cache: user_cache[chat_id]["ref_paid"] = 1

        c_msg = bot_settings["custom_messages"].get("start", {})
        raw_txt = c_msg.get("text", f"{PEM['hi']} Welcome!")
        # html.escape prevents names with HTML chars from breaking the Telegram
        # HTML parse mode if the start message template embeds {name} inside tags.
        _first_name = html.escape(_from.get("first_name") or _from.get("username") or "User")
        raw_txt = raw_txt.replace("{name}", _first_name).replace("{bot_name}", BOT_NAME).replace("{bot_username}", BOT_USERNAME)
        txt = render_body_text(raw_txt)
        kb = []
        for b in c_msg.get("buttons", []):
            b_copy = b.copy()
            if "style" not in b_copy: b_copy["style"] = "primary"
            kb.append([b_copy])
        if kb:
            send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})
            send_message(chat_id, render_body_text(f"{PEM['gear']} Navigation Menu:"), reply_markup=main_menu(chat_id))
        else:
            send_message(chat_id, txt, reply_markup=main_menu(chat_id))
            
    elif text == "TRAFFIC":
        txt, markup = build_traffic_ui()
        send_message(chat_id, txt, reply_markup=markup)
        
    elif text == "Refer":
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{chat_id}"
        refs = get_user(chat_id).get("total_refers", 0)

        txt = (
            f'<tg-emoji emoji-id="6159107733824999752">🌟</tg-emoji> <b>Refer</b>\n'
            f'══════════════════════\n'
            f'<tg-emoji emoji-id="5453957997418004470">👥</tg-emoji> Referrals: <b>{refs}</b>\n'
            f'<tg-emoji emoji-id="5409048419211682843">💵</tg-emoji> Commission: <b>{format_currency(bot_settings.get("ref_commission", 0.0))}</b> / OTP\n'
            f'──────────────────────\n'
            f'<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> <b>Your Invite Link:</b>\n'
            f'<code>{ref_link}</code>'
        )

        kb = [
            [{"text": "Copy Invite Link", "icon_custom_emoji_id": "5271604874419647061",
              "copy_text": {"text": ref_link}, "style": "success"}],
            [{"text": "CLOSE", "icon_custom_emoji_id": "5420130255174145507",
              "callback_data": "close_msg", "style": "danger"}]
        ]
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "WITHDRAWAL":
        if not bot_settings["withdraw_on"]:
            send_message(chat_id, render_body_text(f"{PEM['no']} Withdrawals are currently disabled."))
            return
        
        u_data = get_user(chat_id)
        bal = u_data.get('balance', 0.0)
        
        c_msg = bot_settings["custom_messages"].get("withdrawal", {})
        raw_txt = c_msg.get("text", "Withdrawal").replace("{bal}", format_currency(bal)).replace("{total_otp}", str(u_data.get('total_otps', 0))).replace("{total_ref}", str(u_data.get('total_refers', 0))).replace("{min_w}", format_currency(bot_settings['min_withdraw']))
        txt = render_body_text(raw_txt)
        
        kb = []
        for m in bot_settings["w_methods"]:
            emoji_id = get_payment_emoji_id(m.strip())
            kb.append([{"text": m.strip(), "icon_custom_emoji_id": emoji_id, "callback_data": f"sel_wm_{m.strip()}", "style": "primary"}])
        
        for b in c_msg.get("buttons", []): 
            b_copy = b.copy()
            if "style" not in b_copy: b_copy["style"] = "primary"
            kb.append([b_copy])
        kb.append([{"text": "Cancel", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "PROFILE":
        u_data = get_user(chat_id)
        bal = round(u_data.get('balance', 0.0), 4)
        total_refers = u_data.get('total_refers', 0)
        total_otps = u_data.get('total_otps', 0)
        today_str = datetime.now().strftime("%Y-%m-%d")
        d_entry = daily_otps.get(chat_id, {})
        today_otp_count = d_entry.get("count", 0) if d_entry.get("date") == today_str else 0
        first_name = msg.get("from", {}).get("first_name", "User")
        last_name = msg.get("from", {}).get("last_name", "")
        # html.escape prevents names with <, >, & breaking Telegram HTML
        # and silently killing the send (profile never arrives for that user).
        full_name = html.escape(f"{first_name} {last_name}".strip())
        profile_txt = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"《 {PEM['user']} MY PROFILE 》\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['user']} <b>Name:</b> {full_name}\n"
            f"{PEM['num']} <b>User ID:</b> <code>{chat_id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['money']} <b>Balance:</b> {format_currency(bal)}\n"
            f"{PEM['gift']} <b>Total Refers:</b> {total_refers}\n"
            f"{PEM['msg']} <b>Total OTPs:</b> {total_otps}\n"
            f"{PEM['graph']} <b>Today OTPs:</b> {today_otp_count}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        kb_rows = [
            [{"text": "WITHDRAW", "icon_custom_emoji_id": "5472250091332993630", "callback_data": "profile_withdraw", "style": "success"}],
            [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]
        ]
        kb = {"inline_keyboard": kb_rows}
        send_message(chat_id, render_body_text(profile_txt), reply_markup=kb)

    elif text == "LEADERBOARD":
        txt, markup = build_leaderboard_ui("today")
        send_message(chat_id, txt, reply_markup=markup)

    elif text == "Admin Panel" and is_admin(chat_id):
        send_message(chat_id, get_admin_text(), reply_markup=admin_panel_keyboard())

    elif text == "GET NUMBER":
        local_srvs = set([b["service"] for b in number_batches.values() if b["numbers"]])
        voltx_srvs = set(bot_settings.get("voltx_services", {}).keys())
        stex_srvs  = set(bot_settings.get("stex_services",  {}).keys())
        all_services = local_srvs.union(voltx_srvs).union(stex_srvs)
        # Hide services where every country is locked
        all_services = {s for s in all_services if _service_visible_to_users(s)}

        if not all_services:
            send_message(chat_id, render_body_text(f"{PEM['no']} No numbers or services available!"))
        else:
            c_msg = bot_settings["custom_messages"].get("get_number", {})
            txt = render_body_text(c_msg.get("text", f"{PEM['pin']} Select Service"))
            
            kb = []
            for s in all_services:
                kb.append([_svc_btn(s, f"g_s_{s}", "primary")])
            
            for b in c_msg.get("buttons", []): 
                b_copy = b.copy()
                if "style" not in b_copy: b_copy["style"] = "primary"
                kb.append([b_copy])
            kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
            
            send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})


    elif text == "SUPPORT":
        c_msg = bot_settings["custom_messages"].get("support", {})
        txt = render_body_text(c_msg.get("text", f"{PEM['msg']} Support"))
        if not txt.strip(): txt = render_body_text(f"{PEM['msg']} Support")
        kb = []
        for b in c_msg.get("buttons", []):
            b_copy = b.copy()
            if "style" not in b_copy: b_copy["style"] = "primary"
            kb.append([b_copy])
            
        sup_link = bot_settings.get("support_link", "")
        if sup_link:
            kb.insert(0, [{"text": "Contact Support", "icon_custom_emoji_id": "5337302974806922068", "url": sup_link, "style": "success"}])
            
        kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb} if kb else None)

def expire_previous_number(chat_id, current_msg_id=None, return_to_stock=False):
    if chat_id in user_active_sessions:
        prev_data = user_active_sessions[chat_id]
        prev_msg_id = prev_data["msg_id"]
        nums = prev_data["nums"]

        # Return numbers back to stock if requested (auto-expiry only)
        if return_to_stock and nums:
            service = prev_data.get("service", "")
            country = prev_data.get("country", "")
            if service and country:
                try:
                    b_id = _fs_batch_id(service, country)
                    with number_batches_lock:
                        if b_id not in number_batches:
                            number_batches[b_id] = {"filename": "restocked_expired.txt", "service": service, "country": country, "numbers": []}
                        for num in nums:
                            number_batches[b_id]["numbers"].append({"num": num, "shares": 0, "used_by": []})
                    _fs_sync_batch(b_id)
                    print(f"[expiry] Returned {len(nums)} number(s) to stock for {service}/{country} (user {chat_id})")
                except Exception as ex:
                    print(f"[expiry] Stock return error: {ex}")

        if not return_to_stock:
            _record_released_numbers(chat_id, nums, prev_data.get("service"), prev_data.get("country"))

        save_db()

        # Only show "Number Expired" on a DIFFERENT old message.
        # If same message (e.g. Change Number), we're about to overwrite it — skip.
        if current_msg_id is None or prev_msg_id != current_msg_id:
            kb = [[{"text": "Number Expired ⏰", "icon_custom_emoji_id": "5336997731481193790", "callback_data": "ignore", "style": "danger"}]]
            try:
                edit_message(chat_id, prev_msg_id, "ㅤ\n", reply_markup={"inline_keyboard": kb})
            except:
                pass
        del user_active_sessions[chat_id]

def _evict_number_from_other_sessions(nums: list, new_owner_id: int):
    """
    Remove given numbers from every active session that does NOT belong to
    new_owner_id.  Called right before assigning numbers to a new user so the
    same number can never live in two sessions simultaneously.
    """
    clean_new = [
        str(n).replace("+", "").replace(" ", "").replace("-", "").strip()
        for n in nums
    ]
    for uid in list(user_active_sessions.keys()):
        if uid == new_owner_id:
            continue
        sess = user_active_sessions.get(uid)
        if not sess:
            continue
        remaining = []
        evicted   = False
        for sn in sess.get("nums", []):
            sn_clean = str(sn).replace("+", "").replace(" ", "").replace("-", "").strip()
            if any(_numbers_match(sn_clean, cn) for cn in clean_new):
                evicted = True          # drop this number
            else:
                remaining.append(sn)
        if evicted:
            if remaining:
                user_active_sessions[uid]["nums"] = remaining
            else:
                # All numbers taken — end that session silently
                try:
                    prev_mid = sess.get("msg_id")
                    if prev_mid:
                        edit_message(uid, prev_mid, "ㅤ\n",
                            reply_markup={"inline_keyboard": [[
                                {"text": "Number Expired ⏰",
                                 "icon_custom_emoji_id": "5336997731481193790",
                                 "callback_data": "ignore", "style": "danger"}
                            ]]})
                except Exception:
                    pass
                user_active_sessions.pop(uid, None)

# ==========================================
# Callback Query Handler
# ==========================================
def _withdrawal_history_keyboard(page, total_pages):
    """Build a Telegram-safe premium history keyboard.

    Custom-emoji document IDs are intentionally not sent here. Telegram can
    reject an otherwise valid keyboard with DOCUMENT_INVALID when a custom
    emoji document is unavailable to this bot. Unicode icons provide the
    visual treatment while the supported button styles provide the colors.
    """
    nav = []
    if page > 0:
        nav.append({
            "text": "Prev",
            "callback_data": f"wh_page_{page - 1}",
            "style": "primary",
        })
    nav.append({
        "text": f"{page + 1}/{total_pages}",
        "callback_data": "wh_noop",
        "style": "primary",
    })
    if page < total_pages - 1:
        nav.append({
            "text": "Next",
            "callback_data": f"wh_page_{page + 1}",
            "style": "primary",
        })
    return {
        "inline_keyboard": [
            nav,
            [
                {
                    "text": "Refresh",
                    "callback_data": f"wh_page_{page}",
                    "style": "success",
                },
                {
                    "text": "Back",
                    "callback_data": "lb_main",
                    "style": "danger",
                },
            ],
        ]
    }


def _withdrawal_history_text(page):
    """Read and render one withdrawal-history page from SQLite.

    The query is deliberately bounded to ten rows.  The database lock is held
    only while SQLite is being read, never while formatting or calling
    Telegram.
    """
    page_size = 10
    max_records = 50
    with db_lock:
        conn = get_db_conn()
        try:
            total_row = conn.execute("SELECT COUNT(*) FROM withdrawals").fetchone()
            total = int(total_row[0]) if total_row else 0
            shown_total = min(total, max_records)
            total_pages = max(1, (shown_total + page_size - 1) // page_size)
            page = max(0, min(int(page), total_pages - 1))
            rows = conn.execute(
                """
                SELECT w.user_id, w.amount, w.status, u.username, u.first_name
                FROM withdrawals AS w
                LEFT JOIN users AS u ON u.user_id = w.user_id
                ORDER BY w.timestamp DESC, w.id DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, page * page_size),
            ).fetchall()
            status_rows = conn.execute(
                """
                SELECT LOWER(COALESCE(status, 'pending')), COUNT(*)
                FROM withdrawals
                GROUP BY LOWER(COALESCE(status, 'pending'))
                """
            ).fetchall()
        finally:
            conn.close()

    status_counts = {
        str(status).strip().lower(): int(count)
        for status, count in status_rows
    }
    approved_count = sum(
        status_counts.get(status, 0)
        for status in ("approved", "success", "paid")
    )
    rejected_count = sum(
        status_counts.get(status, 0)
        for status in ("rejected", "reject", "failed")
    )
    pending_count = max(0, total - approved_count - rejected_count)

    # These premium emoji IDs are already part of the bot's verified emoji
    # registry and are used elsewhere successfully.  Do not use arbitrary
    # uploaded document IDs here: Telegram may return DOCUMENT_INVALID.
    premium_header = PEM["admin"]
    premium_calendar = (
        f'<tg-emoji emoji-id="{GLOBAL_BODY_EMOJIS["📅"]}">📅</tg-emoji>'
    )
    premium_amount = PEM["money"]
    premium_approved = PEM["ok"]
    premium_pending = (
        f'<tg-emoji emoji-id="{GLOBAL_BODY_EMOJIS["⌛"]}">⌛</tg-emoji>'
    )
    premium_rejected = PEM["no"]

    lines = []
    for number, row in enumerate(rows, start=page * page_size + 1):
        user_id, amount, status, username, first_name = row
        if username:
            name = f"@{username}"
        elif first_name:
            name = str(first_name)
        else:
            name = f"User_{user_id}"

        normalized_status = str(status or "pending").strip().lower()
        status_icon = (
            premium_approved
            if normalized_status in {"approved", "success", "paid"}
            else premium_rejected
            if normalized_status in {"rejected", "reject", "failed"}
            else premium_pending
        )
        lines.append(
            f"<b>{number:02d}</b> "
            f"<a href=\"tg://user?id={html.escape(str(user_id))}\">"
            f"{html.escape(name)}</a> | "
            f"{premium_amount} "
            f"<b>{html.escape(format_currency(amount))}</b> | {status_icon}"
        )

    body = "\n".join(lines) if lines else "<i>No withdrawal records found.</i>"
    return (
        f"{premium_header} <b>WITHDRAWAL HISTORY</b>\n"
        f"{premium_calendar} "
        f"<i>Page {page + 1}/{total_pages} · {shown_total} of {total} shown</i>\n"
        f"{premium_approved} {approved_count}  "
        f"{premium_pending} {pending_count}  "
        f"{premium_rejected} {rejected_count}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}"
    ), page, total_pages


def _handle_withdrawal_history_callback(call):
    """Standalone callback handler for every wh_page_* button."""
    callback_id = call.get("id")
    message = call.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    back_keyboard = {
        "inline_keyboard": [[{
            "text": "Back",
            "callback_data": "lb_main",
            "style": "danger",
        }]]
    }

    if chat_id is None or message_id is None:
        print("[withdrawal-history] malformed callback: missing chat/message id")
        return

    try:
        if not is_admin(chat_id):
            _edit_or_send(
                chat_id, message_id, "🚫 Admins only!",
                reply_markup=back_keyboard, parse_mode="HTML",
            )
            return

        raw_page = str(call.get("data", "")).removeprefix("wh_page_")
        try:
            requested_page = int(raw_page)
        except (TypeError, ValueError):
            requested_page = 0

        text, page, total_pages = _withdrawal_history_text(requested_page)
        keyboard = _withdrawal_history_keyboard(page, total_pages)
        # Keep pagination in the same message.  This is the expected Telegram
        # menu interaction: Next/Prev replaces only the current page.
        result = edit_message(
            chat_id,
            message_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        if not result.get("ok"):
            # A deleted/stale message cannot be edited.  Do not lose the
            # history page in that edge case.
            print(
                f"[withdrawal-history] edit failed, using fallback: "
                f"{result.get('description', 'unknown')}"
            )
            result = send_message(
                chat_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        if not result.get("ok"):
            print(
                f"[withdrawal-history] Telegram response failed: "
                f"{result.get('description', 'unknown')}"
            )
    except Exception as exc:
        print(f"[withdrawal-history] failed chat={chat_id}: {exc}")
        traceback.print_exc()
        result = send_message(
            chat_id,
            "⚠️ Withdrawal history could not be loaded. Please press Refresh.",
            reply_markup=back_keyboard,
            parse_mode="HTML",
        )
        if not result.get("ok"):
            print(
                f"[withdrawal-history] error response failed: "
                f"{result.get('description', 'unknown')}"
            )
    finally:
        # The common callback entry point acknowledges the callback immediately
        # before routing here.  This final answer is intentionally omitted to
        # avoid duplicate callback responses.
        pass


def handle_callback(call):
    global total_assigned_stats, voltx_assigned_numbers, stex_assigned_numbers
    # Answer immediately — stops Telegram's loading spinner at once.
    try: threading.Thread(target=answer_callback, args=(call["id"],), daemon=True).start()
    except: pass

    chat_id = call["message"]["chat"]["id"]
    chat_type = call["message"]["chat"].get("type", "private")
    data = call.get("data", "")
    msg_id = call["message"]["message_id"]

    _from = call.get("from", {})
    if _from:
        register_user_local(chat_id, username=_from.get("username"), first_name=_from.get("first_name"))

    if _is_duplicate_callback(chat_id, data, msg_id):
        return

    # Withdrawal history has its own fail-safe path.  Route it after the
    # shared registration/debounce steps, but before force-join and the
    # generic menu logic so unrelated handlers cannot swallow this button.
    if data.startswith("wh_page_"):
        _handle_withdrawal_history_callback(call)
        return

    if chat_type != "private" and not (data.startswith("wapp_") or data.startswith("wrej_")):
        return

    if chat_type == "private":
        if is_user_banned(chat_id):
            answer_callback(call["id"], "🚫 You are banned from using this bot!", show_alert=True)
            return

        if bot_settings.get("maintenance_mode") and not is_admin(chat_id):
            answer_callback(call["id"], "🚧 Bot is under maintenance! Please check back later.", show_alert=True)
            return

        if not check_force_join(chat_id) and data != "check_fj":
            send_force_join_msg(chat_id)
            return

    if data == "check_fj":
        # Always clear the FJ cache for this user before re-checking so a
        # fresh getChatMember API call is made. Without this, the cached
        # False result (120 s TTL) is returned even after the user joins,
        # causing "You haven't joined all channels yet!" no matter what.
        _fj_cache.pop(chat_id, None)
        if check_force_join(chat_id):
            delete_message(chat_id, msg_id)
            send_message(chat_id, render_body_text(f"{PEM['ok']} Thanks for joining! You can now use the bot."), reply_markup=main_menu(chat_id))
            
            # --- PROCESS PENDING REFERRAL ---
            u_data = get_user(chat_id)
            if u_data.get("referred_by") and not u_data.get("ref_paid"):
                inviter = u_data["referred_by"]
                add_referral(inviter, chat_id)
                with db_lock:
                    conn = get_db_conn()
                    conn.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (chat_id,))
                    conn.commit()
                    conn.close()
                if chat_id in user_cache: user_cache[chat_id]["ref_paid"] = 1
        else:
            answer_callback(call["id"], "❌ You haven't joined all channels yet!", show_alert=True)
        return

    if data == "close_msg":
        delete_message(chat_id, msg_id)
        
    elif data == "cancel_state":
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]
        delete_message(chat_id, msg_id)

    elif data == "skip_country_suffix":
        if chat_id not in temp_data:
            answer_callback(call["id"], "⚠️ Session expired. Please upload again.", show_alert=True)
            return
        # No suffix — merge with existing batch; proceed to OTP price
        service = temp_data[chat_id].get("service", "")
        _ck_merge = temp_data[chat_id].get("auto_country_key", "")
        user_states[chat_id] = "wait_for_otp_price"
        default_rate = _get_batch_price(service, _ck_merge)
        price_kb = {"inline_keyboard": [
            [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_otp_price", "style": "success"}],
            [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>OTP Price for {service}</b>\n\n"
            f"Enter OTP reward per code (e.g. <code>0.5</code>)\n"
            f"Or tap <b>Skip</b> to use default rate (<b>{format_currency(default_rate)}</b>)"
        ), reply_markup=price_kb)
        answer_callback(call["id"])

    elif data == "skip_upd_country_suffix":
        if chat_id not in temp_data:
            answer_callback(call["id"], "⚠️ Session expired. Please upload again.", show_alert=True)
            return
        # No suffix — merge with existing batch; proceed to OTP price
        service = temp_data[chat_id].get("upd_service", "")
        _ck_upd_merge = temp_data[chat_id].get("upd_country", "")
        user_states[chat_id] = "wait_for_upd_price"
        default_rate = _get_batch_price(service, _ck_upd_merge)
        price_kb = {"inline_keyboard": [
            [{"text": f"⏭ Skip (Default: {format_currency(default_rate)})", "callback_data": "skip_upd_price", "style": "success"}],
            [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_state", "style": "danger"}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>OTP Price for {service}</b>\n\n"
            f"Enter OTP reward per code (e.g. <code>0.5</code>)\n"
            f"Or tap <b>Skip</b> to use current rate (<b>{format_currency(default_rate)}</b>)"
        ), reply_markup=price_kb)
        answer_callback(call["id"])

    elif data == "skip_otp_price":
        if chat_id not in temp_data or "service" not in temp_data.get(chat_id, {}):
            answer_callback(call["id"], "⚠️ Session expired. Please upload again.", show_alert=True)
            return
        _finalize_number_upload(chat_id)

    elif data == "skip_upd_price":
        if chat_id not in temp_data or "upd_service" not in temp_data.get(chat_id, {}):
            answer_callback(call["id"], "⚠️ Session expired. Please upload again.", show_alert=True)
            return
        _finalize_update_number_upload(chat_id)

    elif data == "cancel_2fa":
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]
        txt = "━━━━━━━━━━━━━━━\n《 🔐 <b>2FA ONLINE</b> 》\n━━━━━━━━━━━━━━━\n<i>Generate your 2FA security code instantly using your secret key.</i>\n━━━━━━━━━━━━━━━"
        kb = [[{"text": "Generate 2fa code", "icon_custom_emoji_id": "6068830682359010545", "callback_data": "gen_2fa", "style": "success"}],
              [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data == "gen_2fa":
        user_states[chat_id] = "wait_for_2fa_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        txt = "━━━━━━━━━━━━━━━\n《 🔑 <b>ENTER 2FA KEY</b> 》\n━━━━━━━━━━━━━━━\n📝 <b>SEND YOUR 2FA SECRET KEY</b>\n━━━━━━━━━━━━━━━"
        kb = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_2fa", "style": "danger"}]]}
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=kb)
        answer_callback(call["id"])

    elif data.startswith("ref_2fa_"):
        secret = data.replace("ref_2fa_", "")
        try:
            totp = pyotp.TOTP(secret)
            code = totp.now()
            remaining_time = 30 - (int(time.time()) % 30)
            
            success_txt = (
                f"━━━━━━━━━━━━━━━\n"
                f"《 🔐 <b>2FA CODE</b> 》\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🔐 <b>CODE:</b> <code>{code}</code>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🕓 <b>EXPIRES IN:</b> {remaining_time}s\n"
                f"━━━━━━━━━━━━━━━"
            )
            kb = [[{"text": f"Click to copy {code}", "icon_custom_emoji_id": "6068830682359010545", "copy_text": {"text": code}, "style": "success"}],
                  [{"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": f"ref_2fa_{secret}", "style": "primary"},
                   {"text": "New Code", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "gen_2fa", "style": "danger"}],
                  [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]
            
            edit_message(chat_id, msg_id, render_body_text(success_txt), reply_markup={"inline_keyboard": kb})
        except:
            answer_callback(call["id"], "❌ Error refreshing code!", show_alert=True)

    elif data == "cancel_dxa_edit":
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())
        
    elif data == "dummy_alert":
        answer_callback(call["id"], "This feature will be added later!", show_alert=True)
        
    elif data == "refresh_traffic":
        txt, markup = build_traffic_ui()
        edit_message(chat_id, msg_id, txt, reply_markup=markup)
        answer_callback(call["id"], "✅ Traffic Refreshed!", show_alert=False)

    elif data in ("lb_today", "lb_weekly", "lb_alltime"):
        mode = "today" if data == "lb_today" else ("weekly" if data == "lb_weekly" else "alltime")
        txt, markup = build_leaderboard_ui(mode)
        edit_message(chat_id, msg_id, txt, reply_markup=markup)
        answer_callback(call["id"], "✅ Refreshed!", show_alert=False)

    elif data.startswith("exp_rng_"):
        # BUG FIX: use slice instead of .replace() — .replace() strips ALL
        # occurrences of the prefix inside the string, corrupting service names
        # that happen to contain "exp_rng_".
        srv_query = data[len("exp_rng_"):]
        
        country_stats = {}
        current_time = time.time()
        _tw_sec = bot_settings.get("traffic_window", 60) * 60
        for t in recent_traffic:
            if current_time - t.get("time", 0) <= _tw_sec:
                if t.get("service", "").startswith(srv_query):
                    iso = t.get("iso", "XX")
                    flag = t.get("flag", "🌍")
                    if iso not in country_stats:
                        country_stats[iso] = {"count": 0, "flag": flag}
                    country_stats[iso]["count"] += 1
        
        if not country_stats:
            answer_callback(call["id"], "❌ No recent traffic found for this service!", show_alert=True)
            return
            
        kb = []
        for iso, c_data in sorted(country_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            count = c_data["count"]
            c_name = iso
            emoji_id = "5780471598922337683"
            for code, fdata in bot_settings.get("premium_flags", {}).items():
                if fdata.get("iso") == iso:
                    c_name = fdata.get("name", iso)
                    if "id" in fdata: emoji_id = fdata["id"]
                    break
            
            btn_text = f"{c_name} ({iso}) - {count} OTP"
            kb.append([{"text": btn_text, "icon_custom_emoji_id": emoji_id, "callback_data": f"exp_c_{srv_query}_{iso}", "style": "primary"}])
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "refresh_traffic", "style": "danger"}])
        
        app_full_name, prem_app_html = get_service_info_html(srv_query)
        edit_message(chat_id, msg_id, render_body_text(f"📊 <b>Explore Service: {_format_svc(app_full_name, prem_app_html)}</b>\n\nSelect a country to view available ranges:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("exp_c_"):
        # BUG FIX: data.split("_") broke when service names contained underscores
        # (e.g. "MOBILE_LEGENDS") — parts[2] and parts[3] would hold the wrong
        # fragments. ISO codes are always 2 uppercase letters; split on the last
        # underscore so the service name is preserved in full.
        _exp_c_payload = data[len("exp_c_"):]
        _exp_c_sep = _exp_c_payload.rfind("_")
        if _exp_c_sep == -1:
            answer_callback(call["id"], "❌ Invalid request.", show_alert=True)
            return
        srv_query = _exp_c_payload[:_exp_c_sep]
        iso_query = _exp_c_payload[_exp_c_sep + 1:]
        
        nums = []
        current_time = time.time()
        _tw_sec2 = bot_settings.get("traffic_window", 60) * 60
        for t in recent_traffic:
            if current_time - t.get("time", 0) <= _tw_sec2:
                if t.get("service", "").startswith(srv_query) and t.get("iso") == iso_query:
                    num = t.get("number", "").replace("+", "").strip()
                    if num: nums.append(num)
        
        if not nums:
            answer_callback(call["id"], "❌ No recent numbers found for this country!", show_alert=True)
            return
            

        known_ranges = set()
        for s_name, c_dict in bot_settings.get("voltx_services", {}).items():
            for c_name, r_list in c_dict.items():
                for r in r_list:
                    known_ranges.add(r)
                    
        sorted_known = sorted(list(known_ranges), key=len, reverse=True)
        
        r_counts = Counter()
        for num in nums:
            matched = False
            for r in sorted_known:
                if num.startswith(r):
                    r_counts[r] += 1
                    matched = True
                    break
            if not matched:
                if len(num) >= 7:
                    r_counts[num[:7]] += 1
                else:
                    r_counts[num] += 1
                    
        r_list = r_counts.most_common(12)
        
        kb = []
        for r, count in r_list:

            kb.append([{"text": f"{r} ({count})", "icon_custom_emoji_id": "5352862640592949843", "copy_text": {"text": r}, "style": "primary"}])
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"exp_rng_{srv_query}", "style": "danger"}])
        
        app_full_name, prem_app_html = get_service_info_html(srv_query)
        prem_flag_html = get_flag_info_html(iso_query)
        
        edit_message(chat_id, msg_id, render_body_text(f"📊 <b>Ranges for {_format_svc(app_full_name, prem_app_html)} - {prem_flag_html} {iso_query}</b>\n\nClick on any range to copy it."), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    # --- User Management Flows Integration ---
    elif data == "user_management":
        edit_message(chat_id, msg_id, get_user_management_text(), reply_markup=user_management_keyboard())

    elif data == "um_manage_balance":
        user_states[chat_id] = "wait_for_um_bal_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to Manage Balance:"), reply_markup=get_cancel_kb())
        
    elif data == "um_ban_unban":
        user_states[chat_id] = "wait_for_um_ban_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to Ban or Unban:"), reply_markup=get_cancel_kb())

    elif data == "um_user_profile":
        user_states[chat_id] = "wait_for_um_prof_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to View Profile:"), reply_markup=get_cancel_kb())

    elif data.startswith("um_user_list_"):
        page = int(data.split("_")[-1])
        per_page = 10
        with db_lock:
            conn = get_db_conn()
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows = conn.execute(
                "SELECT user_id, username, first_name, balance, banned FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?",
                (per_page, page * per_page)
            ).fetchall()
            conn.close()   # BUG FIX: connection was never closed → file-descriptor leak on every page flip
        total_pages = max(1, (total_users + per_page - 1) // per_page)
        kb = []
        for row in rows:
            uid, uname, fname, bal, banned = row
            label_name = f"@{uname}" if uname else (fname or str(uid))
            ban_mark = " 🚫" if banned else ""
            kb.append([{"text": f"{label_name}{ban_mark}  |  💰{format_bdt(bal)}", "callback_data": f"um_view_user_{uid}_{page}", "style": "primary"}])
        nav = []
        if page > 0:
            nav.append({"text": "◀ Prev", "callback_data": f"um_user_list_{page-1}", "style": "primary"})
        if (page + 1) < total_pages:
            nav.append({"text": "Next ▶", "callback_data": f"um_user_list_{page+1}", "style": "primary"})
        if nav: kb.append(nav)
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "user_management", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(
            f"👥 <b>User List</b>  —  Page {page+1}/{total_pages}\n"
            f"📊 Total: <b>{total_users}</b> users\n\n"
            f"<i>Tap a user to view full profile</i>"
        ), reply_markup={"inline_keyboard": kb})

    elif data.startswith("um_view_user_"):
        parts = data.split("_")
        # format: um_view_user_{uid}_{page}  or legacy um_view_user_{uid}
        target_uid = int(parts[3])
        back_page  = int(parts[4]) if len(parts) > 4 else 0
        u_data = get_user(target_uid)
        if not u_data:
            answer_callback(call["id"], "❌ User not found!", show_alert=True)
        else:
            is_verified = True if u_data.get('total_otps', 0) > 0 else u_data.get('verified', False)
            uname = u_data.get('username')
            fname = html.escape(u_data.get('first_name', '') or '')
            uname_str = f"@{html.escape(uname)}" if uname else "—"
            prof_text = (
                f"➖➖➖➖➖➖➖➖\n"
                f"<b>USER PROFILE</b>\n"
                f"➖➖➖➖➖➖➖➖\n"
                f"ID: <code>{target_uid}</code>\n"
                f"Name: {fname or '—'}\n"
                f"Username: {uname_str}\n"
                f"Balance: <b>{format_bdt(u_data.get('balance', 0.0))}</b>\n"
                f"Total Refers: {u_data.get('total_refers', 0)}\n"
                f"Total OTPs: {u_data.get('total_otps', 0)}\n"
                f"Verified: {'Yes' if is_verified else 'No'}\n"
                f"Banned: {'Yes' if u_data.get('banned', False) else 'No'}\n"
                f"➖➖➖➖➖➖➖➖"
            )
            is_banned = bool(u_data.get('banned', False))
            if is_banned:
                ban_btn_text = "Unban User"
                ban_btn_style = "success"
                ban_btn_icon = "5352694861990501856"
            else:
                ban_btn_text = "Ban User"
                ban_btn_style = "danger"
                ban_btn_icon = "5334807341109908955"
            kb = {"inline_keyboard": [
                [{"text": ban_btn_text, "icon_custom_emoji_id": ban_btn_icon, "callback_data": f"um_ban_{target_uid}_{back_page}", "style": ban_btn_style},
                 {"text": "Edit Balance", "icon_custom_emoji_id": "5190576863226933563", "callback_data": f"um_editbal_{target_uid}", "style": "primary"}],
                [{"text": "Back to List", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"um_user_list_{back_page}", "style": "primary"}]
            ]}
            edit_message(chat_id, msg_id, render_body_text(prof_text), reply_markup=kb)

    elif data.startswith("um_ban_"):
        # format: um_ban_{uid}_{page}
        ban_parts  = data.split("_")
        target_uid = int(ban_parts[2])
        back_page  = int(ban_parts[3]) if len(ban_parts) > 3 else 0
        u_data = get_user(target_uid)
        current_status = u_data.get("banned", False)
        new_status = not current_status
        with db_lock:
            conn = get_db_conn()
            conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if new_status else 0, target_uid))
            conn.commit()
            conn.close()
        if target_uid in user_cache: user_cache[target_uid]["banned"] = new_status
        user_banned_cache[target_uid] = {'banned': new_status, 'time': time.time()}
        answer_callback(call["id"], "🚫 User Banned!" if new_status else "✅ User Unbanned!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"um_view_user_{target_uid}_{back_page}", "id": "internal"})

    elif data.startswith("um_editbal_"):
        target_uid = int(data.split("_")[-1])
        u_data = get_user(target_uid)
        user_states[chat_id] = "wait_for_um_edit_bal"
        temp_data[chat_id] = {"msg_id": msg_id, "target_uid": target_uid}
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>Edit Balance</b>\n\n"
            f"🆔 User: <code>{target_uid}</code>\n"
            f"💳 Current Balance: <b>{format_bdt(u_data.get('balance', 0.0))}</b>\n\n"
            f"📝 Send new balance in BDT (e.g. <code>10.5</code>)\n"
            f"Or add/deduct (e.g. <code>+5</code> or <code>-3</code>):"
        ), reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"um_view_user_{target_uid}", "style": "danger"}]]})

    # --- Database Management ---
    elif data == "database_management":
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        with db_lock:
            _conn_tmp = get_db_conn()
            _ucnt = _conn_tmp.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            _conn_tmp.close()
        edit_message(chat_id, msg_id, render_body_text(
            f"{PEM['file']} <b>DATABASE MANAGEMENT</b>\n"
            f"— — — — — — — — — —\n"
            f"{PEM['user']} Total Users: <b>{_ucnt}</b>\n"
            f"{PEM['ok']} DB Path: <code>{DB_PATH}</code>\n"
            f"— — — — — — — — — —\n"
            f"<i>Download: Get the real database file.\n"
            f"Upload: Replace the current database with a new one.</i>"
        ), reply_markup=database_management_keyboard())

    elif data == "dl_database":
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        try:
            save_local_db()
            with open(DB_PATH, "rb") as _dbf:
                _db_bytes = _dbf.read()
            requests.post(f"{BASE_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": "✅ Bot Database — Real file", "parse_mode": "HTML"},
                files={'document': ('bot_database.db', _db_bytes)})
            answer_callback(call["id"], "✅ Downloading database...")
        except Exception as e:
            answer_callback(call["id"], f"❌ Error: {e}", show_alert=True)

    elif data == "upload_database":
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        user_states[chat_id] = "wait_for_db_upload"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text(
            f"{PEM['upload']} <b>Upload Database</b>\n\n"
            f"📂 Send your <b>.db</b> file.\n"
            f"⚠️ <b>Warning:</b> This will replace the current database!"
        ), reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "database_management", "style": "danger"}]]})

    elif data == "profile_withdraw":
        if not bot_settings["withdraw_on"]:
            answer_callback(call["id"], "❌ Withdrawals are currently disabled.", show_alert=True)
            return
        u_data = get_user(chat_id)
        bal = round(u_data.get('balance', 0.0), 4)
        min_w = bot_settings['min_withdraw']
        if not bot_settings["w_methods"]:
            answer_callback(call["id"], "❌ No withdrawal methods configured yet.", show_alert=True)
            return
        w_txt = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"《 {PEM['money']} WITHDRAWAL 》\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['money']} <b>Balance:</b> {format_currency(bal)}\n"
            f"{PEM['lock']} <b>Minimum:</b> {format_currency(min_w)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['pin']} <b>Select Withdrawal Method:</b>"
        )
        kb = []
        for m in bot_settings["w_methods"]:
            emoji_id = get_payment_emoji_id(m.strip())
            kb.append([{"text": m.strip(), "icon_custom_emoji_id": emoji_id, "callback_data": f"sel_wm_{m.strip()}", "style": "primary"}])
        kb.append([{"text": "Cancel", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(w_txt), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("sel_wm_"):
        method = data.replace("sel_wm_", "")
        bal = get_user(chat_id).get('balance', 0.0)
        min_w = bot_settings['min_withdraw']
        
        if bal < min_w:
            answer_callback(call["id"], f"❌ Minimum withdrawal: {format_currency(min_w)}\n💰 Balance: {format_currency(bal)}", show_alert=True)
            return
            
        temp_data[chat_id] = {"method": method, "balance": bal, "msg_id": msg_id}
        user_states[chat_id] = "wait_for_withdraw_amount"
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['ok']} Method: {method}\n💰 Available Balance: {format_currency(bal)}\n\n📝 Enter the amount you want to withdraw (Min: {format_currency(min_w)}):"), reply_markup=get_cancel_kb())
        answer_callback(call["id"])

    elif data == "otp_status":
        edit_message(chat_id, msg_id,
            render_body_text(build_otp_status_text()),
            reply_markup={"inline_keyboard": [
                [{"text": "🔄 Refresh", "icon_custom_emoji_id": "5395444784611480792",
                  "callback_data": "otp_status", "style": "success"}],
                [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176",
                  "callback_data": "system_settings", "style": "danger"}]
            ]})
        answer_callback(call["id"])

    elif data.startswith("sbc_yes_") or data.startswith("sbc_no_"):
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admin only!", show_alert=True)
            return
        _yes = data.startswith("sbc_yes_")
        _token = data.split("_", 2)[2]
        _pending = _pending_stock_broadcasts.pop(_token, None)
        if not _pending:
            edit_message(chat_id, msg_id, render_body_text("⚠️ This broadcast request has expired or was already handled."))
            answer_callback(call["id"])
            return
        if _yes:
            edit_message(chat_id, msg_id, render_body_text(
                f"{PEM['ok']} <b>Numbers added!</b>\n📢 Broadcasting to <b>{len(all_known_users)}</b> users..."))
            threading.Thread(target=_run_stock_broadcast, args=(_pending["txt"], _pending["kb"]), daemon=True).start()
        else:
            edit_message(chat_id, msg_id, render_body_text(
                f"{PEM['ok']} <b>Numbers added!</b>\n🔕 Broadcast skipped — no notification sent to users."))
        answer_callback(call["id"])

    elif data in ("low_stock_alert", "low_stock_toggle", "low_stock_set"):
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admin only!", show_alert=True)
            return
        if data == "low_stock_toggle":
            bot_settings["low_stock_alert_on"] = not bot_settings.get("low_stock_alert_on", True)
            _low_stock_alerted.clear()
            save_db()
        if data == "low_stock_set":
            user_states[chat_id] = "wait_for_low_stock_limit"
            temp_data[chat_id] = {"msg_id": msg_id}
            edit_message(chat_id, msg_id,
                render_body_text("📝 Send the stock limit (number).\nYou will be alerted when a service+country has this many numbers or fewer.\n\nExample: <code>50</code>"),
                reply_markup=get_cancel_kb())
        else:
            edit_message(chat_id, msg_id, render_body_text(build_low_stock_text()), reply_markup=low_stock_keyboard())
        answer_callback(call["id"])

    elif data == "total_balance":
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admin only!", show_alert=True)
            return
        edit_message(chat_id, msg_id,
            render_body_text(build_total_balance_text()),
            reply_markup={"inline_keyboard": [
                [{"text": "🔄 Refresh", "icon_custom_emoji_id": "5395444784611480792",
                  "callback_data": "total_balance", "style": "success"}],
                [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176",
                  "callback_data": "system_settings", "style": "danger"}]
            ]})
        answer_callback(call["id"])

    elif data == "test_message_flow":
        user_states[chat_id] = "wait_for_test_service"
        temp_data[chat_id] = {}
        edit_message(chat_id, msg_id, render_body_text("🧪 <b>Test Mode</b>\n\n📝 Send the Service Name (e.g., IG):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "open_settings", "style": "danger"}]]})

    elif data == "manage_emojis":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['star']} <b>Premium Emoji Management</b>\n\nUpload your TXT files or manually add them below:"), reply_markup=emoji_settings_keyboard())

    elif data == "up_flags_txt":
        user_states[chat_id] = "wait_for_flag_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the <b>Flag Emojis</b> <code>.txt</code> file."), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": "danger"}]]})

    elif data == "up_apps_txt":
        user_states[chat_id] = "wait_for_app_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the <b>Service Apps</b> <code>.txt</code> file."), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": "danger"}]]})

    elif data == "add_single_emoji":
        user_states[chat_id] = "wait_for_emoji_extract"
        edit_message(chat_id, msg_id, render_body_text("📝   Premium Emoji   (: 🇧🇩  🚫):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": "danger"}]]})

    elif data == "dl_flags_txt":
        content = generate_emoji_txt("flags")
        if content:
            send_document(chat_id, "Flag_Emojis.txt", content)
            answer_callback(call["id"], "✅ Downloaded!")
        else:
            answer_callback(call["id"], "❌ No Flag Emojis found!", show_alert=True)

    elif data == "dl_apps_txt":
        content = generate_emoji_txt("apps")
        if content:
            send_document(chat_id, "Service_Apps.txt", content)
            answer_callback(call["id"], "✅ Downloaded!")
        else:
            answer_callback(call["id"], "❌ No App Emojis found!", show_alert=True)

    elif data == "del_all_flags":
        bot_settings["premium_flags"] = {}
        save_db()
        answer_callback(call["id"], "✅ All Premium Flags Deleted Successfully!", show_alert=True)

    elif data == "broadcast_msg":
        user_states[chat_id] = "wait_for_broadcast"
        edit_message(chat_id, msg_id, render_body_text("📢 <b>Broadcast Mode</b>\n\nSend the message you want to broadcast (Text, Photo, Video, File etc)."), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]})

    elif data == "upload_num":
        user_states[chat_id] = "wait_for_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the numbers in a <b>.txt</b> file."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]})

    elif data == "delete_files":
        kb = []
        apps_db = bot_settings.get("premium_apps", {})
        flags_db = bot_settings.get("premium_flags", {})
        for b_id, b_data in number_batches.items():
            service = b_data.get("service", "UNKNOWN")
            country = b_data.get("country", "UNKNOWN")
            count = len(b_data.get("numbers", []))

            service_char = "📱"
            service_id = "5352694861990501856"
            for app_key, app_data in apps_db.items():
                if service.upper() == app_key or service.upper() in app_key or app_key in service.upper():
                    service_char = app_data.get("char", "📱")
                    if "id" in app_data:
                        service_id = app_data["id"]
                    break

            country_name, _ = _flag_display(country)
            btn_text = f"{service} ({country_name}) — {count}"
            kb.append([{"text": btn_text, "icon_custom_emoji_id": service_id, "callback_data": f"del_b_{b_id}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "primary"}])
        txt = "🗑 Select a stock to delete:" if len(kb) > 1 else f"{PEM['no']} No files found."
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_b_"):
        b_id = data.split("del_b_")[1]
        with number_batches_lock:
            if b_id in number_batches:
                b_removed = number_batches[b_id]
                _fs_remove_file_for(b_removed.get("service", "UNKNOWN"), b_removed.get("country", "UNKNOWN"))
                del number_batches[b_id]
        if b_id not in number_batches:
            save_db()
            answer_callback(call["id"], "✅ File deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "delete_files", "id": call["id"]})

    elif data == "show_used":
        kb = {"inline_keyboard": [
            [{"text": "Download Used Numbers", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_used", "style": "primary"}],
            [{"text": "Add Used Numbers", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "restock_used", "style": "success"}],
            [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['ok']} <b>Total Used Numbers:</b> {len(used_numbers_list)}"), reply_markup=kb)

    elif data == "dl_used":
        if not used_numbers_list:
            answer_callback(call["id"], "❌ No used numbers to download!", show_alert=True)
            return
        groups = {}
        for entry in used_numbers_list:
            if isinstance(entry, dict):
                num = entry.get("num")
                service = entry.get("service") or "UNKNOWN"
                country = entry.get("country") or "UNKNOWN"
            else:
                num, service, country = entry, "UNKNOWN", "UNKNOWN"
            if not num:
                continue
            groups.setdefault((service, country), []).append(str(num))
        sent = 0
        for (service, country), nums in groups.items():
            fname = f"{_fs_sanitize(country)}_{_fs_sanitize(service)}_used.txt"
            content = "\n".join(nums).encode('utf-8')
            send_document(chat_id, fname, content)
            sent += 1
        answer_callback(call["id"], f"✅ Sent {sent} file(s), separated by service &amp; country.", show_alert=True)

    elif data == "restock_used":
        if not used_numbers_list:
            answer_callback(call["id"], "❌ No used numbers to restock!", show_alert=True)
            return
        restocked = 0
        for entry in list(used_numbers_list):
            if isinstance(entry, dict):
                num, service, country = entry.get("num"), entry.get("service", "UNKNOWN"), entry.get("country", "UNKNOWN")
            else:
                # Legacy plain-string entries (no service/country info) — restock as UNKNOWN.
                num, service, country = entry, "UNKNOWN", "UNKNOWN"
            if not num:
                continue
            target_b_id = None
            for b_id, b_data in number_batches.items():
                if b_data.get("service") == service and b_data.get("country") == country:
                    target_b_id = b_id
                    break
            if not target_b_id:
                target_b_id = _fs_batch_id(service, country)
            with number_batches_lock:
                if target_b_id not in number_batches:
                    number_batches[target_b_id] = {"filename": "restocked_used_numbers.txt", "service": service, "country": country, "numbers": []}
                number_batches[target_b_id]["numbers"].append({"num": num, "shares": 0, "used_by": []})
            restocked += 1
            _fs_sync_batch(target_b_id)
        used_numbers_list.clear()
        save_db()
        kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]}
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['ok']} <b>{restocked}</b> used number(s) added back to stock!"), reply_markup=kb)
        answer_callback(call["id"])

    elif data == "show_unused":
        unused_count = sum(len(b["numbers"]) for b in number_batches.values())
        kb = {"inline_keyboard": [[{"text": "Download TXT", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dlu_svc", "style": "primary"}], [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]}
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['rocket']} <b>Total Unused Numbers:</b> {unused_count}"), reply_markup=kb)

    elif data == "dlu_svc":
        services = sorted(set(b["service"] for b in number_batches.values() if b.get("numbers")))
        if not services:
            answer_callback(call["id"], "❌ No unused numbers available!", show_alert=True)
            return
        kb = []
        for s in services:
            svc_count = sum(len(b["numbers"]) for b in number_batches.values() if b.get("service") == s)
            icon_id, icon_char = _get_svc_icon_info(s)
            label = f"{s} ({svc_count})"
            btn = {"text": label, "callback_data": f"dlu_cty_{s}", "style": "primary"}
            if icon_id:
                btn["icon_custom_emoji_id"] = icon_id
            elif icon_char:
                btn["text"] = f"{icon_char} {label}"
            kb.append([btn])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "show_unused", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['pin']} <b>Download Unused Numbers</b>\n\nSelect the service:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("dlu_cty_"):
        service = data[len("dlu_cty_"):]
        countries = sorted(set(b["country"] for b in number_batches.values() if b["service"] == service and b.get("numbers")))
        if not countries:
            answer_callback(call["id"], "❌ No unused numbers found for this service.", show_alert=True)
            return
        flags_db = bot_settings.get("premium_flags", {})
        kb = []
        for c in countries:
            emoji_id = "5780471598922337683"
            display_name = c
            for flag_code, flag_data in flags_db.items():
                iso = flag_data.get("iso", "").upper()
                name = flag_data.get("name", "").upper()
                if c == flag_code or _country_code_matches(c, iso, name):
                    if "id" in flag_data:
                        emoji_id = flag_data["id"]
                        display_name = flag_data.get("name", c)
                        break
            c_count = sum(len(b["numbers"]) for b in number_batches.values() if b.get("service") == service and b.get("country") == c)
            kb.append([{"text": f"{display_name} ({c_count})", "icon_custom_emoji_id": emoji_id, "callback_data": f"dlu_go_{service}||{c}", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "dlu_svc", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['pin']} <b>{service}</b>\n\nSelect the country:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("dlu_go_"):
        payload = data[len("dlu_go_"):]
        service, country = payload.split("||", 1) if "||" in payload else (payload, "UNKNOWN")
        nums = [n["num"] for b in number_batches.values() if b.get("service") == service and b.get("country") == country for n in b.get("numbers", [])]
        if not nums:
            answer_callback(call["id"], "❌ No unused numbers found for this selection.", show_alert=True)
            return
        fname = f"{_fs_sanitize(country)}_{_fs_sanitize(service)}_unused.txt"
        content = "\n".join(nums).encode('utf-8')
        send_document(chat_id, fname, content)
        answer_callback(call["id"], f"✅ Sent {len(nums)} number(s).", show_alert=True)

    elif data == "view_stock":
        # Group by (service, country) — each country gets its own stock line
        svc_country = {}
        for b_data in number_batches.values():
            svc = b_data.get("service") or "UNKNOWN"
            cntry = b_data.get("country") or "UNKNOWN"
            key = (svc, cntry)
            svc_country[key] = svc_country.get(key, 0) + len(b_data.get("numbers", []))
        # Drop entries with zero numbers so empty batches don't pollute the view
        svc_country = {k: v for k, v in svc_country.items() if v > 0}
        if not svc_country:
            txt = f"{PEM['no']} No stock available. Upload numbers first."
        else:
            lines = [f"━━━━━━━━━━━━━━━━━━", f"《 {PEM['graph']} <b>STOCK OVERVIEW</b> 》", "━━━━━━━━━━━━━━━━━━"]
            flags_db = bot_settings.get("premium_flags", {})

            # Build per-service groups sorted by total stock descending
            by_svc = {}
            for (svc, cntry), count in svc_country.items():
                by_svc.setdefault(svc, []).append((cntry, count))
            for svc in sorted(by_svc.keys(), key=lambda s: -sum(c for _, c in by_svc[s])):
                _sfn2, srv_html = get_service_info_html(svc)
                # Sort countries within each service by stock descending
                for cntry, count in sorted(by_svc[svc], key=lambda x: -x[1]):
                    # _flag_display handles suffixed keys like "58 1" → "Venezuela 1" ✅
                    c_display, flag_html = _flag_display(cntry)
                    lines.append(f"{_format_svc(_sfn2, srv_html)} | {flag_html} {c_display} — <code>{count}</code>")

            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append(f"{PEM['num']} <b>Total:</b> <code>{sum(svc_country.values())}</code> number(s)")
            txt = "\n".join(lines)
        kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]]}
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=kb)
        answer_callback(call["id"])

    elif data == "num_mgmt":
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>NUMBER Management</b>\n\nSelect an action:"), reply_markup=num_mgmt_keyboard())
        answer_callback(call["id"])

    elif data == "num_lock":
        # ── Number Lock: show all services ──────────────────────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        local_srvs = sorted(set(b["service"] for b in number_batches.values()))
        voltx_srvs = sorted(bot_settings.get("voltx_services", {}).keys())
        stex_srvs  = sorted(bot_settings.get("stex_services",  {}).keys())
        all_srvs = sorted(set(local_srvs + voltx_srvs + stex_srvs))
        if not all_srvs:
            answer_callback(call["id"], "❌ No services found. Upload numbers first.", show_alert=True)
            return
        kb = []
        for s in all_srvs:
            kb.append([_svc_btn(s, f"nl_svc_{s}", "primary")])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "num_mgmt", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(
            f"🔒 <b>Number Lock</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Select a service to manage country locks:"
        ), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("nl_svc_"):
        # ── Number Lock: show countries for chosen service ───────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        service = data[len("nl_svc_"):]
        local_cnts = set(b["country"] for b in number_batches.values() if b["service"] == service)
        voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
        stex_cnts  = set(bot_settings.get("stex_services",  {}).get(service, {}).keys())
        all_countries = sorted(local_cnts.union(voltx_cnts).union(stex_cnts))
        if not all_countries:
            answer_callback(call["id"], "❌ No countries found for this service.", show_alert=True)
            return

        flags_db = bot_settings.get("premium_flags", {})

        # Build header with service emoji
        icon_id, icon_char = _get_svc_icon_info(service)
        svc_label = service
        if icon_id:
            svc_label = f'<tg-emoji emoji-id="{icon_id}">{icon_char or "📱"}</tg-emoji> {service}'
        elif icon_char:
            svc_label = f"{icon_char} {service}"

        kb = []
        for c in all_countries:
            # Resolve country display name and emoji
            flag_emoji_id = "5780471598922337683"
            display_name = c
            for flag_code, flag_data in flags_db.items():
                iso = flag_data.get("iso", "").upper()
                name = flag_data.get("name", "").upper()
                if c == flag_code or _country_code_matches(c, iso, name):
                    if "id" in flag_data:
                        flag_emoji_id = flag_data["id"]
                    display_name = flag_data.get("name", c)
                    break

            # Stock count for this country
            stock = sum(
                len(b["numbers"])
                for b in number_batches.values()
                if b.get("service") == service and b.get("country") == c
            )

            locked = is_country_locked(service, c)
            # Action label = what clicking will DO (opposite of current state)
            lock_label = "🔓 Unlock" if locked else "🔒 Lock"
            btn_text = f"{display_name}  Stock:{stock}  {lock_label}"
            btn_style = "danger" if locked else "success"

            kb.append([{
                "text": btn_text,
                "icon_custom_emoji_id": flag_emoji_id,
                "callback_data": f"nl_toggle_{service}||{c}",
                "style": btn_style
            }])

        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "num_lock", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(
            f"🔒 <b>Number Lock</b> — {svc_label}\n━━━━━━━━━━━━━━━━━━\n"
            f"🔒 Lock = Country hidden from users\n"
            f"✅ Unlock = Country visible to users\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Tap a country to toggle its lock:"
        ), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("nl_toggle_"):
        # ── Number Lock: toggle lock for service+country ─────────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        payload = data[len("nl_toggle_"):]
        if "||" not in payload:
            answer_callback(call["id"], "❌ Invalid request.", show_alert=True)
            return
        service, country = payload.split("||", 1)

        if "locked_countries" not in bot_settings:
            bot_settings["locked_countries"] = {}
        locked = bot_settings["locked_countries"]

        if service not in locked:
            locked[service] = []

        if country in locked[service]:
            locked[service].remove(country)
            status_msg = f"✅ {country} unlocked for {service}"
        else:
            locked[service].append(country)
            status_msg = f"🔒 {country} locked for {service}"

        save_db()
        answer_callback(call["id"], status_msg, show_alert=True)

        # Refresh the country list for this service
        handle_callback({
            "message": {"chat": {"id": chat_id}, "message_id": msg_id},
            "data": f"nl_svc_{service}",
            "id": call["id"]
        })
        return

    elif data == "manage_rate":
        # ── Manage Rate: show all services ──────────────────────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        local_srvs = sorted(set(b["service"] for b in number_batches.values()))
        voltx_srvs = sorted(bot_settings.get("voltx_services", {}).keys())
        stex_srvs  = sorted(bot_settings.get("stex_services",  {}).keys())
        all_srvs   = sorted(set(local_srvs + voltx_srvs + stex_srvs))
        if not all_srvs:
            answer_callback(call["id"], "❌ No services found. Upload numbers first.", show_alert=True)
            return
        kb = []
        for s in all_srvs:
            kb.append([_svc_btn(s, f"mr_svc_{s}", "primary")])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "num_mgmt", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>Manage Rate</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Select a service to manage country rates:"
        ), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("mr_svc_"):
        # ── Manage Rate: show countries for chosen service ───────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        service = data[len("mr_svc_"):]
        local_cnts = set(b["country"] for b in number_batches.values() if b["service"] == service)
        voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
        stex_cnts  = set(bot_settings.get("stex_services",  {}).get(service, {}).keys())
        all_countries = sorted(local_cnts.union(voltx_cnts).union(stex_cnts))
        if not all_countries:
            answer_callback(call["id"], "❌ No countries found for this service.", show_alert=True)
            return

        flags_db = bot_settings.get("premium_flags", {})
        svc_prices = bot_settings.get("service_country_prices", {}).get(service, {})
        default_rate = bot_settings.get("service_otp_prices", {}).get(service, bot_settings.get("otp_reward", 0.1))

        icon_id, icon_char = _get_svc_icon_info(service)
        svc_label = service
        if icon_id:
            svc_label = f'<tg-emoji emoji-id="{icon_id}">{icon_char or "📱"}</tg-emoji> {service}'
        elif icon_char:
            svc_label = f"{icon_char} {service}"

        kb = []
        for c in all_countries:
            # _flag_display handles suffixed keys like "58 1" → "Venezuela 1"
            display_name, _ = _flag_display(c)
            # Resolve emoji_id — check full key AND base code for suffixed entries
            base_c = c.split(" ")[0]
            flag_emoji_id = "5780471598922337683"
            for flag_code, flag_data in flags_db.items():
                fiso  = flag_data.get("iso",  "").upper()
                fname = flag_data.get("name", "").upper()
                if (flag_code == c or _country_code_matches(c, fiso, fname) or
                        flag_code == base_c or _country_code_matches(base_c, fiso, fname)):
                    if "id" in flag_data:
                        flag_emoji_id = flag_data["id"]
                    break
            cur_rate = svc_prices.get(c, default_rate)
            btn_text = f"{display_name}  —  {format_currency(cur_rate)}/OTP"
            kb.append([{
                "text": btn_text,
                "icon_custom_emoji_id": flag_emoji_id,
                "callback_data": f"mr_cnt_{service}||{c}",
                "style": "primary"
            }])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_rate", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>Manage Rate</b> — {svc_label}\n━━━━━━━━━━━━━━━━━━\n"
            f"Select a country to update its OTP rate:"
        ), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("mr_cnt_"):
        # ── Manage Rate: prompt for new rate for service+country ─────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        payload = data[len("mr_cnt_"):]
        if "||" not in payload:
            answer_callback(call["id"], "❌ Invalid request.", show_alert=True)
            return
        service, country = payload.split("||", 1)
        svc_prices = bot_settings.get("service_country_prices", {}).get(service, {})
        default_rate = bot_settings.get("service_otp_prices", {}).get(service, bot_settings.get("otp_reward", 0.1))
        cur_rate = svc_prices.get(country, default_rate)
        country_name, flag_html = _flag_display(country)
        temp_data[chat_id] = {"mr_service": service, "mr_country": country, "mr_msg_id": msg_id}
        user_states[chat_id] = "wait_for_mr_rate"
        edit_message(chat_id, msg_id, render_body_text(
            f"💰 <b>Manage Rate</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"Service: <b>{service}</b>\n"
            f"Country: {flag_html} <b>{country_name}</b>\n"
            f"Current Rate: <b>{format_currency(cur_rate)}</b>\n\n"
            f"Enter the new OTP rate (e.g. <code>0.5</code>)\n"
            f"Enter <code>0</code> for no reward:"
        ), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"mr_svc_{service}", "style": "danger"}]]})
        answer_callback(call["id"])

    elif data == "update_num":
        services = sorted(set(b["service"] for b in number_batches.values()))
        if not services:
            answer_callback(call["id"], "❌ No existing services found. Use 'Upload Number' first to create one.", show_alert=True)
            return
        kb = []
        for s in services:
            kb.append([_svc_btn(s, f"upd_svc_{s}", "primary")])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['pin']} <b>Update Number</b>\n\nSelect the service to add numbers to:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("upd_svc_"):
        service = data[len("upd_svc_"):]
        countries = sorted(set(b["country"] for b in number_batches.values() if b["service"] == service))
        if not countries:
            answer_callback(call["id"], "❌ No countries found for this service.", show_alert=True)
            return
        flags_db = bot_settings.get("premium_flags", {})
        kb = []
        for c in countries:
            emoji_id = "5780471598922337683"
            display_name = c
            for flag_code, flag_data in flags_db.items():
                iso = flag_data.get("iso", "").upper()
                name = flag_data.get("name", "").upper()
                if c == flag_code or _country_code_matches(c, iso, name):
                    if "id" in flag_data:
                        emoji_id = flag_data["id"]
                        display_name = flag_data.get("name", c)
                        break
            kb.append([{"text": display_name, "icon_custom_emoji_id": emoji_id, "callback_data": f"upd_cty_{service}||{c}", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "update_num", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['pin']} <b>{service}</b>\n\nSelect the country to add numbers to:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("upd_cty_"):
        payload = data[len("upd_cty_"):]
        service, country = payload.split("||", 1) if "||" in payload else (payload, "UNKNOWN")
        temp_data[chat_id] = {"upd_service": service, "upd_country": country}
        user_states[chat_id] = "wait_for_upd_txt"
        country_name, flag_html = _flag_display(country)
        edit_message(chat_id, msg_id, render_body_text(
            f"{PEM['pin']} <b>{service}</b> / {flag_html} <b>{country_name}</b>\n\n"
            f"📂 Please upload the numbers in a <b>.txt</b> file.\n"
            f"Duplicate numbers already in stock will be skipped automatically."
        ), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "update_num", "style": "danger"}]]})
        answer_callback(call["id"])

    elif data == "lb_main":
        txt = f"━━━━━━━━━━━━━━━\n《 {PEM['admin']} <b>LEADER BOARD MENU</b> 》\n━━━━━━━━━━━━━━━\n<i>Select a category to view the top performers or history.</i>\n━━━━━━━━━━━━━━━"
        kb = [
            [{"text": "Top Referrers", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "lb_top_refs", "style": "primary"}],
            [{"text": "Top OTP Receivers", "icon_custom_emoji_id": "5353001161878182134", "callback_data": "lb_top_otps", "style": "primary"}],
            [{"text": "Withdrawal History", "icon_custom_emoji_id": "5348469219761626211", "callback_data": "wh_page_0", "style": "success"}],
            [{"text": "Back to Admin", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": "danger"}]
        ]
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("lb_"):
        # BUG FIX: use slice — .replace("lb_", "") would strip every occurrence
        # of "lb_" inside the string, not just the leading prefix.
        sub = data[len("lb_"):]
        edit_message(chat_id, msg_id, render_body_text("⌛ <i>Fetching Data...</i>"))
        
        num_map = {"1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣", "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣", "0": "0️⃣"}
        def get_p_num(n): return "".join([num_map.get(c, c) for c in str(n)])
        
        try:
            if sub == "top_refs":
                title, field, limit, icon = "TOP 5 REFERRERS", "total_refers", 5, PEM.get('user', '👥')
                with db_lock:
                    conn = get_db_conn()
                    rows = conn.execute(f"SELECT user_id, {field} FROM users WHERE {field}>0 ORDER BY {field} DESC LIMIT {limit}").fetchall()
                    conn.close()
                res_txt = ""
                # BUG FIX: use len(rows) not limit for the └ check — if fewer
                # rows exist than the limit, count never reaches limit and every
                # row incorrectly shows ├ (open branch) instead of └ (last item).
                _total = len(rows)
                for count, row in enumerate(rows, start=1):
                    p = "└" if count == _total else "├"
                    res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={row[0]}'>{row[0]}</a> ➔ <b>{row[1]}</b>\n"
                if not res_txt: res_txt = "└ <i>No data found.</i>\n"

            elif sub == "top_otps":
                title, field, limit, icon = "TOP 5 OTP RECEIVERS", "total_otps", 5, PEM.get('msg', '📩')
                with db_lock:
                    conn = get_db_conn()
                    rows = conn.execute(f"SELECT user_id, {field} FROM users WHERE {field}>0 ORDER BY {field} DESC LIMIT {limit}").fetchall()
                    conn.close()
                res_txt = ""
                _total = len(rows)
                for count, row in enumerate(rows, start=1):
                    p = "└" if count == _total else "├"
                    res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={row[0]}'>{row[0]}</a> ➔ <b>{row[1]}</b>\n"
                if not res_txt: res_txt = "└ <i>No data found.</i>\n"

            elif sub == "w_history":
                title, limit, icon = "LAST 10 WITHDRAWALS", 10, PEM.get('money', '💸')
                with db_lock:
                    conn = get_db_conn()
                    ws = conn.execute("SELECT user_id, amount, status FROM withdrawals ORDER BY timestamp DESC LIMIT 10").fetchall()
                    conn.close()
                res_txt = ""
                _total = len(ws)
                for count, w in enumerate(ws, start=1):
                    s = str(w[2]).lower()
                    stat_icon = PEM.get('ok','✅') if s in ["approved","success"] else PEM.get('no','❌') if s=="rejected" else "⏳"
                    p = "└" if count == _total else "├"
                    res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={w[0]}'>{w[0]}</a> ➔ <b>{w[1]}</b> {stat_icon}\n"
                if not res_txt: res_txt = "└ <i>No history found.</i>\n"

            final_msg = f"━━━━━━━━━━━━━━━\n{icon} <b>{title}</b>\n━━━━━━━━━━━━━━━\n{res_txt}━━━━━━━━━━━━━━━"
            kb = [[{"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": data, "style": "success"}, {"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "lb_main", "style": "danger"}]]
            edit_message(chat_id, msg_id, render_body_text(final_msg), reply_markup={"inline_keyboard": kb})

        except Exception as e:
            edit_message(chat_id, msg_id, render_body_text(f"❌ Error: {e}"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275276", "callback_data": "lb_main", "style": "danger"}]]})
        answer_callback(call["id"])

    elif data == "wh_noop":
        answer_callback(call["id"])   # page indicator button — do nothing

    elif data == "wh_download":
        # ── Download last-100 history as .txt ───────────────────────────────
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        answer_callback(call["id"], "⏳ Generating file…", show_alert=False)
        try:
            with db_lock:
                conn = get_db_conn()
                rows = conn.execute(
                    "SELECT w.id, w.user_id, w.amount, w.method, w.account, w.status, w.timestamp, "
                    "u.username, u.first_name "
                    "FROM withdrawals w LEFT JOIN users u ON w.user_id = u.user_id "
                    "ORDER BY w.timestamp DESC LIMIT 100"
                ).fetchall()
                conn.close()

            cur  = "BDT"
            rate = _bdt_rate()

            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_ALL)
            writer.writerow(["Username", "UserID", "Amount", "Currency", "Method", "Account", "Status", "Date"])
            for r in rows:
                _, user_id, amount, method, account, status, ts, username, first_name = r
                display   = f"@{username}" if username else (first_name or f"User_{user_id}")
                converted = (amount or 0.0) * rate
                date_str  = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts is not None else ""
                writer.writerow([display, user_id, f"{converted:.6f}", cur, method or "", account or "", status, date_str])

            content  = output.getvalue()
            date_now = datetime.now().strftime("%Y-%m-%d")
            filename = f"withdrawal_history_{date_now}.csv"
            send_document(chat_id, filename, content.encode("utf-8"))
        except Exception as e:
            send_message(chat_id, render_body_text(f"❌ Failed to generate file: {e}"))

    elif data == "back_to_admin":
        if chat_id in user_states: del user_states[chat_id]
        edit_message(chat_id, msg_id, get_admin_text(), reply_markup=admin_panel_keyboard())
        
    elif data == "system_settings":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>System Settings</b>\nManage advanced bot configurations below:"), reply_markup=system_settings_keyboard())

    elif data == "open_settings":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>Settings</b>\nManage maintenance mode & broadcast below:"), reply_markup=settings_keyboard())

    elif data == "toggle_maintenance":
        bot_settings["maintenance_mode"] = not bot_settings.get("maintenance_mode", False)
        save_db()
        state_txt = "ENABLED 🟢" if bot_settings["maintenance_mode"] else "DISABLED 🔴"
        answer_callback(call["id"], f"Maintenance Mode {state_txt}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>Settings</b>\nManage maintenance mode & broadcast below:"), reply_markup=settings_keyboard())

    elif data == "toggle_numbers_broadcast":
        bot_settings["numbers_broadcast_on"] = not bot_settings.get("numbers_broadcast_on", True)
        save_db()
        state_txt = "ON 🟢" if bot_settings["numbers_broadcast_on"] else "OFF 🔴"
        answer_callback(call["id"], f"Numbers Broadcast {state_txt}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>Settings</b>\nManage maintenance mode & broadcast below:"), reply_markup=settings_keyboard())

    elif data == "select_currency":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>Select Currency</b>\nChoose the currency to display across the bot:"), reply_markup=currency_select_keyboard())

    elif data.startswith("set_currency_"):
        new_cur = data.replace("set_currency_", "")
        if new_cur in bot_settings.get("currency_rates", {}):
            bot_settings["currency"] = new_cur
            save_db()
            answer_callback(call["id"], f"Currency set to {new_cur}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>Select Currency</b>\nChoose the currency to display across the bot:"), reply_markup=currency_select_keyboard())

    elif data == "voltx_control":
        edit_message(chat_id, msg_id, render_body_text(f"⚡ <b>Voltx Control Panel</b>\n\nTotal API Keys: {len(bot_settings.get('voltx_keys', []))}\nManage your Voltx API Keys below:"), reply_markup=voltx_control_keyboard())

    elif data == "add_voltx_key":
        user_states[chat_id] = "wait_for_add_voltx_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new Voltx API Key:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": "danger"}]]})

    elif data == "view_voltx_keys":
        kb = []
        for idx, key in enumerate(bot_settings.get("voltx_keys", [])):
            safe_name = key[:10] + "..." if len(key)>10 else key
            kb.append([{"text": f"Delete {safe_name}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_vtx_{idx}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text("🗑 <b>Select Voltx Key to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_vtx_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings.get("voltx_keys", [])):
            del bot_settings["voltx_keys"][idx]
            save_db()
            answer_callback(call["id"], "✅ Voltx Key Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "view_voltx_keys", "id": call["id"]})

    elif data == "voltx_search_country":
        kb = []
        for idx, c in enumerate(bot_settings.get("voltx_search_countries", [])):
            kb.append([{"text": f"Delete {c}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_vsc_{idx}", "style": "danger"}])
        kb.append([{"text": "Add Country Code", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_voltx_search_country", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text("🌍 <b>Voltx Allowed Ranges:</b>\nOnly these ranges/codes will be allowed in Voltx Number Lookup."), reply_markup={"inline_keyboard": kb})

    elif data == "add_voltx_search_country":
        user_states[chat_id] = "wait_for_add_vsc"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Voltx Range Code (e.g. 26134):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_search_country", "style": "danger"}]]})

    elif data.startswith("del_vsc_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings.get("voltx_search_countries", [])):
            del bot_settings["voltx_search_countries"][idx]
            save_db()
            answer_callback(call["id"], "✅ Voltx Range Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "voltx_search_country", "id": call["id"]})

    elif data == "manage_voltx_srv":
        kb = []
        srvs = bot_settings.get("voltx_services", {})
        for srv in srvs:
            kb.append([_svc_btn(srv, f"vx_srv_{srv}", "primary")])
        kb.append([{"text": "Add New Service", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "vx_add_srv", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text("⚡ <b>Voltx Services Manager</b>\nManage your API-based dynamic services below:"), reply_markup={"inline_keyboard": kb})

    elif data == "vx_add_srv":
        user_states[chat_id] = "wait_vx_srv_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Enter Service Name (e.g. TELEGRAM):"), reply_markup=get_cancel_kb())

    elif data.startswith("vx_srv_"):
        srv = data.replace("vx_srv_", "")
        kb = []
        countries = bot_settings["voltx_services"].get(srv, {})
        flags_db = bot_settings.get("premium_flags", {})
        for c in countries:
            emoji_id = "5780471598922337683"
            for flag_code, flag_data in flags_db.items():
                iso = flag_data.get("iso", "").upper()
                name = flag_data.get("name", "").upper()
                if _country_code_matches(c, iso, name):
                    if "id" in flag_data: emoji_id = flag_data["id"]; break
            kb.append([{"text": f"{c} ({len(countries[c])} Ranges)", "icon_custom_emoji_id": emoji_id, "callback_data": f"vx_cnt_{srv}_{c}", "style": "primary"}])
        kb.append([{"text": "Add Country", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"vx_add_cnt_{srv}", "style": "success"}])
        kb.append([{"text": "Delete Service", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"vx_del_srv_{srv}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_voltx_srv", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>Service: {srv}</b>\nManage countries for this service:"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("vx_add_cnt_"):
        srv = data.replace("vx_add_cnt_", "")
        user_states[chat_id] = "wait_vx_cnt_name"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv}
        edit_message(chat_id, msg_id, render_body_text(f"🌍 Enter Country Name for <b>{srv}</b> (e.g. BD, INDIA):"), reply_markup=get_cancel_kb())

    elif data.startswith("vx_cnt_"):
        parts = data.split("_")
        srv, cnt = parts[2], parts[3]
        ranges = bot_settings["voltx_services"][srv].get(cnt, [])
        kb = []
        row = []
        for r in ranges:
            row.append({"text": f"Delete {r}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"vx_dr_{srv}_{cnt}_{r}", "style": "danger"})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        kb.append([{"text": "Add Range", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"vx_addr_{srv}_{cnt}", "style": "success"}])
        kb.append([{"text": "Delete Entire Country", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"vx_del_cnt_{srv}_{cnt}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"vx_srv_{srv}", "style": "primary"}])
        txt = f"📍 <b>Service: {srv} | Country: {cnt}</b>\n\n<b>Total Ranges:</b> {len(ranges)}\n<i>Click on a range below to delete it, or add a new one.</i>"
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("vx_addr_"):
        parts = data.split("_")
        srv, cnt = parts[2], parts[3]
        user_states[chat_id] = "wait_vx_addr"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv, "cnt": cnt}
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the new Range for <b>{cnt}</b> (e.g. 26134):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"vx_cnt_{srv}_{cnt}", "style": "danger"}]]})

    elif data.startswith("vx_dr_"):
        parts = data.split("_")
        srv, cnt, rng = parts[2], parts[3], parts[4]
        if rng in bot_settings["voltx_services"].get(srv, {}).get(cnt, []):
            bot_settings["voltx_services"][srv][cnt].remove(rng)
            save_db()
            answer_callback(call["id"], f"✅ Range {rng} deleted!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"vx_cnt_{srv}_{cnt}", "id": call["id"]})

    elif data.startswith("vx_del_srv_"):
        srv = data.replace("vx_del_srv_", "")
        if srv in bot_settings["voltx_services"]: del bot_settings["voltx_services"][srv]
        save_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_voltx_srv", "id": call["id"]})

    elif data.startswith("vx_del_cnt_"):
        parts = data.split("_")
        srv, cnt = parts[3], parts[4]
        if cnt in bot_settings["voltx_services"].get(srv, {}): del bot_settings["voltx_services"][srv][cnt]
        save_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"vx_srv_{srv}", "id": call["id"]})

    # ═══════════════════════════════════════════════════
    # STEX SMS PANEL — same logic as Voltx, different API
    # ═══════════════════════════════════════════════════
    elif data == "stex_control":
        edit_message(chat_id, msg_id, render_body_text(f"📡 <b>STEX SMS Control Panel</b>\n\nTotal API Keys: {len(bot_settings.get('stex_keys', []))}\nManage your STEX API Keys below:"), reply_markup=stex_control_keyboard())

    elif data == "add_stex_key":
        user_states[chat_id] = "wait_for_add_stex_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new STEX API Key:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": "danger"}]]})

    elif data == "view_stex_keys":
        kb = []
        for idx, key in enumerate(bot_settings.get("stex_keys", [])):
            safe_name = key[:10] + "..." if len(key) > 10 else key
            kb.append([{"text": f"Delete {safe_name}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_stx_{idx}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text("🗑 <b>Select STEX Key to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_stx_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings.get("stex_keys", [])):
            del bot_settings["stex_keys"][idx]
            save_db()
            answer_callback(call["id"], "✅ STEX Key Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "view_stex_keys", "id": call["id"]})

    elif data == "stex_search_country":
        kb = []
        for idx, c in enumerate(bot_settings.get("stex_search_countries", [])):
            kb.append([{"text": f"Delete {c}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_ssc_{idx}", "style": "danger"}])
        kb.append([{"text": "Add Range Code", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_stex_search_country", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text("🌍 <b>STEX Allowed Ranges:</b>\nOnly these range IDs will be used in STEX Number Lookup."), reply_markup={"inline_keyboard": kb})

    elif data == "add_stex_search_country":
        user_states[chat_id] = "wait_for_add_ssc"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the STEX Range ID (e.g. 22501):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_search_country", "style": "danger"}]]})

    elif data.startswith("del_ssc_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings.get("stex_search_countries", [])):
            del bot_settings["stex_search_countries"][idx]
            save_db()
            answer_callback(call["id"], "✅ STEX Range Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "stex_search_country", "id": call["id"]})

    elif data == "manage_stex_srv":
        kb = []
        srvs = bot_settings.get("stex_services", {})
        for srv in srvs:
            kb.append([_svc_btn(srv, f"stx_srv_{srv}", "primary")])
        kb.append([{"text": "Add New Service", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "stx_add_srv", "style": "success"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": "danger"}])
        edit_message(chat_id, msg_id, render_body_text("📡 <b>STEX Services Manager</b>\nManage your STEX API-based dynamic services below:"), reply_markup={"inline_keyboard": kb})

    elif data == "stx_add_srv":
        user_states[chat_id] = "wait_stx_srv_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Enter Service Name (e.g. WHATSAPP):"), reply_markup=get_cancel_kb())

    elif data.startswith("stx_srv_"):
        srv = data.replace("stx_srv_", "")
        kb = []
        countries = bot_settings["stex_services"].get(srv, {})
        flags_db = bot_settings.get("premium_flags", {})
        for c in countries:
            emoji_id = "5780471598922337683"
            for flag_code, flag_data in flags_db.items():
                iso = flag_data.get("iso", "").upper()
                name = flag_data.get("name", "").upper()
                if _country_code_matches(c, iso, name):
                    if "id" in flag_data: emoji_id = flag_data["id"]; break
            kb.append([{"text": f"{c} ({len(countries[c])} Ranges)", "icon_custom_emoji_id": emoji_id, "callback_data": f"stx_cnt_{srv}_{c}", "style": "primary"}])
        kb.append([{"text": "Add Country", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"stx_add_cnt_{srv}", "style": "success"}])
        kb.append([{"text": "Delete Service", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"stx_del_srv_{srv}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_stex_srv", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>STEX Service: {srv}</b>\nManage countries for this service:"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("stx_add_cnt_"):
        srv = data.replace("stx_add_cnt_", "")
        user_states[chat_id] = "wait_stx_cnt_name"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv}
        edit_message(chat_id, msg_id, render_body_text(f"🌍 Enter Country Name for <b>{srv}</b> (e.g. SA, INDIA):"), reply_markup=get_cancel_kb())

    elif data.startswith("stx_cnt_"):
        parts = data.split("_")
        srv, cnt = parts[2], parts[3]
        ranges = bot_settings["stex_services"][srv].get(cnt, [])
        kb = []
        row = []
        for r in ranges:
            row.append({"text": f"Delete {r}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"stx_dr_{srv}_{cnt}_{r}", "style": "danger"})
            if len(row) == 2:
                kb.append(row); row = []
        if row: kb.append(row)
        kb.append([{"text": "Add Range ID", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"stx_addr_{srv}_{cnt}", "style": "success"}])
        kb.append([{"text": "Delete Entire Country", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"stx_del_cnt_{srv}_{cnt}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"stx_srv_{srv}", "style": "primary"}])
        txt = f"📍 <b>STEX: {srv} | {cnt}</b>\n\n<b>Total Ranges:</b> {len(ranges)}\n<i>Click a range to delete, or add a new one.</i>"
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("stx_addr_"):
        parts = data.split("_")
        srv, cnt = parts[2], parts[3]
        user_states[chat_id] = "wait_stx_addr"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv, "cnt": cnt}
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the STEX Range ID for <b>{cnt}</b> (e.g. 22501):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"stx_cnt_{srv}_{cnt}", "style": "danger"}]]})

    elif data.startswith("stx_dr_"):
        parts = data.split("_")
        srv, cnt, rng = parts[2], parts[3], parts[4]
        if rng in bot_settings["stex_services"].get(srv, {}).get(cnt, []):
            bot_settings["stex_services"][srv][cnt].remove(rng)
            save_db()
            answer_callback(call["id"], f"✅ Range {rng} deleted!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"stx_cnt_{srv}_{cnt}", "id": call["id"]})

    elif data.startswith("stx_del_srv_"):
        srv = data.replace("stx_del_srv_", "")
        if srv in bot_settings["stex_services"]: del bot_settings["stex_services"][srv]
        save_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_stex_srv", "id": call["id"]})

    elif data.startswith("stx_del_cnt_"):
        parts = data.split("_")
        srv, cnt = parts[3], parts[4]
        if cnt in bot_settings["stex_services"].get(srv, {}): del bot_settings["stex_services"][srv][cnt]
        save_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"stx_srv_{srv}", "id": call["id"]})

    elif data == "manage_fj":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['link']} <b>FORCE JOIN SYSTEM</b>\nManage channels below:"), reply_markup=fj_settings_keyboard())

    elif data == "toggle_fj":
        bot_settings["fj_on"] = not bot_settings["fj_on"]
        save_db()
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['link']} <b>FORCE JOIN SYSTEM</b>\nManage channels below:"), reply_markup=fj_settings_keyboard())

    elif data == "add_fj":
        user_states[chat_id] = "wait_for_add_fj"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send Channel Username or Invite Link:\n<i>(Note: For private channels, use the numeric ID like -100...)</i>"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_fj", "style": "danger"}]]})

    elif data.startswith("del_fj_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["fj_channels"]):
            del bot_settings["fj_channels"][idx]
            save_db()
            answer_callback(call["id"], "✅ Channel deleted!", show_alert=True)
            edit_message(chat_id, msg_id, render_body_text(f"{PEM['link']} <b>FORCE JOIN SYSTEM</b>\nManage channels below:"), reply_markup=fj_settings_keyboard())

    elif data == "manage_admins":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['user']} <b>ADMIN MANAGEMENT</b>\nManage your bot admins below:"), reply_markup=admin_settings_keyboard())

    elif data == "add_adm":
        user_states[chat_id] = "wait_for_add_adm"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID of the new Admin:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_admins", "style": "danger"}]]})

    elif data.startswith("del_adm_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["admins"]):
            del bot_settings["admins"][idx]
            save_db()
            answer_callback(call["id"], "✅ Admin deleted!", show_alert=True)
            edit_message(chat_id, msg_id, render_body_text(f"{PEM['user']} <b>ADMIN MANAGEMENT</b>\nManage your bot admins below:"), reply_markup=admin_settings_keyboard())

    elif data == "manage_otp_groups":
        edit_message(chat_id, msg_id, render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())

    elif data == "add_fw":
        user_states[chat_id] = "wait_for_add_fw_id"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Group ID/Username to forward messages to:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": "danger"}]]})

    elif data.startswith("manage_fw_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["fw_groups"]):
            grp = bot_settings["fw_groups"][idx]
            grp_label = grp.get("name") or grp["chat_id"]
            edit_message(chat_id, msg_id, render_body_text(f"🛡 <b>Manage Group:</b> {grp_label}"), reply_markup=specific_fw_group_keyboard(idx))

    elif data.startswith("add_fwbtn_"):
        idx = int(data.split("_")[2])
        user_states[chat_id] = "wait_for_add_fw_btn"
        temp_data[chat_id] = {"msg_id": msg_id, "fw_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send Custom Inline Button format:\n<code>Button Text - https://link.com</code>"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_fw_{idx}", "style": "danger"}]]})

    elif data.startswith("del_fwbtn_"):
        parts = data.split("_")
        idx, b_idx = int(parts[2]), int(parts[3])
        if 0 <= idx < len(bot_settings["fw_groups"]):
            if 0 <= b_idx < len(bot_settings["fw_groups"][idx]["buttons"]):
                del bot_settings["fw_groups"][idx]["buttons"][b_idx]
                save_db()
                answer_callback(call["id"], "✅ Button deleted!", show_alert=True)
                grp_lbl = bot_settings['fw_groups'][idx].get("name") or bot_settings['fw_groups'][idx]['chat_id']
                edit_message(chat_id, msg_id, render_body_text(f"🛡 <b>Manage Group:</b> {grp_lbl}"), reply_markup=specific_fw_group_keyboard(idx))

    elif data.startswith("del_fw_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["fw_groups"]):
            del bot_settings["fw_groups"][idx]
            save_db()
            answer_callback(call["id"], "✅ Group deleted!", show_alert=True)
            edit_message(chat_id, msg_id, render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())

    elif data == "edit_otp_link":
        user_states[chat_id] = "wait_for_otp_link"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new OTP Group Link:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": "danger"}]]})

    elif data == "edit_fw_channel_link":
        user_states[chat_id] = "wait_for_fw_channel_link"
        temp_data[chat_id] = {"msg_id": msg_id}
        cur = bot_settings.get("fw_channel_link", "") or "Not set"
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the Channel link for OTP forward message:\n\nCurrent: <code>{cur}</code>"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275166", "callback_data": "manage_otp_groups", "style": "danger"}]]})

    elif data == "manage_panels":
        api_count = len([p for p in bot_settings["panels"] if p.get("type") == "API Panel"])
        cpt_count = len([p for p in bot_settings["panels"] if p.get("type", "API Panel") == "Auto Captcha Panel"])
        text = f"{PEM['gear']} <b>Panel Management</b>\n\nSelect which type of panel system you want to manage:"
        kb = {"inline_keyboard": [
            [{"text": f"Manage API Panels ({api_count})", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "manage_api_panels", "style": "primary"}],
            [{"text": f"Manage Auto Captcha Panels ({cpt_count})", "icon_custom_emoji_id": "6068830682359010545", "callback_data": "manage_cpt_panels", "style": "success"}],
            [{"text": "Back to System", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(text), reply_markup=kb)

    elif data in ["manage_api_panels", "manage_cpt_panels"]:
        p_type = "API Panel" if data == "manage_api_panels" else "Auto Captcha Panel"
        p_list = [p for p in bot_settings["panels"] if p.get("type", "API Panel") == p_type]
        icon = f"{PEM['world']} API" if p_type == 'API Panel' else f"{PEM['lock']} Auto Captcha"
        
        text = f"{icon} <b>{p_type}s Management</b>\n\n👀 <b>Active Monitors:</b> {len(p_list)}\n\n🟢 <b>Available Providers:</b>\n"
        for p in p_list:
            status = "Monitoring" if p['status'] == 'ON' else "Stopped"
            login_state = p.get('login_status', '')
            if p['type'] == 'Auto Captcha Panel':
                conf = f" {login_state}" if login_state else f"{PEM['ok']} Configured"
            else:
                conf = f"{PEM['ok']} Configured" if p.get('api_url') else f"{PEM['no']} Not Configured"
            text += f"• {p['name']}: {PEM['ok'] if p['status']=='ON' else PEM['no']} {status} | {conf}\n"
        edit_message(chat_id, msg_id, render_body_text(text), reply_markup=typed_panels_list_keyboard(p_type))

    elif data in ["add_api_panel", "add_cpt_panel"]:
        user_states[chat_id] = "wait_for_panel_name"
        p_type = "api" if data == "add_api_panel" else "logc"
        temp_data[chat_id] = {"msg_id": msg_id, "add_type": p_type}
        edit_message(chat_id, msg_id, render_body_text("📝 Please send the name of the New Provider:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_{'api' if p_type=='api' else 'cpt'}_panels", "style": "danger"}]]})

    elif data.startswith("add_ptype_"):
        pass

    elif data in ["list_del_api", "list_del_cpt"]:
        p_type = "API Panel" if data == "list_del_api" else "Auto Captcha Panel"
        kb = []
        for idx, p in enumerate(bot_settings["panels"]):
            if p.get("type", "API Panel") == p_type:
                kb.append([{"text": f"Delete {p['name']}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"do_del_pnl_{idx}", "style": "danger"}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_{'api' if p_type=='API Panel' else 'cpt'}_panels", "style": "primary"}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['trash']} <b>Select a Provider to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("do_del_pnl_"):
        idx = int(data.split("_")[3])
        if 0 <= idx < len(bot_settings["panels"]):
            p_type = bot_settings["panels"][idx].get("type", "API Panel")
            del bot_settings["panels"][idx]
            save_db()
            answer_callback(call["id"], "✅ Provider Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"manage_{'api' if p_type=='API Panel' else 'cpt'}_panels", "id": "internal"})

    elif data.startswith("tog_pnl_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["panels"]):
            p = bot_settings["panels"][idx]
            turning_off = (p["status"] == "ON")

            p["status"] = "OFF" if turning_off else "ON"

            if p["type"] == "Auto Captcha Panel":
                if turning_off:
                    # ── Panel stopped: close & remove old session immediately ──
                    old_sess = panel_sessions.pop(idx, None)
                    if old_sess:
                        try:
                            old_sess.close()
                        except Exception:
                            pass
                    p["login_status"] = "🔴 Stopped by admin"
                else:
                    # ── Panel re-enabled: reset login cooldown → login right away ──
                    p["last_login_attempt"] = 0
                    p["login_status"] = "⏳ Starting — logging in..."

            save_db()

            if p["type"] == "Auto Captcha Panel":
                text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>Login Status:</b> {p.get('login_status', 'Unknown')}\n<b>Login URL:</b> <code>{p.get('login_url', 'None')}</code>\n<b>User:</b> <code>{p.get('username', 'None')}</code>"
            else:
                text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>"
            edit_message(chat_id, msg_id, render_body_text(text), reply_markup=panel_config_keyboard(idx))

    elif data.startswith("conf_pnl_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["panels"]):
            p = bot_settings["panels"][idx]
            if p["type"] == "Auto Captcha Panel":
                text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>Login Status:</b> {p.get('login_status', 'Unknown')}\n<b>Login URL:</b> <code>{p.get('login_url', 'None')}</code>\n<b>User:</b> <code>{p.get('username', 'None')}</code>\n<b>Num Col:</b> {p.get('num_col_name')} (Idx: {p.get('num_col_idx')})\n<b>Msg Col:</b> {p.get('msg_col_name')} (Idx: {p.get('msg_col_idx')})"
            else:
                text = f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n<b>Token:</b> <code>{p.get('token', 'None')}</code>\n<b>Full API URL:</b> <code>{p.get('full_api_url', 'None')}</code>"
            edit_message(chat_id, msg_id, render_body_text(text), reply_markup=panel_config_keyboard(idx))

    elif data.startswith("set_p_api_"):
        idx = int(data.split("_")[3])
        user_states[chat_id] = "wait_for_p_api"
        temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the API URL for this provider:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": "danger"}]]})

    elif data.startswith("set_p_tok_"):
        idx = int(data.split("_")[3])
        user_states[chat_id] = "wait_for_p_tok"
        temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Token for this provider:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": "danger"}]]})

    elif data.startswith("set_p_fapi_"):
        idx = int(data.split("_")[3])
        user_states[chat_id] = "wait_for_p_fapi"
        temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the FULL API URL (Example: http://api.com/get?key=YOUR_TOKEN&start=0):"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": "danger"}]]})

    elif data.startswith("set_p_rec_"):
        idx = int(data.split("_")[3])
        user_states[chat_id] = "wait_for_p_rec"
        temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the number of records to fetch (e.g. 10).\nType <code>0</code> for Unlimited:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": "danger"}]]})

    elif data.startswith("set_p_int_"):
        idx = int(data.split("_")[3])
        user_states[chat_id] = "wait_for_p_int"
        temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the fetch delay in seconds for THIS panel only (1-30).\nUse 6 or 7 if this provider's API only allows 1 request every 5 seconds.\nOther panels are not affected."), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": "danger"}]]})

    elif data.startswith("test_p_conn_"):
        idx = int(data.split("_")[3])
        p = bot_settings["panels"][idx]
        wait_msg = send_message(chat_id, render_body_text("⏳ Testing connection. Please wait..."))
        wait_msg_id = wait_msg.get("result", {}).get("message_id") if wait_msg else None
        answer_callback(call["id"])
        
        try:
            parsed = []
            raw_text = ""
            
            if p["type"] == "Auto Captcha Panel":
                sess = panel_sessions.get(idx)
                if not sess:
                    success = attempt_auto_login(p, idx)
                    if not success:
                        if wait_msg_id: delete_message(chat_id, wait_msg_id)
                        send_message(chat_id, render_body_text(f"❌ <b>Auto Login Failed!</b>\nReason: {html.escape(str(p.get('login_status', 'Unknown')))}"))
                        return
                    sess = panel_sessions.get(idx)
                    
                login_url = p.get("login_url", "").strip()
                if not login_url.startswith("http"): login_url = "http://" + login_url
                msg_link = p.get("msg_link", "").strip()
                if not msg_link.startswith("http") and msg_link != "": msg_link = "http://" + msg_link
                check_url = msg_link if msg_link else f"{login_url.split('/login')[0]}/client/SMSCDRStats"
                
                # 🌟 test connection supports sAjaxSource & HTML table parser
                parsed, raw_text = fetch_cpt_panel_cdrs(p, sess, check_url)
                
            else:
                full_url = p.get("full_api_url", "").strip()
                url = p.get("api_url", "").strip()
                token = p.get("token", "").strip()
                if not full_url and not url:
                    if wait_msg_id: delete_message(chat_id, wait_msg_id)
                    send_message(chat_id, render_body_text("❌ Please Set API URL or Full API URL first!"))
                    return
                
                urls_to_try = []
                if full_url:
                    urls_to_try.append(full_url)
                else:
                    if "{token}" in url or "{key}" in url:
                        urls_to_try.append(url.replace("{token}", token).replace("{key}", token))
                    elif "token=" in url or "key=" in url:
                        urls_to_try.append(url)
                    else:
                        sep = '&' if '?' in url else '?'
                        urls_to_try.append(f"{url}{sep}token={token}")
                        urls_to_try.append(f"{url}{sep}key={token}&start=0")
                        urls_to_try.append(f"{url}{sep}key={token}")
                    
                parsed = []
                raw_text = ""
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                for try_url in urls_to_try:
                    try:
                        res = requests.get(try_url, headers=headers, timeout=10)
                        raw_text = res.text
                        parsed = parse_panel_response(raw_text, p)
                        if parsed:
                            if not full_url and try_url != url and token:
                                p["api_url"] = try_url.replace(token, "{token}")
                                save_db()
                            break
                    except: pass
                 
            if wait_msg_id: delete_message(chat_id, wait_msg_id)
                 
            if parsed:
                txt = f"✅ <b>Connection Successful!</b>\n\n🎯 <b>Parsed Data Sample (Max 3):</b>\n\n"
                
                for i, sample in enumerate(parsed[:3]):
                    num = sample['number']
                    msg = sample['message']
                    otp = sample['otp']
                    
                    detected_app = detect_service(msg)
                    app_name = detected_app if detected_app else p.get("name", "Unknown")
                    app_full_name, prem_app_html = get_service_info_html(app_name, msg)
                    
                    txt += f"<b>{i+1}.</b> {_format_svc(app_full_name, prem_app_html)}\n"
                    txt += f"📱 Number: <code>{num}</code>\n"
                    txt += f"📝 Full Msg: <code>{html.escape(msg)}</code>\n"
                    txt += f"🔐 OTP: <code>{otp}</code>\n"
                    txt += "➖" * 12 + "\n"
                    
                send_message(chat_id, render_body_text(txt))
            else:
                if p["type"] == "Auto Captcha Panel":
                    try:
                        soup = BeautifulSoup(raw_text, 'html.parser')
                        tables = soup.find_all('table')
                        if tables:
                            full_table_data = "🔍 FULL TABLE DATA (A-Z)\n" + "="*50 + "\n\n"
                            for t_idx, table in enumerate(tables):
                                full_table_data += f"--- Table {t_idx+1} ---\n"
                                rows = table.find_all('tr')
                                for r_idx, row in enumerate(rows):
                                    cols = row.find_all(['th', 'td'])
                                    col_texts = [f"[{c_idx+1}] {c.get_text(separator=' ', strip=True)}" for c_idx, c in enumerate(cols)]
                                    full_table_data += f"Row {r_idx+1}: {' | '.join(col_texts)}\n"
                                full_table_data += "\n" + "="*50 + "\n"
                            soup.decompose()  # BUG FIX: free HTML tree before sending (no longer needed)
                            send_document(chat_id, f"Full_Panel_Data_{idx}.txt", full_table_data.encode('utf-8'))
                            fail_txt = f"⚠️ <b>Connected, but couldn't parse OTP data!</b>\n\n<i>    (A-Z)   Text File  ।     Column Number (: [1], [3])      ।</i>"
                            send_message(chat_id, render_body_text(fail_txt))
                        else:
                            soup.decompose()  # BUG FIX: free tree even when no tables found
                            send_message(chat_id, render_body_text(f"⚠️ <b>Connected, but no HTML Table found!</b>\nMake sure the message link is correct."))
                    except Exception as e:
                        send_message(chat_id, render_body_text(f"❌ <b>Error parsing HTML:</b> {html.escape(str(e))}"))
                else:
                    safe_html = html.escape(str(raw_text)[:300])
                    send_message(chat_id, render_body_text(f"⚠️ <b>Connected, but couldn't find/parse OTP data.</b>\n\n<i>Make sure your API config is correct.</i>\n\nRaw HTML/Data (excerpt):\n<code>{safe_html}...</code>"))
        except Exception as e:
            if wait_msg_id: delete_message(chat_id, wait_msg_id)
            send_message(chat_id, render_body_text(f"❌ <b>Connection Failed!</b>\nError: {html.escape(str(e))}"))

    elif data == "dxa_control":
        if chat_id in user_states: del user_states[chat_id]
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())

    elif data == "view_w_requests":
        try:
            with db_lock:
                conn = get_db_conn()
                rows = conn.execute(
                    "SELECT id, user_id, amount, method, account, status, timestamp FROM withdrawals WHERE status='pending' ORDER BY timestamp DESC LIMIT 20"
                ).fetchall()
                conn.close()
            w_requests = [tuple(r) for r in rows]
        except:
            w_requests = []
        if not w_requests:
            hdr = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"《 {PEM['money']} WITHDRAWAL REQUESTS 》\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{PEM['no']} No pending withdrawal requests.\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "dxa_control", "style": "danger"}]]}
            edit_message(chat_id, msg_id, render_body_text(hdr), reply_markup=kb)
        else:
            hdr = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"《 {PEM['money']} WITHDRAWAL REQUESTS 》\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{PEM['ok']} Pending: <b>{len(w_requests)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Click any request for details:"
            )
            edit_message(chat_id, msg_id, render_body_text(hdr), reply_markup=withdrawal_requests_list_keyboard(w_requests))

    elif data.startswith("wreq_detail_"):
        db_id = data.replace("wreq_detail_", "")
        try:
            with db_lock:
                conn = get_db_conn()
                row = conn.execute(
                    "SELECT id, user_id, amount, method, account, status, timestamp FROM withdrawals WHERE id=?", (db_id,)
                ).fetchone()
                conn.close()
        except:
            row = None
        if not row:
            answer_callback(call["id"], "❌ Request not found!", show_alert=True)
            return
        r_id, r_uid, r_amt, r_method, r_acc, r_status, r_ts = tuple(row)
        ts_str = datetime.fromtimestamp(r_ts).strftime("%Y-%m-%d %H:%M") if r_ts else "N/A"
        r_method_eid = get_payment_emoji_id(r_method)
        r_method_html = f'<tg-emoji emoji-id="{r_method_eid}">💳</tg-emoji>'
        # Fetch username to show instead of raw user ID
        try:
            with db_lock:
                _uc = get_db_conn()
                _ur = _uc.execute("SELECT username, first_name FROM users WHERE user_id=?", (r_uid,)).fetchone()
                _uc.close()
            _uname = _ur[0] if (_ur and _ur[0]) else None
            _fname = _ur[1] if (_ur and _ur[1]) else None
        except Exception:
            _uname, _fname = None, None
        r_display = f"@{_uname}" if _uname else (_fname or str(r_uid))
        detail_txt = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"《 {PEM['money']} REQUEST #{r_id} 》\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['user']} <b>User:</b> <a href='tg://user?id={r_uid}'>{r_display}</a>\n"
            f'{PEM["money"]} <b>Amount:</b> {format_currency(r_amt)}\n'
            f'{PEM["phone"]} <b>Account:</b> <code>{r_acc}</code>\n'
            f'{r_method_html} <b>Method:</b> {r_method}\n'
            f'{PEM["ok"]} <b>Status:</b> {r_status.upper()}\n'
            f'{PEM["star"]} <b>Time:</b> {ts_str}\n'
            f"━━━━━━━━━━━━━━━━━━"
        )
        if r_status == "pending":
            kb = {"inline_keyboard": [
                [{"text": "APPROVE", "icon_custom_emoji_id": "5352694861990501856", "callback_data": f"wappr_{r_id}", "style": "success"},
                 {"text": "REJECT", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"wrejr_{r_id}", "style": "danger"}],
                [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "view_w_requests", "style": "primary"}]
            ]}
        else:
            kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "view_w_requests", "style": "primary"}]]}
        edit_message(chat_id, msg_id, render_body_text(detail_txt), reply_markup=kb)

    elif data.startswith("wappr_") or data.startswith("wrejr_"):
        if not is_admin(chat_id):
            answer_callback(call["id"], "🚫 Admins only!", show_alert=True)
            return
        action = "APPROVE" if data.startswith("wappr_") else "REJECT"
        db_id = data.replace("wappr_", "").replace("wrejr_", "")
        try:
            with db_lock:
                conn = get_db_conn()
                row = conn.execute(
                    "SELECT id, user_id, amount, method, account, status FROM withdrawals WHERE id=?", (db_id,)
                ).fetchone()
                conn.close()
        except:
            row = None
        if not row:
            answer_callback(call["id"], "❌ Request not found!", show_alert=True)
            return
        r_id, r_uid, r_amt, r_method, r_acc, r_status = tuple(row)
        if r_status != "pending":
            answer_callback(call["id"], "❌ Already processed!", show_alert=True)
            return
        new_status = "approved" if action == "APPROVE" else "rejected"
        try:
            with db_lock:
                conn = get_db_conn()
                conn.execute("UPDATE withdrawals SET status=? WHERE id=?", (new_status, db_id))
                conn.commit()
                conn.close()
        except: pass
        if action == "REJECT":
            update_balance(r_uid, r_amt)
            send_message(r_uid, render_body_text(f"{PEM['no']} Your {format_currency(r_amt)} withdrawal request was rejected. Balance refunded."))
        else:
            send_message(r_uid, render_body_text(f"{PEM['ok']} Your {format_currency(r_amt)} withdrawal request has been paid!"))
        status_icon = "5352694861990501856" if action == "APPROVE" else "5420130255174145507"
        r_method_eid2 = get_payment_emoji_id(r_method)
        r_method_html2 = f'<tg-emoji emoji-id="{r_method_eid2}">💳</tg-emoji>'
        # Fetch username for done message
        try:
            with db_lock:
                _dc = get_db_conn()
                _dr = _dc.execute("SELECT username, first_name FROM users WHERE user_id=?", (r_uid,)).fetchone()
                _dc.close()
            _duname = _dr[0] if (_dr and _dr[0]) else None
            _dfname = _dr[1] if (_dr and _dr[1]) else None
        except Exception:
            _duname, _dfname = None, None
        r_done_display = f"@{_duname}" if _duname else (_dfname or str(r_uid))
        done_txt = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"《 {PEM['money']} REQUEST #{r_id} — {new_status.upper()} 》\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['user']} <b>User:</b> <a href='tg://user?id={r_uid}'>{r_done_display}</a>\n"
            f"{PEM['money']} <b>Amount:</b> {format_currency(r_amt)}\n"
            f"{PEM['phone']} <b>Account:</b> <code>{r_acc}</code>\n"
            f"{r_method_html2} <b>Method:</b> {r_method}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{PEM['ok'] if action == 'APPROVE' else PEM['no']} <b>Processed by admin</b>"
        )
        kb = {"inline_keyboard": [
            [{"text": new_status.upper(), "icon_custom_emoji_id": status_icon, "callback_data": "ignore", "style": "success" if action == "APPROVE" else "danger"}],
            [{"text": "Back to Requests", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "view_w_requests", "style": "primary"}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(done_txt), reply_markup=kb)
        answer_callback(call["id"])

    elif data == "dxa_toggle_w":
        bot_settings["withdraw_on"] = not bot_settings["withdraw_on"]
        save_db()
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())

    elif data == "dxa_toggle_refer":
        bot_settings["refer_on"] = not bot_settings.get("refer_on", True)
        save_db()
        status = "ON ✅" if bot_settings["refer_on"] else "OFF ❌"
        answer_callback(call["id"], f"Refer & Earn: {status}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())

    elif data == "dxa_toggle_lb":
        bot_settings["leaderboard_on"] = not bot_settings.get("leaderboard_on", True)
        save_db()
        status = "ON ✅" if bot_settings["leaderboard_on"] else "OFF ❌"
        answer_callback(call["id"], f"Leaderboard: {status}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())

    elif data == "dxa_toggle_auto_w":
        bot_settings["auto_withdraw"] = not bot_settings.get("auto_withdraw", False)
        save_db()
        status = "ON ✅" if bot_settings["auto_withdraw"] else "OFF ❌"
        answer_callback(call["id"], f"Auto Withdraw: {status}", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text("🕹 <b>DEV CONTROL PANEL</b>"), reply_markup=dxa_control_keyboard())

    elif data == "manage_w_methods":
        edit_message(chat_id, msg_id, render_body_text("💳 <b>WITHDRAWAL METHODS</b>\n\nManage your withdrawal methods below:"), reply_markup=w_methods_keyboard())

    elif data == "add_wm":
        user_states[chat_id] = "wait_for_add_wm"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the name of the new Withdrawal Method:"), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_w_methods", "style": "danger"}]]})

    elif data.startswith("del_wm_"):
        idx = int(data.split("_")[2])
        if 0 <= idx < len(bot_settings["w_methods"]):
            del bot_settings["w_methods"][idx]
            save_db()
            answer_callback(call["id"], "✅ Method deleted!", show_alert=True)
            edit_message(chat_id, msg_id, render_body_text("💳 <b>WITHDRAWAL METHODS</b>\n\nManage your withdrawal methods below:"), reply_markup=w_methods_keyboard())

    elif data.startswith("dxa_"):
        key = data.replace("dxa_", "")
        key_map = {"min_w": "min_withdraw", "otp_r": "otp_reward", "cool": "cooldown", "num_req": "num_req", "sup_link": "support_link", "traffic_w": "traffic_window", "num_expiry": "num_expiry", "old_num": "old_num_window", "ref_comm": "ref_commission"}
        if key in key_map:
            temp_data[chat_id] = {"msg_id": msg_id, "key": key_map[key]}
            user_states[chat_id] = "set_dxa"
            cancel_kb = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_dxa_edit", "style": "danger"}]]}
            prompt = f"📝 Please send the new value for <code>{key_map[key]}</code>:"
            edit_message(chat_id, msg_id, render_body_text(prompt), reply_markup=cancel_kb)
            answer_callback(call["id"])

    elif data == "toggle_cc":
        # Add CC / Remove CC removed: numbers always copy without country code.
        answer_callback(call["id"])
        return
        session = user_active_sessions.get(chat_id)
        if not session:
            answer_callback(call["id"], "❌ Session expired. Please get a new number.", show_alert=True)
            return
        cc_on   = not session.get("cc_on", True)
        nums    = session.get("nums", [])
        service = session.get("service", "")
        country = session.get("country", "")
        msg_id  = session.get("msg_id")
        session["cc_on"] = cc_on
        _set_user_cc(chat_id, cc_on)

        emoji_id_srv, _ = _get_svc_icon_info(service)
        if not emoji_id_srv:
            apps_db = bot_settings.get("premium_apps", {})
            for app_key, app_data in apps_db.items():
                if service.upper() == app_key or service.upper() in app_key or app_key in service.upper():
                    if "id" in app_data:
                        emoji_id_srv = app_data["id"]
                        break
        if not emoji_id_srv:
            emoji_id_srv = "5337302974806922068"

        country_name_disp, hdr_flag_html = _flag_display(country)
        app_full_name_tc, srv_html_cb = get_service_info_html(service)
        _tc_otp_price = _get_batch_price(service, country)
        header_txt = render_body_text(
            f"{_format_svc(app_full_name_tc, srv_html_cb)}  |  {hdr_flag_html} <b>{country_name_disp}</b>\n"
            f'<tg-emoji emoji-id="5409048419211682843">💲</tg-emoji> Price: <b>{format_currency(_tc_otp_price)}</b> / OTP'
        )
        kb = _build_num_card_kb(nums, service, country, emoji_id_srv, cc_on)
        kb.append([
            {"text": "Country", "icon_custom_emoji_id": "5370715282044100355", "callback_data": f"g_c_{service}", "style": "primary"},
            {"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": f"c_n_{service}_{country}", "style": "success"}
        ])
        if cc_on:
            kb.append([{"text": "Remove CC", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "toggle_cc", "style": "danger"}])
        else:
            kb.append([{"text": "Add CC", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "toggle_cc", "style": "success"}])
        kb.append([{"text": "OTP Group", "icon_custom_emoji_id": "5429405838345265327", "url": bot_settings["otp_link"]}])

        answer_callback(call["id"])
        if msg_id:
            try:
                edit_message(chat_id, msg_id, header_txt, reply_markup={"inline_keyboard": kb})
            except Exception:
                pass

    elif data == "get_number":
        local_srvs = set([b["service"] for b in number_batches.values() if b["numbers"]])
        voltx_srvs = set(bot_settings.get("voltx_services", {}).keys())
        stex_srvs  = set(bot_settings.get("stex_services",  {}).keys())
        all_services = local_srvs.union(voltx_srvs).union(stex_srvs)
        # Hide services where every country is locked
        all_services = {s for s in all_services if _service_visible_to_users(s)}
        if not all_services:
            answer_callback(call["id"], "❌ No numbers or services available!", show_alert=True)
        else:
            c_msg = bot_settings["custom_messages"].get("get_number", {})
            txt = render_body_text(c_msg.get("text", f"{PEM['pin']} Select Service"))
            gn_kb = []
            for s in sorted(all_services):
                gn_kb.append([_svc_btn(s, f"g_s_{s}", "primary")])
            for b in c_msg.get("buttons", []):
                b_copy = b.copy()
                if "style" not in b_copy: b_copy["style"] = "primary"
                gn_kb.append([b_copy])
            gn_kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
            edit_message(chat_id, msg_id, txt, reply_markup={"inline_keyboard": gn_kb})

    elif data.startswith("g_s_"):
        service = data.split("g_s_")[1]
        local_cnts = set([b["country"] for b in number_batches.values() if b["service"] == service and b["numbers"]])
        voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
        stex_cnts  = set(bot_settings.get("stex_services",  {}).get(service, {}).keys())
        all_countries = local_cnts.union(voltx_cnts).union(stex_cnts)

        # Filter out locked countries — users cannot see or select them
        all_countries = {c for c in all_countries if not is_country_locked(service, c)}

        c_msg = bot_settings["custom_messages"].get("select_country", {})
        raw_txt = c_msg.get("text", "📌 Select a country for {service}:").replace("{service}", service)
        txt = render_body_text(raw_txt)
        
        flags_db     = bot_settings.get("premium_flags", {})
        _svc_prices  = bot_settings.get("service_country_prices", {}).get(service, {})
        _def_rate    = bot_settings.get("service_otp_prices", {}).get(service, bot_settings.get("otp_reward", 0.1))
        kb = []
        for c in all_countries:
            display_name, _ = _flag_display(c)
            # Resolve emoji ID using full match logic (same as _flag_display)
            base_c = c.split(" ")[0]
            emoji_id = "5780471598922337683"
            for flag_code, flag_data in flags_db.items():
                fiso = flag_data.get("iso", "").upper()
                fname = flag_data.get("name", "").upper()
                if (flag_code == c or _country_code_matches(c, fiso, fname) or
                        flag_code == base_c or _country_code_matches(base_c, fiso, fname)):
                    if "id" in flag_data:
                        emoji_id = flag_data["id"]
                        break
            c_rate    = _svc_prices.get(c, _def_rate)
            btn_label = f"{display_name}  —  {format_currency(c_rate)}/OTP"
            kb.append([{"text": btn_label, "icon_custom_emoji_id": emoji_id, "callback_data": f"g_c_{service}_{c}", "style": "success"}])
        
        for b in c_msg.get("buttons", []): 
            b_copy = b.copy()
            if "style" not in b_copy: b_copy["style"] = "primary"
            kb.append([b_copy])
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "get_number", "style": "danger"}])
        edit_message(chat_id, msg_id, txt, reply_markup={"inline_keyboard": kb})

    elif data.startswith("ntf_get_"):
        # format: ntf_get_{service}||{country}  (|| separator avoids breaking on _ in service names)
        payload = data[len("ntf_get_"):]
        if "||" in payload:
            ntf_service, ntf_country = payload.split("||", 1)
        else:
            # Legacy fallback: ntf_get_{service}_{country}
            parts = payload.split("_", 1)
            ntf_service = parts[0] if parts else ""
            ntf_country = parts[1] if len(parts) > 1 else ""

        # Cooldown check — same as normal GET NUMBER
        now = time.time()
        if now - user_cooldowns.get(chat_id, 0) < bot_settings["cooldown"]:
            answer_callback(call["id"], f"⌛ Please wait {int(bot_settings['cooldown'] - (now - user_cooldowns.get(chat_id, 0)))}s.", show_alert=True)
            return
        user_cooldowns[chat_id] = now

        # Build available_indices AND pick/delete in one locked section
        # so no other thread can modify the list between scan and delete.
        with number_batches_lock:
            available_indices = []
            for b_id, b_data in number_batches.items():
                if b_data["service"].upper() == ntf_service.upper() and b_data["country"] == ntf_country:
                    for idx, n_obj in enumerate(b_data["numbers"]):
                        if not n_obj.get("exhausted") and chat_id not in n_obj.get("used_by", []):
                            available_indices.append((b_id, idx))

        if not available_indices:
            answer_callback(call["id"], f"❌ No stock available for {ntf_service}", show_alert=True)
            return

        with number_batches_lock:
            random.shuffle(available_indices)
            fetched_nums = []
            to_delete_ntf = []
            affected_batches_ntf = set()
            for b_id, idx in available_indices:
                if len(fetched_nums) >= bot_settings["num_req"]: break
                if b_id not in number_batches or idx >= len(number_batches[b_id]["numbers"]):
                    continue  # stale index — another thread already deleted it
                n_obj = number_batches[b_id]["numbers"][idx]
                fetched_nums.append(n_obj["num"])
                used_numbers_list.append({
                    "num": n_obj.get("num"),
                    "service": number_batches[b_id].get("service"),
                    "country": number_batches[b_id].get("country")
                })
                to_delete_ntf.append((b_id, idx))
                affected_batches_ntf.add(b_id)
                total_assigned_stats += 1
            # Delete in reverse-index order so earlier indices are not shifted
            for b_id, idx in sorted(to_delete_ntf, key=lambda x: x[1], reverse=True):
                if b_id in number_batches and idx < len(number_batches[b_id]["numbers"]):
                    del number_batches[b_id]["numbers"][idx]
            # Auto-remove batches that are now empty
            for b_id in list(affected_batches_ntf):
                if b_id in number_batches and not number_batches[b_id].get("numbers"):
                    b = number_batches.pop(b_id)
                    _fs_remove_file_for(b.get("service", "UNKNOWN"), b.get("country", "UNKNOWN"))
                    affected_batches_ntf.discard(b_id)

        save_db()
        for b_id in affected_batches_ntf:
            _fs_sync_batch(b_id)

        if not fetched_nums:
            answer_callback(call["id"], "❌ No stock available!", show_alert=True)
            return

        # Build card UI — identical to g_c_ flow
        app_full_name, srv_html_cb = get_service_info_html(ntf_service)
        emoji_id_srv = "5337302974806922068"
        apps_db = bot_settings.get("premium_apps", {})
        for app_key, app_data in apps_db.items():
            if ntf_service.upper() == app_key or ntf_service.upper() in app_key or app_key in ntf_service.upper():
                if "id" in app_data:
                    emoji_id_srv = app_data["id"]
                    break

        country_name_disp, hdr_flag_html = _flag_display(ntf_country)
        _ntf_otp_price = _get_batch_price(ntf_service, ntf_country)
        header_txt = render_body_text(
            f"{_format_svc(app_full_name, srv_html_cb)}  |  {hdr_flag_html} <b>{country_name_disp}</b>\n"
            f'<tg-emoji emoji-id="5409048419211682843">💲</tg-emoji> Price: <b>{format_currency(_ntf_otp_price)}</b> / OTP'
        )
        _cc_pref = _user_cc_on(chat_id)
        kb = _build_num_card_kb(fetched_nums, ntf_service, ntf_country, emoji_id_srv, _cc_pref)
        kb.append([
            {"text": "Country", "icon_custom_emoji_id": "5370715282044100355", "callback_data": f"g_c_{ntf_service}", "style": "primary"},
            {"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": f"c_n_{ntf_service}_{ntf_country}", "style": "success"}
        ])
        kb.append([{"text": "OTP Group", "icon_custom_emoji_id": "5429405838345265327", "url": bot_settings["otp_link"]}])

        answer_callback(call["id"])
        expire_previous_number(chat_id)
        _evict_number_from_other_sessions(fetched_nums, chat_id)
        num_msg_res = send_message(chat_id, header_txt, reply_markup={"inline_keyboard": kb})
        if num_msg_res and "result" in num_msg_res:
            user_active_sessions[chat_id] = {"msg_id": num_msg_res["result"]["message_id"], "nums": fetched_nums, "service": ntf_service, "country": ntf_country, "cc_on": _cc_pref, "assigned_at": time.time()}

    elif data.startswith("g_c_") or data.startswith("c_n_"):

        now = time.time()
        if now - user_cooldowns.get(chat_id, 0) < bot_settings["cooldown"]:
            answer_callback(call["id"], f"⌛ Please wait {int(bot_settings['cooldown'] - (now - user_cooldowns.get(chat_id, 0)))}s.", show_alert=True)
            return
        

        user_cooldowns[chat_id] = now
        
        # expire_previous_number is called AFTER successful fetch below



        parts = data.split("_")
        service = parts[2] if len(parts) > 2 else ""
        country = parts[3] if len(parts) > 3 else ""

        # If only service given (e.g. g_c_WHATSAPP), show country selection
        if not country:
            local_cnts = set([b["country"] for b in number_batches.values() if b["service"] == service and b["numbers"]])
            voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
            stex_cnts  = set(bot_settings.get("stex_services",  {}).get(service, {}).keys())
            all_countries = local_cnts.union(voltx_cnts).union(stex_cnts)
            c_msg = bot_settings["custom_messages"].get("select_country", {})
            raw_txt = c_msg.get("text", "📌 Select a country for {service}:").replace("{service}", service)
            txt = render_body_text(raw_txt)
            flags_db     = bot_settings.get("premium_flags", {})
            _svc_prices2 = bot_settings.get("service_country_prices", {}).get(service, {})
            _def_rate2   = bot_settings.get("service_otp_prices", {}).get(service, bot_settings.get("otp_reward", 0.1))
            ck_kb = []
            for c in all_countries:
                # _flag_display handles suffixed keys like "58 1" → "Venezuela 1"
                display_name, _ = _flag_display(c)
                base_c2 = c.split(" ")[0]
                emoji_id = "5780471598922337683"
                for flag_code, flag_data in flags_db.items():
                    iso  = flag_data.get("iso",  "").upper()
                    name = flag_data.get("name", "").upper()
                    if (c == flag_code or _country_code_matches(c, iso, name) or
                            base_c2 == flag_code or _country_code_matches(base_c2, iso, name)):
                        if "id" in flag_data:
                            emoji_id = flag_data["id"]
                        break
                c_rate2    = _svc_prices2.get(c, _def_rate2)
                btn_label2 = f"{display_name}  —  {format_currency(c_rate2)}/OTP"
                ck_kb.append([{"text": btn_label2, "icon_custom_emoji_id": emoji_id, "callback_data": f"g_c_{service}_{c}", "style": "success"}])
            ck_kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "get_number", "style": "danger"}])
            edit_message(chat_id, msg_id, txt, reply_markup={"inline_keyboard": ck_kb})
            return

        # Build available_indices inside lock so the list is consistent.
        with number_batches_lock:
            available_indices = []
            # Check Local Stock First
            for b_id, b_data in number_batches.items():
                if b_data["service"] == service and b_data["country"] == country:
                    for idx, n_obj in enumerate(b_data["numbers"]):
                        if not n_obj.get("exhausted") and chat_id not in n_obj.get("used_by", []):
                            available_indices.append((b_id, idx))

        # IF NO LOCAL STOCK, Check Voltx then STEX Services
        fetched_nums = []
        if not available_indices:
            wanted_count = max(1, bot_settings.get("num_req", 1))

            def _fetch_from_api(base_url, api_keys, srv_data, assigned_dict):
                """Try to fetch wanted_count numbers from any API (Voltx or STEX)."""
                nums = []
                if not (srv_data and len(srv_data) > 0 and api_keys):
                    return nums
                ranges_to_try = list(srv_data)
                random.shuffle(ranges_to_try)
                attempts = 0
                max_att = max(wanted_count * len(api_keys) * 3, len(ranges_to_try) * len(api_keys))
                range_idx = 0
                while len(nums) < wanted_count and attempts < max_att and ranges_to_try:
                    target_range = ranges_to_try[range_idx % len(ranges_to_try)]
                    range_idx += 1
                    got_one = False
                    for api_key in api_keys:
                        attempts += 1
                        try:
                            headers = {"mauthapi": api_key}
                            res = requests.post(f"{base_url}/getnum", headers=headers, json={"rid": target_range}, timeout=10)
                            resp_data = res.json()
                            if resp_data.get("meta", {}).get("code") == 200 and "data" in resp_data:
                                full_num = str(resp_data["data"].get("full_number") or resp_data["data"].get("no_plus_number") or "").replace("+", "").strip()
                                if full_num and full_num not in nums:
                                    nums.append(full_num)
                                    assigned_dict[full_num] = chat_id
                                    got_one = True
                                    break
                        except Exception:
                            continue
                    if not got_one and attempts >= max_att:
                        break
                return nums

            # Try Voltx first
            voltx_srv_data = bot_settings.get("voltx_services", {}).get(service, {}).get(country)
            voltx_keys = bot_settings.get("voltx_keys", [])
            fetched_nums = _fetch_from_api(VOLTX_BASE_URL, voltx_keys, voltx_srv_data, voltx_assigned_numbers)
            total_assigned_stats += len(fetched_nums)

            # If Voltx gave nothing, try STEX
            if not fetched_nums:
                stex_srv_data = bot_settings.get("stex_services", {}).get(service, {}).get(country)
                stex_keys = bot_settings.get("stex_keys", [])
                fetched_nums = _fetch_from_api(STEX_BASE_URL, stex_keys, stex_srv_data, stex_assigned_numbers)
                total_assigned_stats += len(fetched_nums)

            if not fetched_nums:
                answer_callback(call["id"])
                edit_message(chat_id, msg_id, render_body_text("❌ <b>Number out of stock!</b>\n\nPlease try again later."), reply_markup={"inline_keyboard": [[{"text": "🔄 Try Again", "icon_custom_emoji_id": "5370715282044100355", "callback_data": "get_number", "style": "primary"}, {"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]})
                return
        else:
            # number_batches_lock makes the select→delete sequence atomic across threads.
            with number_batches_lock:
                random.shuffle(available_indices)
                to_delete_gc = []
                affected_batches_gc = set()

                for b_id, idx in available_indices:
                    if len(fetched_nums) >= bot_settings["num_req"]: break
                    if b_id not in number_batches or idx >= len(number_batches[b_id]["numbers"]):
                        continue  # stale index — another thread already deleted it
                    n_obj = number_batches[b_id]["numbers"][idx]

                    fetched_nums.append(n_obj["num"])
                    used_numbers_list.append({
                        "num": n_obj.get("num"),
                        "service": number_batches[b_id].get("service"),
                        "country": number_batches[b_id].get("country")
                    })
                    to_delete_gc.append((b_id, idx))
                    affected_batches_gc.add(b_id)
                    total_assigned_stats += 1

                # Delete in reverse-index order so earlier indices are not shifted
                for b_id, idx in sorted(to_delete_gc, key=lambda x: x[1], reverse=True):
                    if b_id in number_batches and idx < len(number_batches[b_id]["numbers"]):
                        del number_batches[b_id]["numbers"][idx]
                # Auto-remove batches that are now empty
                for b_id in list(affected_batches_gc):
                    if b_id in number_batches and not number_batches[b_id].get("numbers"):
                        b = number_batches.pop(b_id)
                        _fs_remove_file_for(b.get("service", "UNKNOWN"), b.get("country", "UNKNOWN"))
                        affected_batches_gc.discard(b_id)

            save_db()
            for b_id in affected_batches_gc:
                _fs_sync_batch(b_id)

            if not fetched_nums:
                answer_callback(call["id"])
                edit_message(chat_id, msg_id, render_body_text("❌ <b>Number out of stock!</b>\n\nPlease try again later."), reply_markup={"inline_keyboard": [[{"text": "🔄 Try Again", "icon_custom_emoji_id": "5370715282044100355", "callback_data": "get_number", "style": "primary"}, {"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]})
                return

        app_full_name, srv_html_cb = get_service_info_html(service)
        emoji_id_srv, _srv_char = _get_svc_icon_info(service)
        if not emoji_id_srv:
            emoji_id_srv = "5337302974806922068"

        # Country display — uses _flag_display() which handles suffixed keys like "966 1"
        country_name_disp, hdr_flag_html3 = _flag_display(country)
        _gc_otp_price = _get_batch_price(service, country)
        header_txt = render_body_text(
            f"{_format_svc(app_full_name, srv_html_cb)}  |  {hdr_flag_html3} <b>{country_name_disp}</b>\n"
            f'<tg-emoji emoji-id="5409048419211682843">💲</tg-emoji> Price: <b>{format_currency(_gc_otp_price)}</b> / OTP'
        )
        # Number rows
        _cc_pref = _user_cc_on(chat_id)
        kb = _build_num_card_kb(fetched_nums, service, country, emoji_id_srv, _cc_pref)
        # Bottom action row
        kb.append([
            {"text": "Country", "icon_custom_emoji_id": "5370715282044100355", "callback_data": f"g_c_{service}", "style": "primary"},
            {"text": "Refresh", "icon_custom_emoji_id": "5798596554184986461", "callback_data": f"c_n_{service}_{country}", "style": "success"}
        ])
        kb.append([{"text": "OTP Group", "icon_custom_emoji_id": "5429405838345265327", "url": bot_settings["otp_link"]}])

        expire_previous_number(chat_id, current_msg_id=msg_id)
        _evict_number_from_other_sessions(fetched_nums, chat_id)
        try:
            edit_message(chat_id, msg_id, header_txt, reply_markup={"inline_keyboard": kb})
            user_active_sessions[chat_id] = {"msg_id": msg_id, "nums": fetched_nums, "service": service, "country": country, "cc_on": _cc_pref, "assigned_at": time.time()}
        except:
            num_msg_res = send_message(chat_id, header_txt, reply_markup={"inline_keyboard": kb})
            if num_msg_res and "result" in num_msg_res:
                user_active_sessions[chat_id] = {"msg_id": num_msg_res["result"]["message_id"], "nums": fetched_nums, "service": service, "country": country, "cc_on": _cc_pref, "assigned_at": time.time()}

    elif data.startswith("wapp_") or data.startswith("wrej_"):

        user_id_clicked = call["from"]["id"]
        if not is_admin(user_id_clicked):
            answer_callback(call["id"], "🚫 Only Bot Admins can process withdrawals!", show_alert=True)
            return
            
        action = "APPROVE" if data.startswith("wapp_") else "REJECT"
        req_id = data.replace("wapp_", "").replace("wrej_", "")
        
        if req_id in pending_withdrawals:
            req_data = pending_withdrawals[req_id]
            u_id, amt = req_data["user_id"], req_data["amount"]
            num = req_data["number"]
            method = req_data.get("method", "")
            full_name = req_data.get("full_name", u_id)
            # New requests carry the SQLite row id.  Restored requests from
            # older databases carry it as db_id; never use the display
            # request id (W_...) as SQLite's integer primary key.
            db_id = req_data.get("db_id")
            if db_id is None:
                with db_lock:
                    conn = get_db_conn()
                    row = conn.execute(
                        "SELECT id FROM withdrawals "
                        "WHERE request_id=? AND status='pending'",
                        (req_id,),
                    ).fetchone()
                    conn.close()
                db_id = row[0] if row else None
            if action == "REJECT":
                # ── Reject: refund balance ──────────────────────────────────
                update_balance(u_id, amt)
                emoji_icon_id = "5420130255174145507"
                new_text = f"🎙 <b>WITHDRAWAL REJECTED</b>\n\n👤 <b>USER:</b> <a href='tg://user?id={u_id}'>{full_name}</a>\n💳 <b>WITHDRAWAL:</b> {format_currency(amt)}\n🍏 <b>NUMBER:</b> <code>{num}</code>\n🏦 <b>METHOD:</b> {method}\n\n🧾 <b>REQ ID:</b> {req_id}\n❌ <b>REJECTED BY ADMIN</b>"
                kb = {"inline_keyboard": [[{"text": "REJECTED", "icon_custom_emoji_id": emoji_icon_id, "callback_data": "ignore", "style": "danger"}]]}
                edit_message(chat_id, msg_id, render_body_text(new_text), reply_markup=kb)
                send_message(u_id, render_body_text(f"❌ Your {format_currency(amt)} withdrawal request was rejected. Balance refunded."))
                try:
                    with db_lock:
                        conn = get_db_conn()
                        if db_id is not None:
                            conn.execute(
                                "UPDATE withdrawals SET status='rejected' "
                                "WHERE id=? AND status='pending'",
                                (db_id,),
                            )
                        conn.commit(); conn.close()
                except Exception as db_error:
                    print(f"[withdrawal] reject status update error: {db_error}")

            else:
                # ── Approve ─────────────────────────────────────────────────
                if True:
                    if len(num) >= 7:
                        masked_num = f"{num[:4]}❖DXA❖{num[-3:]}"
                    else:
                        masked_num = num
                    new_text = f"🎙 <b>WITHDRAWAL APPROVED</b>\n\n👤 <b>USER:</b> <a href='tg://user?id={u_id}'>{full_name}</a>\n💳 <b>WITHDRAWAL:</b> {format_currency(amt)}\n🍏 <b>NUMBER:</b> <code>{masked_num}</code>\n🏦 <b>METHOD:</b> {method}\n\n🧾 <b>REQ ID:</b> {req_id}\n✅ <b>APPROVED BY ADMIN</b>"
                    kb = {"inline_keyboard": [[{"text": "APPROVED", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "ignore", "style": "success"}]]}
                    edit_message(chat_id, msg_id, render_body_text(new_text), reply_markup=kb)
                    send_message(u_id, render_body_text(f"{PEM['ok']} Your {format_currency(amt)} withdrawal request has been paid successfully!"))
                    try:
                        with db_lock:
                            conn = get_db_conn()
                            if db_id is not None:
                                conn.execute(
                                    "UPDATE withdrawals SET status='approved' "
                                    "WHERE id=? AND status='pending'",
                                    (db_id,),
                                )
                            conn.commit(); conn.close()
                    except Exception as db_error:
                        print(f"[withdrawal] approve status update error: {db_error}")

            del pending_withdrawals[req_id]
        else:
            answer_callback(call["id"], "❌ Request already processed!", show_alert=True)


def voltx_sms_listener():
    """
    Polls all Voltx API keys for new OTPs every 1 s.
    Each Telegram send is enqueued (non-blocking) so the polling loop
    never stalls waiting for Telegram to respond.
    """
    while True:
        try:
            voltx_keys = bot_settings.get("voltx_keys", [])
            for api_key in voltx_keys:
                try:
                    headers  = {"mauthapi": api_key}
                    res      = requests.get(f"{VOLTX_BASE_URL}/success-otp", headers=headers, timeout=10)
                    resp_data = res.json()

                    if (resp_data.get("meta", {}).get("code") == 200
                            and "data" in resp_data
                            and "otps" in resp_data["data"]):
                        for item in resp_data["data"]["otps"]:
                            num      = str(item.get("number", "")).replace("+", "")
                            msg_text = str(item.get("message", ""))
                            otp_id   = str(item.get("otp_id") or "")

                            if not num:
                                continue

                            # BUG FIX: was `extract_otp_code(msg_text) or "CODE"` —
                            # if no OTP is found the string "CODE" was used as the
                            # OTP code, forwarded to groups/inbox, AND balance was
                            # credited for a non-OTP message.  Skip items with no
                            # extractable OTP code entirely.
                            otp = extract_otp_code(msg_text)
                            if not otp:
                                continue

                            # Use otp_id as dedup anchor when available (stable
                            # across polls); fall back to otp code if absent.
                            dedup_anchor = otp_id if otp_id else otp
                            unique_id  = f"VOLTX_{num}_{dedup_anchor}"
                            if not _otp_mark(unique_id):
                                continue  # already forwarded

                            app_name     = detect_service(msg_text) or "Voltx Service"
                            char, iso    = get_flag_and_code(num)
                            app_full_name, prem_app_html = get_service_info_html(app_name, msg_text)

                            recent_traffic.append({
                                "service": app_full_name, "iso": iso,
                                "flag": char, "number": num, "time": time.time()
                            })
                            # Count ALL Voltx OTPs (not just matched) in today_stats
                            try:
                                _vt_d = datetime.now().strftime("%Y-%m-%d")
                                if today_stats.get("date") != _vt_d:
                                    today_stats.update({"date": _vt_d, "earned": 0.0, "by_service": {}})
                                _vt_s = (app_full_name or "Unknown").strip()
                                _vt_i = iso or "??"
                                today_stats["by_service"].setdefault(_vt_s, {})
                                today_stats["by_service"][_vt_s][_vt_i] = today_stats["by_service"][_vt_s].get(_vt_i, 0) + 1
                            except Exception:
                                pass

                            display_num = f"+{num}" if not str(num).startswith("+") else str(num)
                            masked      = mask_number(display_num)
                            lang        = detect_language(msg_text)
                            display_msg = render_body_text(
                                f"╔═══════════════╗\n║ {_format_svc(app_full_name, prem_app_html)} {get_flag_info_html(display_num)} <b>{iso}</b> <b>{masked}</b> {lang}\n╚═══════════════╝"
                            )

                            # Enqueue fw_group sends — non-blocking. Each group
                            # isolated so one broken config can't block others
                            # or the owner-inbox dispatch further below.
                            for fw in bot_settings.get("fw_groups", []):
                                try:
                                    kb = build_otp_fw_kb(otp, fw)
                                    _enqueue_otp_send(send_otp_message, fw["chat_id"], display_msg, {"inline_keyboard": kb})
                                except Exception as e:
                                    print(f"[OTP] fw_group send failed ({fw.get('chat_id')}): {e}")

                            # Resolve owner (session or voltx_assigned_numbers)
                            clean_api_num = num.replace("+", "").replace(" ", "").replace("-", "").strip()
                            owner_id      = None
                            owner_service = None
                            owner_country = None

                            for uid, session_data in list(user_active_sessions.items()):
                                for act_num in session_data.get("nums", []):
                                    act_clean = str(act_num).replace("+", "").replace(" ", "").replace("-", "").strip()
                                    if _numbers_match(act_clean, clean_api_num):
                                        owner_id      = uid
                                        owner_service = session_data.get("service")
                                        owner_country = session_data.get("country")
                                        break
                                if owner_id:
                                    break

                            if not owner_id:
                                for vtx_n, n_owner in list(voltx_assigned_numbers.items()):
                                    clean_vtx = str(vtx_n).replace("+", "").replace(" ", "").replace("-", "").strip()
                                    if _numbers_match(clean_vtx, clean_api_num):
                                        owner_id = n_owner
                                        break

                            if owner_id:
                                if owner_service:
                                    o_app_full, o_prem_html = get_service_info_html(owner_service)
                                else:
                                    o_app_full, o_prem_html = app_full_name, prem_app_html

                                inbox_msg = render_body_text(
                                    f"╔═══════════════╗\n║ {_format_svc(o_app_full, o_prem_html)} {get_flag_info_html(display_num)} <b>{iso}</b> {lang}\n╚═══════════════╝\n<b>{display_num}</b>"
                                )
                                inbox_kb = [[{"text": f"{otp}", "icon_custom_emoji_id": "6068830682359010545",
                                              "copy_text": {"text": otp}, "style": "success"}]]

                                reward = get_service_otp_reward(o_app_full, owner_country, owner_service)
                                if reward > 0:
                                    update_balance(owner_id, reward)
                                    inbox_kb.append([{"text": f"Added {format_currency(reward)}",
                                                      "icon_custom_emoji_id": "5409048419211682843",
                                                      "callback_data": "ignore", "style": "primary"}])
                                pay_ref_commission(owner_id, reward)
                                # Track today earned only (by_service already counted above for all OTPs)
                                _vt_today = datetime.now().strftime("%Y-%m-%d")
                                if today_stats.get("date") != _vt_today:
                                    today_stats.update({"date": _vt_today, "earned": 0.0, "by_service": {}})
                                today_stats["earned"] = today_stats.get("earned", 0.0) + reward

                                _enqueue_otp_send(send_otp_message, owner_id, inbox_msg, {"inline_keyboard": inbox_kb})

                                def _update_db(oid=owner_id):
                                    try:
                                        with db_lock:
                                            conn = get_db_conn()
                                            conn.execute("UPDATE users SET total_otps=total_otps+1 WHERE user_id=?", (oid,))
                                            conn.commit()
                                            conn.close()
                                        if oid in user_cache:
                                            user_cache[oid]["total_otps"] = user_cache[oid].get("total_otps", 0) + 1
                                        # lb_record_otp is the single place that updates both the DB
                                        # leaderboard table AND the in-memory daily_otps mirror.
                                        # It must only be called ONCE per OTP — calling it here (inside
                                        # _update_db which is enqueued) and also outside caused every
                                        # Voltx OTP to be counted twice in leaderboard and "Today OTPs".
                                        lb_record_otp(oid)
                                    except Exception:
                                        pass
                                _enqueue_otp_send(_update_db)
                except Exception as _voltx_key_err:
                    # BUG FIX: was `except: pass` — all per-key errors (network
                    # failure, bad JSON, parse error) were silently swallowed with
                    # no trace, making it impossible to diagnose Voltx delivery
                    # failures.  Now logged so issues are visible in the console.
                    print(f"[Voltx] key error: {_voltx_key_err}")
        except Exception as _voltx_outer_err:
            print(f"[Voltx] outer loop error: {_voltx_outer_err}")
        time.sleep(1)   # was 2 s → now 1 s for faster OTP pickup

def stex_sms_listener():
    """
    Polls all STEX API keys for new OTPs every 1 s.
    Same logic as voltx_sms_listener but uses STEX_BASE_URL and stex_assigned_numbers.
    """
    while True:
        try:
            stex_keys = bot_settings.get("stex_keys", [])
            for api_key in stex_keys:
                try:
                    headers  = {"mauthapi": api_key}
                    res      = requests.get(f"{STEX_BASE_URL}/success-otp", headers=headers, timeout=10)
                    resp_data = res.json()

                    if (resp_data.get("meta", {}).get("code") == 200
                            and "data" in resp_data
                            and "otps" in resp_data["data"]):
                        for item in resp_data["data"]["otps"]:
                            num      = str(item.get("number", "")).replace("+", "")
                            msg_text = str(item.get("message", ""))
                            otp_id   = str(item.get("otp_id") or "")

                            if not num:
                                continue

                            # BUG FIX: same as Voltx — skip items where no OTP
                            # code can be extracted instead of forwarding "CODE"
                            # and wrongly crediting balance for a non-OTP message.
                            otp = extract_otp_code(msg_text)
                            if not otp:
                                continue

                            dedup_anchor = otp_id if otp_id else otp
                            unique_id = f"STEX_{num}_{dedup_anchor}"
                            if not _otp_mark(unique_id):
                                continue  # already forwarded

                            app_name     = detect_service(msg_text) or "STEX SMS"
                            char, iso    = get_flag_and_code(num)
                            app_full_name, prem_app_html = get_service_info_html(app_name, msg_text)

                            recent_traffic.append({
                                "service": app_full_name, "iso": iso,
                                "flag": char, "number": num, "time": time.time()
                            })
                            # Count ALL STEX OTPs (not just matched) in today_stats
                            try:
                                _sx_d = datetime.now().strftime("%Y-%m-%d")
                                if today_stats.get("date") != _sx_d:
                                    today_stats.update({"date": _sx_d, "earned": 0.0, "by_service": {}})
                                _sx_s = (app_full_name or "Unknown").strip()
                                _sx_i = iso or "??"
                                today_stats["by_service"].setdefault(_sx_s, {})
                                today_stats["by_service"][_sx_s][_sx_i] = today_stats["by_service"][_sx_s].get(_sx_i, 0) + 1
                            except Exception:
                                pass

                            display_num = f"+{num}" if not str(num).startswith("+") else str(num)
                            masked      = mask_number(display_num)
                            lang        = detect_language(msg_text)
                            display_msg = render_body_text(
                                f"╔═══════════════╗\n║ {_format_svc(app_full_name, prem_app_html)} {get_flag_info_html(display_num)} <b>{iso}</b> <b>{masked}</b> {lang}\n╚═══════════════╝"
                            )

                            for fw in bot_settings.get("fw_groups", []):
                                try:
                                    kb = build_otp_fw_kb(otp, fw)
                                    _enqueue_otp_send(send_otp_message, fw["chat_id"], display_msg, {"inline_keyboard": kb})
                                except Exception as e:
                                    print(f"[STEX OTP] fw_group send failed ({fw.get('chat_id')}): {e}")

                            clean_api_num = num.replace("+", "").replace(" ", "").replace("-", "").strip()
                            owner_id      = None
                            owner_service = None
                            owner_country = None

                            for uid, session_data in list(user_active_sessions.items()):
                                for act_num in session_data.get("nums", []):
                                    act_clean = str(act_num).replace("+", "").replace(" ", "").replace("-", "").strip()
                                    if _numbers_match(act_clean, clean_api_num):
                                        owner_id      = uid
                                        owner_service = session_data.get("service")
                                        owner_country = session_data.get("country")
                                        break
                                if owner_id:
                                    break

                            if not owner_id:
                                for stx_n, n_owner in list(stex_assigned_numbers.items()):
                                    clean_stx = str(stx_n).replace("+", "").replace(" ", "").replace("-", "").strip()
                                    if _numbers_match(clean_stx, clean_api_num):
                                        owner_id = n_owner
                                        break

                            if owner_id:
                                if owner_service:
                                    o_app_full, o_prem_html = get_service_info_html(owner_service)
                                else:
                                    o_app_full, o_prem_html = app_full_name, prem_app_html

                                inbox_msg = render_body_text(
                                    f"╔═══════════════╗\n║ {_format_svc(o_app_full, o_prem_html)} {get_flag_info_html(display_num)} <b>{iso}</b> {lang}\n╚═══════════════╝\n<b>{display_num}</b>"
                                )
                                inbox_kb = [[{"text": f"{otp}", "icon_custom_emoji_id": "6068830682359010545",
                                              "copy_text": {"text": otp}, "style": "success"}]]

                                reward = get_service_otp_reward(o_app_full, owner_country, owner_service)
                                if reward > 0:
                                    update_balance(owner_id, reward)
                                    inbox_kb.append([{"text": f"Added {format_currency(reward)}",
                                                      "icon_custom_emoji_id": "5409048419211682843",
                                                      "callback_data": "ignore", "style": "primary"}])
                                pay_ref_commission(owner_id, reward)
                                # Track today earned only (by_service already counted above for all OTPs)
                                _sx_today = datetime.now().strftime("%Y-%m-%d")
                                if today_stats.get("date") != _sx_today:
                                    today_stats.update({"date": _sx_today, "earned": 0.0, "by_service": {}})
                                today_stats["earned"] = today_stats.get("earned", 0.0) + reward

                                _enqueue_otp_send(send_otp_message, owner_id, inbox_msg, {"inline_keyboard": inbox_kb})

                                def _update_db(oid=owner_id):
                                    try:
                                        with db_lock:
                                            conn = get_db_conn()
                                            conn.execute("UPDATE users SET total_otps=total_otps+1 WHERE user_id=?", (oid,))
                                            conn.commit()
                                            conn.close()
                                        if oid in user_cache:
                                            user_cache[oid]["total_otps"] = user_cache[oid].get("total_otps", 0) + 1
                                        # Single call here — the earlier outer lb_record_otp was removed
                                        # because it caused every STEX OTP to count twice in the
                                        # leaderboard and "Today OTPs" (same fix as Voltx above).
                                        lb_record_otp(oid)
                                    except Exception:
                                        pass
                                _enqueue_otp_send(_update_db)
                except Exception as _stex_key_err:
                    # BUG FIX: was `except: pass` — all per-key errors silently
                    # swallowed with no trace.  Now logged for visibility.
                    print(f"[STEX] key error: {_stex_key_err}")
        except Exception as _stex_outer_err:
            print(f"[STEX] outer loop error: {_stex_outer_err}")
        time.sleep(1)

def global_sms_listener():
    # Nexa SMS polling removed — panels handled by panel_monitor_thread and scraper2
    while True:
        time.sleep(60)

def _scraper2_otp_callback(num: str, otp: str, msg_text: str, panel_name: str, cli: str = "", received_ts: str = ""):
    """
    Called from scraper2's asyncio thread — MUST return in microseconds.

    BUG FIX (high-load OTP skip): the old version ran detect_service(),
    get_flag_and_code(), render_body_text(), and built display_msg all
    SYNCHRONOUSLY here in the asyncio event loop thread, then enqueued the
    result.  Under high load (200 OTPs/batch) that is ~2 ms per OTP ×
    200 = 400 ms of event-loop blocking, during which fetch_records() on
    all other panels cannot run — new records pile up on the server and
    can fall off its visible list before the next poll, causing permanent
    OTP loss.

    Fix: make this callback identical to _process_otp_item — just parse
    the timestamp, dedup-check, and enqueue.  All enrichment (service
    detection, flag lookup, display message formatting) runs in a sender
    thread via _enrich_and_forward_otp, completely off the asyncio loop.
    The dedup key and forwarding logic are identical to the API-panel path
    so cross-source deduplication continues to work correctly.
    """
    # Parse received_ts string → Unix float (or None if absent/unparseable).
    # Must happen here because _parse_row_timestamp is not async-safe to
    # call from a sender thread (it only reads, but keep it on this side
    # to keep item dict self-contained).
    _recv_ts = _parse_row_timestamp(received_ts) if received_ts else None

    # Build a normalised item dict compatible with _process_otp_item /
    # _enrich_and_forward_otp — same shape as what parse_panel_response
    # produces for the API-panel path.
    item = {
        "number":      num,
        "otp":         otp,
        "message":     msg_text,
        "cli":         cli,
        "received_ts": _recv_ts,
    }

    # Delegate to the shared hot path: dedup + enqueue enrichment.
    # Returns in ~1 µs; all heavy work runs in a sender thread.
    _process_otp_item(item, panel_name)


def main():
    global BOT_USERNAME, BOT_NAME
    res = api_call("getMe")
    if res.get("ok"):
        BOT_USERNAME = res["result"]["username"]
        BOT_NAME = res["result"].get("first_name", BOT_USERNAME)
    print(f"🤖 Bot is starting... @{BOT_USERNAME}")

    # Migrate start message to new clean format
    NEW_START_TEXT = (
        '<tg-emoji emoji-id="5199885118214255386">👋</tg-emoji> '
        "Welcome to <b>{bot_name}</b>, <b>{name}</b>!\n\n"
        '<tg-emoji emoji-id="4958479549265347295">⚡</tg-emoji> Fast delivery\n'
        '<tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji> Secure numbers\n'
        '<tg-emoji emoji-id="5017470156276761427">♻️</tg-emoji> Change anytime\n\n'
        '<tg-emoji emoji-id="5042147419156907206">👇</tg-emoji> <i>Choose an option below to begin:</i>'
    )
    bot_settings.setdefault("custom_messages", {}).setdefault("start", {})["text"] = NEW_START_TEXT
    save_db()
    
    threading.Thread(target=panel_monitor_thread, daemon=True).start()
    threading.Thread(target=low_stock_monitor_thread, daemon=True, name="low-stock-monitor").start()
    threading.Thread(target=global_sms_listener, daemon=True).start()
    threading.Thread(target=voltx_sms_listener, daemon=True).start()
    threading.Thread(target=stex_sms_listener,  daemon=True).start()
    print("📡 Background APIs & Global SMS Listener Started!")

    # 🌟 Scraper2 — Method 2 (IVAS, PSCall, Multi-Panel backup method)
    try:
        import scraper2
        scraper2.start(on_otp_found=_scraper2_otp_callback, get_settings=lambda: bot_settings)
        print("🔄 Scraper2 (Method 2) Started!")
    except Exception as e:
        print(f"⚠️ Scraper2 load error: {e}")
    
    # ─── MAXIMUM THROUGHPUT SYSTEM ───────────────────────────────────────────
    # • 10,000 logical queued worker slots, with bounded native execution
    # • 50 dedicated OTP sender threads
    # • Queue-based dispatch: polling loop is NEVER blocked by slow handlers
    # • Two separate executors: messages + callbacks — neither starves the other
    # • Thread-local sessions: zero HTTP pool contention across workers
    # • 50 dedicated OTP sender threads drain the forwarding queue in parallel
    threading.stack_size(2 * 1024 * 1024)   # 2 MB stack per thread — 512 KB was too small and caused segfaults in complex handler functions

    # Start OTP forwarding queue workers BEFORE panels start delivering OTPs
    for _i in range(OTP_SENDER_THREADS):
        threading.Thread(target=_otp_sender_worker, daemon=True,
                         name=f"otp-sender-{_i}").start()
    print(f"⚡ {OTP_SENDER_THREADS} OTP sender threads started!")

    # Start the persistent OTP retry worker — handles sends that exhausted all
    # 8 normal rapid retries (sustained flood-wait during heavy panel load).
    threading.Thread(target=_otp_retry_worker, daemon=True,
                     name="otp-retry-worker").start()
    print("⚡ OTP retry worker started (persistent queue active)")

    msg_executor  = ThreadPoolExecutor(max_workers=REAL_MESSAGE_WORKERS)   # message handlers
    cb_executor   = ThreadPoolExecutor(max_workers=REAL_CALLBACK_WORKERS)   # callback handlers
    # Handlers are I/O-bound (Telegram API calls). Native workers stay bounded;
    # the logical queue absorbs bursts up to LOGICAL_WORKER_CAP safely.

    import queue as _queue
    # Up to 10,000 pending logical update slots; native execution remains bounded.
    _update_q = _queue.Queue(maxsize=LOGICAL_WORKER_CAP)

    def _run_callback_safely(callback):
        """Run a callback without allowing executor failures to disappear."""
        try:
            handle_callback(callback)
        except Exception as exc:
            print(f"[callback-worker] unhandled error: {exc}")
            traceback.print_exc()

    def _dispatch_worker():
        """Pulls updates from queue and submits to the right executor."""
        while True:
            try:
                update = _update_q.get()
                if "message" in update:
                    msg_executor.submit(handle_message, update["message"])
                elif "callback_query" in update:
                    cb_executor.submit(_run_callback_safely, update["callback_query"])
            except Exception as exc:
                print(f"[dispatch-worker] error: {exc}")
                traceback.print_exc()
            finally:
                try:
                    _update_q.task_done()
                except Exception:
                    pass

    # 4 dispatcher threads — kept modest to fit a ~1GB RAM server alongside
    # the executor pools above.
    for _ in range(4):
        threading.Thread(target=_dispatch_worker, daemon=True).start()

    offset = None
    while True:
        try:
            # Short timeout (10 s) so the loop spins faster under load
            # NOTE: never pass offset=None as a literal string — Telegram rejects it.
            _poll_method = "getUpdates?timeout=25"
            if offset is not None:
                _poll_method += f"&offset={offset}"
            updates = api_call(_poll_method)
            if updates and "result" in updates:
                for update in updates["result"]:
                    try:
                        _update_q.put(update, timeout=0.25)
                    except _queue.Full:
                        print(f"[dispatch-worker] logical queue full ({LOGICAL_WORKER_CAP}); pausing poll")
                        break
                    offset = update["update_id"] + 1
        except Exception:
            time.sleep(1)

if __name__ == "__main__":
    main()    