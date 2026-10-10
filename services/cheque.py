"""Cheque creation / activation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from xrocket.data.coins import COIN_CODES_BY_LEN, get_coin, resolve_coin_token
from xrocket.database import db
from xrocket.utils.formatters import (
    cheque_image_url,
    fiat_for_amount,
    format_amount_nb,
    format_fiat,
    money_pair,
    tg_emoji,
    user_mention_html,
)


@dataclass
class ParsedChequeQuery:
    coin_code: str
    amount: float
    description: str | None = None
    bound_username: str | None = None


_NUM = r"\d+(?:[.,]\d+)?"
_USER = r"[A-Za-z0-9_]{3,}"


def _canon_code(coin: object) -> str:
    return coin.code  # type: ignore[attr-defined]


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _parse_rest(rest: str) -> tuple[str | None, str | None]:
    """Из хвоста: опциональный @username и описание."""
    rest = (rest or "").strip()
    if not rest:
        return None, None

    m = re.match(rf"^@({_USER})(?:\s+(.*))?$", rest, re.DOTALL)
    if m:
        desc = (m.group(2) or "").strip() or None
        return m.group(1), desc[:1000] if desc else None

    return None, rest[:1000]


def parse_inline_query(text: str, default_coin: str = "USDT") -> ParsedChequeQuery | None:
    text = (text or "").strip()
    if not text:
        return None

    # Убрать ведущий @bot (для обработчика упоминаний)
    text = re.sub(r"^@\w+\s+", "", text, count=1).strip()
    if not text:
        return None

    # amount [coin] [rest]
    m = re.match(
        rf"^({_NUM})(?:\s+([A-Za-z][A-Za-z0-9]*))?(?:\s+(.*))?$",
        text,
        re.DOTALL,
    )
    if m:
        amount = float(m.group(1).replace(",", "."))
        maybe_coin = m.group(2)
        rest = (m.group(3) or "").strip()
        coin_code = default_coin
        if maybe_coin:
            coin = resolve_coin_token(maybe_coin)
            if coin:
                coin_code = _canon_code(coin)
            else:
                rest = f"{maybe_coin} {rest}".strip() if rest else maybe_coin
        bound_un, desc = _parse_rest(rest)
        return ParsedChequeQuery(
            coin_code=coin_code,
            amount=amount,
            description=desc,
            bound_username=bound_un,
        )

    # coin amount [rest]
    m = re.match(
        rf"^([A-Za-z][A-Za-z0-9]*)\s+({_NUM})(?:\s+(.*))?$",
        text,
        re.DOTALL,
    )
    if m:
        coin = resolve_coin_token(m.group(1))
        if coin:
            bound_un, desc = _parse_rest((m.group(3) or "").strip())
            return ParsedChequeQuery(
                coin_code=_canon_code(coin),
                amount=float(m.group(2).replace(",", ".")),
                description=desc,
                bound_username=bound_un,
            )

    # Компактные формы без описания: 150USDT / USDT150
    compact = text.replace(" ", "")
    m = re.fullmatch(rf"(?P<amount>{_NUM})(?P<coin>[A-Za-z][A-Za-z0-9]*)", compact)
    if m:
        coin = resolve_coin_token(m.group("coin"))
        if coin:
            return ParsedChequeQuery(
                coin_code=_canon_code(coin),
                amount=float(m.group("amount").replace(",", ".")),
            )

    upper = compact.upper()
    for code in COIN_CODES_BY_LEN:
        if upper.startswith(code):
            rest = compact[len(code):]
            if re.fullmatch(_NUM, rest):
                coin = get_coin(code)
                if coin:
                    return ParsedChequeQuery(
                        coin_code=_canon_code(coin),
                        amount=float(rest.replace(",", ".")),
                    )
        if upper.endswith(code):
            rest = compact[: -len(code)]
            if re.fullmatch(_NUM, rest):
                coin = get_coin(code)
                if coin:
                    return ParsedChequeQuery(
                        coin_code=_canon_code(coin),
                        amount=float(rest.replace(",", ".")),
                    )

    return None


def can_create(user_id: int, coin_code: str, amount: float) -> bool:
    if amount <= 0:
        return False

    if db.find_reusable_cheque(user_id, coin_code, amount):
        return True

    return db.get_balance(user_id, coin_code) + 1e-12 >= amount


def create_cheque_for_user(
    user_id: int,
    coin_code: str,
    amount: float,
    *,
    description: str | None = None,
    bound_user_id: int | None = None,
    bound_username: str | None = None,
) -> str:
    description = (description or "").strip() or None
    bound_username = (bound_username or "").lstrip("@").strip() or None

    existing = db.find_reusable_cheque(user_id, coin_code, amount)
    if existing:
        db.update_cheque(
            str(existing["code"]),
            description=description,
            bound_user_id=bound_user_id,
            bound_username=bound_username,
        )
        return str(existing["code"])

    if db.get_balance(user_id, coin_code) + 1e-12 < amount:
        raise ValueError("insufficient_balance")

    amount_fiat = fiat_for_amount(coin_code, amount)
    db.change_balance(user_id, coin_code, -amount)

    return db.create_cheque(
        user_id,
        coin_code,
        amount,
        amount_fiat,
        cheque_type="personal",
        description=description,
        bound_user_id=bound_user_id,
        bound_username=bound_username,
    )


def create_personal(
    user_id: int,
    coin_code: str,
    amount: float,
) -> str:
    if db.get_balance(user_id, coin_code) + 1e-12 < amount:
        raise ValueError("insufficient_balance")

    amount_fiat = fiat_for_amount(coin_code, amount)
    db.change_balance(user_id, coin_code, -amount)

    return db.create_cheque(
        user_id,
        coin_code,
        amount,
        amount_fiat,
        cheque_type="personal",
        activations_total=1,
    )


def create_multi(
    user_id: int,
    coin_code: str,
    per_amount: float,
    activations: int,
) -> str:
    total = per_amount * activations

    if db.get_balance(user_id, coin_code) + 1e-12 < total:
        raise ValueError("insufficient_balance")

    amount_fiat = fiat_for_amount(coin_code, total)
    db.change_balance(user_id, coin_code, -total)

    return db.create_cheque(
        user_id,
        coin_code,
        per_amount,
        amount_fiat,
        cheque_type="multi",
        activations_total=activations,
        total_locked=total,
    )


def cheque_message_html(
    coin_code: str,
    amount: float,
    amount_fiat: float | None = None,
    *,
    premium_rocket: bool = True,
    for_username: str | None = None,
    for_user_id: int | None = None,
    for_display_name: str | None = None,
    description: str | None = None,
) -> str:
    if amount_fiat is None:
        amount_fiat = fiat_for_amount(coin_code, amount)

    img = cheque_image_url(coin_code, amount, amount_fiat)
    amount_s = format_amount_nb(amount)
    fiat_s = format_fiat(amount_fiat)

    # Telegram Premium custom emoji
    rocket = '<tg-emoji emoji-id="5258332798409783582">🚀</tg-emoji>'

    text = (
        f'<a href="{img}">\u200d</a>'
        f'{rocket} <b>Чек</b> на '
        f'<b>{amount_s}\u00a0{coin_code} ({fiat_s}$)</b>'
    )

    un = (for_username or "").lstrip("@").strip()
    if un:
        text += f" для @{un}"
    elif for_user_id and for_display_name:
        text += f" для {user_mention_html(for_user_id, for_display_name)}"
    elif for_user_id:
        text += f' для <a href="tg://user?id={for_user_id}">пользователя</a>'

    desc = (description or "").strip()
    if desc:
        text += f"\n\n💬 {_escape_html(desc)}"

    return text


def multi_share_html(
    cheque: dict,
    *,
    premium_rocket: bool = True,
) -> str:
    coin = cheque["coin_code"]
    per = float(cheque["amount"])
    total_n = int(cheque["activations_total"])

    total_amt = per * total_n
    total_fiat = fiat_for_amount(coin, total_amt)
    per_fiat = fiat_for_amount(coin, per)

    img = cheque_image_url(
        coin,
        total_amt,
        total_fiat,
        activations=total_n,
    )

    # Telegram Premium custom emoji
    rocket = '<tg-emoji emoji-id="5258332798409783582">🚀</tg-emoji>'

    return (
        f'<a href="{img}">\u200d</a>'
        f'{rocket} <b>Мульти-чек на '
        f'{money_pair(total_amt, coin, total_fiat)}</b>\n\n'
        f'<b>Внутри чека:</b> {total_n} активация(й) по '
        f'{money_pair(per, coin, per_fiat)}'
    )


def activation_success_html(cheque: dict) -> str:
    coin = cheque["coin_code"]
    amount = float(cheque["amount"])
    fiat = fiat_for_amount(coin, amount)

    text = f"💰 Вы успешно получили <b>{money_pair(amount, coin, fiat)}</b>."

    desc = (cheque.get("description") or "").strip()
    if desc:
        text += f"\n\n💬 {_escape_html(desc)}"

    return text


def creator_notify_html(
    activator_id: int,
    activator_name: str,
    coin_code: str,
    amount: float,
    amount_fiat: float,
) -> str:
    mention = user_mention_html(activator_id, activator_name)

    return (
        f"{mention} активировал(а) ваш чек на "
        f"<b>{money_pair(amount, coin_code, amount_fiat)}</b>"
    )


def personal_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=t_{code}"


def multi_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=mc_{code}"


def warning_block() -> str:
    return (
        "‼️ <b>Никогда не делайте скриншот и не передавайте ссылку на чек людям, "
        "которым вы не доверяете.</b> Делая это, вы передаете средства в этом чеке "
        "безвозмездно, без гарантий получить что-то взамен. Мошенники могут "
        "использовать это, чтобы получить ваши монеты"
    )


def personal_manage_text(cheque: dict, bot_username: str) -> str:
    icon = tg_emoji("cheques", "🏷")
    coin = cheque["coin_code"]
    amount = float(cheque["amount"])
    fiat = fiat_for_amount(coin, amount)
    link = personal_link(bot_username, cheque["code"])

    lines = [
        f"{icon} <b>Персональный чек</b>",
        "",
        f"<b>Сумма чека</b>: {money_pair(amount, coin, fiat)}",
        "",
    ]

    if cheque.get("description"):
        lines += [f"<b>Описание:</b> {_escape_html(str(cheque['description']))}", ""]

    if cheque.get("bound_user_id") or cheque.get("bound_username"):
        who = cheque.get("bound_username") or str(cheque.get("bound_user_id"))

        if not str(who).startswith("@") and not str(who).isdigit():
            who = f"@{who}"
        elif cheque.get("bound_username") and not str(who).startswith("@"):
            who = f"@{who}"

        lines += [f"<b>Привязан к:</b> {who}", ""]

    lines += [
        warning_block(),
        "",
        "<b>Ссылка на чек</b>:",
        f"<tg-spoiler>{link}</tg-spoiler>",
    ]

    return "\n".join(lines)


def multi_manage_text(cheque: dict, bot_username: str) -> str:
    icon = tg_emoji("cheques", "🏷")
    coin = cheque["coin_code"]

    per = float(cheque["amount"])
    total_n = int(cheque["activations_total"])
    used = int(cheque.get("activations_used") or 0)

    total_amt = per * total_n
    total_fiat = fiat_for_amount(coin, total_amt)
    per_fiat = fiat_for_amount(coin, per)

    img = cheque_image_url(
        coin,
        total_amt,
        total_fiat,
        activations=total_n,
    )

    link = multi_link(bot_username, cheque["code"])

    notify = "вкл" if cheque.get("notify_on", 1) else "выкл"
    captcha = "вкл" if cheque.get("captcha_on", 1) else "выкл"

    return (
        f"{icon} <b>Мульти-чек</b>\n\n"
        f'<a href="{img}">\u200d</a>'
        f"<b>Сумма чека:</b> "
        f"<b>{money_pair(total_amt, coin, total_fiat)}</b>\n\n"
        f"<b>Внутри чека:</b> {total_n} активация(й) по "
        f"{money_pair(per, coin, per_fiat)}\n\n"
        f"Активировано: <b>{used} из {total_n}</b>\n"
        f"Выплачено наград: <b>0</b>\n\n"
        f"{warning_block()}\n"
        f"<b>Ссылка на чек:</b>\n"
        f"<tg-spoiler>{link}</tg-spoiler>"
    )