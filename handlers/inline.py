"""Inline mode: create / share cheques."""

from __future__ import annotations

import logging
import re

from aiogram import Bot, Router
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
)

from xrocket.config import CHEQUE_THUMB_URL, DEFAULT_COIN
from xrocket.database import db
from xrocket.keyboards.cheques import claim_kb
from xrocket.services import cheque as cheque_service
from xrocket.services.action_log import log_action
from xrocket.utils.formatters import (
    fiat_for_amount,
    format_amount_nb,
    format_fiat,
    money_pair,
)

router = Router(name="inline")
logger = logging.getLogger("xrocket-fun")
BOT_LABEL = "xRocket"

# Префикс result_id: по нему chosen_inline_result понимает, что это чек
RID_PREFIX = "x:"


def _preview_opts() -> LinkPreviewOptions:
    return LinkPreviewOptions(
        is_disabled=False,
        show_above_text=True,
    )


def _build_cheque_view(ch: dict, bot_username: str, premium: bool):
    """Собирает текст и клавиатуру для существующего чека."""
    coin = ch["coin_code"]
    if ch.get("cheque_type") == "multi":
        text = cheque_service.multi_share_html(ch, premium_rocket=premium)
        markup = claim_kb(
            float(ch["amount"]),
            coin,
            bot_username,
            f"mc_{ch['code']}",
        )
    else:
        amount = float(ch["amount"])
        fiat = fiat_for_amount(coin, amount)
        text = cheque_service.cheque_message_html(
            coin,
            amount,
            fiat,
            premium_rocket=premium,
            for_username=ch.get("bound_username"),
            for_user_id=ch.get("bound_user_id"),
            description=ch.get("description"),
        )
        markup = claim_kb(
            amount,
            coin,
            bot_username,
            f"t_{ch['code']}",
        )
    return text, markup


@router.inline_query()
async def on_inline_query(query: InlineQuery) -> None:
    user = query.from_user

    if db.is_user_blocked(user.id):
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    db.ensure_user(user.id, user.username, user.full_name)

    q = (query.query or "").strip()

    me = await query.bot.get_me()
    bot_username = me.username or "xrockets_mbot"

    raw = q

    # ── Существующий чек / поделиться чеком ──────────────────────────
    if raw.startswith("mc_") or re.fullmatch(r"[A-Za-z0-9]{8,20}", raw):
        ch = db.get_cheque(raw)

        if ch and ch["status"] == "active":
            rid = f"{RID_PREFIX}{ch['code']}"
            coin = ch["coin_code"]

            if ch.get("cheque_type") == "multi":
                per = float(ch["amount"])
                total_n = int(ch["activations_total"])
                used = int(ch.get("activations_used") or 0)
                total = per * total_n

                title = f"Мульти-чек на {format_amount_nb(total)} {coin}"
                desc = (
                    f"Одна активация: "
                    f"{format_amount_nb(per)} {coin} · "
                    f"{format_amount_nb(total)} {coin} ·\n"
                    f"{used} / {total_n}"
                )
            else:
                amount = float(ch["amount"])
                fiat = fiat_for_amount(coin, amount)

                title = f"Чек на {format_amount_nb(amount)} {coin}"
                desc = f"{money_pair(amount, coin, fiat)} • Fun Bot"

            # Отправляем с обычной 🚀 — на премиум заменим в on_chosen
            text, markup = _build_cheque_view(ch, bot_username, premium=False)

            result = InlineQueryResultArticle(
                id=rid,
                title=title,
                description=desc,
                thumbnail_url=CHEQUE_THUMB_URL,
                thumbnail_width=128,
                thumbnail_height=128,
                input_message_content=InputTextMessageContent(
                    message_text=text,
                    parse_mode="HTML",
                    link_preview_options=_preview_opts(),
                ),
                reply_markup=markup,
            )

            await query.answer(results=[result], cache_time=1, is_personal=True)
            return

    # ── Создание нового чека ─────────────────────────────────────────
    parsed = cheque_service.parse_inline_query(q, DEFAULT_COIN)

    if not parsed:
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    if not cheque_service.can_create(user.id, parsed.coin_code, parsed.amount):
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    try:
        code = cheque_service.create_cheque_for_user(
            user.id,
            parsed.coin_code,
            parsed.amount,
            description=parsed.description,
            bound_username=parsed.bound_username,
        )
    except ValueError:
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    fiat = fiat_for_amount(parsed.coin_code, parsed.amount)
    amount_s = format_amount_nb(parsed.amount)
    fiat_s = format_fiat(fiat)

    # Отправляем с обычной 🚀 — на премиум заменим в on_chosen
    text = cheque_service.cheque_message_html(
        parsed.coin_code,
        parsed.amount,
        fiat,
        premium_rocket=False,
        for_username=parsed.bound_username,
        description=parsed.description,
    )

    markup = claim_kb(
        parsed.amount,
        parsed.coin_code,
        bot_username,
        f"t_{code}",
    )

    title = f"Чек на {amount_s} {parsed.coin_code}"
    if parsed.bound_username:
        title += f" для @{parsed.bound_username.lstrip('@')}"
    desc_parts = [f"{amount_s} {parsed.coin_code} ({fiat_s}$)"]
    if parsed.description:
        desc_parts.append(parsed.description[:60])
    desc_parts.append("Fun Bot")

    result = InlineQueryResultArticle(
        id=f"{RID_PREFIX}{code}",
        title=title,
        description=" • ".join(desc_parts),
        thumbnail_url=CHEQUE_THUMB_URL,
        thumbnail_width=128,
        thumbnail_height=128,
        input_message_content=InputTextMessageContent(
            message_text=text,
            parse_mode="HTML",
            link_preview_options=_preview_opts(),
        ),
        reply_markup=markup,
    )

    await query.answer(results=[result], cache_time=1, is_personal=True)


@router.chosen_inline_result()
async def on_chosen(chosen: ChosenInlineResult, bot: Bot) -> None:
    """После отправки заменяем обычную 🚀 на премиум-эмодзи через edit.

    Требует: @BotFather → /setinlinefeedback → Enabled (лучше 100%).
    """
    logger.info(
        "chosen_inline_result: result_id=%s inline_message_id=%s",
        chosen.result_id,
        chosen.inline_message_id,
    )

    if not chosen.inline_message_id:
        logger.warning("нет inline_message_id (у результата нет reply_markup?)")
        return
    if not chosen.result_id.startswith(RID_PREFIX):
        logger.warning("result_id без префикса: %s", chosen.result_id)
        return

    code = chosen.result_id[len(RID_PREFIX):]
    ch = db.get_cheque(code)
    if not ch:
        logger.warning("чек не найден в БД по коду %s", code)
        return

    # Mark as sent so it won't be reused for the next inline create
    db.update_cheque(code, inline_message_id=chosen.inline_message_id)

    me = await bot.get_me()
    text, markup = _build_cheque_view(
        ch,
        me.username or "xrockets_mbot",
        premium=True,
    )
    logger.info("edit text: %r", text)

    try:
        await bot.edit_message_text(
            text=text,
            inline_message_id=chosen.inline_message_id,
            reply_markup=markup,
            link_preview_options=_preview_opts(),
        )
        logger.info("edit OK")
    except Exception:
        logger.exception("edit FAILED")

    await log_action(
        bot,
        BOT_LABEL,
        "Чек отправлен (inline)",
        user=chosen.from_user,
        lines=[
            f"· Код: <code>{code}</code>",
            f"· Сумма: <b>{format_amount_nb(float(ch['amount']))} {ch['coin_code']}</b>",
        ],
        emoji_key="cheque",
        fallback="🏷",
    )