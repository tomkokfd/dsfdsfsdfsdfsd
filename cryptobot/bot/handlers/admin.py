"""Admin panel for Crypto Bot."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import ADMIN_IDS, BLOCKED_TEXT
from .. import coins
from ..db import db
from ..formatters import format_amount as format_amount_nb
from ..action_log import log_action

router = Router(name="admin")
log = logging.getLogger("admin")
MSK = timezone(timedelta(hours=3))
BOT_LABEL = "Crypto Bot"

_pending_bc: dict[str, dict] = {}
_scheduled_tasks: dict[str, asyncio.Task] = {}


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def _total_usd(uid: int) -> float:
    bals = db.get_all_balances(uid)
    total = 0.0
    for code, amount in bals.items():
        total += coins.usd_for_amount(code, float(amount))
    return total


def _all_coins():
    return list(coins.COINS)


class AdminBC(StatesGroup):
    waiting_message = State()
    button_text = State()
    button_url = State()
    schedule_time = State()
    reschedule_time = State()


class AdminUser(StatesGroup):
    search = State()
    set_balance = State()
    add_balance = State()
    message_user = State()


class AdminLink(StatesGroup):
    name = State()


def _back(cb: str = "adm:home") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="‹ Назад", callback_data=cb)


def admin_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
            ],
            [
                InlineKeyboardButton(text="📣 Рассылка", callback_data="adm:bc"),
                InlineKeyboardButton(text="🔗 Ссылки", callback_data="adm:links"),
            ],
            [
                InlineKeyboardButton(text="🏷 Чеки", callback_data="adm:cheques"),
                InlineKeyboardButton(text="💵 Балансы", callback_data="adm:balances"),
            ],
            [InlineKeyboardButton(text="‹ В меню", callback_data="menu:home")],
        ]
    )


def bc_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить сейчас", callback_data="adm:bc:now")],
            [InlineKeyboardButton(text="Запланировать", callback_data="adm:bc:schedule")],
            [InlineKeyboardButton(text="Запланированные", callback_data="adm:bc:list")],
            [_back()],
        ]
    )


def bc_btn_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить кнопку", callback_data="adm:bc:addbtn")],
            [InlineKeyboardButton(text="Без кнопки", callback_data="adm:bc:nobtn")],
            [_back("adm:bc")],
        ]
    )


def bc_confirm_kb(bc_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=f"adm:bc:send:{bc_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="adm:bc"),
            ]
        ]
    )


def _bc_markup(text: str | None, url: str | None) -> InlineKeyboardMarkup | None:
    if not text or not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]]
    )


def admin_text(s: dict | None = None) -> str:
    if s is None:
        s = db.get_admin_stats()
    inv_active = s.get("invoices_active", 0)
    inv_total = s.get("invoices_total", 0)
    return (
        "🛠 <b>Админ-панель Crypto Bot</b>\n\n"
        f"👥 Пользователей: <b>{s['total']}</b>\n"
        f"🚀 /start всего: <b>{s['starts']}</b>\n"
        f"🚫 Заблокировали бота: <b>{s['bot_blocked']}</b>\n"
        f"🔒 Блок админа: <b>{s['blocked']}</b>\n"
        f"🏷 Чеков активно: <b>{s['cheques_active']}</b> / {s['cheques_total']}\n"
        f"📥 Счетов активно: <b>{inv_active}</b> / {inv_total}\n\n"
        "<i>Выберите раздел:</i>"
    )


# ── Home ───────────────────────────────────────────────────


@router.message(Command("admin"))
@router.callback_query(F.data == "adm:home")
@router.callback_query(F.data == "menu:admin")
async def adm_home(event: Message | CallbackQuery, state: FSMContext) -> None:
    uid = event.from_user.id if event.from_user else 0
    if not is_admin(uid):
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    await state.clear()
    text = admin_text()
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=admin_home_kb())
        await event.answer()
    else:
        await event.answer(text, reply_markup=admin_home_kb())


# ── Stats ──────────────────────────────────────────────────


@router.callback_query(F.data == "adm:stats")
async def adm_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    s = db.get_admin_stats()
    active_users = max(0, s["total"] - s["bot_blocked"] - s["blocked"])
    text = (
        "📊 <b>Статистика</b>\n\n"
        "<b>Пользователи</b>\n"
        f"· Всего: <b>{s['total']}</b>\n"
        f"· Активных (оценка): <b>{active_users}</b>\n"
        f"· Сегодня: <b>{s['today']}</b>\n"
        f"· Вчера: <b>{s['yesterday']}</b>\n"
        f"· За 7 дней: <b>{s['week']}</b>\n"
        f"· За 30 дней: <b>{s['month']}</b>\n"
        f"· Нажали /start (сумма): <b>{s['starts']}</b>\n"
        f"· Заблокированы админом: <b>{s['blocked']}</b>\n"
        f"· Заблокировали бота: <b>{s['bot_blocked']}</b>\n\n"
        "<b>Чеки</b>\n"
        f"· Всего создано: <b>{s['cheques_total']}</b>\n"
        f"· Активных: <b>{s['cheques_active']}</b>\n"
        f"· Активированных: <b>{s['cheques_activated']}</b>\n"
        f"· Персональных: <b>{s['cheques_personal']}</b>\n"
        f"· Мульти: <b>{s['cheques_multi']}</b>\n"
        f"· Claims (мульти): <b>{s['claims']}</b>\n\n"
        "<b>Счета</b>\n"
        f"· Всего: <b>{s.get('invoices_total', 0)}</b>\n"
        f"· Активных: <b>{s.get('invoices_active', 0)}</b>\n"
        f"· Оплаченных: <b>{s.get('invoices_paid', 0)}</b>\n\n"
        "<b>Экономика</b>\n"
        f"· Σ USDT на балансах: <b>{s['usdt_sum']:.2f}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back()]]),
    )
    await callback.answer()


# ── Cheques overview ───────────────────────────────────────


@router.callback_query(F.data == "adm:cheques")
async def adm_cheques(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    s = db.get_admin_stats()
    recent = db.list_recent_cheques(12)
    lines = [
        "🏷 <b>Чеки</b>\n",
        f"Активных: <b>{s['cheques_active']}</b> / всего <b>{s['cheques_total']}</b>",
        f"Персональных: <b>{s['cheques_personal']}</b> · Мульти: <b>{s['cheques_multi']}</b>",
        f"Claims: <b>{s['claims']}</b>\n",
        "<b>Последние:</b>",
    ]
    if not recent:
        lines.append("<i>Пока пусто</i>")
    else:
        for ch in recent:
            kind = "P" if ch.get("cheque_type") == "personal" else "M"
            st = ch.get("status") or "?"
            amt = format_amount_nb(float(ch["amount"]))
            lines.append(
                f"· [{kind}/{st}] <code>{ch['code']}</code> "
                f"{amt} {ch['coin_code']} · uid <code>{ch['creator_id']}</code>"
            )
    rows = [
        [InlineKeyboardButton(text="🗑 Удалить по коду", callback_data="adm:chk:delask")],
        [_back()],
    ]
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


class AdminCheque(StatesGroup):
    delete_code = State()


@router.callback_query(F.data == "adm:chk:delask")
async def adm_chk_delask(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.set_state(AdminCheque.delete_code)
    await callback.message.edit_text(
        "Введите <b>код чека</b> для удаления (с возвратом средств создателю, если активен):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:cheques")]]),
    )
    await callback.answer()


@router.message(AdminCheque.delete_code)
async def adm_chk_delete(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    code = (message.text or "").strip()
    await state.clear()
    ch = db.delete_cheque(code, refund=True)
    if not ch:
        await message.answer("Чек не найден.", reply_markup=admin_home_kb())
        return
    await message.answer(
        f"✅ Чек <code>{code}</code> удалён.",
        reply_markup=admin_home_kb(),
    )


# ── Balances top ───────────────────────────────────────────


@router.callback_query(F.data == "adm:balances")
async def adm_balances(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    rows = db.list_top_usdt_balances(limit=15)
    lines = ["💵 <b>Топ USDT балансов</b>\n"]
    for i, r in enumerate(rows, 1):
        if isinstance(r, (tuple, list)):
            uid, amt, un = r[0], r[1], (r[2] if len(r) > 2 else None)
        else:
            uid, amt, un = r.get("user_id"), r.get("amount"), r.get("username")
        tag = f" @{un}" if un else ""
        lines.append(f"{i}. <code>{uid}</code>{tag} — <b>{float(amt):.4f}</b>")
    if len(lines) == 1:
        lines.append("<i>Пусто</i>")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back()]]),
    )
    await callback.answer()


# ── Users ──────────────────────────────────────────────────


def _users_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="adm:users:search")],
            [InlineKeyboardButton(text="🆕 Недавние", callback_data="adm:users:recent")],
            [InlineKeyboardButton(text="🔒 Заблокированные", callback_data="adm:users:blocked")],
            [_back()],
        ]
    )


@router.callback_query(F.data == "adm:users")
async def adm_users(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    s = db.get_admin_stats()
    await callback.message.edit_text(
        "👥 <b>Пользователи</b>\n\n"
        f"Всего: <b>{s['total']}</b> · блок админа: <b>{s['blocked']}</b> · "
        f"блок бота: <b>{s['bot_blocked']}</b>\n\n"
        "Поиск по <b>ID</b> или <b>@username</b>.",
        reply_markup=_users_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:users:search")
async def adm_users_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.set_state(AdminUser.search)
    await callback.message.edit_text(
        "🔎 Введите <b>Telegram ID</b> или <b>@username</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:users")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:users:recent")
async def adm_users_recent(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    users = db.list_recent_users(12)
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        un = f"@{u['username']}" if u.get("username") else u.get("full_name") or "—"
        flag = "🔒" if u.get("is_blocked") else ("🚫" if u.get("bot_blocked") else "·")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{flag} {u['user_id']} {un}"[:64],
                    callback_data=f"adm:user:open:{u['user_id']}",
                )
            ]
        )
    rows.append([_back("adm:users")])
    await callback.message.edit_text(
        "🆕 <b>Недавние пользователи</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:users:blocked")
async def adm_users_blocked(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    users = db.list_blocked_users(20)
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        un = f"@{u['username']}" if u.get("username") else str(u["user_id"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔒 {u['user_id']} {un}"[:64],
                    callback_data=f"adm:user:open:{u['user_id']}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Список пуст", callback_data="noop")])
    rows.append([_back("adm:users")])
    await callback.message.edit_text(
        "🔒 <b>Заблокированные админом</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


def _user_kb(uid: int, blocked: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔓 Разблокировать" if blocked else "🔒 Заблокировать",
                    callback_data=f"adm:user:block:{uid}",
                )
            ],
            [
                InlineKeyboardButton(text="💵 Задать USDT", callback_data=f"adm:user:bal:{uid}"),
                InlineKeyboardButton(text="➕ Выдать монету", callback_data=f"adm:user:add:{uid}"),
            ],
            [
                InlineKeyboardButton(text="✉️ Написать", callback_data=f"adm:user:msg:{uid}"),
                InlineKeyboardButton(text="🏷 Чеки юзера", callback_data=f"adm:user:chks:{uid}"),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Сброс notice блока",
                    callback_data=f"adm:user:resetnotice:{uid}",
                )
            ],
            [_back("adm:users")],
        ]
    )


def _user_card_text(uid: int) -> tuple[str, bool]:
    card = db.get_user_admin_card(uid)
    if not card:
        db.ensure_user(uid, None, f"User {uid}")
        card = db.get_user_admin_card(uid) or {}
    usd = _total_usd(uid)
    bals = card.get("balances") or {}
    bals_lines = []
    for k, v in sorted(bals.items(), key=lambda x: -x[1])[:12]:
        bals_lines.append(f"  {coins.coin_emoji_tag(k)} <b>{k}</b>: {format_amount_nb(v)}")
    bals_s = "\n".join(bals_lines) if bals_lines else "  —"
    blocked = bool(card.get("is_blocked"))
    text = (
        f"👤 <b>Пользователь</b> <code>{uid}</code>\n\n"
        f"Username: @{card.get('username') or '—'}\n"
        f"Имя: {card.get('full_name') or '—'}\n"
        f"/start: <b>{card.get('starts_count') or 0}</b>\n"
        f"Чеков создано: <b>{card.get('cheques') or 0}</b>\n"
        f"≈ баланс: <b>{usd:.2f} $</b>\n"
        f"Монеты:\n{bals_s}\n\n"
        f"Блок админа: <b>{'да' if blocked else 'нет'}</b>\n"
        f"Блок бота: <b>{'да' if card.get('bot_blocked') else 'нет'}</b>"
    )
    return text, blocked


async def _show_user_card(target: Message | CallbackQuery, uid: int) -> None:
    text, blocked = _user_card_text(uid)
    kb = _user_kb(uid, blocked)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


@router.message(AdminUser.search)
async def adm_user_search(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    uid: int | None = None
    if raw.startswith("@") or (raw and not raw.lstrip("-").isdigit()):
        uid = db.find_user_id_by_username(raw)
        if uid is None:
            await message.answer("Пользователь с таким username не найден в боте.")
            return
    else:
        try:
            uid = int(raw)
        except ValueError:
            await message.answer("Введите числовой ID или @username.")
            return
    await state.clear()
    await _show_user_card(message, uid)


@router.callback_query(F.data.startswith("adm:user:open:"))
async def adm_user_open(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    uid = int(callback.data.split(":")[-1])
    await _show_user_card(callback, uid)


@router.callback_query(F.data.startswith("adm:user:block:"))
async def adm_user_block(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    card = db.get_user_admin_card(uid)
    if not card:
        return await callback.answer()
    new_blocked = not bool(card.get("is_blocked"))
    db.set_user_blocked(uid, new_blocked)
    if new_blocked:
        try:
            await callback.bot.send_message(uid, BLOCKED_TEXT)
        except Exception:
            db.set_bot_blocked(uid, True)
    await log_action(
        callback.bot,
        BOT_LABEL,
        "Админ: блок пользователя" if new_blocked else "Админ: разблок пользователя",
        user=callback.from_user,
        lines=[f"· Цель: <code>{uid}</code>"],
        emoji_key="warn",
        fallback="🍂",
    )
    await _show_user_card(callback, uid)
    await callback.answer("Заблокирован" if new_blocked else "Разблокирован")


@router.callback_query(F.data.startswith("adm:user:resetnotice:"))
async def adm_user_reset_notice(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    db.set_block_notice_sent(uid, False)
    await callback.answer("Сброшено")


@router.callback_query(F.data.startswith("adm:user:bal:"))
async def adm_user_bal(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminUser.set_balance)
    await callback.message.edit_text(
        f"Введите новый баланс <b>USDT</b> для <code>{uid}</code> "
        f"(абсолютное значение):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_back(f"adm:user:open:{uid}")]]
        ),
    )
    await callback.answer()


@router.message(AdminUser.set_balance)
async def adm_set_bal(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    uid = data.get("target_uid")
    await state.clear()
    try:
        amount = float((message.text or "").replace(",", "."))
        if amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("Неверная сумма")
        return
    db.set_balance(uid, "USDT", amount)
    await log_action(
        message.bot,
        BOT_LABEL,
        "Админ: задан баланс USDT",
        user=message.from_user,
        lines=[
            f"· Цель: <code>{uid}</code>",
            f"· Новый баланс: <b>{amount} USDT</b>",
        ],
        emoji_key="wallet",
        fallback="👛",
    )
    await message.answer(
        f"✅ USDT пользователя <code>{uid}</code> = <b>{amount}</b>"
    )
    await _show_user_card(message, int(uid))


@router.callback_query(F.data.startswith("adm:user:add:"))
async def adm_user_add_coin(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminUser.add_balance)
    codes = ", ".join(c.code for c in _all_coins()[:12]) + "…"
    await callback.message.edit_text(
        f"Выдать монету пользователю <code>{uid}</code>.\n\n"
        f"Формат: <code>USDT 100</code> или <code>BTC 0.01</code>\n"
        f"<i>Примеры монет: {codes}</i>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_back(f"adm:user:open:{uid}")]]
        ),
    )
    await callback.answer()


@router.message(AdminUser.add_balance)
async def adm_add_bal(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    uid = int(data.get("target_uid") or 0)
    await state.clear()
    parts = (message.text or "").strip().replace(",", ".").split()
    if len(parts) != 2:
        await message.answer("Формат: <code>COIN AMOUNT</code>")
        return
    coin, raw_amt = parts[0].upper(), parts[1]
    try:
        amount = float(raw_amt)
    except ValueError:
        await message.answer("Неверная сумма")
        return
    try:
        db.change_balance(uid, coin, amount)
    except Exception as exc:
        await message.answer(f"Ошибка: {exc}")
        return
    await log_action(
        message.bot,
        BOT_LABEL,
        "Админ: выдача монеты",
        user=message.from_user,
        lines=[
            f"· Цель: <code>{uid}</code>",
            f"· Сумма: <b>{('+' if amount >= 0 else '')}{format_amount_nb(amount)} {coin}</b>",
        ],
        emoji_key="wallet",
        fallback="👛",
    )
    await message.answer(
        f"✅ {coins.coin_emoji_tag(coin)} <b>{coin}</b> {('+' if amount >= 0 else '')}"
        f"{format_amount_nb(amount)} → <code>{uid}</code>"
    )
    await _show_user_card(message, uid)


@router.callback_query(F.data.startswith("adm:user:msg:"))
async def adm_user_msg(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminUser.message_user)
    await callback.message.edit_text(
        f"✉️ Отправьте сообщение для <code>{uid}</code> "
        f"(текст/фото/что угодно — будет скопировано):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_back(f"adm:user:open:{uid}")]]
        ),
    )
    await callback.answer()


@router.message(AdminUser.message_user)
async def adm_send_user_msg(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    uid = int(data.get("target_uid") or 0)
    await state.clear()
    try:
        await message.bot.copy_message(
            chat_id=uid,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await message.answer("✅ Отправлено")
    except Exception as exc:
        await message.answer(f"❌ Не удалось: {exc}")
        db.set_bot_blocked(uid, True)
    await _show_user_card(message, uid)


@router.callback_query(F.data.startswith("adm:user:chks:"))
async def adm_user_chks(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[-1])
    items = db.list_active_cheques(uid)
    lines = [f"🏷 <b>Активные чеки</b> <code>{uid}</code>\n"]
    if not items:
        lines.append("<i>Нет активных чеков</i>")
    else:
        for ch in items[:30]:
            kind = "P" if ch.get("cheque_type") == "personal" else "M"
            lines.append(
                f"· [{kind}] <code>{ch['code']}</code> — "
                f"{format_amount_nb(float(ch['amount']))} {ch['coin_code']}"
            )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_back(f"adm:user:open:{uid}")]]
        ),
    )
    await callback.answer()


# ── Tracking links ─────────────────────────────────────────


@router.callback_query(F.data == "adm:links")
async def adm_links(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    links = db.list_tracking_links()
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Создать ссылку", callback_data="adm:link:create")]
    ]
    for lnk in links[:30]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📎 {lnk['name']} · {lnk.get('clicks', 0)}",
                    callback_data=f"adm:link:view:{lnk['slug']}",
                )
            ]
        )
    rows.append([_back()])
    await callback.message.edit_text(
        "🔗 <b>Трекинг-ссылки</b>\n\n"
        "Ссылки вида <code>t.me/BOT?start=ref_SLUG</code>\n"
        "Считают уникальные переходы по /start.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:link:create")
async def adm_link_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.set_state(AdminLink.name)
    await callback.message.edit_text(
        "Введите название ссылки (например <code>instagram</code>):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:links")]]),
    )
    await callback.answer()


@router.message(AdminLink.name)
async def adm_link_name(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    await state.clear()
    if not name:
        await message.answer("Пустое имя")
        return
    link = db.create_tracking_link(name)
    me = await bot.get_me()
    uname = me.username or "bot"
    url = f"https://t.me/{uname}?start=ref_{link['slug']}"
    await message.answer(
        f"✅ Ссылка создана\n\n"
        f"<b>{link['name']}</b>\n"
        f"<code>{url}</code>",
        reply_markup=admin_home_kb(),
    )


@router.callback_query(F.data.startswith("adm:link:view:"))
async def adm_link_view(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    slug = callback.data.split(":")[-1]
    link = db.get_tracking_link(slug)
    if not link:
        await callback.answer()
        return
    me = await bot.get_me()
    uname = me.username or "bot"
    url = f"https://t.me/{uname}?start=ref_{slug}"
    text = (
        f"📎 <b>{link['name']}</b>\n\n"
        f"Slug: <code>{slug}</code>\n"
        f"Клики (уник.): <b>{link.get('unique', 0)}</b>\n"
        f"Клики (всего): <b>{link.get('clicks', 0)}</b>\n\n"
        f"<code>{url}</code>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"adm:link:del:{slug}",
                    )
                ],
                [_back("adm:links")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:link:del:"))
async def adm_link_del(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    slug = callback.data.split(":")[-1]
    db.delete_tracking_link(slug)
    await callback.answer("Удалено")
    await adm_links(callback, state)


# ── Broadcast ──────────────────────────────────────────────


@router.callback_query(F.data == "adm:bc")
async def adm_bc(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "📣 <b>Рассылка</b>\n\n"
        "Отправка любого сообщения всем пользователям "
        "(кроме заблокированных админом).\n"
        "Поддержка текста, фото, видео, гифок — через copy_message.",
        reply_markup=bc_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:bc:now")
async def adm_bc_now(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.update_data(bc_scheduled=False)
    await state.set_state(AdminBC.waiting_message)
    await callback.message.edit_text(
        "📣 <b>Рассылка — сейчас</b>\n\n"
        "Отправь сообщение для рассылки.\n"
        "<i>Текст, фото, видео, гиф — всё будет скопировано как есть.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:bc")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:bc:schedule")
async def adm_bc_schedule(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.update_data(bc_scheduled=True)
    await state.set_state(AdminBC.waiting_message)
    await callback.message.edit_text(
        "⏰ <b>Рассылка — запланировать</b>\n\nОтправь сообщение для рассылки.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:bc")]]),
    )
    await callback.answer()


@router.message(AdminBC.waiting_message)
async def adm_bc_msg(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(
        bc_from_chat_id=message.chat.id,
        bc_message_id=message.message_id,
    )
    await message.answer(
        "Добавить inline-кнопку к этой рассылке?",
        reply_markup=bc_btn_choice_kb(),
    )


@router.callback_query(F.data == "adm:bc:nobtn")
async def adm_bc_nobtn(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.update_data(bc_button_text=None, bc_button_url=None)
    await _continue_bc(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "adm:bc:addbtn")
async def adm_bc_addbtn(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.set_state(AdminBC.button_text)
    await callback.message.edit_text("Введите текст кнопки (до 64 символов):")
    await callback.answer()


@router.message(AdminBC.button_text)
async def adm_bc_btn_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    t = (message.text or "").strip()
    if not t or len(t) > 64:
        await message.answer("1–64 символа")
        return
    await state.update_data(bc_button_text=t)
    await state.set_state(AdminBC.button_url)
    await message.answer("Введите ссылку (http/https):")


@router.message(AdminBC.button_url)
async def adm_bc_btn_url(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    url = (message.text or "").strip()
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or not p.netloc:
        await message.answer("Нужна корректная ссылка")
        return
    await state.update_data(bc_button_url=url)
    await _continue_bc(message, state)


async def _continue_bc(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("bc_scheduled"):
        await state.set_state(AdminBC.schedule_time)
        await message.answer(
            "⏰ Введите дату и время по МСК:\n<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back("adm:bc")]]),
        )
        return
    bc_id = str(uuid.uuid4())[:8]
    await state.update_data(bc_id=bc_id)
    await _show_bc_preview(message, state, None)


@router.message(AdminBC.schedule_time)
async def adm_bc_time(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    try:
        dt = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M").replace(
            tzinfo=MSK
        )
    except ValueError:
        await message.answer("Формат: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    if dt <= datetime.now(MSK):
        await message.answer("Время должно быть в будущем")
        return
    bc_id = str(uuid.uuid4())[:8]
    await state.update_data(bc_id=bc_id, bc_run_at=dt.isoformat())
    await _show_bc_preview(message, state, dt.strftime("%d.%m.%Y %H:%M МСК"))


async def _show_bc_preview(
    message: Message, state: FSMContext, scheduled_str: str | None
) -> None:
    data = await state.get_data()
    bc_id = data["bc_id"]
    users = db.get_all_user_ids()
    sched = f"\n⏰ Отправка: <b>{scheduled_str}</b>" if scheduled_str else ""
    await state.clear()
    await message.answer(
        f"📣 <b>Предпросмотр</b>\n👥 Получателей: <b>{len(users)}</b>{sched}\n\n"
        "<i>Сообщение ниже будет разослано:</i>"
    )
    await message.bot.copy_message(
        chat_id=message.chat.id,
        from_chat_id=data["bc_from_chat_id"],
        message_id=data["bc_message_id"],
        reply_markup=_bc_markup(data.get("bc_button_text"), data.get("bc_button_url")),
    )
    await message.answer(
        "▲ Так получат пользователи",
        reply_markup=bc_confirm_kb(bc_id),
    )
    _pending_bc[bc_id] = {
        "id": bc_id,
        "from_chat_id": data["bc_from_chat_id"],
        "message_id": data["bc_message_id"],
        "run_at": data.get("bc_run_at"),
        "admin_id": message.from_user.id,
        "admin_chat_id": message.chat.id,
        "status": "pending",
        "button_text": data.get("bc_button_text"),
        "button_url": data.get("bc_button_url"),
        "created_at": datetime.now(MSK).isoformat(),
    }


@router.callback_query(F.data.startswith("adm:bc:send:"))
async def adm_bc_send(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    bc_id = callback.data.split(":")[-1]
    bc = _pending_bc.pop(bc_id, None)
    if not bc:
        await callback.answer("Устарело — создайте заново", show_alert=True)
        return
    users = db.get_all_user_ids()
    if bc.get("run_at"):
        bc["status"] = "pending"
        db.save_broadcast(bc)
        task = asyncio.create_task(_run_scheduled(bot, bc))
        _scheduled_tasks[bc_id] = task
        await callback.message.edit_text(
            f"✅ Рассылка запланирована\n👥 {len(users)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back()]]),
        )
    else:
        await callback.message.edit_text("🔄 Рассылка запущена...")
        ok, fail = await _do_broadcast(
            bot,
            bc["from_chat_id"],
            bc["message_id"],
            bc.get("button_text"),
            bc.get("button_url"),
        )
        await callback.message.edit_text(
            f"✅ Готово\nУспешно: <b>{ok}</b>\nОшибок: <b>{fail}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_back()]]),
        )
    await callback.answer()


async def _do_broadcast(
    bot: Bot,
    from_chat_id: int,
    message_id: int,
    button_text: str | None = None,
    button_url: str | None = None,
) -> tuple[int, int]:
    users = db.get_all_user_ids()
    ok = fail = 0
    markup = _bc_markup(button_text, button_url)
    for uid in users:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id,
                reply_markup=markup,
            )
            ok += 1
            db.set_bot_blocked(uid, False)
        except Exception as e:
            fail += 1
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "forbidden" in err:
                db.set_bot_blocked(uid, True)
            log.debug("bc fail %s: %s", uid, e)
        await asyncio.sleep(0.05)
    return ok, fail


async def _run_scheduled(bot: Bot, bc: dict) -> None:
    try:
        run_at = datetime.fromisoformat(bc["run_at"])
        aware = run_at if run_at.tzinfo else run_at.replace(tzinfo=MSK)
        delay = (aware - datetime.now(MSK)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        ok, fail = await _do_broadcast(
            bot,
            bc["from_chat_id"],
            bc["message_id"],
            bc.get("button_text"),
            bc.get("button_url"),
        )
        db.update_broadcast_status(
            bc["id"], "done", result={"success": ok, "failed": fail}
        )
        try:
            await bot.send_message(
                bc["admin_chat_id"],
                f"✅ Запланированная рассылка завершена\nУспешно: {ok}\nОшибок: {fail}",
            )
        except Exception:
            pass
    except asyncio.CancelledError:
        raise
    finally:
        _scheduled_tasks.pop(bc["id"], None)


@router.callback_query(F.data == "adm:bc:list")
async def adm_bc_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    pending = db.get_pending_broadcasts()
    if not pending:
        text = "⏰ Нет запланированных рассылок."
        rows = [[_back("adm:bc")]]
    else:
        text = f"⏰ Запланировано: <b>{len(pending)}</b>"
        rows = []
        for bc in pending:
            try:
                dt = datetime.fromisoformat(bc["run_at"])
                label = dt.astimezone(MSK).strftime("%d.%m %H:%M")
            except Exception:
                label = str(bc.get("run_at", "?"))
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"⏰ {label} · {bc['id']}",
                        callback_data=f"adm:bc:view:{bc['id']}",
                    )
                ]
            )
        rows.append([_back("adm:bc")])
    await callback.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:bc:view:"))
async def adm_bc_view(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    bc_id = callback.data.split(":")[-1]
    bc = db.get_broadcast(bc_id)
    if not bc:
        await callback.answer()
        return
    try:
        dt = datetime.fromisoformat(bc["run_at"])
        when = dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M МСК")
    except Exception:
        when = str(bc.get("run_at"))
    text = (
        f"📣 <b>Рассылка</b> <code>{bc_id}</code>\n\n"
        f"Статус: <b>{bc.get('status')}</b>\n"
        f"Время: <b>{when}</b>\n"
        f"Кнопка: {bc.get('button_text') or '—'}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Изменить время",
                        callback_data=f"adm:bc:resched:{bc_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"adm:bc:del:{bc_id}",
                    )
                ],
                [_back("adm:bc:list")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:bc:resched:"))
async def adm_bc_resched(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    bc_id = callback.data.split(":")[-1]
    await state.update_data(resched_id=bc_id)
    await state.set_state(AdminBC.reschedule_time)
    await callback.message.edit_text(
        "⏰ Новое время по МСК:\n<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[_back(f"adm:bc:view:{bc_id}")]]
        ),
    )
    await callback.answer()


@router.message(AdminBC.reschedule_time)
async def adm_bc_resched_time(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    bc_id = data.get("resched_id")
    await state.clear()
    try:
        dt = datetime.strptime((message.text or "").strip(), "%d.%m.%Y %H:%M").replace(
            tzinfo=MSK
        )
    except ValueError:
        await message.answer("Формат: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    if dt <= datetime.now(MSK):
        await message.answer("Время должно быть в будущем")
        return
    bc = db.get_broadcast(bc_id)
    if not bc or bc.get("status") != "pending":
        await message.answer("Рассылка не найдена")
        return
    old = _scheduled_tasks.pop(bc_id, None)
    if old:
        old.cancel()
    db.update_broadcast_status(bc_id, "pending", run_at=dt.isoformat())
    bc["run_at"] = dt.isoformat()
    task = asyncio.create_task(_run_scheduled(bot, bc))
    _scheduled_tasks[bc_id] = task
    await message.answer(
        f"✅ Новое время: <b>{dt.strftime('%d.%m.%Y %H:%M МСК')}</b>",
        reply_markup=admin_home_kb(),
    )


@router.callback_query(F.data.startswith("adm:bc:del:"))
async def adm_bc_del(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    bc_id = callback.data.split(":")[-1]
    db.update_broadcast_status(bc_id, "cancelled")
    task = _scheduled_tasks.pop(bc_id, None)
    if task:
        task.cancel()
    await callback.answer("Удалено")
    await adm_bc_list(callback, state)


async def restore_scheduled_broadcasts(bot: Bot) -> None:
    for bc in db.get_pending_broadcasts():
        task = asyncio.create_task(_run_scheduled(bot, bc))
        _scheduled_tasks[bc["id"]] = task
