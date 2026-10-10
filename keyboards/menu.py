"""Main menu keyboards with premium custom emoji icons."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.config import (
    EMOJI,
    URL_APP,
    URL_EXCHANGE,
    URL_QR_PAY,
)


def _btn(
    text: str,
    *,
    emoji_key: str | None = None,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
) -> InlineKeyboardButton:
    kwargs: dict = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if emoji_key and emoji_key in EMOJI:
        kwargs["icon_custom_emoji_id"] = EMOJI[emoji_key]
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def main_menu_keyboard(
    balance_usd: float = 0.0,
    cheques_n: int = 0,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    from xrocket.config import ADMIN_IDS

    bal = f"{balance_usd:.2f}"
    cheques_label = f"Чеки • {cheques_n}" if cheques_n > 0 else "Чеки"
    rows = [
            [
                _btn(
                    f"Кошелек • {bal} $",
                    emoji_key="wallet",
                    callback_data="wallet:page:0",
                )
            ],
            [
                _btn("Пополнить", emoji_key="deposit", callback_data="noop"),
                _btn("Вывести", emoji_key="withdraw", callback_data="noop"),
            ],
            [
                _btn("Биржа", emoji_key="exchange", url=URL_EXCHANGE),
                _btn("Обмен", emoji_key="swap", callback_data="swap:start"),
            ],
            [
                _btn("Купить/Продать", emoji_key="buy_sell", callback_data="noop"),
                _btn("P2P Маркет", emoji_key="p2p", callback_data="noop"),
            ],
            [
                _btn("Оплатить по QR", emoji_key="qr", url=URL_QR_PAY),
                _btn("Рефералы", emoji_key="referrals", callback_data="noop"),
            ],
            [
                _btn("Pay API", emoji_key="pay_api", callback_data="noop"),
                _btn("Разработчикам", emoji_key="devs", callback_data="noop"),
            ],
            [
                _btn(cheques_label, emoji_key="cheques", callback_data="menu:cheques"),
                _btn("Счета", emoji_key="invoices", callback_data="noop"),
                _btn("Подписки", emoji_key="subs", callback_data="noop"),
            ],
            [
                _btn("Об xRocket", emoji_key="about", callback_data="nav:about"),
                _btn("Команды", emoji_key="commands", callback_data="noop"),
            ],
            [
                _btn("Настройки", emoji_key="settings", callback_data="nav:settings"),
                _btn("Свернуть меню", emoji_key="collapse", callback_data="menu:collapse"),
            ],
            [
                InlineKeyboardButton(
                    text="📱 Открыть приложение",
                    url=URL_APP,
                    style="primary",
                ),
            ],
    ]
    if user_id is not None and user_id in ADMIN_IDS:
        rows.insert(
            -1,
            [
                InlineKeyboardButton(
                    text="🛠 Админ-панель",
                    callback_data="menu:admin",
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cheque_claim_keyboard(
    amount: float, coin_code: str, bot_username: str, code: str
) -> InlineKeyboardMarkup:
    amount_s = str(int(amount)) if abs(amount - round(amount)) < 1e-9 else f"{amount:g}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Получить {amount_s} {coin_code.upper()}",
                    url=f"https://t.me/{bot_username}?start=t_{code}",
                )
            ]
        ]
    )
