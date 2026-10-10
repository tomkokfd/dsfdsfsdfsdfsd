"""Invoice payment flow."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from .. import coins
from ..config import EMOJI
from ..db import db
from ..formatters import clickable_name, format_amount, format_usd
from ..images import cheque_image_url, invoice_image_url
from ..keyboards import invoice_coins_kb, invoice_confirm_kb, invoice_paid_markup
from ..messages import invoice_paid_html, paid_success_html, preview_opts
from ..action_log import log_action

router = Router(name="invoices")
log = logging.getLogger(__name__)
BOT_LABEL = "Crypto Bot"

_pending_anon: dict[tuple[int, str], bool] = {}


def _find_invoice(code: str) -> dict[str, Any] | None:
    inv = db.get_invoice(code)
    if inv:
        return inv
    for inv in db.list_invoices():
        if inv.get("code", "").lower() == code.lower():
            return inv
    return None


async def handle_invoice_start(message: Message, code: str) -> None:
    user = message.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)

    inv = _find_invoice(code)
    if not inv:
        await message.answer("Счёт не найден.")
        return

    code = inv["code"]
    if inv.get("status") != "active":
        await message.answer(f"Счёт #{code} уже оплачен.")
        return

    usd = float(inv["amount_usd"])
    text = (
        f"Выберите монету для оплаты счета #{code} на сумму "
        f"<b>${format_usd(usd)}</b>."
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=invoice_coins_kb(code, usd),
    )


def _confirm_text(code: str, coin: str, amount: float, usd: float) -> str:
    inv_emoji = EMOJI["invoices"]
    return (
        f'<tg-emoji emoji-id="{inv_emoji}">📥</tg-emoji> '
        f"<b>Подтвердите оплату счёта </b><b>#{code}</b>\n"
        f"\n"
        f"<b>Отправляете</b>: {format_amount(amount)} {coin} (${format_usd(usd)})\n"
        f"   \n"
        f"Вы уверены, что хотите оплатить этот счёт?"
    )


@router.callback_query(F.data.startswith("inv:coin:"))
async def cb_inv_coin(callback: CallbackQuery) -> None:
    await callback.answer()
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        return
    code = parts[2]
    coin = parts[3].upper()
    inv = _find_invoice(code)
    if not inv or inv.get("status") != "active":
        await callback.answer("Счёт недоступен", show_alert=True)
        return
    usd = float(inv["amount_usd"])
    amount = coins.amount_for_usd(coin, usd)
    anon = _pending_anon.get((callback.from_user.id, code), False)
    text = _confirm_text(code, coin, amount, usd)
    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=invoice_confirm_kb(code, coin, amount, anonymous=anon),
        )


@router.callback_query(F.data.startswith("inv:anon:"))
async def cb_inv_anon(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    code = parts[2]
    coin = parts[3].upper()
    key = (callback.from_user.id, code)
    _pending_anon[key] = not _pending_anon.get(key, False)
    anon = _pending_anon[key]
    await callback.answer("Анонимно: Да" if anon else "Анонимно: Нет")

    inv = _find_invoice(code)
    if not inv:
        return
    usd = float(inv["amount_usd"])
    amount = coins.amount_for_usd(coin, usd)
    text = _confirm_text(code, coin, amount, usd)
    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=invoice_confirm_kb(code, coin, amount, anonymous=anon),
        )


@router.callback_query(F.data.startswith("inv:back:"))
async def cb_inv_back(callback: CallbackQuery) -> None:
    await callback.answer()
    code = (callback.data or "").split(":", 2)[2]
    inv = _find_invoice(code)
    if not inv:
        return
    usd = float(inv["amount_usd"])
    text = (
        f"Выберите монету для оплаты счета #{code} на сумму "
        f"<b>${format_usd(usd)}</b>."
    )
    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=invoice_coins_kb(code, usd),
        )


@router.callback_query(F.data.startswith("inv:pay:"))
async def cb_inv_pay(callback: CallbackQuery) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    code = parts[2]
    coin = parts[3].upper()
    user = callback.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)

    inv = _find_invoice(code)
    if not inv or inv.get("status") != "active":
        await callback.answer("Счёт недоступен", show_alert=True)
        return

    usd = float(inv["amount_usd"])
    amount = coins.amount_for_usd(coin, usd)
    anon = _pending_anon.get((user.id, code), False)

    bal = db.get_balance(user.id, coin)
    if bal + 1e-12 < amount:
        await callback.answer("Недостаточно средств", show_alert=True)
        return

    await callback.answer()
    msg = callback.message
    if not msg:
        return

    try:
        await msg.edit_text("⏳", parse_mode="HTML")
    except Exception:
        pass
    await asyncio.sleep(1)

    try:
        await msg.edit_text("👌", parse_mode="HTML")
    except Exception:
        pass
    await asyncio.sleep(1.5)

    try:
        paid = db.pay_invoice(
            code,
            payer_id=user.id,
            coin=coin,
            amount_paid=amount,
            anonymous=anon,
        )
    except ValueError as e:
        await msg.edit_text(f"Ошибка оплаты: {e}", parse_mode="HTML")
        return

    coin_tag = coins.coin_emoji_tag(coin)
    amt_fmt = format_amount(amount)
    paid_usd = coins.usd_for_amount(coin, amount)
    fiat_fmt = format_usd(paid_usd)
    success = paid_success_html(code, coin, amount, paid_usd, premium=True)
    try:
        await msg.edit_text(
            success,
            parse_mode="HTML",
            link_preview_options=preview_opts(cheque_image_url(coin, amount, paid_usd)),
        )
    except Exception:
        await msg.edit_text(success, parse_mode="HTML")

    # Update original inline invoice message (premium + paid status)
    inline_id = paid.get("inline_message_id")
    paid_at = float(paid.get("paid_at") or time.time())
    if inline_id:
        me = await callback.bot.get_me()
        uname = me.username or paid.get("bot_username") or "bot"
        try:
            await callback.bot.edit_message_text(
                text=invoice_paid_html(uname, code, usd, paid_at, premium=True),
                inline_message_id=inline_id,
                parse_mode="HTML",
                reply_markup=invoice_paid_markup(usd),
                link_preview_options=preview_opts(invoice_image_url(usd)),
            )
        except Exception as e:
            log.debug("edit paid invoice inline failed: %s", e)
            try:
                await callback.bot.edit_message_reply_markup(
                    inline_message_id=inline_id,
                    reply_markup=invoice_paid_markup(usd),
                )
            except Exception:
                pass

    await log_action(
        callback.bot,
        BOT_LABEL,
        "Счёт оплачен",
        user=user,
        lines=[
            f"· Код: <code>{code}</code>",
            f"· Оплачено: <b>{amt_fmt} {coin}</b> (${fiat_fmt})",
            f"· Создатель: <code>{paid.get('creator_id')}</code>",
            f"· Анонимно: {'да' if anon else 'нет'}",
        ],
        emoji_key="cheque",
        fallback="📥",
    )

    creator_id = paid.get("creator_id")
    if creator_id and int(creator_id) != int(user.id):
        if anon:
            who = "<b>Кто-то</b>"
        else:
            name = user.full_name or user.first_name or "User"
            who = clickable_name(user.id, name)
        notify = (
            f"{who} оплатил(а) ваш счёт #{code}. "
            f"Вы получили <b>{coin_tag} {amt_fmt} {coin} (${fiat_fmt})</b>."
        )
        try:
            await callback.bot.send_message(
                chat_id=int(creator_id),
                text=notify,
                parse_mode="HTML",
            )
        except Exception as e:
            log.debug("notify invoice creator failed: %s", e)

    _pending_anon.pop((user.id, code), None)
