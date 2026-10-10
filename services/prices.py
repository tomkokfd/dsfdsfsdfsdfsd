"""Cached live USD prices for assets with verified CoinGecko IDs."""

from __future__ import annotations

import asyncio
import logging
import math

from aiohttp import ClientError, ClientSession, ClientTimeout

from xrocket.data.coins import get_coin

logger = logging.getLogger(__name__)

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "SOL": "solana",
    "TRX": "tron",
    "BNB": "binancecoin",
    "XAUT": "tether-gold",
    "NOT": "notcoin",
    "DOGS": "dogs-2",
    "STON": "ston",
    "TSTON": "tonstakers",
    "TRUMP": "official-trump",
    "CATI": "catizen",
    "MELANIA": "melania-meme",
}

_API_URL = "https://api.coingecko.com/api/v3/simple/price"
_REFRESH_INTERVAL = 300
_live_prices: dict[str, float] = {}


def coin_price_usd(code: str) -> float:
    coin = get_coin(code)
    if not coin:
        return 0.0
    return _live_prices.get(coin.code, coin.usd_price)


async def refresh_price_cache() -> int:
    params = {
        "ids": ",".join(COINGECKO_IDS.values()),
        "vs_currencies": "usd",
    }
    try:
        async with ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.get(_API_URL, params=params) as response:
                response.raise_for_status()
                payload = await response.json()
    except (ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("Could not refresh CoinGecko prices: %s", exc)
        return 0

    if not isinstance(payload, dict):
        logger.warning("CoinGecko returned an unexpected price response")
        return 0

    refreshed: dict[str, float] = {}
    for code, asset_id in COINGECKO_IDS.items():
        try:
            price = float(payload[asset_id]["usd"])
        except (KeyError, TypeError, ValueError):
            continue
        if price > 0 and math.isfinite(price):
            refreshed[code] = price

    _live_prices.update(refreshed)
    if refreshed:
        logger.info("Refreshed %d live coin prices", len(refreshed))
    return len(refreshed)


async def refresh_prices_forever() -> None:
    while True:
        await refresh_price_cache()
        await asyncio.sleep(_REFRESH_INTERVAL)