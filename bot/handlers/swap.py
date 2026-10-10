"""In-bot swap / exchange (like xrocket)."""

from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .. import coins
from ..action_log import log_action
from ..db import db
from ..formatters import format_amount

router = Router(name="swap")
BOT_LABEL = "Crypto Bot"


class SwapStates(StatesGroup):
    waiting_amount = State()


def _rate(from_code: str, to_code: str) -> float:
    a = coins.get_coin(from_code)
    b = coins.get_coin(to_code)
    if not a or not b or b.approx_usd_price <= 0:
        return 0.0
    return a.approx_usd_price / b.approx_usd_price


def _fmt_split_html(value: float) -> str:
    if abs(value - round(value)) < 1e-12:
        return f"<b>{int(round(value))}</b>"
    s = f"{value:.9f}".rstrip("0").rstrip(".")
    if "." not in s:
        return f"<b>{s}</b>"
    whole, frac = s.split(".", 1)
    return f"<b>{whole}.</b><b>{frac}</b>"


def _coin_grid(
    codes: list[str],
    prefix: str,
    back: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code in codes:
        c = coins.get_coin(code)
        btn = InlineKeyboardButton(
            text=code,
            callback_data=f"{prefix}:{code}",
        )
        if c:
            btn = InlineKeyboardButton(
                text=code,
                callback_data=f"{prefix}:{code}",
                icon_custom_emoji_id=c.emoji_id,
            )
        row.append(btn)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="swap:confirm")],
            [InlineKeyboardButton(text="‹ Отмена", callback_data="swap:cancel")],
        ]
    )


def _back_kb(cb: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="‹ Назад", callback_data=cb)]]
    )


@router.callback_query(F.data.in_({"swap:start", "menu:swap", "exchange"}))
async def swap_start(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)
    await state.clear()
    balances = db.get_all_balances(user.id)
    codes = [c for c, a in balances.items() if a > 1e-12]
    text = (
        "<b>1. Вы отдаёте:</b>\n\n"
        "Выберите монету, которую хотите обменять:"
    )
    if not codes:
        text += "\n\nНет монет с доступным балансом для обмена."
    await callback.message.edit_text(
        text,
        reply_markup=_coin_grid(codes, "swap:from", "menu:home"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("swap:from:"))
async def swap_from(callback: CallbackQuery, state: FSMContext) -> None:
    from_code = (callback.data or "").split(":")[-1].upper()
    if not coins.get_coin(from_code):
        await callback.answer()
        return
    await state.update_data(from_code=from_code)
    tag = coins.coin_emoji_tag(from_code)
    text = (
        f"<b>1. Вы отдаёте: </b>{tag} <b>{from_code}</b>\n\n"
        f"<b>2. Вы получаете:</b>\n\n"
        "Выберите монету, которую хотите получить:"
    )
    codes = [c.code for c in coins.COINS if c.code.upper() != from_code]
    await callback.message.edit_text(
        text,
        reply_markup=_coin_grid(codes, "swap:to", "swap:start"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("swap:to:"))
async def swap_to(callback: CallbackQuery, state: FSMContext) -> None:
    to_code = (callback.data or "").split(":")[-1].upper()
    data = await state.get_data()
    from_code = (data.get("from_code") or "").upper()
    if not from_code or not coins.get_coin(to_code):
        await callback.answer()
        return
    if from_code == to_code:
        await callback.answer()
        return

    await state.update_data(
        to_code=to_code,
        prompt_message_id=callback.message.message_id if callback.message else None,
    )
    bal = db.get_balance(callback.from_user.id, from_code)
    e_from = coins.coin_emoji_tag(from_code)
    e_to = coins.coin_emoji_tag(to_code)
    text = (
        f"<b>1. Вы отдаёте:</b> {e_from} <b>{from_code}</b>\n\n"
        f"<b>2. Вы получаете:</b> {e_to} <b>{to_code}</b>\n\n"
        f"Введите сумму <b>{from_code}</b>, которую хотите обменять:\n"
        f"Баланс: <b>{format_amount(bal)} {from_code}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=_back_kb("swap:start"),
        parse_mode="HTML",
    )
    await state.set_state(SwapStates.waiting_amount)
    await callback.answer()


@router.message(SwapStates.waiting_amount)
async def swap_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    from_code = data.get("from_code")
    to_code = data.get("to_code")
    prompt_id = data.get("prompt_message_id")
    if not from_code or not to_code:
        await state.clear()
        return

    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        try:
            await message.delete()
        except Exception:
            pass
        return

    if amount <= 0:
        try:
            await message.delete()
        except Exception:
            pass
        return

    bal = db.get_balance(message.from_user.id, from_code)
    if amount > bal + 1e-12:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("❌ Недостаточно средств на балансе.")
        return

    rate = _rate(from_code, to_code)
    out_amount = amount * rate
    await state.update_data(amount=amount, out_amount=out_amount, rate=rate)

    try:
        await message.delete()
    except Exception:
        pass

    e_from = coins.coin_emoji_tag(from_code)
    e_to = coins.coin_emoji_tag(to_code)
    text = (
        "<b>3. Подтверждение:</b>\n\n"
        f"Вы уверены, что вы хотите поменять {e_from} <b>{from_code}</b> "
        f"в количестве <b>{format_amount(amount)}</b> на {e_to} <b>{to_code}</b> "
        f"в количестве <b>{format_amount(out_amount)}</b> ?"
    )

    if prompt_id:
        try:
            await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=_confirm_kb(),
                parse_mode="HTML",
            )
            await state.set_state(None)
            return
        except Exception:
            pass

    sent = await message.answer(text, reply_markup=_confirm_kb(), parse_mode="HTML")
    await state.update_data(prompt_message_id=sent.message_id)
    await state.set_state(None)


@router.callback_query(F.data == "swap:confirm")
async def swap_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    from_code = data.get("from_code")
    to_code = data.get("to_code")
    amount = data.get("amount")
    out_amount = data.get("out_amount")
    rate = data.get("rate")
    if not all([from_code, to_code, amount is not None, out_amount is not None, rate is not None]):
        await callback.answer()
        await state.clear()
        return

    user_id = callback.from_user.id
    try:
        db.change_balance(user_id, from_code, -float(amount))
        db.change_balance(user_id, to_code, float(out_amount))
    except ValueError:
        await callback.answer("Недостаточно средств", show_alert=True)
        return

    order_id = f"S{random.randint(100000, 999999)}"
    e_from = coins.coin_emoji_tag(from_code)
    e_to = coins.coin_emoji_tag(to_code)
    swap_icon = f'<tg-emoji emoji-id="5361993818373655559">🔁</tg-emoji>'

    in_s = format_amount(float(amount))
    out_html = _fmt_split_html(float(out_amount))
    rate_html = _fmt_split_html(float(rate))

    text = (
        f"{swap_icon} <b>Заявка на обмен</b> #{order_id} исполнена.\n\n"
        f"{e_from}\u00a0<b>{in_s}\u00a0{from_code}</b> 🔁\u00a0"
        f"{e_to}\u00a0{out_html}<b>\u00a0{to_code}</b>\n\n"
        f"Курс: {e_to}\u00a0{rate_html}<b>\u00a0{to_code}</b> за\u00a0"
        f"{e_from}\u00a0<b>1\u00a0{from_code}</b>\n"
        f"Получено: {e_to}\u00a0{out_html}<b>\u00a0{to_code}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=_back_kb("menu:home"),
        parse_mode="HTML",
    )
    await log_action(
        callback.bot,
        BOT_LABEL,
        "Обмен выполнен",
        user=callback.from_user,
        lines=[
            f"· Заявка: <code>#{order_id}</code>",
            f"· Отдано: <b>{in_s} {from_code}</b>",
            f"· Получено: <b>{format_amount(float(out_amount))} {to_code}</b>",
        ],
        emoji_key="swap",
        fallback="🔁",
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "swap:cancel")
async def swap_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await swap_start(callback, state)
