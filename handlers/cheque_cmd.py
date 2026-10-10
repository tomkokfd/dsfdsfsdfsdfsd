"""/cheque command + @bot mention — create a cheque without Inline Mode."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, Filter, StateFilter
from aiogram.types import LinkPreviewOptions, Message

from xrocket.config import DEFAULT_COIN
from xrocket.database import db
from xrocket.keyboards.menu import cheque_claim_keyboard
from xrocket.services import cheque as cheque_service

router = Router(name="cheque_cmd")


class BotMentionFilter(Filter):
    """Срабатывает, если в тексте есть упоминание этого бота."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        text = message.text or ""
        if not text:
            return False
        me = await bot.get_me()
        if not me.username:
            return False
        uname = me.username.lower()
        for ent in message.entities or []:
            if ent.type == "mention":
                frag = text[ent.offset : ent.offset + ent.length]
                if frag.lower() == f"@{uname}":
                    return True
            elif ent.type == "text_mention" and ent.user and ent.user.id == me.id:
                return True
        return text.lower().startswith(f"@{uname}")


def _preview() -> LinkPreviewOptions:
    return LinkPreviewOptions(is_disabled=False, show_above_text=True)


def _reply_target(message: Message) -> tuple[int | None, str | None, str | None]:
    """user_id, username, display_name from reply_to_message."""
    reply = message.reply_to_message
    if not reply or not reply.from_user or reply.from_user.is_bot:
        return None, None, None
    u = reply.from_user
    return u.id, u.username, u.full_name


async def _send_cheque(
    message: Message,
    *,
    coin_code: str,
    amount: float,
    code: str,
    for_username: str | None = None,
    for_user_id: int | None = None,
    for_display_name: str | None = None,
    description: str | None = None,
) -> None:
    fiat = cheque_service.fiat_for_amount(coin_code, amount)
    me = await message.bot.get_me()
    kb = cheque_claim_keyboard(
        amount, coin_code, me.username or "xrockets_mbot", code
    )
    preview = _preview()
    kwargs = dict(
        for_username=for_username,
        for_user_id=for_user_id,
        for_display_name=for_display_name,
        description=description,
    )

    sent = await message.answer(
        cheque_service.cheque_message_html(
            coin_code, amount, fiat, premium_rocket=False, **kwargs
        ),
        reply_markup=kb,
        link_preview_options=preview,
    )
    try:
        await sent.edit_text(
            cheque_service.cheque_message_html(
                coin_code, amount, fiat, premium_rocket=True, **kwargs
            ),
            reply_markup=kb,
            link_preview_options=preview,
        )
    except Exception:
        pass


async def _create_from_parsed(
    message: Message,
    parsed: cheque_service.ParsedChequeQuery,
) -> None:
    user = message.from_user
    if not user:
        return

    bound_id, bound_un, bound_name = _reply_target(message)
    # reply имеет приоритет над @username из текста
    if bound_id is None and parsed.bound_username:
        bound_un = parsed.bound_username
        bound_name = None

    if not cheque_service.can_create(user.id, parsed.coin_code, parsed.amount):
        await message.answer("❌ Недостаточно средств на балансе.")
        return

    try:
        code = cheque_service.create_cheque_for_user(
            user.id,
            parsed.coin_code,
            parsed.amount,
            description=parsed.description,
            bound_user_id=bound_id,
            bound_username=bound_un,
        )
    except ValueError:
        await message.answer("❌ Недостаточно средств на балансе.")
        return

    await _send_cheque(
        message,
        coin_code=parsed.coin_code,
        amount=parsed.amount,
        code=code,
        for_username=bound_un,
        for_user_id=bound_id,
        for_display_name=bound_name,
        description=parsed.description,
    )


@router.message(Command("cheque", "check", "чек"))
async def cmd_cheque(message: Message, command: CommandObject) -> None:
    user = message.from_user
    if not user:
        return
    db.ensure_user(user.id, user.username, user.full_name)

    args = (command.args or "").strip()
    parsed = cheque_service.parse_inline_query(args, DEFAULT_COIN)
    if not parsed:
        await message.answer(
            "🏷 <b>Создание чека (Fun Bot)</b>\n\n"
            "Пример:\n"
            "<code>/cheque 1</code>\n"
            "<code>/cheque USDT 5</code>\n"
            "<code>/cheque 0.01 ETH</code>\n"
            "<code>/cheque 150 за обед</code>\n\n"
            "Reply на сообщение + сумма — чек для этого человека.\n\n"
            "Или через Inline: <code>@xrockets_mbot 1</code>"
        )
        return

    await _create_from_parsed(message, parsed)


@router.message(StateFilter(None), F.text, BotMentionFilter())
async def mention_cheque(message: Message) -> None:
    """@bot 150 [описание] — создание чека; reply → привязка к человеку."""
    user = message.from_user
    if not user or not message.text:
        return

    parsed = cheque_service.parse_inline_query(message.text, DEFAULT_COIN)
    if not parsed:
        return

    db.ensure_user(user.id, user.username, user.full_name)
    await _create_from_parsed(message, parsed)
