from __future__ import annotations


def format_amount(value: float, max_decimals: int = 8) -> str:
    """Format like 4,296.8533 — comma thousands, dot decimal."""
    if value is None:
        value = 0.0
    value = float(value)

    if abs(value) >= 1000:
        decimals = min(4, max_decimals)
    elif abs(value) >= 1:
        decimals = min(4, max_decimals)
    elif abs(value) >= 0.01:
        decimals = min(6, max_decimals)
    else:
        decimals = max_decimals

    rounded = round(value, decimals)
    if rounded == int(rounded) and abs(rounded) < 1e12:
        # keep at least some decimals for crypto feel when fractional was intended
        text = f"{int(rounded):,}"
        return text

    fmt = f"{{:,.{decimals}f}}"
    text = fmt.format(rounded)
    if "." in text:
        whole, frac = text.split(".", 1)
        frac = frac.rstrip("0")
        if not frac:
            return whole
        return f"{whole}.{frac}"
    return text


def format_usd(value: float) -> str:
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def clickable_name(user_id: int, name: str) -> str:
    safe = (name or "User").replace("<", "").replace(">", "")
    return f'<b><a href="tg://user?id={int(user_id)}">\u2068{safe}\u2069</a></b>'
