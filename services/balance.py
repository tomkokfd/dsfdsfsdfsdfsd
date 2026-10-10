"""Balance helpers and wallet text."""

from __future__ import annotations

from xrocket.data.coin_emojis import coin_tg_emoji
from xrocket.data.coins import COIN_PAGES, get_coin
from xrocket.database import db
from xrocket.services.prices import coin_price_usd
from xrocket.utils.formatters import format_amount_nb, tg_emoji


def total_usd(user_id: int, balances: dict[str, float] | None = None) -> float:
    if balances is None:
        balances = db.get_all_balances(user_id)
    total = 0.0
    for code, amount in balances.items():
        coin = get_coin(code)
        price = coin_price_usd(code) if coin else 0.0
        total += amount * price
    return total


def _format_amount_display(amount: float) -> str:
    if abs(amount - round(amount)) < 1e-9:
        return f"{int(round(amount)):,}".replace(",", " ")
    # Use comma as thousands? User example: 8,350.916667 — comma thousands, dot decimal
    s = f"{amount:,.6f}".rstrip("0").rstrip(".")
    return s


def wallet_text(user_id: int, page: int = 0) -> tuple[str, int]:
    pages = COIN_PAGES
    total_pages = len(pages)
    page = max(0, min(page, total_pages - 1))
    settings = db.get_user_settings(user_id)
    balances = db.get_view_balances(user_id)
    display_mode = settings["display_mode"]

    wallet_icon = tg_emoji("wallet", "👛")
    lines = [f"{wallet_icon} <b>Мой кошелёк</b>", ""]

    shown = 0
    for coin in pages[page]:
        amount = balances.get(coin.code, 0.0)
        usd = amount * coin_price_usd(coin.code)
        if display_mode == "hide_zero" and amount <= 0:
            continue
        if display_mode == "hide_lt1" and usd < 1.0:
            continue
        if shown:
            lines.append("")  # spacing between coins
        emoji = coin_tg_emoji(coin.code)
        amount_s = _format_amount_display(amount) if amount else "0"
        if coin.linked:
            name = f'<a href="{coin.url}"><b>{coin.code}</b></a>'
        else:
            name = f"<b>{coin.code}</b>"
        lines.append(f"{emoji} {name}: {amount_s} {coin.code}")
        shown += 1

    if shown == 0:
        lines.append("<i>Нет монет для отображения</i>")

    lines.extend(
        [
            "",
            'Чтобы настроить отображение, нажми на кнопку "Отображение балансов".',
        ]
    )
    return "\n".join(lines), total_pages


def balances_overview_text(user_id: int) -> str:
    main = total_usd(user_id, db.get_all_balances(user_id))
    trade = total_usd(user_id, db.get_trade_balances(user_id))
    overall = main + trade
    return (
        "<b>Отображение балансов</b>\n\n"
        f"💼 Общий баланс: {overall:.2f} $\n"
        f"👛 Основной баланс: {main:.2f} $\n"
        f"⚖️ Торговый баланс: {trade:.2f} $\n\n"
        "Выберите, какой баланс отображать в разделе <b>Мой кошелек</b>"
    )


def display_settings_text() -> str:
    icon = tg_emoji("wallet", "💼")
    return (
        f"{icon} <b>Отображение балансов</b>\n\n"
        "Выберите как отображать баланс Вашего кошелька:"
    )
