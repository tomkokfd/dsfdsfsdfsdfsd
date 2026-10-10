"""Wallet keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.config import EMOJI, URL_APP


def _primary_url(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url, style="primary")


def wallet_pager(page: int, total_pages: int) -> list[InlineKeyboardButton]:
    """Build pager like: 1  2  3  4 ›  7 »"""
    page = max(0, min(page, total_pages - 1))
    buttons: list[InlineKeyboardButton] = []

    if total_pages <= 5:
        for i in range(total_pages):
            label = f"·{i + 1}·" if i == page else str(i + 1)
            buttons.append(
                InlineKeyboardButton(text=label, callback_data=f"wallet:page:{i}")
            )
        return buttons

    window_start = min(max(0, page - 1), max(0, total_pages - 4))
    window_end = min(total_pages - 1, window_start + 3)
    for i in range(window_start, window_end + 1):
        label = str(i + 1)
        if i == window_end and window_end < total_pages - 1:
            label = f"{i + 1} ›"
        if i == page:
            label = f"·{label}·"
        buttons.append(
            InlineKeyboardButton(text=label, callback_data=f"wallet:page:{i}")
        )
    last = total_pages - 1
    if window_end < last:
        label = f"{total_pages} »"
        if page == last:
            label = f"·{total_pages} »·"
        buttons.append(
            InlineKeyboardButton(text=label, callback_data=f"wallet:page:{last}")
        )
    return buttons


def wallet_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [wallet_pager(page, total_pages)]
    rows.append(
        [
            InlineKeyboardButton(
                text="Пополнение",
                callback_data="noop",
                icon_custom_emoji_id=EMOJI["deposit"],
            ),
            InlineKeyboardButton(
                text="Вывод",
                callback_data="noop",
                icon_custom_emoji_id=EMOJI["withdraw"],
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="💼 Общий баланс", callback_data="wallet:overview")]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Перевод между балансами",
                callback_data="noop",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔗 Повысить безопасность",
                callback_data="noop",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="Отображение балансов",
                callback_data="wallet:display",
                icon_custom_emoji_id=EMOJI["wallet"],
            )
        ]
    )
    rows.append(
        [_primary_url("📱 В приложении удобней", URL_APP)]
    )
    rows.append(
        [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def overview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💼 Общий баланс", callback_data="wallet:view:total")],
            [InlineKeyboardButton(text="👛 Основной баланс", callback_data="wallet:view:main")],
            [InlineKeyboardButton(text="⚖️ Торговый баланс", callback_data="wallet:view:trade")],
            [InlineKeyboardButton(text="‹ Назад", callback_data="wallet:page:0")],
        ]
    )


def display_mode_keyboard(current: str) -> InlineKeyboardMarkup:
    def mark(mode: str, label: str) -> str:
        return f"✅ {label}" if current == mode else label

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=mark("all", "Показывать все"),
                    callback_data="wallet:mode:all",
                )
            ],
            [
                InlineKeyboardButton(
                    text=mark("hide_zero", "Скрывать нулевые"),
                    callback_data="wallet:mode:hide_zero",
                )
            ],
            [
                InlineKeyboardButton(
                    text=mark("hide_lt1", "Скрывать менее 1 USD"),
                    callback_data="wallet:mode:hide_lt1",
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="wallet:page:0")],
        ]
    )
