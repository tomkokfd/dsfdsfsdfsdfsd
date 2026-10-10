from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Coin:
    code: str
    name: str
    url: str
    emoji_id: str
    approx_usd_price: float
    fallback_emoji: str = "🪙"


COINS: list[Coin] = [
    Coin("USDT", "Tether", "https://tether.to/", "5406841020769936275", 0.999),
    Coin("GRAM", "Gram", "https://ton.org/", "5318901904686754959", 1.53),
    Coin("SOL", "Solana", "https://solana.com/", "5407016676342401484", 121.0),
    Coin("TRX", "TRON", "https://tron.network/", "5406978786140918829", 0.336),
    Coin("BTC", "Bitcoin", "https://bitcoin.org/", "5409133571233319295", 85000.0),
    Coin("ETH", "Ethereum", "https://ethereum.org/", "5406930321729948822", 2700.0),
    Coin("DOGE", "Dogecoin", "https://dogecoin.org/", "5406581441536495663", 0.0935),
    Coin("LTC", "Litecoin", "https://litecoin.org/", "5407128573125366746", 71.0),
    Coin("BNB", "Binance Coin", "https://binance.org/", "5406671889252781489", 788.0),
    Coin("USDC", "USD Coin", "https://www.centre.io/usdc", "5406575600380974539", 1.0),
    Coin("XAUT", "Tether Gold", "https://gold.tether.to/", "5407080001340215945", 2650.0),
]

_BY_CODE: dict[str, Coin] = {c.code.upper(): c for c in COINS}


def get_coin(code: str) -> Optional[Coin]:
    return _BY_CODE.get(code.upper())


def all_codes() -> list[str]:
    return [c.code for c in COINS]


def default_balances() -> dict[str, float]:
    return {c.code: 0.0 for c in COINS}


def amount_for_usd(coin: str, usd: float) -> float:
    c = get_coin(coin)
    if not c or c.approx_usd_price <= 0:
        return 0.0
    raw = usd / c.approx_usd_price
    if c.code in ("USDT", "USDC"):
        return round(raw * 1.000065, 6)
    # keep readable precision for other coins
    if raw >= 1:
        return round(raw, 4)
    if raw >= 0.01:
        return round(raw, 6)
    return round(raw, 8)


def usd_for_amount(coin: str, amt: float) -> float:
    c = get_coin(coin)
    if not c:
        return 0.0
    return amt * c.approx_usd_price


def coin_emoji_tag(coin: str) -> str:
    c = get_coin(coin)
    if not c:
        return "🪙"
    return f'<tg-emoji emoji-id="{c.emoji_id}">{c.fallback_emoji}</tg-emoji>'
