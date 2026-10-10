"""Cheque activation deep-links (personal + multi + password)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from .. import coins
from ..action_log import log_action
from ..config import EMOJI
from ..db import db
from ..formatters import clickable_name, format_amount, format_usd
from ..images import cheque_image_url
from ..keyboards import cheque_claimed_markup, cheque_received_kb
from ..messages import (
    cheque_claim_kb,
    cheque_message_html,
    multi_share_html,
    preview_opts,
    receive_done_html,
    receive_waiting_html,
)

router = Router(name="cheques")
log = logging.getLogger(__name__)
BOT_LABEL = "Crypto Bot"


class ActivateStates(StatesGroup):
    waiting_password = State()


async def handle_cheque_activation(
    message: Message,
    code: str,
    state: FSMContext | None = None,
) -> None:
    user = message.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)

    cheque = db.get_cheque(code)
    if not cheque:
        await message.answer("Чек не найден.")
        return

    if cheque.get("status") != "active":
        await message.answer("Этот чек уже был активирован.")
        return

    # Already claimed this multi-cheque?
    if (cheque.get("cheque_type") or "personal") == "multi":
        claims = None
        # soft pre-check via activate errors later
        pass

    password = (cheque.get("password") or "").strip()
    if password:
        if state is None:
            await message.answer(
                "Для активации этого чека нужен пароль. "
                "Откройте чек ещё раз через кнопку «Получить»."
            )
            return
        await state.update_data(activate_code=cheque["code"])
        await state.set_state(ActivateStates.waiting_password)
        await message.answer(
            f'<tg-emoji emoji-id="{EMOJI["cheques"]}">🦋</tg-emoji> '
            "<b>Введите пароль</b> для активации чека:",
            parse_mode="HTML",
        )
        return

    await _do_activate(message, cheque["code"])


@router.message(ActivateStates.waiting_password)
async def activate_password_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data.get("activate_code")
    typed = (message.text or "").strip()
    if not code:
        await state.clear()
        return

    cheque = db.get_cheque(code)
    if not cheque or cheque.get("status") != "active":
        await state.clear()
        await message.answer("Этот чек уже недоступен.")
        return

    expected = (cheque.get("password") or "").strip()
    if typed != expected:
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз:")
        return

    await state.clear()
    await _do_activate(message, code)


async def _do_activate(message: Message, code: str) -> None:
    user = message.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)

    cheque = db.get_cheque(code)
    if not cheque:
        await message.answer("Чек не найден.")
        return

    coin = cheque["coin"]
    amount = float(cheque["amount"])
    fiat = float(cheque.get("amount_fiat") or coins.usd_for_amount(coin, amount))
    photo = cheque_image_url(coin, amount, fiat)
    amt_fmt = format_amount(amount)
    fiat_fmt = format_usd(fiat)
    coin_tag = coins.coin_emoji_tag(coin)
    is_multi = (cheque.get("cheque_type") or "personal") == "multi"

    if cheque.get("status") != "active":
        await message.answer("Этот чек уже был активирован.")
        return

    waiting = receive_waiting_html(coin, amount, fiat, premium=True)
    try:
        msg = await message.answer(
            waiting,
            parse_mode="HTML",
            link_preview_options=preview_opts(photo),
        )
    except Exception:
        msg = await message.answer(waiting, parse_mode="HTML")

    await asyncio.sleep(2)

    try:
        activated = db.activate_cheque(code, user.id)
    except ValueError as e:
        err = str(e)
        if err == "already_claimed":
            text = "Вы уже активировали этот мульти-чек."
        elif err == "forbidden":
            text = "Вы <b>не можете активировать</b> данный чек."
        elif "already" in err:
            text = "Этот чек уже был активирован."
        else:
            text = f"Ошибка: {err}"
        try:
            await msg.edit_text(text, parse_mode="HTML")
        except Exception:
            await message.answer(text, parse_mode="HTML")
        return

    done = receive_done_html(coin, amount, fiat, premium=True)
    try:
        await msg.edit_text(
            done,
            parse_mode="HTML",
            reply_markup=cheque_received_kb(),
            link_preview_options=preview_opts(photo),
        )
    except Exception:
        await message.answer(
            done,
            parse_mode="HTML",
            reply_markup=cheque_received_kb(),
            link_preview_options=preview_opts(photo),
        )

    # Update original inline message
    inline_id = activated.get("inline_message_id")
    if inline_id:
        try:
            bot: Bot = message.bot
            me = await bot.get_me()
            uname = me.username or activated.get("bot_username") or "bot"
            still_active = activated.get("status") == "active" and is_multi

            if is_multi:
                total = amount * int(activated.get("activations_total") or 1)
                total_fiat = coins.usd_for_amount(coin, total)
                img = cheque_image_url(coin, total, total_fiat)
                text = multi_share_html(activated, uname, premium=True)
                if still_active:
                    markup = cheque_claim_kb(
                        uname, code, amount, coin, start_payload=f"mc_{code}"
                    )
                else:
                    used = int(activated.get("activations_used") or 0)
                    total_n = int(activated.get("activations_total") or 1)
                    markup = cheque_claimed_markup(amount, coin)
                    # Prefer showing fully claimed
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

                    markup = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=f"✅ Активирован: {used}/{total_n}",
                                    callback_data="noop",
                                )
                            ]
                        ]
                    )
            else:
                img = photo
                text = cheque_message_html(
                    uname,
                    coin,
                    amount,
                    fiat,
                    code=code,
                    description=activated.get("description") or "",
                    premium=True,
                )
                markup = cheque_claimed_markup(amount, coin)

            await bot.edit_message_text(
                text=text,
                inline_message_id=inline_id,
                parse_mode="HTML",
                reply_markup=markup,
                link_preview_options=preview_opts(img),
            )
        except Exception as e:
            log.debug("edit inline after claim failed: %s", e)
            try:
                if not is_multi or activated.get("status") != "active":
                    await message.bot.edit_message_reply_markup(
                        inline_message_id=inline_id,
                        reply_markup=cheque_claimed_markup(amount, coin),
                    )
            except Exception:
                pass

    await log_action(
        message.bot,
        BOT_LABEL,
        "Чек активирован",
        user=user,
        lines=[
            f"· Код: <code>{code}</code>",
            f"· Получено: <b>{amt_fmt} {coin}</b> (${fiat_fmt})",
            f"· Создатель: <code>{activated.get('creator_id')}</code>",
            f"· Тип: {'мульти' if is_multi else 'персональный'}",
        ],
        emoji_key="cheque",
        fallback="📥",
    )

    # Notify creator (respect notify_on; skip self-activation)
    creator_id = activated.get("creator_id")
    notify_on = bool(activated.get("notify_on", 1))
    if creator_id and int(creator_id) != int(user.id) and notify_on:
        name = user.full_name or user.first_name or "User"
        notify = (
            f'<tg-emoji emoji-id="{EMOJI["cheques"]}">🦋</tg-emoji> '
            f"{clickable_name(user.id, name)} "
            f"активировал(а) ваш чек и получил(а) "
            f"<b>{coin_tag} {amt_fmt} {coin} (${fiat_fmt})</b>."
        )
        try:
            await message.bot.send_message(
                chat_id=int(creator_id),
                text=notify,
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("notify creator failed: %s", e)
