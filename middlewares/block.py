"""Block middleware for restricted accounts."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject

from xrocket.config import ADMIN_IDS
from xrocket.data.coin_emojis import UI_EMOJI
from xrocket.database import db

BLOCKED_TEXT = (
    f'<tg-emoji emoji-id="{UI_EMOJI["blocked"]}">❌</tg-emoji>'
    "<b> Доступ к аккаунту ограничен</b>\n\n"
    "Использование <b>xRocket</b> для вашего аккаунта временно недоступно.\n\n"
    "<i>Для получения подробной информации и уточнения причины ограничения "
    "обратитесь в службу поддержки.</i>"
)


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
            if not db.is_user_blocked(user.id):
                return await handler(event, data)
        except Exception:
            return await handler(event, data)

        # First touch → show restriction notice once; then silence forever
        try:
            first = not db.was_block_notice_sent(user.id)
        except Exception:
            first = True

        if first:
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
                    await event.message.edit_text(BLOCKED_TEXT)
                except Exception:
                    try:
                        await event.message.answer(BLOCKED_TEXT)
                    except Exception:
                        pass
                try:
                    await event.answer()
                except Exception:
                    pass
            elif isinstance(event, InlineQuery):
                try:
                    await event.answer(results=[], cache_time=1, is_personal=True)
                except Exception:
                    pass
            return None

        # Subsequent events: no replies
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        elif isinstance(event, InlineQuery):
            try:
                await event.answer(results=[], cache_time=1, is_personal=True)
            except Exception:
                pass
        return None
