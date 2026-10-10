"""In-bot swap / exchange flow."""

from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from xrocket.data.coin_emojis import UI_EMOJI, coin_tg_emoji
from xrocket.data.coins import all_coins, get_coin
from xrocket.database import db
from xrocket.keyboards.swap import (
    back_only,
    coin_grid,
    confirm_keyboard,
    owned_coins_grid,
)
from xrocket.services.action_log import log_action
from xrocket.services.prices import coin_price_usd
from xrocket.utils.formatters import format_amount_nb

router = Router(name="swap")
BOT_LABEL = "xRocket"


class SwapStates(StatesGroup):
    waiting_amount = State()


def _rate(from_code: str, to_code: str) -> float:
    pa = coin_price_usd(from_code)
    pb = coin_price_usd(to_code)
    if pb <= 0:
        return 0.0
    return pa / pb


def _fmt_split_html(value: float) -> str:
    """Split decimal for bold markup like original: 3.<b>246809209</b>"""
    if abs(value - round(value)) < 1e-12:
        return f"<b>{int(round(value))}</b>"
    s = f"{value:.9f}".rstrip("0").rstrip(".")
    if "." not in s:
        return f"<b>{s}</b>"
    whole, frac = s.split(".", 1)
    return f"<b>{whole}.</b><b>{frac}</b>"


@router.callback_query(F.data == "swap:start")
async def swap_start(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    db.ensure_user(user.id, user.username, user.full_name)
    await state.clear()
    text = (
        "<b>1. Вы отдаёте:</b>\n\n"
        "Выберите монету, которую хотите обменять:"
    )
    balances = db.get_all_balances(user.id)
    if not any(amount > 1e-12 for amount in balances.values()):
        text += "\n\nНет монет с доступным балансом для обмена."
    await callback.message.edit_text(
        text,
        reply_markup=owned_coins_grid(balances, "swap:from", "menu:home"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("swap:from:"))
async def swap_from(callback: CallbackQuery, state: FSMContext) -> None:
    from_code = (callback.data or "").split(":")[-1]
    if not get_coin(from_code):
        await callback.answer()
        return

    await state.update_data(from_code=from_code)
    emoji = coin_tg_emoji(from_code)
    text = (
        f"<b>1. Вы отдаёте: </b>{emoji} <b>{from_code}</b>\n\n"
        f"<b>2. Вы получаете:</b>\n\n"
        "Выберите монету, которую хотите получить:"
    )
    codes = [c.code for c in all_coins() if c.code.upper() != from_code.upper()]
    await callback.message.edit_text(
        text,
        reply_markup=coin_grid(codes, "swap:to", "swap:start", sort=False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("swap:to:"))
async def swap_to(callback: CallbackQuery, state: FSMContext) -> None:
    to_code = (callback.data or "").split(":")[-1]
    data = await state.get_data()
    from_code = data.get("from_code")
    if not from_code or not get_coin(to_code):
        await callback.answer()
        return
    if from_code.upper() == to_code.upper():
        await callback.answer()
        return

    await state.update_data(to_code=to_code, prompt_message_id=callback.message.message_id)
    bal = db.get_balance(callback.from_user.id, from_code)
    bal_s = format_amount_nb(bal)
    e_from = coin_tg_emoji(from_code)
    e_to = coin_tg_emoji(to_code)
    text = (
        f"<b>1. Вы отдаёте:</b> {e_from} <b>{from_code}</b>\n\n"
        f"<b>2. Вы получаете:</b> {e_to} <b>{to_code}</b>\n\n"
        f"Введите сумму <b>{from_code}</b>, которую хотите обменять:\n"
        f"Баланс: <b>{bal_s} {from_code}</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_only("swap:start"))
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
        await message.delete()
        return

    if amount <= 0:
        await message.delete()
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

    e_from = coin_tg_emoji(from_code)
    e_to = coin_tg_emoji(to_code)
    amount_s = format_amount_nb(amount)
    out_s = format_amount_nb(out_amount)
    text = (
        "<b>3. Подтверждение:</b>\n\n"
        f"Вы уверены, что вы хотите поменять {e_from} <b>{from_code}</b> "
        f"в количестве <b>{amount_s}</b> на {e_to} <b>{to_code}</b> "
        f"в количестве <b>{out_s}</b> ?"
    )

    if prompt_id:
        try:
            await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=confirm_keyboard(),
            )
            await state.set_state(None)
            return
        except Exception:
            pass

    sent = await message.answer(text, reply_markup=confirm_keyboard())
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
    if not all([from_code, to_code, amount, out_amount, rate]):
        await callback.answer()
        await state.clear()
        return

    user_id = callback.from_user.id
    try:
        db.change_balance(user_id, from_code, -float(amount))
        db.change_balance(user_id, to_code, float(out_amount))
    except ValueError:
        await callback.answer()
        return

    order_id = f"S{random.randint(100000, 999999)}"
    e_from = coin_tg_emoji(from_code)
    e_to = coin_tg_emoji(to_code)
    swap_icon = f'<tg-emoji emoji-id="{UI_EMOJI["swap_done"]}">💱</tg-emoji>'
    repeat = f'<tg-emoji emoji-id="{UI_EMOJI["repeat"]}">🔁</tg-emoji>'

    in_s = format_amount_nb(float(amount))
    out_html = _fmt_split_html(float(out_amount))
    rate_html = _fmt_split_html(float(rate))

    text = (
        f"{swap_icon} <b>Заявка на обмен</b> #{order_id} исполнена.\n\n"
        f"{e_from}\u00a0<b>{in_s}\u00a0{from_code}</b> {repeat}\u00a0"
        f"{e_to}\u00a0{out_html}<b>\u00a0{to_code}</b>\n\n"
        f"Курс: {e_to}\u00a0{rate_html}<b>\u00a0{to_code}</b> за\u00a0"
        f"{e_from}\u00a0<b>1\u00a0{from_code}</b>\n"
        f"Получено: {e_to}\u00a0{out_html}<b>\u00a0{to_code}</b>"
    )
    await callback.message.edit_text(text, reply_markup=back_only("menu:home"))
    await log_action(
        callback.bot,
        BOT_LABEL,
        "Обмен выполнен",
        user=callback.from_user,
        lines=[
            f"· Заявка: <code>#{order_id}</code>",
            f"· Отдано: <b>{in_s} {from_code}</b>",
            f"· Получено: <b>{format_amount_nb(float(out_amount))} {to_code}</b>",
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
