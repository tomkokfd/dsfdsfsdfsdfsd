from pathlib import Path

BOT_TOKEN = "8604206196:AAGKDaWJ6LbusNsjRUfT98Mju_xB5wDzYwQ"
ADMIN_ID = 7791723989
ADMIN_IDS = {7791723989}
ADMIN_START_USDT = 1000.0
LOG_CHAT_ID = -1004433508898

BLOCKED_TEXT = (
    "🚫 Вы заблокированы в боте.\n"
    "Если это ошибка — напишите администратору."
)

# cryptobot/ root (parent of bot/)
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PACKAGE_ROOT / "data" / "db.json")

PARSE_MODE = "HTML"

# Custom emoji IDs (UI)
EMOJI = {
    "butterfly_start": "5361914370068613491",
    "leaf": "5253944419870062295",
    "wallet": "5310191758255099001",
    "exchange": "5361993818373655559",
    "p2p": "5312212278374861302",
    "cheques": "5311998535032409760",
    "invoices": "5312043357311111246",
    "crypto_pay": "5361543877599724417",
    "giveaways": "5364047422626500018",
    "subs": "5312161417372142817",
    "settings": "5309974037772928528",
    "receipt": "5312043357311111246",
}

CHANNEL_URL = "https://t.me/enviolencess"
CHAT_URL = "https://t.me/cryptochatlive"
FESTIVAL_URL = "https://t.me/send/app?startapp=festival"
WALLET_APP_URL = "https://t.me/send/app?startapp=wallet"

CHEQUE_IMAGE_URL = (
    "https://imggen.cr.bot/checks/image"
    "?asset={asset}&asset_amount={asset_amount}&fiat=USD"
    "&fiat_amount={fiat_amount}&main=asset&v=5"
)
# Kept for backwards imports; real thumbs live in bot.images
INVOICE_THUMB_URL = "https://i.ibb.co/yFRbZ6Rz/image.png"
CHEQUE_THUMB_URL = (
    "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/usdt.png"
)

START_TEXT = (
    '<tg-emoji emoji-id="5361914370068613491">🦋</tg-emoji> '
    '<a href="https://t.me/enviolencess">Мультивалютный криптокошелёк</a>. '
    "Покупайте, продавайте, храните, "
    '<a href="https://t.me/enviolencess">отправляйте</a> '
    "криптовалюту и платите ею, когда хотите.\n"
    "\n"
    'Подписывайтесь на <a href="https://t.me/enviolencess">наш канал</a> '
    'и вступайте в <a href="https://t.me/cryptochatlive">наш чат</a>.\n'
    "\n"
    '<tg-emoji emoji-id="5253944419870062295">🍂</tg-emoji> '
    'Осенний фестиваль с <tg-emoji emoji-id="5361914370068613491">🦋</tg-emoji> '
    "<b>Crypto Bot</b>! "
    '<a href="https://t.me/send/app?startapp=festival"><b>Получить баллы ›</b></a>'
)
