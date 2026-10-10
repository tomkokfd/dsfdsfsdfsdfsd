"""Formatting helpers."""

from __future__ import annotations

from xrocket.config import EMOJI
from xrocket.data.coins import Coin, get_coin
from xrocket.services.prices import coin_price_usd


def tg_emoji(key: str, fallback: str) -> str:
    emoji_id = EMOJI.get(key)
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def format_amount(value: float, max_decimals: int = 6) -> str:
    if abs(value - round(value)) < 1e-12:
        return f"{int(round(value))}"
    return f"{value:.{max_decimals}f}".rstrip("0").rstrip(".")


def format_amount_nb(value: float, max_decimals: int = 6) -> str:
    """Format amount like original bot (1 or 57.523578)."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def format_fiat(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}.0"
    return f"{value:.2f}".rstrip("0").rstrip(".") if value % 1 else f"{value:.1f}"


def fiat_for_amount(coin_code: str, amount: float) -> float:
    coin = get_coin(coin_code)
    price = coin_price_usd(coin_code) if coin else 1.0
    return amount * price


def format_coin_line(coin: Coin, amount: float) -> str:
    price = coin_price_usd(coin.code)
    fiat = amount * price
    amount_s = format_amount_nb(amount)
    if coin.code in {"USDT", "USDC", "STBL"} or price == 1.0:
        fiat_s = f"{fiat:.1f}" if abs(fiat - round(fiat, 1)) < 1e-9 else f"{fiat:.2f}"
        return (
            f'🪙 <a href="{coin.url}">{coin.code}</a>: '
            f"{amount_s}\u00a0{coin.code} ({fiat_s}$)"
        )
    # Non-stable: show crypto only when zero-ish fiat omitted style from screenshots
    if amount == 0:
        return f'🪙 <a href="{coin.url}">{coin.code}</a>: 0\u00a0{coin.code}'
    fiat_s = f"{fiat:.2f}"
    return (
        f'🪙 <a href="{coin.url}">{coin.code}</a>: '
        f"{amount_s}\u00a0{coin.code} ({fiat_s}$)"
    )


def cheque_image_url(
    coin_code: str,
    amount: float,
    amount_fiat: float,
    activations: int | None = None,
) -> str:
    import time

    v = int(time.time() * 1000)
    url = (
        "https://image.api.xrocket.exchange/image/cheque"
        f"?coinCode={coin_code.upper()}"
        f"&amountCrypto={format_amount_nb(amount)}"
        f"&backgroundType=default&v={v}"
        f"&amountFiat={amount_fiat}"
        f"&fiatCode=usd"
    )
    if activations and activations > 1:
        url += f"&chequeActivations={activations}"
    return url


def money_pair(amount: float, coin_code: str, fiat: float) -> str:
    return f"{format_amount_nb(amount)}\u00a0{coin_code} ({format_fiat(fiat)}$)"


def user_mention_html(user_id: int, full_name: str) -> str:
    safe = (
        full_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<a href="tg://user?id={user_id}">{safe}</a>'
