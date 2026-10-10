"""Action logs → Telegram log chat (premium HTML)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot

log = logging.getLogger("action_log")

# Shared log channel for xRocket + Crypto Bot
try:
    from .config import LOG_CHAT_ID as _CFG_LOG  # type: ignore
except Exception:  # pragma: no cover
    _CFG_LOG = None

LOG_CHAT_ID = int(_CFG_LOG) if _CFG_LOG is not None else -1004433508898

_EMOJI = {
    "butterfly": "5361914370068613491",
    "rocket": "5258332798409783582",
    "wallet": "5310191758255099001",
    "cheque": "5312043357311111246",
    "swap": "5361993818373655559",
    "user": "5311998535032409760",
    "ok": "5310191758255099001",
    "warn": "5253944419870062295",
}


def _e(key: str, fallback: str) -> str:
    eid = _EMOJI.get(key)
    if not eid:
        return fallback
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def user_block(user: Any | None, *, user_id: int | None = None) -> str:
    """Pretty user card fragment for logs."""
    uid = user_id
    username = None
    full_name = None
    if user is not None:
        uid = getattr(user, "id", None) or uid
        username = getattr(user, "username", None)
        full_name = getattr(user, "full_name", None) or getattr(user, "first_name", None)
    uid = int(uid or 0)
    name = _esc((full_name or "User").strip() or "User")
    un = f"@{_esc(username)}" if username else "—"
    mention = f'<a href="tg://user?id={uid}">\u2068{name}\u2069</a>'
    return (
        f"{_e('user', '👤')} <b>Пользователь</b>\n"
        f"· Имя: {mention}\n"
        f"· Username: <code>{un}</code>\n"
        f"· ID: <code>{uid}</code>"
    )


def build_log(
    bot_label: str,
    title: str,
    *,
    user: Any | None = None,
    user_id: int | None = None,
    lines: list[str] | None = None,
    emoji_key: str = "butterfly",
    fallback: str = "🦋",
) -> str:
    head = f"{_e(emoji_key, fallback)} <b>{_esc(bot_label)}</b> · {_esc(title)}"
    parts = [head, ""]
    if user is not None or user_id is not None:
        parts.append(user_block(user, user_id=user_id))
        parts.append("")
    if lines:
        parts.extend(lines)
    return "\n".join(parts).rstrip()


async def send_log(bot: Bot | None, text: str) -> None:
    if not bot or not text:
        return
    try:
        await bot.send_message(
            LOG_CHAT_ID,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.debug("log chat send failed: %s", exc)


async def log_action(
    bot: Bot | None,
    bot_label: str,
    title: str,
    *,
    user: Any | None = None,
    user_id: int | None = None,
    lines: list[str] | None = None,
    emoji_key: str = "butterfly",
    fallback: str = "🦋",
) -> None:
    text = build_log(
        bot_label,
        title,
        user=user,
        user_id=user_id,
        lines=lines,
        emoji_key=emoji_key,
        fallback=fallback,
    )
    await send_log(bot, text)
