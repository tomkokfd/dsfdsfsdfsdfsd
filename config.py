"""Configuration for xRocket Fun Bot (entertainment only)."""

from pathlib import Path

BOT_TOKEN = "8838277127:AAFb1X5UVhexJD1qJHjJbwlkDQ-1Ku9sjk8"

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
DB_JSON_PATH = DATA_DIR / "bot.json"
DB_PATH = DB_JSON_PATH  # legacy alias; persistence is JSON

CHEQUE_THUMB_PATH = ASSETS_DIR / "cheque_thumb.png"
CHEQUE_THUMB_URL = "https://i.ibb.co/jZ9VdCWg/image.png"

INITIAL_BALANCE_USD = 0.0
ADMIN_START_USDT = 1000.0
DEFAULT_COIN = "USDT"

# Deep-link / Mini App URLs from original UX
URL_APP = "https://t.me/xrocket/app?startapp=wallet"
URL_SWAP = "https://t.me/xrocket/app?startapp=swap"
URL_EXCHANGE = "https://t.me/xrocket/app?startapp=exchange"
URL_QR_PAY = "https://t.me/xrocket/app?startapp=qr_pay"
URL_NEWS = "https://t.me/enviolencess"

# Premium custom emoji IDs
EMOJI = {
    "rocket": "5258332798409783582",
    "wallet": "5379639755933781390",
    "deposit": "5222153011815553801",
    "withdraw": "5219926964625779761",
    "exchange": "5379733369040964216",
    "swap": "5222200204916201346",
    "buy_sell": "5377660282816468683",
    "p2p": "5380002586181015442",
    "qr": "5361580286037499439",
    "referrals": "5379722665982466441",
    "pay_api": "5377510826544503722",
    "devs": "5380010248402673340",
    "cheques": "5380066521064183952",
    "invoices": "5379608870823959165",
    "subs": "5379800374825753052",
    "about": "5379612946747921985",
    "commands": "5379634554728389744",
    "settings": "5377531785984907932",
    "collapse": "5379650214179149063",
    "send_money": "5379745661237367511",
    "cheque_board": "5379608870823959165",
    "support": "5380048048409845114",
    "eye": "5379897093194291033",
    "lock": "5380057342719073800",
    "lang": "5379975536476983686",
    "currency": "5379892188341637600",
    "history": "5377529952033873344",
    "listing": "5380107576656565584",
    "link": "5379798613889161748",
    "groups": "5379990740661210900",
    "limits": "5364265190353286344",
    "books": "5379944187510692920",
    "phone": "5380048048409845114",
}

URL_SUPPORT = "https://t.me/hollysceo"

ADMIN_IDS = {7791723989}
LOG_CHAT_ID = -1004433508898
