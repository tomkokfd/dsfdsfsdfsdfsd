"""Swap / exchange keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.data.coin_emojis import UI_EMOJI, coin_emoji_id
from xrocket.data.coins import all_coins


def coin_grid(
    coins: list[str],
    callback_prefix: str,
    back_callback: str,
    *,
    sort: bool = False,
) -> InlineKeyboardMarkup:
    codes = sorted(coins, key=lambda c: c.upper()) if sort else list(coins)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code in codes:
        row.append(
            InlineKeyboardButton(
                text=code,
                callback_data=f"{callback_prefix}:{code}",
                icon_custom_emoji_id=coin_emoji_id(code),
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def all_coins_grid(callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    codes = [c.code for c in all_coins()]
    return coin_grid(codes, callback_prefix, back_callback, sort=False)


def owned_coins_grid(
    balances: dict[str, float],
    callback_prefix: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    codes = [code for code, amt in balances.items() if amt > 1e-12]
    return coin_grid(codes, callback_prefix, back_callback)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data="swap:confirm",
                    icon_custom_emoji_id=UI_EMOJI["confirm"],
                )
            ],
            [InlineKeyboardButton(text="‹ Отмена", callback_data="swap:cancel")],
        ]
    )


def back_only(callback: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="‹ Назад", callback_data=callback)]]
    )
