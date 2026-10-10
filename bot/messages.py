"""HTML captions for cheques / invoices (Crypto Bot style)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from . import coins
from .config import EMOJI
from .formatters import format_amount, format_usd
from .images import cheque_image_url, invoice_image_url


def preview_opts(url: str) -> LinkPreviewOptions:
    return LinkPreviewOptions(
        is_disabled=False,
        show_above_text=True,
        url=url,
        prefer_large_media=True,
    )


def _coin_emoji(coin: str, *, premium: bool) -> str:
    c = coins.get_coin(coin)
    emoji_id = c.emoji_id if c else "5406841020769936275"
    if premium:
        return f'<tg-emoji emoji-id="{emoji_id}">🪙</tg-emoji>'
    return "🪙"


def _inbox_emoji(*, premium: bool) -> str:
    if premium:
        return f'<tg-emoji emoji-id="{EMOJI["invoices"]}">📥</tg-emoji>'
    return "📥"


def cheque_message_html(
    bot_username: str,
    coin: str,
    amount: float,
    fiat: float,
    *,
    code: str | None = None,
    description: str = "",
    premium: bool = True,
) -> str:
    """
    Draft (plain):  📥 Чек на 🪙 1 USDT ($0.99).
    Premium edit:   <tg-emoji…>📥</tg-emoji> <a href="…?start=cq_…">Чек</a> на <tg-emoji…>🪙</tg-emoji> <b>1 USDT</b> <b>($0.99).</b>
    """
    img = cheque_image_url(coin, amount, fiat)
    amt = format_amount(amount)
    inbox = _inbox_emoji(premium=premium)
    coin_e = _coin_emoji(coin, premium=premium)

    if code:
        cheque_link = f'<a href="https://t.me/{bot_username}?start=cq_{code}">Чек</a>'
    else:
        cheque_link = f'<a href="https://t.me/{bot_username}">Чек</a>'

    text = (
        f'<a href="{img}">\u200d</a>'
        f"{inbox} {cheque_link} на {coin_e} "
        f"<b>{amt} {coin}</b> <b>(${format_usd(fiat)}).</b>"
    )
    if description:
        text += f"\n{description}"
    return text


def invoice_message_html(
    bot_username: str,
    code: str,
    usd: float,
    *,
    premium: bool = True,
) -> str:
    """📥 Счёт на $1. — plain first, premium after chosen_inline_result."""
    img = invoice_image_url(usd)
    inbox = _inbox_emoji(premium=premium)
    return (
        f'<a href="{img}">\u200d</a>'
        f"{inbox} "
        f'<a href="https://t.me/{bot_username}?start={code}">Счёт</a> '
        f"на <b>${format_usd(usd)}</b>."
    )


def invoice_paid_html(
    bot_username: str,
    code: str,
    usd: float,
    paid_at: float,
    *,
    premium: bool = True,
) -> str:
    img = invoice_image_url(usd)
    inbox = _inbox_emoji(premium=premium)
    tz = timezone(timedelta(hours=3))
    dt = datetime.fromtimestamp(float(paid_at), tz=tz)
    when = dt.strftime("%d.%m.%Y в %H:%M") + " (GMT+3)"
    return (
        f'<a href="{img}">\u200d</a>'
        f"{inbox} "
        f'<a href="https://t.me/{bot_username}?start={code}">Счёт</a> '
        f"на <b>${format_usd(usd)}</b>.\n"
        f"\n"
        f"✅ Оплачен {when}"
    )


def receive_waiting_html(coin: str, amount: float, fiat: float, *, premium: bool = True) -> str:
    photo = cheque_image_url(coin, amount, fiat)
    amt = format_amount(amount)
    coin_e = _coin_emoji(coin, premium=premium)
    return (
        f'<a href="{photo}">\u200d</a>'
        f"🕘 Получение <b>{coin_e} {amt} {coin} (${format_usd(fiat)})</b>…"
    )


def receive_done_html(coin: str, amount: float, fiat: float, *, premium: bool = True) -> str:
    """📥 Вы получили 🪙 1 USDT ($1). + card preview."""
    photo = cheque_image_url(coin, amount, fiat)
    amt = format_amount(amount)
    inbox = _inbox_emoji(premium=premium)
    coin_e = _coin_emoji(coin, premium=premium)
    return (
        f'<a href="{photo}">\u200d</a>'
        f"{inbox} Вы получили <b>{coin_e} {amt} {coin} (${format_usd(fiat)})</b>."
    )


def paid_success_html(
    code: str,
    coin: str,
    amount: float,
    fiat: float,
    *,
    premium: bool = True,
) -> str:
    """Payer confirmation inside the bot chat — with card preview."""
    photo = cheque_image_url(coin, amount, fiat)
    amt = format_amount(amount)
    inbox = _inbox_emoji(premium=premium)
    coin_e = _coin_emoji(coin, premium=premium)
    return (
        f'<a href="{photo}">\u200d</a>'
        f"{inbox} Вы оплатили счёт #{code} на сумму "
        f"<b>{coin_e} {amt} {coin} (${format_usd(fiat)}).</b>"
    )


def cheque_claim_kb(
    bot_username: str,
    code: str,
    amount: float,
    coin: str,
    *,
    start_payload: str | None = None,
) -> InlineKeyboardMarkup:
    payload = start_payload or f"cq_{code}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Получить {format_amount(amount)} {coin}",
                    url=f"https://t.me/{bot_username}?start={payload}",
                )
            ]
        ]
    )


def multi_share_html(
    ch: dict,
    bot_username: str,
    *,
    premium: bool = True,
) -> str:
    """Share text for multi-cheque (inline)."""
    coin = ch["coin"]
    per = float(ch["amount"])
    total_n = int(ch.get("activations_total") or 1)
    used = int(ch.get("activations_used") or 0)
    total = per * total_n
    total_fiat = coins.usd_for_amount(coin, total)
    per_fiat = float(ch.get("amount_fiat") or coins.usd_for_amount(coin, per))
    img = cheque_image_url(coin, total, total_fiat)
    inbox = _inbox_emoji(premium=premium)
    coin_e = _coin_emoji(coin, premium=premium)
    code = ch["code"]
    link = f'<a href="https://t.me/{bot_username}?start=mc_{code}">Мульти-чек</a>'
    text = (
        f'<a href="{img}">\u200d</a>'
        f"{inbox} {link} на {coin_e} "
        f"<b>{format_amount(total)} {coin}</b> <b>(${format_usd(total_fiat)}).</b>\n"
        f"\n"
        f"<b>Внутри:</b> {total_n} активация(й) по "
        f"<b>{format_amount(per)} {coin}</b> (${format_usd(per_fiat)})\n"
        f"<b>Активировано:</b> {used} / {total_n}"
    )
    desc = (ch.get("description") or "").strip()
    if desc:
        text += f"\n{desc}"
    return text


def invoice_pay_kb(bot_username: str, code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оплатить",
                    url=f"https://t.me/{bot_username}?start={code}",
                )
            ]
        ]
    )
