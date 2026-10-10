"""Block middleware for restricted accounts."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from ..config import ADMIN_IDS, BLOCKED_TEXT
from ..db import db


class BlockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        try:
            blocked = db.is_user_blocked(user.id)
        except Exception:
            return await handler(event, data)

        if not blocked:
            try:
                db.set_bot_blocked(user.id, False)
            except Exception:
                pass
            return await handler(event, data)

        # Blocked: show notice once, then silence
        notice_sent = False
        try:
            u = db.get_user(user.id)
            notice_sent = bool(u and int(u.get("block_notice_sent") or 0))
        except Exception:
            notice_sent = False

        if not notice_sent:
            try:
                db.set_block_notice_sent(user.id, True)
            except Exception:
                pass
            if isinstance(event, Message):
                try:
                    await event.answer(BLOCKED_TEXT)
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    if event.message:
                        await event.message.answer(BLOCKED_TEXT)
                except Exception:
                    pass
                try:
                    await event.answer()
                except Exception:
                    pass
            return None

        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return None
