from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import coins
from ..action_log import log_action
from ..config import EMOJI
from ..db import db
from ..formatters import format_amount
from ..keyboards import wallet_kb

router = Router(name="wallet")
BOT_LABEL = "Crypto Bot"


def build_wallet_text(user_id: int) -> str:
    balances = db.get_all_balances(user_id)
    wallet_emoji = EMOJI["wallet"]
    lines = [
        f'<tg-emoji emoji-id="{wallet_emoji}">👛</tg-emoji> <b>Кошелёк</b>',
        "",
    ]
    for c in coins.COINS:
        amt = balances.get(c.code, 0.0)
        fmt = format_amount(amt)
        lines.append(
            f'<tg-emoji emoji-id="{c.emoji_id}">🪙</tg-emoji> '
            f'<a href="{c.url}"><b>{c.name}</b></a>: {fmt} {c.code}'
        )
        lines.append("")  # blank line between coins (Crypto Bot spacing)
    # drop trailing empty line
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


async def show_wallet(target: Message | CallbackQuery) -> None:
    if isinstance(target, CallbackQuery):
        user = target.from_user
        message = target.message
        db.ensure_user(user.id, username=user.username, full_name=user.full_name)
        text = build_wallet_text(user.id)
        if not message:
            return
        try:
            await message.edit_text(
                text,
                reply_markup=wallet_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer(
                text,
                reply_markup=wallet_kb(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        user = target.from_user
        db.ensure_user(user.id, username=user.username, full_name=user.full_name)
        text = build_wallet_text(user.id)
        await target.answer(
            text,
            reply_markup=wallet_kb(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.in_({"wallet", "menu:wallet"}))
async def cb_wallet(callback: CallbackQuery) -> None:
    await callback.answer()
    await show_wallet(callback)
    await log_action(
        callback.bot,
        BOT_LABEL,
        "Открыт кошелёк",
        user=callback.from_user,
        emoji_key="wallet",
        fallback="👛",
    )
