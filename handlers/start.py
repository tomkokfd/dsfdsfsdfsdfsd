"""Start command and cheque deep-link activation."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from xrocket.config import URL_NEWS
from xrocket.database import db
from xrocket.keyboards.menu import main_menu_keyboard
from xrocket.services import balance as balance_service
from xrocket.services import cheque as cheque_service
from xrocket.services.action_log import log_action
from xrocket.utils.formatters import fiat_for_amount, format_amount_nb, tg_emoji

router = Router(name="start")
BOT_LABEL = "xRocket"


def _full_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "User"
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or (user.username or "User")


def _back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")]]
    )


async def send_home(message: Message, *, count_start: bool = True) -> None:
    user = message.from_user
    if not user:
        return
    db.ensure_user(user.id, user.username, _full_name(message))
    if count_start:
        db.bump_starts(user.id)
        await log_action(
            message.bot,
            BOT_LABEL,
            "Запуск /start",
            user=user,
            emoji_key="rocket",
            fallback="🚀",
        )
    total = balance_service.total_usd(user.id)
    cheques_n = db.count_active_cheques(user.id)
    rocket = tg_emoji("rocket", "🚀")
    text = (
        f"{rocket} <b>xRocket</b> — это бот-кошелёк для получения, отправки, "
        f"покупки и хранения криптовалюты в Telegram.\n\n"
        f"Обо всех возможностях читай в "
        f'<a href="{URL_NEWS}">официальном канале</a>'
    )
    await message.answer(
        text,
        reply_markup=main_menu_keyboard(total, cheques_n, user.id),
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    if not user:
        return
    db.ensure_user(user.id, user.username, _full_name(message))
    payload = (command.args or "").strip()

    if payload.startswith(("cheque_", "t_", "mc_")):
        code = payload
        for prefix in ("cheque_", "t_", "mc_"):
            if code.startswith(prefix):
                code = code[len(prefix) :]
                break
        await _activate_cheque(message, code)
        return

    if payload.startswith("ref_"):
        slug = payload[4:].strip()
        if slug:
            try:
                db.track_link_hit(slug, user.id)
            except Exception:
                pass

    await send_home(message)


@router.message(Command("p2p", "wallet", "cheques", "api", "lang", "settings"))
async def cmd_home_alias(message: Message) -> None:
    await send_home(message, count_start=False)


async def _activate_cheque(message: Message, code: str) -> None:
    user = message.from_user
    if not user:
        return

    cheque = db.get_cheque(code)
    if not cheque or cheque["status"] != "active":
        await message.answer(
            "Этот перевод уже активирован.",
            reply_markup=_back_home(),
        )
        return

    try:
        result = db.activate_cheque(code, user.id, user.username)
    except ValueError as exc:
        err = str(exc)
        if err == "forbidden":
            await message.answer(
                "Вы <b>не можете активировать</b> данный перевод.",
                reply_markup=_back_home(),
            )
        elif err == "already_claimed":
            await message.answer(
                "Вы уже активировали этот мульти-чек.",
                reply_markup=_back_home(),
            )
        else:
            await message.answer(
                "Этот перевод уже активирован.",
                reply_markup=_back_home(),
            )
        return

    amount = float(result["amount"])
    coin = result["coin_code"]
    await message.answer(cheque_service.activation_success_html(result))
    amount_fiat = fiat_for_amount(coin, amount)
    await log_action(
        message.bot,
        BOT_LABEL,
        "Чек активирован",
        user=user,
        lines=[
            f"· Код: <code>{code}</code>",
            f"· Получено: <b>{format_amount_nb(amount)} {coin}</b> (${amount_fiat:.2f})",
            f"· Создатель: <code>{result.get('creator_id')}</code>",
        ],
        emoji_key="cheque",
        fallback="🏷",
    )

    creator_id = int(result["creator_id"])
    notify_on = bool(result.get("notify_on", 1))
    if creator_id != user.id and notify_on:
        try:
            await message.bot.send_message(
                creator_id,
                cheque_service.creator_notify_html(
                    user.id, _full_name(message), coin, amount, amount_fiat
                ),
            )
        except Exception:
            pass

    await send_home(message)
