"""Cheque keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.config import EMOJI
from xrocket.data.coin_emojis import UI_EMOJI, coin_emoji_id
from xrocket.data.coins import all_coins
from xrocket.utils.formatters import format_amount_nb, format_fiat, money_pair


def cheques_home_kb(personal_n: int = 0, multi_n: int = 0) -> InlineKeyboardMarkup:
    p_label = f"Персональный · {personal_n}" if personal_n else "Персональный"
    m_label = f"Мульти-чек · {multi_n}" if multi_n else "Мульти-чек"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=p_label, callback_data="chk:personal"),
                InlineKeyboardButton(text=m_label, callback_data="chk:multi"),
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Rocket-чек",
                    callback_data="noop",
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")],
        ]
    )


def personal_menu_kb(cheques: list | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Создать чек",
                callback_data="chk:p:create",
                icon_custom_emoji_id=EMOJI["cheques"],
            )
        ]
    ]
    for ch in (cheques or [])[:20]:
        amt = format_amount_nb(float(ch["amount"]))
        # Only premium icon — no unicode emoji in button text
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{amt} {ch['coin_code']}",
                    callback_data=f"chk:p:open:{ch['code']}",
                    icon_custom_emoji_id=EMOJI["cheques"],
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="chk:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def multi_menu_kb(cheques: list | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Создать чек",
                callback_data="chk:m:create",
                icon_custom_emoji_id=EMOJI["cheques"],
            )
        ]
    ]
    for ch in (cheques or [])[:20]:
        per = float(ch["amount"])
        total_n = int(ch["activations_total"])
        used = int(ch.get("activations_used") or 0)
        total = format_amount_nb(per * total_n)
        # Only premium icon — no unicode emoji in button text
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{total} {ch['coin_code']} ({used}/{total_n})",
                    callback_data=f"chk:m:open:{ch['code']}",
                    icon_custom_emoji_id=EMOJI["cheques"],
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="chk:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coin_pick_kb(
    prefix: str,
    back: str,
    balances: dict[str, float] | None = None,
) -> InlineKeyboardMarkup:
    if balances is not None:
        codes = sorted(
            (c for c, a in balances.items() if a > 1e-12),
            key=lambda x: x.upper(),
        )
    else:
        codes = sorted((c.code for c in all_coins()), key=lambda x: x.upper())
    rows: list[list[InlineKeyboardButton]] = []
    if not codes:
        rows.append(
            [InlineKeyboardButton(text="Нет монет с балансом", callback_data="noop")]
        )
    else:
        row: list[InlineKeyboardButton] = []
        for code in codes:
            row.append(
                InlineKeyboardButton(
                    text=code,
                    callback_data=f"{prefix}:{code}",
                    icon_custom_emoji_id=coin_emoji_id(code),
                )
            )
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def amount_input_kb(
    max_label: str,
    back_coin: str,
    back: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=max_label, callback_data="chk:max")],
            [InlineKeyboardButton(text="‹ Выбор валюты", callback_data=back_coin)],
            [InlineKeyboardButton(text="‹ Назад", callback_data=back)],
        ]
    )


def activations_input_kb(max_n: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Максимум • {max_n}",
                    callback_data="chk:max_act",
                )
            ],
            [InlineKeyboardButton(text="‹ Изменить сумму", callback_data="chk:m:back_amt")],
            [InlineKeyboardButton(text="‹ Назад", callback_data="chk:multi")],
        ]
    )


def confirm_kb(change_cb: str, back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтверждаю", callback_data="chk:yes"),
                InlineKeyboardButton(text="❌ Отклоняю", callback_data="chk:no"),
            ],
            [InlineKeyboardButton(text="‹ Изменить сумму", callback_data=change_cb)],
            [InlineKeyboardButton(text="‹ Назад", callback_data=back_cb)],
        ]
    )


def multi_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтверждаю", callback_data="chk:yes"),
                InlineKeyboardButton(text="❌ Отклоняю", callback_data="chk:no"),
            ],
            [
                InlineKeyboardButton(
                    text="‹ Изменить количество активаций",
                    callback_data="chk:m:back_act",
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="chk:multi")],
        ]
    )


def personal_manage_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить",
                    switch_inline_query=code,
                    icon_custom_emoji_id=EMOJI["send_money"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Добавить описание",
                    callback_data=f"chk:p:desc:{code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Привязать к пользователю",
                    callback_data=f"chk:p:bind:{code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Удалить",
                    callback_data=f"chk:del:{code}",
                    style="danger",
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="chk:personal")],
        ]
    )


def multi_manage_kb(code: str, notify_on: bool = True, captcha_on: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить в канал или чат",
                    switch_inline_query=f"mc_{code}",
                    icon_custom_emoji_id=EMOJI["send_money"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Добавить описание",
                    callback_data=f"chk:m:desc:{code}",
                )
            ],
            [
                InlineKeyboardButton(text="Задать пароль", callback_data="noop"),
                InlineKeyboardButton(text="Добавить картинку", callback_data="noop"),
            ],
            [
                InlineKeyboardButton(
                    text=f"Уведомл.: {'вкл' if notify_on else 'выкл'}",
                    callback_data=f"chk:m:notify:{code}",
                ),
                InlineKeyboardButton(
                    text=f"Каптча: {'вкл' if captcha_on else 'выкл'}",
                    callback_data=f"chk:m:captcha:{code}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Удалить",
                    callback_data=f"chk:del:{code}",
                    style="danger",
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="chk:multi")],
        ]
    )


def back_kb(callback: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="‹ Назад", callback_data=callback)]]
    )


def claim_kb(amount: float, coin: str, bot_username: str, start_payload: str) -> InlineKeyboardMarkup:
    amount_s = format_amount_nb(amount)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Получить {amount_s} {coin}",
                    url=f"https://t.me/{bot_username}?start={start_payload}",
                )
            ]
        ]
    )
