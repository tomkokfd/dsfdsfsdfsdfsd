from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import coins
from .config import ADMIN_IDS, EMOJI, WALLET_APP_URL
from .formatters import format_amount, format_usd


def main_menu_kb(user_id: int | None = None, cheques_n: int = 0) -> InlineKeyboardMarkup:
    e = EMOJI
    cheques_label = f"Чеки • {cheques_n}" if cheques_n > 0 else "Чеки"
    rows = [
        [
            InlineKeyboardButton(
                text="Кошелёк",
                callback_data="wallet",
                icon_custom_emoji_id=e["wallet"],
            ),
            InlineKeyboardButton(
                text="Обмен",
                callback_data="swap:start",
                icon_custom_emoji_id=e["exchange"],
            ),
        ],
        [
            InlineKeyboardButton(
                text="P2P",
                callback_data="noop",
                icon_custom_emoji_id=e["p2p"],
            ),
            InlineKeyboardButton(
                text="Биржа",
                callback_data="noop",
                icon_custom_emoji_id=e["p2p"],
            ),
        ],
        [
            InlineKeyboardButton(
                text=cheques_label,
                callback_data="menu:cheques",
                icon_custom_emoji_id=e["cheques"],
            ),
            InlineKeyboardButton(
                text="Счета",
                callback_data="noop",
                icon_custom_emoji_id=e["invoices"],
            ),
        ],
        [
            InlineKeyboardButton(
                text="Crypto Pay",
                callback_data="noop",
                icon_custom_emoji_id=e["crypto_pay"],
            ),
            InlineKeyboardButton(
                text="Розыгрыши",
                callback_data="noop",
                icon_custom_emoji_id=e["giveaways"],
            ),
        ],
        [
            InlineKeyboardButton(
                text="Подписки",
                callback_data="noop",
                icon_custom_emoji_id=e["subs"],
            ),
            InlineKeyboardButton(
                text="Настройки",
                callback_data="noop",
                icon_custom_emoji_id=e["settings"],
            ),
        ],
    ]
    if user_id is not None and user_id in ADMIN_IDS:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Админ-панель",
                    callback_data="menu:admin",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wallet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть кошелёк",
                    url=WALLET_APP_URL,
                )
            ],
            [
                InlineKeyboardButton(text="Пополнить", callback_data="noop"),
                InlineKeyboardButton(text="Вывести", callback_data="noop"),
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")],
        ]
    )


def open_wallet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть кошелёк", callback_data="wallet")]
        ]
    )


def cheque_received_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть кошелёк", callback_data="wallet")]
        ]
    )


def cheque_claimed_markup(amount: float, coin: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Получено: {format_amount(amount)} {coin}",
                    callback_data="noop",
                )
            ]
        ]
    )


def invoice_paid_markup(usd: float) -> InlineKeyboardMarkup:
    # "Оплачено: 1$" — dollar sign right after amount
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Оплачено: {format_usd(usd)}$",
                    callback_data="noop",
                )
            ]
        ]
    )


def invoice_coins_kb(code: str, amount_usd: float) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in coins.COINS:
        amt = coins.amount_for_usd(c.code, amount_usd)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{c.code} · {format_amount(amt)} {c.code}",
                    callback_data=f"inv:coin:{code}:{c.code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invoice_confirm_kb(
    code: str,
    coin: str,
    amount: float,
    anonymous: bool = False,
) -> InlineKeyboardMarkup:
    anon_label = "Да" if anonymous else "Нет"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 Оплатить {format_amount(amount)} {coin}",
                    callback_data=f"inv:pay:{code}:{coin}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Оплатить анонимно: {anon_label}",
                    callback_data=f"inv:anon:{code}:{coin}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Добавить комментарий",
                    callback_data="noop",
                )
            ],
            [
                InlineKeyboardButton(
                    text="‹ Назад",
                    callback_data=f"inv:back:{code}",
                )
            ],
        ]
    )


def cheque_claim_url_kb(bot_username: str, code: str, amount: float, coin: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Получить {format_amount(amount)} {coin}",
                    url=f"https://t.me/{bot_username}?start=cq_{code}",
                )
            ]
        ]
    )


def invoice_pay_url_kb(bot_username: str, code: str) -> InlineKeyboardMarkup:
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
