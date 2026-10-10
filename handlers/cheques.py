"""Cheques menu: personal + multi flows."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from xrocket.database import db
from xrocket.keyboards import cheques as kb
from xrocket.services import cheque as cheque_service
from xrocket.services.action_log import log_action
from xrocket.utils.formatters import (
    cheque_image_url,
    fiat_for_amount,
    format_amount_nb,
    money_pair,
    tg_emoji,
)

router = Router(name="cheques")
BOT_LABEL = "xRocket"


class ChkStates(StatesGroup):
    p_amount = State()
    p_desc = State()
    p_bind = State()
    m_amount = State()
    m_activations = State()
    m_desc = State()


def _icon() -> str:
    return tg_emoji("cheques", "🏷")


def _home_text() -> str:
    return (
        f"{_icon()} <b>Чеки</b>\n\n"
        "<b>Чеки</b> позволяют отправлять криптовалюту прямо в сообщениях.\n\n"
        "· <i>Персональный чек</i> - для отправки монет одному пользователю\n"
        "· <i>Мульти-чек</i> - для отправки монет нескольким пользователям "
        "с возможностью добавить условие подписки\n"
        "· <i>Rocket-чек</i> - улучшенный мульти-чек с наградой за распространение\n\n"
        "<b>Выберите тип чека:</b>"
    )


async def show_cheques_home(target: CallbackQuery | Message, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    user = target.from_user
    assert user
    db.ensure_user(user.id, user.username, user.full_name or "")
    p_n = db.count_active_cheques(user.id, "personal")
    m_n = db.count_active_cheques(user.id, "multi")
    text = _home_text()
    markup = kb.cheques_home_kb(p_n, m_n)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "chk:home")
@router.callback_query(F.data == "menu:cheques")
async def chk_home(callback: CallbackQuery, state: FSMContext) -> None:
    await show_cheques_home(callback, state)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "chk:personal")
async def chk_personal(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    items = db.list_cheques_by_type(callback.from_user.id, "personal")
    await callback.message.edit_text(
        f"{_icon()} <b>Персональные чеки</b>\n\n"
        "Создайте персональный чек, чтобы отправить сообщение с монетами "
        "выбранному Вами пользователю.",
        reply_markup=kb.personal_menu_kb(items),
    )
    await callback.answer()


@router.callback_query(F.data == "chk:multi")
async def chk_multi(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    items = db.list_cheques_by_type(callback.from_user.id, "multi")
    await callback.message.edit_text(
        f"{_icon()} <b>Мульти-чеки</b>\n\n"
        "Создайте Мульти-чек, чтобы раздать монеты нескольким пользователям, "
        "например, в чате или канале.\n\n"
        "Можно добавить условие подписки на канал/чат.",
        reply_markup=kb.multi_menu_kb(items),
    )
    await callback.answer()


@router.callback_query(F.data == "chk:board")
async def chk_board(callback: CallbackQuery) -> None:
    items = db.list_active_cheques(callback.from_user.id)
    if not items:
        text = f"{_icon()} <b>Доска чеков</b>\n\nАктивных чеков нет."
    else:
        lines = [f"{_icon()} <b>Доска чеков</b>", ""]
        for ch in items[:30]:
            kind = "P" if ch.get("cheque_type") == "personal" else "M"
            lines.append(
                f"· [{kind}] <code>{ch['code']}</code> — "
                f"{format_amount_nb(float(ch['amount']))} {ch['coin_code']}"
            )
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=kb.back_kb("chk:home"))
    await callback.answer()


@router.callback_query(F.data == "chk:p:create")
async def p_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(mode="personal", prompt_id=callback.message.message_id)
    bals = db.get_all_balances(callback.from_user.id)
    await callback.message.edit_text(
        f"{_icon()} <b>Персональный чек</b>\n\n<b>Выберите валюту чека:</b>",
        reply_markup=kb.coin_pick_kb("chk:p:coin", "chk:personal", bals),
    )
    await callback.answer()


@router.callback_query(F.data == "chk:m:create")
async def m_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(mode="multi", prompt_id=callback.message.message_id)
    bals = db.get_all_balances(callback.from_user.id)
    await callback.message.edit_text(
        f"{_icon()} <b>Мульти-чек</b>\n\n<b>Выберите валюту чека:</b>",
        reply_markup=kb.coin_pick_kb("chk:m:coin", "chk:multi", bals),
    )
    await callback.answer()


async def _ask_personal_amount(callback: CallbackQuery, state: FSMContext, coin: str) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    fiat_bal = fiat_for_amount(coin, bal)
    min_amt = 0.01
    min_fiat = fiat_for_amount(coin, min_amt)
    await state.update_data(coin=coin, prompt_id=callback.message.message_id)
    max_label = f"Максимум • {money_pair(bal, coin, fiat_bal)}"
    text = (
        f"{_icon()} <b>Персональный чек</b>\n\n"
        f"Сколько {coin} Вы хотите отправить пользователю с помощью чека?\n\n"
        f"<b>Максимум:</b> <b>{money_pair(bal, coin, fiat_bal)}</b>\n"
        f"Минимум: <b>{money_pair(min_amt, coin, min_fiat)}</b>\n\n"
        f"<b>Введите сумму чека в {coin}:</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb.amount_input_kb(max_label, "chk:p:create", "chk:personal"),
    )
    await state.set_state(ChkStates.p_amount)


async def _ask_multi_amount(callback: CallbackQuery, state: FSMContext, coin: str) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    fiat_bal = fiat_for_amount(coin, bal)
    min_amt = 0.02
    min_fiat = fiat_for_amount(coin, min_amt)
    await state.update_data(coin=coin, prompt_id=callback.message.message_id)
    max_label = f"Максимум • {money_pair(bal, coin, fiat_bal)}"
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f"Сколько {coin} получит каждый пользователь, который активирует этот чек?\n\n"
        f"<b>Максимум</b>: <b>{money_pair(bal, coin, fiat_bal)}</b>\n"
        f"Минимум: <b>{money_pair(min_amt, coin, min_fiat)}</b>\n\n"
        f"<i>Чем больше сумма активации, тем больше каналов/чатов можно добавить "
        f"в условие подписки (по 1 каналу на каждые 0.01\u00a0{coin})</i>\n\n"
        f"<b>Введите сумму одной активации в {coin}:</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb.amount_input_kb(max_label, "chk:m:create", "chk:multi"),
    )
    await state.set_state(ChkStates.m_amount)


@router.callback_query(F.data.startswith("chk:p:coin:"))
async def p_coin(callback: CallbackQuery, state: FSMContext) -> None:
    coin = (callback.data or "").split(":")[-1]
    await _ask_personal_amount(callback, state, coin)
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:coin:"))
async def m_coin(callback: CallbackQuery, state: FSMContext) -> None:
    coin = (callback.data or "").split(":")[-1]
    await _ask_multi_amount(callback, state, coin)
    await callback.answer()


@router.callback_query(F.data == "chk:max")
async def chk_max(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data.get("coin")
    if not coin:
        await callback.answer()
        return
    bal = db.get_balance(callback.from_user.id, coin)
    mode = data.get("mode")
    if mode == "multi" or await state.get_state() == ChkStates.m_amount.state:
        await state.update_data(amount=bal)
        await _show_multi_activations(callback, state, coin, bal)
    else:
        await state.update_data(amount=bal)
        await _show_personal_confirm(callback.message, state, coin, bal)
    await callback.answer()


@router.callback_query(F.data == "chk:max_act")
async def chk_max_act(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    max_n = int(data.get("max_act") or 1)
    await state.update_data(activations=max_n)
    await _show_multi_confirm(callback, state)
    await callback.answer()


async def _show_personal_confirm(message: Message, state: FSMContext, coin: str, amount: float) -> None:
    fiat = fiat_for_amount(coin, amount)
    text = (
        f"{_icon()} <b>Персональный чек</b>\n\n"
        f"<b>Сумма чека</b>: {money_pair(amount, coin, fiat)}\n\n"
        "<b>Пожалуйста, подтвердите корректность данных:</b>"
    )
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    markup = kb.confirm_kb("chk:p:create", "chk:personal")
    await state.update_data(amount=amount, mode="personal")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=markup,
        )
    else:
        sent = await message.answer(text, reply_markup=markup)
        await state.update_data(prompt_id=sent.message_id)
    await state.set_state(None)


async def _show_multi_activations(
    callback: CallbackQuery, state: FSMContext, coin: str, amount: float
) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    max_n = max(1, int(bal // amount)) if amount > 0 else 1
    fiat = fiat_for_amount(coin, amount)
    await state.update_data(amount=amount, max_act=max_n, mode="multi")
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Сколько пользователей смогут активировать этот чек?\n\n"
        f"<b>Одна активация</b>: {money_pair(amount, coin, fiat)}\n\n"
        "<b>Введите количество активаций:</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb.activations_input_kb(max_n))
    await state.set_state(ChkStates.m_activations)


async def _show_multi_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data["coin"]
    amount = float(data["amount"])
    acts = int(data["activations"])
    total = amount * acts
    total_fiat = fiat_for_amount(coin, total)
    per_fiat = fiat_for_amount(coin, amount)
    img = cheque_image_url(coin, total, total_fiat, activations=acts)
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> <b>{money_pair(total, coin, total_fiat)}</b>\n\n"
        f"<b>Внутри чека:</b> {acts} активация(й) по {money_pair(amount, coin, per_fiat)}\n\n"
        "<b>Пожалуйста, подтвердите корректность данных:</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb.multi_confirm_kb())
    await state.set_state(None)


@router.message(ChkStates.p_amount)
async def p_amount_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data.get("coin")
    if not coin:
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
    try:
        await message.delete()
    except Exception:
        pass
    bal = db.get_balance(message.from_user.id, coin)
    if amount < 0.01 - 1e-12 or amount > bal + 1e-12:
        return
    await _show_personal_confirm(message, state, coin, amount)


@router.message(ChkStates.m_amount)
async def m_amount_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data.get("coin")
    if not coin:
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
    try:
        await message.delete()
    except Exception:
        pass
    bal = db.get_balance(message.from_user.id, coin)
    if amount < 0.02 - 1e-12 or amount > bal + 1e-12:
        return
    # Fake callback-like edit via bot
    class _C:
        pass

    # reuse activations screen via bot edit
    max_n = max(1, int(bal // amount))
    fiat = fiat_for_amount(coin, amount)
    await state.update_data(amount=amount, max_act=max_n, mode="multi")
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Сколько пользователей смогут активировать этот чек?\n\n"
        f"<b>Одна активация</b>: {money_pair(amount, coin, fiat)}\n\n"
        "<b>Введите количество активаций:</b>"
    )
    prompt_id = data.get("prompt_id")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.activations_input_kb(max_n),
        )
    await state.set_state(ChkStates.m_activations)


@router.message(ChkStates.m_activations)
async def m_act_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    try:
        acts = int(raw)
    except ValueError:
        try:
            await message.delete()
        except Exception:
            pass
        return
    try:
        await message.delete()
    except Exception:
        pass
    max_n = int(data.get("max_act") or 1)
    if acts < 1 or acts > max_n:
        return
    await state.update_data(activations=acts)
    coin = data["coin"]
    amount = float(data["amount"])
    total = amount * acts
    total_fiat = fiat_for_amount(coin, total)
    per_fiat = fiat_for_amount(coin, amount)
    img = cheque_image_url(coin, total, total_fiat, activations=acts)
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> <b>{money_pair(total, coin, total_fiat)}</b>\n\n"
        f"<b>Внутри чека:</b> {acts} активация(й) по {money_pair(amount, coin, per_fiat)}\n\n"
        "<b>Пожалуйста, подтвердите корректность данных:</b>"
    )
    prompt_id = data.get("prompt_id")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.multi_confirm_kb(),
        )
    await state.set_state(None)


@router.callback_query(F.data == "chk:m:back_amt")
async def m_back_amt(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data.get("coin")
    if coin:
        await _ask_multi_amount(callback, state, coin)
    await callback.answer()


@router.callback_query(F.data == "chk:m:back_act")
async def m_back_act(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data.get("coin")
    amount = data.get("amount")
    if coin and amount:
        await _show_multi_activations(callback, state, coin, float(amount))
    await callback.answer()


@router.callback_query(F.data == "chk:yes")
async def chk_yes(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    mode = data.get("mode")
    coin = data.get("coin")
    amount = data.get("amount")
    if not coin or amount is None:
        await callback.answer()
        return
    me = await callback.bot.get_me()
    username = me.username or "xrockets_mbot"
    try:
        if mode == "multi":
            acts = int(data.get("activations") or 0)
            if acts < 1:
                await callback.answer()
                return
            code = cheque_service.create_multi(callback.from_user.id, coin, float(amount), acts)
            ch = db.get_cheque(code)
            text = cheque_service.multi_manage_text(ch, username)
            markup = kb.multi_manage_kb(code)
        else:
            code = cheque_service.create_personal(callback.from_user.id, coin, float(amount))
            ch = db.get_cheque(code)
            text = cheque_service.personal_manage_text(ch, username)
            markup = kb.personal_manage_kb(code)
    except ValueError:
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(text, reply_markup=markup)
    await log_action(
        callback.bot,
        BOT_LABEL,
        "Создан мульти-чек" if mode == "multi" else "Создан персональный чек",
        user=callback.from_user,
        lines=[
            f"· Код: <code>{code}</code>",
            f"· Сумма: <b>{format_amount_nb(float(amount))} {coin}</b>",
        ],
        emoji_key="cheque",
        fallback="🏷",
    )
    await callback.answer()


@router.callback_query(F.data == "chk:no")
async def chk_no(callback: CallbackQuery, state: FSMContext) -> None:
    await show_cheques_home(callback, state)


@router.callback_query(F.data.startswith("chk:p:desc:"))
async def p_desc(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        f"{_icon()} <b>Персональный чек</b>\n\n"
        "Введите описание, которое хотите прикрепить к персональному чеку.\n\n"
        "<i>Максимальная длина - </i><b><i>1000 символов</i></b>",
        reply_markup=kb.back_kb(f"chk:p:open:{code}"),
    )
    await state.set_state(ChkStates.p_desc)
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:desc:"))
async def m_desc(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Введите описание для мульти-чека.\n\n"
        "<i>Максимальная длина - </i><b><i>1000 символов</i></b>",
        reply_markup=kb.back_kb(f"chk:m:open:{code}"),
    )
    await state.set_state(ChkStates.m_desc)
    await callback.answer()


@router.message(ChkStates.p_desc)
@router.message(ChkStates.m_desc)
async def desc_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data.get("edit_code")
    desc = (message.text or "")[:1000]
    try:
        await message.delete()
    except Exception:
        pass
    if not code:
        return
    db.update_cheque(code, description=desc)
    ch = db.get_cheque(code)
    me = await message.bot.get_me()
    username = me.username or "xrockets_mbot"
    prompt_id = data.get("prompt_id")
    if ch and ch.get("cheque_type") == "multi":
        text = cheque_service.multi_manage_text(ch, username)
        markup = kb.multi_manage_kb(code, bool(ch.get("notify_on", 1)), bool(ch.get("captcha_on", 1)))
    else:
        text = cheque_service.personal_manage_text(ch, username)
        markup = kb.personal_manage_kb(code)
    if prompt_id:
        await message.bot.edit_message_text(
            text, chat_id=message.chat.id, message_id=prompt_id, reply_markup=markup
        )
    await state.clear()


@router.callback_query(F.data.startswith("chk:p:bind:"))
async def p_bind(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        f"{_icon()} <b>Персональный чек</b>\n\n"
        "Отправьте мне <b>@username</b> или <b>Telegram ID</b> пользователя "
        "или перешлите любое сообщение от него.",
        reply_markup=kb.back_kb(f"chk:p:open:{code}"),
    )
    await state.set_state(ChkStates.p_bind)
    await callback.answer()


@router.message(ChkStates.p_bind)
async def p_bind_msg(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data.get("edit_code")
    try:
        await message.delete()
    except Exception:
        pass
    if not code:
        return
    bound_id = None
    bound_un = None
    if message.forward_from:
        bound_id = message.forward_from.id
        bound_un = message.forward_from.username
    else:
        text = (message.text or "").strip()
        if text.startswith("@"):
            bound_un = text[1:]
        elif text.isdigit():
            bound_id = int(text)
        else:
            return
    db.update_cheque(code, bound_user_id=bound_id, bound_username=bound_un)
    ch = db.get_cheque(code)
    me = await message.bot.get_me()
    text = cheque_service.personal_manage_text(ch, me.username or "xrockets_mbot")
    prompt_id = data.get("prompt_id")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.personal_manage_kb(code),
        )
    await state.clear()


@router.callback_query(F.data.startswith("chk:p:open:"))
async def p_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    code = (callback.data or "").split(":")[-1]
    ch = db.get_cheque(code)
    if not ch:
        await callback.answer()
        return
    me = await callback.bot.get_me()
    await callback.message.edit_text(
        cheque_service.personal_manage_text(ch, me.username or "xrockets_mbot"),
        reply_markup=kb.personal_manage_kb(code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:open:"))
async def m_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    code = (callback.data or "").split(":")[-1]
    ch = db.get_cheque(code)
    if not ch:
        await callback.answer()
        return
    me = await callback.bot.get_me()
    await callback.message.edit_text(
        cheque_service.multi_manage_text(ch, me.username or "xrockets_mbot"),
        reply_markup=kb.multi_manage_kb(
            code, bool(ch.get("notify_on", 1)), bool(ch.get("captcha_on", 1))
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:notify:"))
async def m_notify(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":")[-1]
    ch = db.get_cheque(code)
    if not ch:
        await callback.answer()
        return
    new_val = 0 if ch.get("notify_on", 1) else 1
    db.update_cheque(code, notify_on=new_val)
    ch = db.get_cheque(code)
    me = await callback.bot.get_me()
    await callback.message.edit_text(
        cheque_service.multi_manage_text(ch, me.username or "xrockets_mbot"),
        reply_markup=kb.multi_manage_kb(code, bool(new_val), bool(ch.get("captcha_on", 1))),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:captcha:"))
async def m_captcha(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":")[-1]
    ch = db.get_cheque(code)
    if not ch:
        await callback.answer()
        return
    new_val = 0 if ch.get("captcha_on", 1) else 1
    db.update_cheque(code, captcha_on=new_val)
    ch = db.get_cheque(code)
    me = await callback.bot.get_me()
    await callback.message.edit_text(
        cheque_service.multi_manage_text(ch, me.username or "xrockets_mbot"),
        reply_markup=kb.multi_manage_kb(code, bool(ch.get("notify_on", 1)), bool(new_val)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chk:del:"))
async def chk_del(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    db.delete_cheque(code, refund=True)
    await show_cheques_home(callback, state)
