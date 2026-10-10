"""JSON persistence for users, balances and cheques."""

from __future__ import annotations

import json
import os
import re
import secrets
import string
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from types import SimpleNamespace

from xrocket.config import ADMIN_IDS, ADMIN_START_USDT, DATA_DIR, INITIAL_BALANCE_USD
from xrocket.data.coins import all_coins

try:
    from xrocket.config import DB_JSON_PATH as _CFG_JSON_PATH
except ImportError:  # pragma: no cover
    _CFG_JSON_PATH = None

DB_JSON_PATH: Path = Path(_CFG_JSON_PATH) if _CFG_JSON_PATH is not None else (DATA_DIR / "bot.json")

_lock = threading.RLock()
_data: dict[str, Any] | None = None


def _empty_store() -> dict[str, Any]:
    return {
        "users": {},
        "balances": {},
        "trade_balances": {},
        "cheques": {},
        "cheque_claims": {},
        "tracking_links": {},
        "tracking_hits": {},
        "broadcasts": {},
    }


def _uid(user_id: int) -> str:
    return str(int(user_id))


def _json_path() -> Path:
    return Path(DB_JSON_PATH)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _is_empty_store(store: dict[str, Any]) -> bool:
    return all(not store.get(k) for k in _empty_store())


def _load_from_disk() -> dict[str, Any]:
    path = _json_path()
    if not path.exists() or path.stat().st_size == 0:
        return _empty_store()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    if not isinstance(raw, dict):
        return _empty_store()
    store = _empty_store()
    for key in store:
        val = raw.get(key)
        store[key] = val if isinstance(val, dict) else {}
    return store


def _save() -> None:
    assert _data is not None
    _atomic_write(_json_path(), _data)


def _store() -> dict[str, Any]:
    global _data
    if _data is None:
        _data = _load_from_disk()
    return _data


def _gen_code(length: int = 15) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _find_coin_key(balances: dict[str, Any], coin_code: str) -> str | None:
    if coin_code in balances:
        return coin_code
    upper = coin_code.upper()
    for key in balances:
        if str(key).upper() == upper:
            return str(key)
    return None


def _get_bal_amount(balances: dict[str, Any], coin_code: str) -> tuple[str, float]:
    key = _find_coin_key(balances, coin_code)
    if key is None:
        return coin_code, 0.0
    return key, float(balances.get(key) or 0.0)


def _set_bal_amount(balances: dict[str, Any], coin_code: str, amount: float) -> None:
    key = _find_coin_key(balances, coin_code) or coin_code
    balances[key] = float(amount)


def _user_copy(user: dict[str, Any]) -> dict[str, Any]:
    return dict(user)


def _cheque_copy(code: str, ch: dict[str, Any]) -> dict[str, Any]:
    out = dict(ch)
    out["code"] = code
    return out


def _normalize_cheque_code(code: str) -> str:
    code = code.strip()
    if code.startswith("mc_"):
        code = code[3:]
    if code.startswith("t_"):
        code = code[2:]
    return code


@contextmanager
def get_db() -> Iterator[SimpleNamespace]:
    """Optional compatibility context manager yielding the in-memory store."""
    with _lock:
        yield SimpleNamespace(data=_store(), save=_save)


def init_db() -> None:
    global _data
    with _lock:
        path = _json_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            _data = _load_from_disk()
        else:
            _data = _empty_store()
            _save()
        _ensure_admin_seed()


def _ensure_admin_seed() -> None:
    """Make sure admin accounts exist with ADMIN_START_USDT (does not reset if already higher)."""
    store = _store()
    changed = False
    for admin_id in ADMIN_IDS:
        key = _uid(admin_id)
        if key not in store["users"]:
            store["users"][key] = {
                "user_id": int(admin_id),
                "username": None,
                "full_name": "Admin",
                "created_at": time.time(),
                "display_mode": "all",
                "balance_view": "main",
                "is_blocked": 0,
                "starts_count": 0,
                "bot_blocked": 0,
                "block_notice_sent": 0,
            }
            bals = {coin.code: 0.0 for coin in all_coins()}
            bals["USDT"] = float(ADMIN_START_USDT)
            store["balances"][key] = bals
            store["trade_balances"][key] = {coin.code: 0.0 for coin in all_coins()}
            changed = True
        else:
            bals = store["balances"].setdefault(key, {})
            _, cur = _get_bal_amount(bals, "USDT")
            if cur + 1e-12 < float(ADMIN_START_USDT):
                _set_bal_amount(bals, "USDT", float(ADMIN_START_USDT))
                changed = True
            for coin in all_coins():
                if coin.code not in bals and not _find_coin_key(bals, coin.code):
                    bals[coin.code] = 0.0
                    changed = True
    if changed:
        _save()


def ensure_user(user_id: int, username: str | None, full_name: str) -> None:
    with _lock:
        store = _store()
        key = _uid(user_id)
        users = store["users"]
        if key in users:
            users[key]["username"] = username
            users[key]["full_name"] = full_name
            users[key]["user_id"] = int(user_id)
            _save()
            return

        users[key] = {
            "user_id": int(user_id),
            "username": username,
            "full_name": full_name,
            "created_at": time.time(),
            "display_mode": "all",
            "balance_view": "main",
            "is_blocked": 0,
            "starts_count": 0,
            "bot_blocked": 0,
            "block_notice_sent": 0,
        }
        bals: dict[str, float] = {}
        trade: dict[str, float] = {}
        for coin in all_coins():
            # New users start at 0; admin gets ADMIN_START_USDT in USDT only.
            if coin.code == "USDT" and int(user_id) in ADMIN_IDS:
                amount = float(ADMIN_START_USDT)
            elif coin.code == "USDT":
                amount = float(INITIAL_BALANCE_USD)
            else:
                amount = 0.0
            bals[coin.code] = amount
            trade[coin.code] = 0.0
        store["balances"][key] = bals
        store["trade_balances"][key] = trade
        _save()


def get_user(user_id: int) -> dict[str, Any] | None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        return _user_copy(user) if user else None


def get_user_settings(user_id: int) -> dict[str, str]:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if not user:
            return {"display_mode": "all", "balance_view": "main"}
        return {
            "display_mode": user.get("display_mode") or "all",
            "balance_view": user.get("balance_view") or "main",
        }


def set_display_mode(user_id: int, mode: str) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if user:
            user["display_mode"] = mode
            _save()


def set_balance_view(user_id: int, view: str) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if user:
            user["balance_view"] = view
            _save()


def get_balance(user_id: int, coin_code: str) -> float:
    with _lock:
        bals = _store()["balances"].get(_uid(user_id)) or {}
        _, amount = _get_bal_amount(bals, coin_code)
        return amount


def get_all_balances(user_id: int) -> dict[str, float]:
    with _lock:
        bals = _store()["balances"].get(_uid(user_id)) or {}
        return {str(k): float(v) for k, v in bals.items()}


def get_trade_balances(user_id: int) -> dict[str, float]:
    with _lock:
        bals = _store()["trade_balances"].get(_uid(user_id)) or {}
        return {str(k): float(v) for k, v in bals.items()}


def get_view_balances(user_id: int) -> dict[str, float]:
    settings = get_user_settings(user_id)
    main = get_all_balances(user_id)
    trade = get_trade_balances(user_id)
    view = settings["balance_view"]
    if view == "trade":
        return trade
    if view == "total":
        codes = set(main) | set(trade)
        return {c: main.get(c, 0.0) + trade.get(c, 0.0) for c in codes}
    return main


def set_balance(user_id: int, coin_code: str, amount: float) -> None:
    with _lock:
        store = _store()
        key = _uid(user_id)
        bals = store["balances"].setdefault(key, {})
        _set_bal_amount(bals, coin_code, amount)
        _save()


def change_balance(user_id: int, coin_code: str, delta: float) -> float:
    with _lock:
        store = _store()
        key = _uid(user_id)
        bals = store["balances"].setdefault(key, {})
        real_code, current = _get_bal_amount(bals, coin_code)
        new_amount = current + delta
        if new_amount < -1e-12:
            raise ValueError("insufficient_balance")
        new_amount = max(0.0, new_amount)
        bals[real_code] = new_amount
        _save()
        return new_amount


def create_cheque(
    creator_id: int,
    coin_code: str,
    amount: float,
    amount_fiat: float,
    *,
    cheque_type: str = "personal",
    activations_total: int = 1,
    total_locked: float | None = None,
    description: str | None = None,
    bound_user_id: int | None = None,
    bound_username: str | None = None,
) -> str:
    code = _gen_code(15)
    locked = total_locked if total_locked is not None else amount * activations_total
    with _lock:
        store = _store()
        cheques = store["cheques"]
        while code in cheques:
            code = _gen_code(15)
        cheques[code] = {
            "code": code,
            "creator_id": int(creator_id),
            "coin_code": coin_code,
            "amount": float(amount),
            "amount_fiat": float(amount_fiat),
            "status": "active",
            "activator_id": None,
            "created_at": time.time(),
            "activated_at": None,
            "cheque_type": cheque_type,
            "activations_total": int(activations_total),
            "activations_used": 0,
            "description": description,
            "bound_user_id": bound_user_id,
            "bound_username": bound_username,
            "password": None,
            "notify_on": 1,
            "captcha_on": 1,
            "total_locked": float(locked),
            "inline_message_id": None,
        }
        _save()
    return code


def find_reusable_cheque(
    creator_id: int,
    coin_code: str,
    amount: float,
    max_age_sec: float = 900.0,
) -> dict[str, Any] | None:
    with _lock:
        cutoff = time.time() - max_age_sec
        upper = coin_code.upper()
        matches: list[dict[str, Any]] = []
        for code, ch in _store()["cheques"].items():
            if int(ch.get("creator_id") or 0) != int(creator_id):
                continue
            if str(ch.get("coin_code") or "").upper() != upper:
                continue
            if ch.get("status") != "active":
                continue
            if (ch.get("cheque_type") or "personal") != "personal":
                continue
            if abs(float(ch.get("amount") or 0.0) - amount) >= 1e-9:
                continue
            if float(ch.get("created_at") or 0.0) < cutoff:
                continue
            # Already shared in a chat — never reuse (avoids "already activated" for next recipient)
            if ch.get("inline_message_id"):
                continue
            matches.append(_cheque_copy(code, ch))
        if not matches:
            return None
        matches.sort(key=lambda c: float(c.get("created_at") or 0.0), reverse=True)
        return matches[0]


def get_cheque(code: str) -> dict[str, Any] | None:
    code = _normalize_cheque_code(code)
    with _lock:
        ch = _store()["cheques"].get(code)
        return _cheque_copy(code, ch) if ch else None


def update_cheque(code: str, **fields: Any) -> None:
    if not fields:
        return
    with _lock:
        ch = _store()["cheques"].get(code)
        if not ch:
            return
        for k, v in fields.items():
            ch[k] = v
        _save()


def delete_cheque(code: str, refund: bool = True) -> dict[str, Any] | None:
    with _lock:
        store = _store()
        ch = store["cheques"].get(code)
        if not ch:
            return None
        out = _cheque_copy(code, ch)
        if refund and ch.get("status") == "active":
            used = int(ch.get("activations_used") or 0)
            total = int(ch.get("activations_total") or 1)
            remaining = total - used
            per = float(ch["amount"])
            refund_amt = per * remaining if ch.get("cheque_type") == "multi" else per
            if remaining > 0 and ch.get("status") == "active":
                creator_key = _uid(int(ch["creator_id"]))
                bals = store["balances"].setdefault(creator_key, {})
                real_code, current = _get_bal_amount(bals, str(ch["coin_code"]))
                bals[real_code] = current + refund_amt
        del store["cheques"][code]
        _save()
        return out


def count_active_cheques(user_id: int, cheque_type: str | None = None) -> int:
    with _lock:
        n = 0
        for ch in _store()["cheques"].values():
            if int(ch.get("creator_id") or 0) != int(user_id):
                continue
            if ch.get("status") != "active":
                continue
            if cheque_type is not None and (ch.get("cheque_type") or "personal") != cheque_type:
                continue
            n += 1
        return n


def list_active_cheques(user_id: int) -> list[dict[str, Any]]:
    with _lock:
        rows = [
            _cheque_copy(code, ch)
            for code, ch in _store()["cheques"].items()
            if int(ch.get("creator_id") or 0) == int(user_id) and ch.get("status") == "active"
        ]
        rows.sort(key=lambda c: float(c.get("created_at") or 0.0), reverse=True)
        return rows


def activate_cheque(
    code: str, activator_id: int, activator_username: str | None = None
) -> dict[str, Any]:
    """Activate personal or multi cheque."""
    code = _normalize_cheque_code(code)
    with _lock:
        store = _store()
        ch = store["cheques"].get(code)
        if not ch:
            raise ValueError("not_found")
        if ch.get("status") != "active":
            raise ValueError("already_used")

        cheque_type = ch.get("cheque_type") or "personal"
        creator_id = int(ch["creator_id"])

        # Creator cannot activate their own cheque (personal or multi)
        if activator_id == creator_id:
            raise ValueError("forbidden")

        if cheque_type == "multi":
            claims = store["cheque_claims"].setdefault(code, {})
            if _uid(activator_id) in claims or str(activator_id) in claims:
                raise ValueError("already_claimed")

        bound_id = ch.get("bound_user_id")
        bound_un = (ch.get("bound_username") or "").lstrip("@").lower()
        if bound_id and int(bound_id) != activator_id:
            raise ValueError("forbidden")
        if bound_un and not bound_id:
            if not activator_username or activator_username.lower() != bound_un:
                raise ValueError("forbidden")

        coin = ch["coin_code"]
        amount = float(ch["amount"])
        used = int(ch.get("activations_used") or 0)
        total = int(ch.get("activations_total") or 1)
        if used >= total:
            raise ValueError("already_used")

        act_key = _uid(activator_id)
        bals = store["balances"].setdefault(act_key, {})
        real_code, current = _get_bal_amount(bals, str(coin))
        bals[real_code] = current + amount

        if cheque_type == "multi":
            claims = store["cheque_claims"].setdefault(code, {})
            claims[_uid(activator_id)] = time.time()

        used += 1
        ch["activations_used"] = used
        if used >= total:
            ch["status"] = "activated"
            ch["activator_id"] = activator_id
            ch["activated_at"] = time.time()
        else:
            ch["status"] = "active"

        out = _cheque_copy(code, ch)
        out["activator_id"] = activator_id
        _save()
        return out


def list_cheques_by_type(user_id: int, cheque_type: str) -> list[dict[str, Any]]:
    with _lock:
        rows = [
            _cheque_copy(code, ch)
            for code, ch in _store()["cheques"].items()
            if int(ch.get("creator_id") or 0) == int(user_id)
            and ch.get("status") == "active"
            and (ch.get("cheque_type") or "personal") == cheque_type
        ]
        rows.sort(key=lambda c: float(c.get("created_at") or 0.0), reverse=True)
        return rows


def is_user_blocked(user_id: int) -> bool:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        return bool(user and user.get("is_blocked"))


def set_user_blocked(user_id: int, blocked: bool) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if not user:
            return
        user["is_blocked"] = 1 if blocked else 0
        user["block_notice_sent"] = 0
        _save()


def was_block_notice_sent(user_id: int) -> bool:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        return bool(user and user.get("block_notice_sent"))


def set_block_notice_sent(user_id: int, sent: bool = True) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if not user:
            return
        user["block_notice_sent"] = 1 if sent else 0
        _save()


def find_user_id_by_username(username: str) -> int | None:
    un = username.lstrip("@").lower()
    if not un:
        return None
    with _lock:
        for user in _store()["users"].values():
            u = (user.get("username") or "").lstrip("@").lower()
            if u == un:
                return int(user["user_id"])
        return None


def list_recent_users(limit: int = 15) -> list[dict[str, Any]]:
    with _lock:
        rows = []
        for user in _store()["users"].values():
            rows.append(
                {
                    "user_id": int(user["user_id"]),
                    "username": user.get("username"),
                    "full_name": user.get("full_name"),
                    "created_at": user.get("created_at"),
                    "starts_count": user.get("starts_count") or 0,
                    "is_blocked": int(user.get("is_blocked") or 0),
                    "bot_blocked": int(user.get("bot_blocked") or 0),
                }
            )
        rows.sort(key=lambda u: float(u.get("created_at") or 0.0), reverse=True)
        return rows[:limit]


def list_blocked_users(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        rows = []
        for user in _store()["users"].values():
            if int(user.get("is_blocked") or 0) != 1:
                continue
            rows.append(
                {
                    "user_id": int(user["user_id"]),
                    "username": user.get("username"),
                    "full_name": user.get("full_name"),
                    "created_at": user.get("created_at"),
                    "starts_count": user.get("starts_count") or 0,
                    "is_blocked": 1,
                    "bot_blocked": int(user.get("bot_blocked") or 0),
                }
            )
        rows.sort(key=lambda u: float(u.get("created_at") or 0.0), reverse=True)
        return rows[:limit]


def list_recent_cheques(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        rows = [
            _cheque_copy(code, ch) for code, ch in _store()["cheques"].items()
        ]
        rows.sort(key=lambda c: float(c.get("created_at") or 0.0), reverse=True)
        return rows[:limit]


def set_bot_blocked(user_id: int, blocked: bool = True) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if not user:
            return
        user["bot_blocked"] = 1 if blocked else 0
        _save()


def bump_starts(user_id: int) -> None:
    with _lock:
        user = _store()["users"].get(_uid(user_id))
        if not user:
            return
        user["starts_count"] = int(user.get("starts_count") or 0) + 1
        _save()


def get_all_user_ids(*, only_active: bool = True) -> list[int]:
    with _lock:
        out: list[int] = []
        for user in _store()["users"].values():
            if only_active:
                if int(user.get("is_blocked") or 0) != 0:
                    continue
                if int(user.get("bot_blocked") or 0) != 0:
                    continue
            out.append(int(user["user_id"]))
        return out


def get_admin_stats() -> dict[str, Any]:
    with _lock:
        store = _store()
        users = list(store["users"].values())
        cheques = list(store["cheques"].values())
        now = time.time()
        day_ago = now - 86400
        total = len(users)
        blocked = sum(1 for u in users if int(u.get("is_blocked") or 0) == 1)
        bot_blocked = sum(1 for u in users if int(u.get("bot_blocked") or 0) == 1)
        starts = sum(int(u.get("starts_count") or 0) for u in users)
        today = sum(1 for u in users if float(u.get("created_at") or 0) >= day_ago)
        yesterday = sum(
            1
            for u in users
            if now - 2 * 86400 <= float(u.get("created_at") or 0) < day_ago
        )
        week = sum(1 for u in users if float(u.get("created_at") or 0) >= now - 7 * 86400)
        month = sum(1 for u in users if float(u.get("created_at") or 0) >= now - 30 * 86400)
        cheques_total = len(cheques)
        cheques_active = sum(1 for c in cheques if c.get("status") == "active")
        cheques_personal = sum(1 for c in cheques if (c.get("cheque_type") or "personal") == "personal")
        cheques_multi = sum(1 for c in cheques if c.get("cheque_type") == "multi")
        activated = sum(1 for c in cheques if c.get("status") == "activated")
        claims = sum(len(v) for v in store["cheque_claims"].values() if isinstance(v, dict))
        usdt_sum = 0.0
        for bals in store["balances"].values():
            if not isinstance(bals, dict):
                continue
            _, amt = _get_bal_amount(bals, "USDT")
            usdt_sum += amt
        return {
            "total": int(total),
            "blocked": int(blocked),
            "bot_blocked": int(bot_blocked),
            "starts": int(starts),
            "today": int(today),
            "yesterday": int(yesterday),
            "week": int(week),
            "month": int(month),
            "cheques_total": int(cheques_total),
            "cheques_active": int(cheques_active),
            "cheques_personal": int(cheques_personal),
            "cheques_multi": int(cheques_multi),
            "cheques_activated": int(activated),
            "claims": int(claims),
            "usdt_sum": float(usdt_sum),
        }


def get_user_admin_card(user_id: int) -> dict[str, Any] | None:
    with _lock:
        store = _store()
        user = store["users"].get(_uid(user_id))
        if not user:
            return None
        data = _user_copy(user)
        bals = store["balances"].get(_uid(user_id)) or {}
        data["balances"] = {
            str(k): float(v) for k, v in bals.items() if float(v) > 0
        }
        data["cheques"] = sum(
            1
            for ch in store["cheques"].values()
            if int(ch.get("creator_id") or 0) == int(user_id)
        )
        return data


def list_top_usdt_balances(limit: int = 15) -> list[dict[str, Any]]:
    with _lock:
        rows: list[dict[str, Any]] = []
        for uid_key, bals in _store()["balances"].items():
            if not isinstance(bals, dict):
                continue
            _, amount = _get_bal_amount(bals, "USDT")
            if amount > 0:
                rows.append({"user_id": int(uid_key), "amount": float(amount)})
        rows.sort(key=lambda r: r["amount"], reverse=True)
        return rows[:limit]


def save_broadcast(bc: dict[str, Any]) -> None:
    with _lock:
        store = _store()
        store["broadcasts"][str(bc["id"])] = {
            "id": bc["id"],
            "from_chat_id": bc.get("from_chat_id"),
            "message_id": bc.get("message_id"),
            "run_at": bc.get("run_at"),
            "status": bc.get("status", "pending"),
            "button_text": bc.get("button_text"),
            "button_url": bc.get("button_url"),
            "admin_id": bc.get("admin_id"),
            "admin_chat_id": bc.get("admin_chat_id"),
            "created_at": bc.get("created_at"),
            "result": bc.get("result") or {},
        }
        _save()


def get_broadcast(bc_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _store()["broadcasts"].get(str(bc_id))
        if not row:
            return None
        d = dict(row)
        if "result" not in d:
            d["result"] = {}
        return d


def get_pending_broadcasts() -> list[dict[str, Any]]:
    with _lock:
        rows = []
        for row in _store()["broadcasts"].values():
            if row.get("status") == "pending" and row.get("run_at") is not None:
                rows.append(dict(row))
        return rows


def update_broadcast_status(
    bc_id: str,
    status: str,
    *,
    result: dict | None = None,
    run_at: str | None = None,
) -> None:
    with _lock:
        row = _store()["broadcasts"].get(str(bc_id))
        if not row:
            return
        row["status"] = status
        row["result"] = result or {}
        if run_at is not None:
            row["run_at"] = run_at
        _save()


def create_tracking_link(name: str, slug: str | None = None) -> dict[str, Any]:
    raw = slug or name
    s = re.sub(r"[^a-zA-Z0-9_-]+", "", raw.replace(" ", "_"))[:32] or _gen_code(8)
    with _lock:
        store = _store()
        links = store["tracking_links"]
        base = s
        i = 1
        while s in links:
            s = f"{base}{i}"[:32]
            i += 1
        links[s] = {
            "slug": s,
            "name": name,
            "created_at": time.time(),
            "clicks": 0,
        }
        _save()
        return {"slug": s, "name": name, "clicks": 0}


def list_tracking_links() -> list[dict[str, Any]]:
    with _lock:
        rows = [dict(v) for v in _store()["tracking_links"].values()]
        rows.sort(key=lambda r: float(r.get("created_at") or 0.0), reverse=True)
        return rows


def get_tracking_link(slug: str) -> dict[str, Any] | None:
    with _lock:
        store = _store()
        row = store["tracking_links"].get(slug)
        if not row:
            return None
        data = dict(row)
        hits = store["tracking_hits"].get(slug) or {}
        data["unique"] = len(hits) if isinstance(hits, dict) else 0
        return data


def delete_tracking_link(slug: str) -> None:
    with _lock:
        store = _store()
        store["tracking_hits"].pop(slug, None)
        store["tracking_links"].pop(slug, None)
        _save()


def track_link_hit(slug: str, user_id: int) -> bool:
    with _lock:
        store = _store()
        if slug not in store["tracking_links"]:
            return False
        hits = store["tracking_hits"].setdefault(slug, {})
        key = _uid(user_id)
        if key in hits:
            return False
        hits[key] = time.time()
        link = store["tracking_links"][slug]
        link["clicks"] = int(link.get("clicks") or 0) + 1
        _save()
        return True
