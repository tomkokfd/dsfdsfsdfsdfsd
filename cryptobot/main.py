from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

# Allow running as `python main.py` from cryptobot/
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import BOT_TOKEN, DB_PATH  # noqa: E402
from bot.db import Database, db  # noqa: E402
from bot.handlers import setup_routers  # noqa: E402
from bot.handlers import admin as admin_handlers  # noqa: E402
from bot.middlewares.block import BlockMiddleware  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cryptobot")


async def set_commands(bot: Bot) -> None:
    # Clear all scopes, then set the Crypto Bot command list
    from aiogram.types import BotCommandScopeDefault

    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open Main Menu"),
            BotCommand(command="p2p", description="Buy and Sell Crypto"),
            BotCommand(command="wallet", description="Open Wallet"),
            BotCommand(command="checks", description="Send Crypto via Checks"),
            BotCommand(command="invoices", description="Receive Crypto via Invoices"),
            BotCommand(command="giveaways", description="Get new followers by gifting coins"),
            BotCommand(command="subscriptions", description="Open Subscriptions"),
        ],
        scope=BotCommandScopeDefault(),
    )


async def main() -> None:
    # Ensure DB exists
    Database(DB_PATH)
    log.info("Database ready at %s", DB_PATH)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    block_mw = BlockMiddleware()
    dp.message.middleware(block_mw)
    dp.callback_query.middleware(block_mw)
    dp.inline_query.middleware(block_mw)
    dp.include_router(setup_routers())

    await bot.delete_webhook(drop_pending_updates=True)
    await set_commands(bot)
    try:
        await admin_handlers.restore_scheduled_broadcasts(bot)
    except Exception as exc:
        log.warning("restore broadcasts: %s", exc)
    me = await bot.get_me()
    log.info("Starting bot @%s", me.username)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
