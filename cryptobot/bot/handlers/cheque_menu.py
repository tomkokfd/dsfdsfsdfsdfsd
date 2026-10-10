"""Cheques menu: personal + multi (Crypto Bot, xRocket-style UX)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import coins
from ..action_log import log_action
from ..config import EMOJI
from ..db import db
from ..formatters import format_amount, format_usd
from ..images import cheque_image_url
from .. import keyboards_cheques as kb

router = Router(name="cheque_menu")
BOT_LABEL = "Crypto Bot"


class ChkStates(StatesGroup):
    p_amount = State()
    p_desc = State()
    p_bind = State()
    m_amount = State()
    m_activations = State()
    m_desc = State()
    m_password = State()
    activate_password = State()


def _icon() -> str:
    return f'<tg-emoji emoji-id="{EMOJI["cheques"]}">🦋</tg-emoji>'


def _fiat(coin: str, amount: float) -> float:
    return coins.usd_for_amount(coin, amount)


def _pair(amount: float, coin: str, fiat: float | None = None) -> str:
    if fiat is None:
        fiat = _fiat(coin, amount)
    return f"{format_amount(amount)}\u00a0{coin} (${format_usd(fiat)})"


def _multi_kb(ch: dict):
    return kb.multi_manage_kb(
        ch["code"],
        bool(ch.get("notify_on", 1)),
        bool(ch.get("captcha_on", 1)),
        has_password=bool(ch.get("password")),
    )


def _home_text() -> str:
    return (
        f"{_icon()} <b>Чеки</b>\n\n"
        "<b>Чеки</b> позволяют отправлять криптовалюту прямо в сообщениях.\n\n"
        "· <i>Персональный чек</i> — для отправки монет одному пользователю\n"
        "· <i>Мульти-чек</i> — для отправки монет нескольким пользователям\n\n"
        "<b>Выберите тип чека:</b>"
    )


def personal_manage_text(ch: dict, bot_username: str) -> str:
    coin = ch["coin"]
    amount = float(ch["amount"])
    fiat = float(ch.get("amount_fiat") or _fiat(coin, amount))
    link = f"https://t.me/{bot_username}?start=cq_{ch['code']}"
    lines = [
        f"{_icon()} <b>Персональный чек</b>",
        "",
        f"<b>Сумма:</b> {_pair(amount, coin, fiat)}",
        f"<b>Ссылка:</b> <code>{link}</code>",
        "",
    ]
    if ch.get("description"):
        lines += [f"<b>Описание:</b> {ch['description']}", ""]
    if ch.get("bound_user_id") or ch.get("bound_username"):
        who = ch.get("bound_username") or str(ch.get("bound_user_id"))
        if ch.get("bound_username") and not str(who).startswith("@"):
            who = f"@{who}"
        lines += [f"<b>Привязан к:</b> {who}", ""]
    lines.append("Выберите действие:")
    return "\n".join(lines)


def multi_manage_text(ch: dict, bot_username: str) -> str:
    coin = ch["coin"]
    per = float(ch["amount"])
    total_n = int(ch.get("activations_total") or 1)
    used = int(ch.get("activations_used") or 0)
    total = per * total_n
    total_fiat = _fiat(coin, total)
    per_fiat = float(ch.get("amount_fiat") or _fiat(coin, per))
    img = cheque_image_url(coin, total, total_fiat)
    link = f"https://t.me/{bot_username}?start=mc_{ch['code']}"
    notify = "вкл" if ch.get("notify_on", 1) else "выкл"
    captcha = "вкл" if ch.get("captcha_on", 1) else "выкл"
    pwd = "задана" if ch.get("password") else "нет"
    lines = [
        f"{_icon()} <b>Мульти-чек</b>",
        "",
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> {_pair(total, coin, total_fiat)}",
        f"<b>Внутри:</b> {total_n} × {_pair(per, coin, per_fiat)}",
        f"<b>Активировано:</b> {used} из {total_n}",
        f"<b>Уведомления:</b> {notify} · <b>Каптча:</b> {captcha}",
        f"<b>Пароль:</b> {pwd}",
        f"<b>Ссылка:</b> <code>{link}</code>",
        "",
    ]
    if ch.get("description"):
        lines += [f"<b>Описание:</b> {ch['description']}", ""]
    lines.append("Выберите действие:")
    return "\n".join(lines)


async def show_cheques_home(
    target: CallbackQuery | Message, state: FSMContext | None = None
) -> None:
    if state:
        await state.clear()
    user = target.from_user
    assert user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)
    p_n = db.count_active_cheques(user.id, "personal")
    m_n = db.count_active_cheques(user.id, "multi")
    text = _home_text()
    markup = kb.cheques_home_kb(p_n, m_n)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.in_({"chk:home", "menu:cheques"}))
async def chk_home(callback: CallbackQuery, state: FSMContext) -> None:
    await show_cheques_home(callback, state)


@router.callback_query(F.data == "chk:personal")
async def chk_personal(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    items = db.list_cheques_by_type(callback.from_user.id, "personal")
    await callback.message.edit_text(
        f"{_icon()} <b>Персональные чеки</b>\n\n"
        "Создайте персональный чек, чтобы отправить монеты выбранному пользователю.",
        reply_markup=kb.personal_menu_kb(items),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "chk:multi")
async def chk_multi(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    items = db.list_cheques_by_type(callback.from_user.id, "multi")
    await callback.message.edit_text(
        f"{_icon()} <b>Мульти-чеки</b>\n\n"
        "Создайте мульти-чек, чтобы раздать монеты нескольким пользователям.",
        reply_markup=kb.multi_menu_kb(items),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "chk:p:create")
async def p_create(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(mode="personal", prompt_id=callback.message.message_id)
    bals = db.get_all_balances(callback.from_user.id)
    await callback.message.edit_text(
        f"{_icon()} <b>Персональный чек</b>\n\n<b>Выберите валюту чека:</b>",
        reply_markup=kb.coin_pick_kb("chk:p:coin", "chk:personal", bals),
        parse_mode="HTML",
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
        parse_mode="HTML",
    )
    await callback.answer()


async def _ask_personal_amount(callback: CallbackQuery, state: FSMContext, coin: str) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    await state.update_data(coin=coin, prompt_id=callback.message.message_id)
    max_label = f"Максимум • {_pair(bal, coin)}"
    text = (
        f"{_icon()} <b>Персональный чек</b>\n\n"
        f"Сколько {coin} Вы хотите отправить?\n\n"
        f"<b>Максимум:</b> {_pair(bal, coin)}\n"
        f"Минимум: {_pair(0.01, coin)}\n\n"
        f"<b>Введите сумму чека в {coin}:</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb.amount_input_kb(max_label, "chk:p:create", "chk:personal"),
        parse_mode="HTML",
    )
    await state.set_state(ChkStates.p_amount)


async def _ask_multi_amount(callback: CallbackQuery, state: FSMContext, coin: str) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    await state.update_data(coin=coin, prompt_id=callback.message.message_id)
    max_label = f"Максимум • {_pair(bal, coin)}"
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f"Сколько {coin} получит каждый, кто активирует чек?\n\n"
        f"<b>Максимум:</b> {_pair(bal, coin)}\n"
        f"Минимум: {_pair(0.02, coin)}\n\n"
        f"<b>Введите сумму одной активации в {coin}:</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb.amount_input_kb(max_label, "chk:m:create", "chk:multi"),
        parse_mode="HTML",
    )
    await state.set_state(ChkStates.m_amount)


@router.callback_query(F.data.startswith("chk:p:coin:"))
async def p_coin(callback: CallbackQuery, state: FSMContext) -> None:
    coin = (callback.data or "").split(":")[-1].upper()
    await _ask_personal_amount(callback, state, coin)
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:coin:"))
async def m_coin(callback: CallbackQuery, state: FSMContext) -> None:
    coin = (callback.data or "").split(":")[-1].upper()
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


async def _show_personal_confirm(
    message: Message, state: FSMContext, coin: str, amount: float
) -> None:
    text = (
        f"{_icon()} <b>Персональный чек</b>\n\n"
        f"<b>Сумма чека</b>: {_pair(amount, coin)}\n\n"
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
            parse_mode="HTML",
        )
    else:
        sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")
        await state.update_data(prompt_id=sent.message_id)
    await state.set_state(None)


async def _show_multi_activations(
    callback: CallbackQuery, state: FSMContext, coin: str, amount: float
) -> None:
    bal = db.get_balance(callback.from_user.id, coin)
    max_n = max(1, int(bal // amount)) if amount > 0 else 1
    await state.update_data(amount=amount, max_act=max_n, mode="multi")
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Сколько пользователей смогут активировать этот чек?\n\n"
        f"<b>Одна активация</b>: {_pair(amount, coin)}\n\n"
        "<b>Введите количество активаций:</b>"
    )
    await callback.message.edit_text(
        text, reply_markup=kb.activations_input_kb(max_n), parse_mode="HTML"
    )
    await state.set_state(ChkStates.m_activations)


async def _show_multi_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    coin = data["coin"]
    amount = float(data["amount"])
    acts = int(data["activations"])
    total = amount * acts
    img = cheque_image_url(coin, total, _fiat(coin, total))
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> {_pair(total, coin)}\n\n"
        f"<b>Внутри чека:</b> {acts} активация(й) по {_pair(amount, coin)}\n\n"
        "<b>Пожалуйста, подтвердите корректность данных:</b>"
    )
    await callback.message.edit_text(
        text, reply_markup=kb.multi_confirm_kb(), parse_mode="HTML"
    )
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
    prompt_id = data.get("prompt_id")
    await state.update_data(amount=amount, mode="multi")
    bal = db.get_balance(message.from_user.id, coin)
    max_n = max(1, int(bal // amount)) if amount > 0 else 1
    await state.update_data(max_act=max_n)
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Сколько пользователей смогут активировать этот чек?\n\n"
        f"<b>Одна активация</b>: {_pair(amount, coin)}\n\n"
        "<b>Введите количество активаций:</b>"
    )
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.activations_input_kb(max_n),
            parse_mode="HTML",
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
    img = cheque_image_url(coin, total, _fiat(coin, total))
    text = (
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> {_pair(total, coin)}\n\n"
        f"<b>Внутри чека:</b> {acts} активация(й) по {_pair(amount, coin)}\n\n"
        "<b>Пожалуйста, подтвердите корректность данных:</b>"
    )
    prompt_id = data.get("prompt_id")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.multi_confirm_kb(),
            parse_mode="HTML",
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
    username = me.username or "bot"
    user = callback.from_user
    try:
        if mode == "multi":
            acts = int(data.get("activations") or 0)
            if acts < 1:
                await callback.answer()
                return
            ch = db.create_cheque(
                user.id,
                coin,
                float(amount),
                _fiat(coin, float(amount)),
                bot_username=username,
                debit=True,
                cheque_type="multi",
                activations_total=acts,
            )
            code = ch["code"]
            text = multi_manage_text(ch, username)
            markup = _multi_kb(ch)
            await log_action(
                callback.bot,
                BOT_LABEL,
                "Создан мульти-чек",
                user=user,
                lines=[
                    f"· Код: <code>{code}</code>",
                    f"· {_pair(float(amount), coin)} × {acts}",
                ],
                emoji_key="cheque",
                fallback="📥",
            )
        else:
            ch = db.create_cheque(
                user.id,
                coin,
                float(amount),
                _fiat(coin, float(amount)),
                bot_username=username,
                debit=True,
                cheque_type="personal",
            )
            code = ch["code"]
            text = personal_manage_text(ch, username)
            markup = kb.personal_manage_kb(code)
            await log_action(
                callback.bot,
                BOT_LABEL,
                "Создан персональный чек",
                user=user,
                lines=[
                    f"· Код: <code>{code}</code>",
                    f"· Сумма: {_pair(float(amount), coin)}",
                ],
                emoji_key="cheque",
                fallback="📥",
            )
    except ValueError:
        await callback.answer("Недостаточно средств", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
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
        "Введите описание для чека (до 1000 символов):",
        reply_markup=kb.back_kb(f"chk:p:open:{code}"),
        parse_mode="HTML",
    )
    await state.set_state(ChkStates.p_desc)
    await callback.answer()


@router.callback_query(F.data.startswith("chk:m:desc:"))
async def m_desc(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        f"{_icon()} <b>Мульти-чек</b>\n\n"
        "Введите описание для мульти-чека (до 1000 символов):",
        reply_markup=kb.back_kb(f"chk:m:open:{code}"),
        parse_mode="HTML",
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
    username = me.username or "bot"
    prompt_id = data.get("prompt_id")
    if ch and ch.get("cheque_type") == "multi":
        text = multi_manage_text(ch, username)
        markup = _multi_kb(ch)
    else:
        text = personal_manage_text(ch, username)
        markup = kb.personal_manage_kb(code)
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=markup,
            parse_mode="HTML",
        )
    await state.clear()


@router.callback_query(F.data.startswith("chk:p:bind:"))
async def p_bind(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await callback.message.edit_text(
        f"{_icon()} <b>Персональный чек</b>\n\n"
        "Отправьте <b>@username</b> или <b>Telegram ID</b> "
        "или перешлите сообщение от пользователя.",
        reply_markup=kb.back_kb(f"chk:p:open:{code}"),
        parse_mode="HTML",
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
    text = personal_manage_text(ch, me.username or "bot")
    prompt_id = data.get("prompt_id")
    if prompt_id:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=prompt_id,
            reply_markup=kb.personal_manage_kb(code),
            parse_mode="HTML",
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
        personal_manage_text(ch, me.username or "bot"),
        reply_markup=kb.personal_manage_kb(code),
        parse_mode="HTML",
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
        multi_manage_text(ch, me.username or "bot"),
        reply_markup=_multi_kb(ch),
        parse_mode="HTML",
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
        multi_manage_text(ch, me.username or "bot"),
        reply_markup=_multi_kb(ch),
        parse_mode="HTML",
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
        multi_manage_text(ch, me.username or "bot"),
        reply_markup=_multi_kb(ch),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chk:del:"))
async def chk_del(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    ch = db.delete_cheque(code, refund=True)
    if ch:
        await log_action(
            callback.bot,
            BOT_LABEL,
            "Удалён чек",
            user=callback.from_user,
            lines=[
                f"· Код: <code>{code}</code>",
                f"· {ch.get('coin')} {format_amount(float(ch.get('amount') or 0))}",
            ],
            emoji_key="warn",
            fallback="🍂",
        )
    await show_cheques_home(callback, state)


@router.callback_query(F.data.startswith("chk:m:pass:"))
async def m_pass_ask(callback: CallbackQuery, state: FSMContext) -> None:
    code = (callback.data or "").split(":")[-1]
    ch = db.get_cheque(code)
    if not ch:
        await callback.answer()
        return
    await state.update_data(edit_code=code, prompt_id=callback.message.message_id)
    await state.set_state(ChkStates.m_password)
    hint = ""
    if ch.get("password"):
        hint = (
            "\n\nТекущий пароль будет заменён. "
            "Отправьте <code>-</code>, чтобы удалить пароль."
        )
    await callback.message.edit_text(
        f"{_icon()} <b>Пароль мульти-чека</b>\n\n"
        f"Введите пароль, который нужно будет ввести для активации.{hint}",
        reply_markup=kb.back_kb(f"chk:m:open:{code}"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ChkStates.m_password)
async def m_pass_set(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data.get("edit_code")
    raw = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass
    if not code:
        await state.clear()
        return

    if raw in {"-", "—", "удалить", "delete", "none"}:
        db.update_cheque(code, password=None)
    else:
        db.update_cheque(code, password=raw[:64])

    ch = db.get_cheque(code)
    me = await message.bot.get_me()
    prompt_id = data.get("prompt_id")
    if ch and prompt_id:
        try:
            await message.bot.edit_message_text(
                multi_manage_text(ch, me.username or "bot"),
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=_multi_kb(ch),
                parse_mode="HTML",
            )
        except Exception:
            await message.answer(
                multi_manage_text(ch, me.username or "bot"),
                reply_markup=_multi_kb(ch),
                parse_mode="HTML",
            )
    await state.clear()
