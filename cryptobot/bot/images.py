"""Cheque / invoice card image URLs (imggen.cr.bot)."""

from __future__ import annotations

# API asset codes that differ from our wallet codes
_ASSET_ALIASES: dict[str, str] = {
    "GRAM": "TON",  # imggen has TON, not GRAM
}

# Inline-result thumbnails (small square icons)
_COIN_THUMBS: dict[str, str] = {
    "USDT": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/usdt.png",
    "USDC": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/usdc.png",
    "BTC": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/btc.png",
    "ETH": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/eth.png",
    "SOL": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/sol.png",
    "TRX": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/trx.png",
    "DOGE": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/doge.png",
    "LTC": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/ltc.png",
    "BNB": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/bnb.png",
    "TON": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/ton.png",
    "GRAM": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/ton.png",
    "XAUT": "https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/usdt.png",
}

INVOICE_THUMB_URL = "https://i.ibb.co/yFRbZ6Rz/image.png"
DEFAULT_COIN_THUMB = _COIN_THUMBS["USDT"]


def api_asset(coin: str) -> str:
    code = (coin or "USDT").upper()
    return _ASSET_ALIASES.get(code, code)


def _fmt_asset_amount(value: float) -> str:
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    # keep enough precision for small BTC etc.
    s = f"{value:.8f}".rstrip("0").rstrip(".")
    return s or "0"


def cheque_image_url(
    coin: str,
    amount: float,
    fiat: float,
    *,
    main: str = "asset",
) -> str:
    """
    https://imggen.cr.bot/checks/image
      ?asset=USDT&asset_amount=12&fiat=USD&fiat_amount=12.00&main=asset&v=5
    """
    asset = api_asset(coin)
    return (
        "https://imggen.cr.bot/checks/image"
        f"?asset={asset}"
        f"&asset_amount={_fmt_asset_amount(amount)}"
        f"&fiat=USD"
        f"&fiat_amount={float(fiat):.2f}"
        f"&main={main}"
        f"&v=5"
    )


def invoice_image_url(usd: float) -> str:
    """Invoice cards are always shown in USD / USDT style."""
    return cheque_image_url("USDT", float(usd), float(usd), main="asset")


def coin_thumb_url(coin: str) -> str:
    return _COIN_THUMBS.get((coin or "USDT").upper(), DEFAULT_COIN_THUMB)
