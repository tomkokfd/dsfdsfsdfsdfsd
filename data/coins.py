"""Supported coins and wallet pages for xRocket Fun Bot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Coin:
    code: str
    url: str
    usd_price: float = 1.0
    # Page 1 shows hyperlinks; later pages usually bold-only in original UI
    linked: bool = False


# Exact page order + emoji pairing from user dump (9 coins per page)
COIN_PAGES: list[list[Coin]] = [
    [
        Coin("USDT", "https://tether.to/", 1.0, True),
        Coin("XROCK", "https://t.me/xrocketnews", 0.01, True),
        Coin("USDC", "https://www.circle.com/usdc", 1.0, True),
        Coin("GRAM", "https://gram.org/", 0.01, True),
        Coin("SOL", "https://solana.com/", 150.0, True),
        Coin("ETH", "https://ethereum.org/", 2500.0, True),
        Coin("BTC", "https://bitcoin.org/", 65000.0, True),
        Coin("TRX", "https://tron.network/", 0.12, True),
        Coin("BNB", "https://www.bnbchain.org/", 600.0, True),
    ],
    [
        Coin("XAUT", "https://gold.tether.to/", 2500.0),
        Coin("JETTON", "https://t.me/jetton", 0.01),
        Coin("NOT", "https://t.me/notcoin", 0.01),
        Coin("TAKE", "https://t.me/TonTake", 0.01),
        Coin("EVAA", "https://evaa.finance/", 0.01),
        Coin("STBL", "https://t.me/stablemetal", 1.0),
        Coin("DFC", "https://definder.club/", 0.01),
        Coin("GRBS", "https://t.me/grabscape_ru", 0.01),
        Coin("WEB3", "https://t.me/web3ton", 0.01),
    ],
    [
        Coin("DOGS", "https://t.me/dogs_community", 0.001),
        Coin("STON", "https://ston.fi/", 0.01),
        Coin("GEMSTON", "https://t.me/stonfidex", 0.01),
        Coin("MRDN", "https://meridian.wtf/", 0.01),
        Coin("BOLT", "https://t.me/boltfoundation", 0.01),
        Coin("GRM", "https://t.me/gramcommunity", 0.01),
        Coin("STORM", "https://storm.tg/", 0.01),
        Coin("HYDRA", "https://t.me/Ton_HYDRA_Community", 0.01),
        Coin("DUST", "https://t.me/dedust", 0.01),
    ],
    [
        Coin("1MBABYDOGE", "https://babydoge.com/", 0.001),
        Coin("TNX", "https://tonex.app/", 0.01),
        Coin("TONNEL", "https://t.me/tonnel_en", 0.01),
        Coin("MAJOR", "https://t.me/major", 0.01),
        Coin("DHD", "https://t.me/CoinDHD", 0.01),
        Coin("WOOF", "https://t.me/lostdogscoeng", 0.01),
        Coin("PUNK", "https://t.me/punkton", 0.01),
        Coin("OPEN", "https://t.me/opensites", 0.01),
        Coin("TRUMP", "https://gettrumpmemes.com/", 0.01),
    ],
    [
        Coin("GRC", "https://t.me/grouche_coin", 0.01),
        Coin("ANON", "https://t.me/anon_club", 0.01),
        Coin("CATS", "https://t.me/toncats_tg", 0.01),
        Coin("KINGY", "https://ton.org.in/", 0.01),
        Coin("SP", "https://sp.one/", 0.01),
        Coin("PUMP", "https://pump.fun/", 0.01),
        Coin("RAFF", "https://tonraffles.org/", 0.01),
        Coin("ALENKA", "https://t.me/AlenkaOnTON", 0.01),
        Coin("BUILD", "https://t.me/join_community", 0.01),
    ],
    [
        Coin("FID", "https://t.me/fid_token/10", 0.01),
        Coin("CATI", "https://catizen.ai/", 0.01),
        Coin("MELANIA", "https://melaniameme.com/", 0.01),
        Coin("VIRUS", "https://t.me/epidemy", 0.01),
        Coin("TSTON", "https://tonstakers.com/", 5.0),
        Coin("DUREV", "https://poveldurev.net/", 0.01),
        Coin("GGT", "https://t.me/grabscape_ru", 0.01),
        Coin("STXP", "https://bemo.fi/", 0.01),
        Coin("AAPLX", "https://xstocks.com/", 1.0),
    ],
    [
        Coin("LIFEYT", "https://t.me/lifeyt", 0.01),
        Coin("JVT", "https://jvault.xyz/", 0.01),
        Coin("DRA", "http://t.me/dragons_ton", 0.01),
        Coin("CES", "https://swap.coffee/", 0.01),
        Coin("GOOGLX", "https://xstocks.com/", 1.0),
        Coin("FISH", "https://t.me/tonfish_tg", 0.01),
        Coin("AMZNX", "https://xstocks.com/", 1.0),
        Coin("NVDAX", "https://xstocks.com/", 1.0),
        Coin("VWS", "https://t.me/MagicVipClub", 0.01),
    ],
]


def all_coins() -> list[Coin]:
    return [coin for page in COIN_PAGES for coin in page]


def get_coin(code: str) -> Coin | None:
    code_up = code.upper().replace(" ", "")
    aliases = {
        "KFISH": "FISH",
        "TSTON": "TSTON",
        "STXP": "STXP",
        "BABYDOGE": "1MBABYDOGE",
    }
    code_up = aliases.get(code_up, code_up)
    for coin in all_coins():
        if coin.code.upper() == code_up:
            return coin
    return None


def resolve_coin_token(token: str) -> Coin | None:
    return get_coin(token)


COIN_CODES = {c.code.upper() for c in all_coins()}
COIN_CODES_BY_LEN = sorted(COIN_CODES, key=len, reverse=True)
