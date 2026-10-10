from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from ..config import START_TEXT
from ..db import db
from ..keyboards import main_menu_kb
from ..action_log import log_action

router = Router(name="start")
BOT_LABEL = "Crypto Bot"

# All menu commands open the main screen
MENU_COMMANDS = ("p2p", "wallet", "checks", "invoices", "giveaways", "subscriptions")


def _user_meta(message_or_cb) -> tuple[int, str | None, str]:
    u = message_or_cb.from_user
    full_name = (u.full_name or "").strip() or (u.first_name or "User")
    return u.id, u.username, full_name


async def send_main_menu(message: Message, *, count_start: bool = False) -> None:
    uid, username, full_name = _user_meta(message)
    db.ensure_user(uid, username=username, full_name=full_name)
    if count_start:
        db.bump_starts(uid)
    cheques_n = db.count_active_cheques(uid)
    await message.answer(
        START_TEXT,
        reply_markup=main_menu_kb(uid, cheques_n),
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    uid, username, full_name = _user_meta(message)
    db.ensure_user(uid, username=username, full_name=full_name)
    db.bump_starts(uid)

    args = (command.args or "").strip()

    if args.startswith("cq_"):
        from .cheques import handle_cheque_activation

        await handle_cheque_activation(message, args[3:], state)
        return

    if args.startswith("mc_"):
        from .cheques import handle_cheque_activation

        await handle_cheque_activation(message, args[3:], state)
        return

    if args.startswith("ref_"):
        slug = args[4:].strip()
        if slug:
            try:
                db.track_link_hit(slug, uid)
            except Exception:
                pass

    if args.upper().startswith("IV"):
        from .invoices import handle_invoice_start

        await handle_invoice_start(message, args)
        return

    await state.clear()

    await log_action(
        message.bot,
        BOT_LABEL,
        "Запуск /start",
        user=message.from_user,
        emoji_key="butterfly",
        fallback="🦋",
    )

    await send_main_menu(message)


@router.message(Command(*MENU_COMMANDS))
async def cmd_menu_aliases(message: Message, state: FSMContext) -> None:
    """/p2p /wallet /checks /invoices /giveaways /subscriptions → главное меню."""
    await state.clear()
    await send_main_menu(message)


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery) -> None:
    uid, username, full_name = _user_meta(callback)
    db.ensure_user(uid, username=username, full_name=full_name)
    await callback.answer()
    cheques_n = db.count_active_cheques(uid)
    if callback.message:
        try:
            await callback.message.edit_text(
                START_TEXT,
                reply_markup=main_menu_kb(uid, cheques_n),
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                disable_web_page_preview=True,
            )
        except Exception:
            await callback.message.answer(
                START_TEXT,
                reply_markup=main_menu_kb(uid, cheques_n),
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                disable_web_page_preview=True,
            )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
