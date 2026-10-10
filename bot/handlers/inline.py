"""Inline mode: send cheque / create invoice / share existing multi-cheque."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from aiogram import Bot, Router
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from .. import coins
from ..action_log import log_action
from ..db import db
from ..formatters import format_amount, format_usd
from ..images import cheque_image_url, coin_thumb_url, invoice_image_url, INVOICE_THUMB_URL
from ..messages import (
    cheque_claim_kb,
    cheque_message_html,
    invoice_message_html,
    invoice_pay_kb,
    multi_share_html,
    preview_opts,
)

router = Router(name="inline")
log = logging.getLogger(__name__)
BOT_LABEL = "Crypto Bot"

_pending_results: dict[str, dict] = {}
_reuse_cache: dict[str, tuple[float, str]] = {}
_REUSE_TTL = 45.0

_AMOUNT_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<rest>.*)$",
    re.UNICODE,
)


def _parse_inline_query(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    m = _AMOUNT_RE.match(text)
    if not m:
        return None

    raw_amt = m.group("amount").replace(",", ".")
    try:
        amount = float(raw_amt)
    except ValueError:
        return None
    if amount <= 0:
        return None

    rest = (m.group("rest") or "").strip()
    coin_code = "USDT"
    description = ""

    if rest:
        parts = rest.split(None, 1)
        first = parts[0].upper()
        if coins.get_coin(first):
            coin_code = first
            description = parts[1].strip() if len(parts) > 1 else ""
        else:
            description = rest

    if description.lower().startswith("за "):
        description = description[3:].strip()

    return {
        "amount": amount,
        "coin": coin_code,
        "description": description,
    }


def _cache_get(key: str) -> Optional[str]:
    item = _reuse_cache.get(key)
    if not item:
        return None
    ts, code = item
    if time.time() - ts > _REUSE_TTL:
        _reuse_cache.pop(key, None)
        return None
    return code


def _cache_set(key: str, code: str) -> None:
    _reuse_cache[key] = (time.time(), code)


async def _answer_share_existing(
    query: InlineQuery,
    bot_username: str,
    raw: str,
) -> bool:
    """Handle @bot mc_CODE / bare CODE — share existing active cheque."""
    ch = db.get_cheque(raw)
    if not ch or ch.get("status") != "active":
        return False

    code = ch["code"]
    coin = ch["coin"]
    amount = float(ch["amount"])
    fiat = float(ch.get("amount_fiat") or coins.usd_for_amount(coin, amount))
    is_multi = (ch.get("cheque_type") or "personal") == "multi"
    result_id = f"sh_{code}"

    if is_multi:
        per = amount
        total_n = int(ch.get("activations_total") or 1)
        used = int(ch.get("activations_used") or 0)
        total = per * total_n
        total_fiat = coins.usd_for_amount(coin, total)
        title = f"Мульти-чек на {format_amount(total)} {coin}"
        desc = (
            f"Одна активация: {format_amount(per)} {coin} · "
            f"{format_amount(total)} {coin}\n"
            f"{used} / {total_n}"
        )
        caption = multi_share_html(ch, bot_username, premium=False)
        kb = cheque_claim_kb(
            bot_username, code, per, coin, start_payload=f"mc_{code}"
        )
        img = cheque_image_url(coin, total, total_fiat)
    else:
        title = f"Чек на {format_amount(amount)} {coin}"
        desc = f"{format_amount(amount)} {coin} (${format_usd(fiat)})"
        caption = cheque_message_html(
            bot_username,
            coin,
            amount,
            fiat,
            code=code,
            description=ch.get("description") or "",
            premium=False,
        )
        kb = cheque_claim_kb(bot_username, code, amount, coin, start_payload=f"cq_{code}")
        img = cheque_image_url(coin, amount, fiat)

    result = InlineQueryResultArticle(
        id=result_id,
        title=title,
        description=desc,
        thumbnail_url=coin_thumb_url(coin),
        thumbnail_width=128,
        thumbnail_height=128,
        input_message_content=InputTextMessageContent(
            message_text=caption,
            parse_mode="HTML",
            link_preview_options=preview_opts(img),
        ),
        reply_markup=kb,
    )
    _pending_results[result_id] = {
        "type": "share",
        "code": code,
        "multi": is_multi,
    }
    await query.answer(results=[result], cache_time=1, is_personal=True)
    return True


@router.inline_query()
async def on_inline_query(query: InlineQuery) -> None:
    user = query.from_user
    db.ensure_user(user.id, username=user.username, full_name=user.full_name)

    me = await query.bot.get_me()
    bot_username = me.username or "bot"
    raw = (query.query or "").strip()

    # Share existing cheque: mc_CODE or bare alphanumeric code
    if raw.startswith("mc_") or re.fullmatch(r"[A-Za-z0-9]{8,24}", raw):
        if await _answer_share_existing(query, bot_username, raw):
            return
        # unknown code — empty
        if raw.startswith("mc_") or not _parse_inline_query(raw):
            await query.answer(results=[], cache_time=1, is_personal=True)
            return

    parsed = _parse_inline_query(raw)
    if not parsed:
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    amount = parsed["amount"]
    coin = parsed["coin"]
    description = parsed["description"]
    fiat = coins.usd_for_amount(coin, amount)
    if coin in ("USDT", "USDC"):
        invoice_usd = round(amount, 2)
    else:
        invoice_usd = round(fiat, 2) if fiat > 0 else round(amount, 2)

    balance = db.get_balance(user.id, coin)
    can_send = balance + 1e-12 >= amount
    results: list = []

    if can_send:
        cq_key = f"cq:{user.id}:{coin}:{amount}:{description}"
        code = _cache_get(cq_key)
        cheque = db.get_cheque(code) if code else None
        if not cheque or cheque.get("status") != "active":
            code = None

        try:
            if not code:
                cheque = db.create_cheque(
                    creator_id=user.id,
                    coin=coin,
                    amount=amount,
                    amount_fiat=fiat,
                    description=description,
                    bot_username=bot_username,
                    debit=True,
                )
                code = cheque["code"]
                _cache_set(cq_key, code)
                balance_after = balance - amount
            else:
                balance_after = db.get_balance(user.id, coin)

            result_id = f"cq_{code}"
            img = cheque_image_url(coin, amount, fiat)
            caption = cheque_message_html(
                bot_username,
                coin,
                amount,
                fiat,
                code=code,
                description=description,
                premium=False,
            )
            kb = cheque_claim_kb(bot_username, code, amount, coin)
            bal_fiat = coins.usd_for_amount(coin, balance_after)
            results.append(
                InlineQueryResultArticle(
                    id=result_id,
                    title=f"Отправить {format_amount(amount)} {coin}",
                    description=(
                        f"Чек на {format_amount(amount)} {coin} (${format_usd(fiat)}).\n"
                        f"Ваш баланс: {format_amount(balance_after)} {coin} "
                        f"(${format_usd(bal_fiat)})"
                    ),
                    thumbnail_url=coin_thumb_url(coin),
                    thumbnail_width=128,
                    thumbnail_height=128,
                    input_message_content=InputTextMessageContent(
                        message_text=caption,
                        parse_mode="HTML",
                        link_preview_options=preview_opts(img),
                    ),
                    reply_markup=kb,
                )
            )
            _pending_results[result_id] = {
                "type": "cheque",
                "code": code,
                "coin": coin,
                "amount": amount,
                "fiat": fiat,
                "description": description,
            }
        except ValueError:
            can_send = False

    try:
        iv_key = f"iv:{user.id}:{invoice_usd}:{description}"
        inv_code = _cache_get(iv_key)
        inv = db.get_invoice(inv_code) if inv_code else None
        if not inv or inv.get("status") != "active":
            inv = db.create_invoice(
                creator_id=user.id,
                amount_usd=invoice_usd,
                comment=description,
                bot_username=bot_username,
            )
            inv_code = inv["code"]
            _cache_set(iv_key, inv_code)

        inv_result_id = f"iv_{inv_code}"
        img = invoice_image_url(invoice_usd)
        inv_caption = invoice_message_html(
            bot_username, inv_code, invoice_usd, premium=False
        )
        results.append(
            InlineQueryResultArticle(
                id=inv_result_id,
                title=f"Создать счёт • ${format_usd(invoice_usd)}",
                description=f"Счёт на ${format_usd(invoice_usd)}.",
                thumbnail_url=INVOICE_THUMB_URL,
                thumbnail_width=128,
                thumbnail_height=128,
                input_message_content=InputTextMessageContent(
                    message_text=inv_caption,
                    parse_mode="HTML",
                    link_preview_options=preview_opts(img),
                ),
                reply_markup=invoice_pay_kb(bot_username, inv_code),
            )
        )
        _pending_results[inv_result_id] = {
            "type": "invoice",
            "code": inv_code,
            "usd": invoice_usd,
        }
    except Exception as e:
        log.exception("invoice create failed: %s", e)

    if not results:
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    await query.answer(results=results, cache_time=1, is_personal=True)


@router.chosen_inline_result()
async def on_chosen_inline(result: ChosenInlineResult, bot: Bot) -> None:
    result_id = result.result_id
    inline_message_id = result.inline_message_id
    meta = _pending_results.pop(result_id, None)

    log.info(
        "chosen_inline_result id=%s inline_message_id=%s meta=%s",
        result_id,
        inline_message_id,
        meta,
    )

    if not inline_message_id:
        log.warning("no inline_message_id — enable Inline Feedback in BotFather")
        return

    me = await bot.get_me()
    bot_username = me.username or "bot"

    kind = None
    code = None
    if meta:
        kind = meta["type"]
        code = meta["code"]
    elif result_id.startswith("cq_"):
        kind, code = "cheque", result_id[3:]
    elif result_id.startswith("iv_"):
        kind, code = "invoice", result_id[3:]
    elif result_id.startswith("sh_"):
        kind, code = "share", result_id[3:]
    else:
        return

    if kind in {"cheque", "share"}:
        db.update_cheque(code, inline_message_id=inline_message_id)
        ch = db.get_cheque(code)
        if not ch:
            return
        coin = ch["coin"]
        amount = float(ch["amount"])
        fiat = float(ch.get("amount_fiat") or coins.usd_for_amount(coin, amount))
        is_multi = (ch.get("cheque_type") or "personal") == "multi"

        if is_multi:
            total = amount * int(ch.get("activations_total") or 1)
            total_fiat = coins.usd_for_amount(coin, total)
            img = cheque_image_url(coin, total, total_fiat)
            text = multi_share_html(ch, bot_username, premium=True)
            kb = cheque_claim_kb(
                bot_username, code, amount, coin, start_payload=f"mc_{code}"
            )
        else:
            img = cheque_image_url(coin, amount, fiat)
            text = cheque_message_html(
                bot_username,
                coin,
                amount,
                fiat,
                code=code,
                description=ch.get("description") or "",
                premium=True,
            )
            kb = cheque_claim_kb(bot_username, code, amount, coin)

        try:
            await bot.edit_message_text(
                text=text,
                inline_message_id=inline_message_id,
                parse_mode="HTML",
                reply_markup=kb,
                link_preview_options=preview_opts(img),
            )
        except Exception:
            log.exception("cheque/share premium edit FAILED %s", code)

        if kind == "cheque":
            await log_action(
                bot,
                BOT_LABEL,
                "Чек отправлен (inline)",
                user=result.from_user,
                lines=[
                    f"· Код: <code>{code}</code>",
                    f"· Сумма: <b>{format_amount(amount)} {coin}</b> (${format_usd(fiat)})",
                ],
                emoji_key="cheque",
                fallback="📥",
            )
        return

    if kind == "invoice":
        db.update_invoice(code, inline_message_id=inline_message_id)
        inv = db.get_invoice(code)
        if not inv:
            return
        usd = float(inv["amount_usd"])
        img = invoice_image_url(usd)
        text = invoice_message_html(bot_username, code, usd, premium=True)
        kb = invoice_pay_kb(bot_username, code)
        try:
            await bot.edit_message_text(
                text=text,
                inline_message_id=inline_message_id,
                parse_mode="HTML",
                reply_markup=kb,
                link_preview_options=preview_opts(img),
            )
        except Exception:
            log.exception("invoice premium edit FAILED %s", code)
        await log_action(
            bot,
            BOT_LABEL,
            "Счёт создан (inline)",
            user=result.from_user,
            lines=[
                f"· Код: <code>{code}</code>",
                f"· Сумма: <b>${format_usd(usd)}</b>",
            ],
            emoji_key="cheque",
            fallback="📥",
        )
        return
