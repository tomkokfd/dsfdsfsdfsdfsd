"""Wallet screens."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.database import db
from xrocket.keyboards.wallet import (
    display_mode_keyboard,
    overview_keyboard,
    wallet_keyboard,
)
from xrocket.services import balance as balance_service
from xrocket.services.action_log import log_action

router = Router(name="wallet")
BOT_LABEL = "xRocket"


async def _show_wallet(callback: CallbackQuery, page: int = 0) -> None:
    user = callback.from_user
    text, total_pages = balance_service.wallet_text(user.id, page)
    await callback.message.edit_text(
        text,
        reply_markup=wallet_keyboard(page, total_pages),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("wallet:"))
async def open_wallet(callback: CallbackQuery) -> None:
    user = callback.from_user
    db.ensure_user(user.id, user.username, user.full_name)
    parts = (callback.data or "wallet:page:0").split(":")

    action = parts[1] if len(parts) > 1 else "page"

    if action == "0" and len(parts) == 2:
        # legacy wallet:0
        await _show_wallet(callback, 0)
        await callback.answer()
        await log_action(
            callback.bot,
            BOT_LABEL,
            "Открыт кошелёк",
            user=user,
            emoji_key="wallet",
            fallback="👛",
        )
        return

    if action == "page":
        page = int(parts[2]) if len(parts) > 2 else 0
        await _show_wallet(callback, page)
        await callback.answer()
        if page == 0:
            await log_action(
                callback.bot,
                BOT_LABEL,
                "Открыт кошелёк",
                user=user,
                emoji_key="wallet",
                fallback="👛",
            )
        return

    if action == "security":
        # Intentionally do nothing (non-interactive feel)
        await callback.answer()
        return

    if action == "transfer":
        await callback.answer()
        return

    if action == "overview":
        await callback.message.edit_text(
            balance_service.balances_overview_text(user.id),
            reply_markup=overview_keyboard(),
        )
        await callback.answer()
        return

    if action == "view" and len(parts) > 2:
        db.set_balance_view(user.id, parts[2])
        await _show_wallet(callback, 0)
        await callback.answer()
        return

    if action == "display":
        settings = db.get_user_settings(user.id)
        await callback.message.edit_text(
            balance_service.display_settings_text(),
            reply_markup=display_mode_keyboard(settings["display_mode"]),
        )
        await callback.answer()
        return

    if action == "mode" and len(parts) > 2:
        db.set_display_mode(user.id, parts[2])
        await _show_wallet(callback, 0)
        await callback.answer()
        return

    await _show_wallet(callback, 0)
    await callback.answer()
