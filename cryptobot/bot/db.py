"""JSON database for Crypto Bot — users, cheques, invoices, admin extras."""

from __future__ import annotations

import json
import os
import secrets
import string
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from . import coins
from .config import ADMIN_ID, ADMIN_IDS, ADMIN_START_USDT, DB_PATH

_lock = threading.RLock()


def _default_db() -> dict[str, Any]:
    return {
        "users": {},
        "cheques": {},
        "invoices": {},
        "cheque_claims": {},
        "broadcasts": {},
        "tracking_links": {},
        "tracking_hits": {},
    }


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(_default_db())

    def _read(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = _default_db()
        for k in _default_db():
            data.setdefault(k, {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def _mutate(self, fn):
        with _lock:
            data = self._read()
            result = fn(data)
            self._write(data)
            return result

    def _view(self, fn):
        with _lock:
            return fn(self._read())

    @staticmethod
    def _gen_code(prefix: str = "", length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits
        return prefix + "".join(secrets.choice(alphabet) for _ in range(length))

    # ── users ──────────────────────────────────────────────

    def ensure_user(
        self,
        user_id: int | str,
        username: str | None = None,
        full_name: str | None = None,
    ) -> dict[str, Any]:
        uid = str(user_id)

        def op(data: dict[str, Any]):
            users = data["users"]
            if uid not in users:
                balances = coins.default_balances()
                if int(uid) in ADMIN_IDS:
                    balances["USDT"] = float(ADMIN_START_USDT)
                users[uid] = {
                    "username": username,
                    "full_name": full_name or "",
                    "created_at": time.time(),
                    "balances": balances,
                    "starts": 0,
                    "is_blocked": 0,
                    "bot_blocked": 0,
                    "block_notice_sent": 0,
                }
            else:
                u = users[uid]
                if username is not None:
                    u["username"] = username
                if full_name is not None:
                    u["full_name"] = full_name
                bal = u.setdefault("balances", coins.default_balances())
                for code in coins.all_codes():
                    bal.setdefault(code, 0.0)
                u.setdefault("is_blocked", 0)
                u.setdefault("bot_blocked", 0)
                u.setdefault("block_notice_sent", 0)
            return deepcopy(users[uid])

        return self._mutate(op)

    def get_user(self, user_id: int | str) -> Optional[dict[str, Any]]:
        uid = str(user_id)
        return self._view(lambda d: deepcopy(d["users"].get(uid)))

    def is_user_blocked(self, user_id: int | str) -> bool:
        u = self.get_user(user_id)
        return bool(u and int(u.get("is_blocked") or 0))

    def set_user_blocked(self, user_id: int | str, blocked: bool) -> None:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if not u:
                return
            u["is_blocked"] = 1 if blocked else 0
            if blocked:
                u["block_notice_sent"] = 0

        self._mutate(op)

    def set_bot_blocked(self, user_id: int | str, blocked: bool) -> None:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if u:
                u["bot_blocked"] = 1 if blocked else 0

        self._mutate(op)

    def set_block_notice_sent(self, user_id: int | str, sent: bool = True) -> None:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if u:
                u["block_notice_sent"] = 1 if sent else 0

        self._mutate(op)

    def bump_starts(self, user_id: int | str) -> int:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if not u:
                return 0
            u["starts"] = int(u.get("starts", 0)) + 1
            return u["starts"]

        return self._mutate(op)

    def get_balance(self, user_id: int | str, coin: str) -> float:
        uid = str(user_id)
        code = coin.upper()

        def op(data):
            u = data["users"].get(uid)
            if not u:
                return 0.0
            return float(u.get("balances", {}).get(code, 0.0))

        return self._view(op)

    def get_all_balances(self, user_id: int | str) -> dict[str, float]:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if not u:
                return coins.default_balances()
            return {c: float(u.get("balances", {}).get(c, 0.0)) for c in coins.all_codes()}

        return self._view(op)

    def change_balance(self, user_id: int | str, coin: str, delta: float) -> float:
        uid = str(user_id)
        code = coin.upper()

        def op(data):
            u = data["users"].get(uid)
            if not u:
                raise ValueError("user not found")
            bal = u.setdefault("balances", coins.default_balances())
            bal.setdefault(code, 0.0)
            new_val = float(bal[code]) + float(delta)
            if new_val < -1e-12:
                raise ValueError("insufficient balance")
            bal[code] = max(0.0, new_val)
            return float(bal[code])

        return self._mutate(op)

    def set_balance(self, user_id: int | str, coin: str, amount: float) -> float:
        uid = str(user_id)
        code = coin.upper()

        def op(data):
            u = data["users"].get(uid)
            if not u:
                raise ValueError("user not found")
            bal = u.setdefault("balances", coins.default_balances())
            bal[code] = float(amount)
            return float(bal[code])

        return self._mutate(op)

    def get_all_user_ids(self) -> list[int]:
        return self._view(lambda d: [int(uid) for uid in d["users"].keys()])

    def list_recent_users(self, limit: int = 12) -> list[dict[str, Any]]:
        def op(data):
            items = list(data["users"].items())
            items.sort(key=lambda x: float(x[1].get("created_at") or 0), reverse=True)
            out = []
            for uid, u in items[:limit]:
                row = deepcopy(u)
                row["user_id"] = int(uid)
                out.append(row)
            return out

        return self._view(op)

    def list_blocked_users(self) -> list[dict[str, Any]]:
        def op(data):
            out = []
            for uid, u in data["users"].items():
                if int(u.get("is_blocked") or 0):
                    row = deepcopy(u)
                    row["user_id"] = int(uid)
                    out.append(row)
            return out

        return self._view(op)

    def find_user_id_by_username(self, username: str) -> int | None:
        un = username.lstrip("@").lower()

        def op(data):
            for uid, u in data["users"].items():
                if (u.get("username") or "").lower() == un:
                    return int(uid)
            return None

        return self._view(op)

    def get_user_admin_card(self, user_id: int | str) -> dict[str, Any] | None:
        uid = str(user_id)

        def op(data):
            u = data["users"].get(uid)
            if not u:
                return None
            bals = u.get("balances") or {}
            usdt = float(bals.get("USDT", 0))
            cheques_n = sum(
                1
                for ch in data["cheques"].values()
                if int(ch.get("creator_id") or 0) == int(uid)
            )
            return {
                "user_id": int(uid),
                "username": u.get("username"),
                "full_name": u.get("full_name"),
                "created_at": u.get("created_at"),
                "starts": int(u.get("starts") or 0),
                "is_blocked": int(u.get("is_blocked") or 0),
                "bot_blocked": int(u.get("bot_blocked") or 0),
                "block_notice_sent": int(u.get("block_notice_sent") or 0),
                "usdt": usdt,
                "balances": {k: float(v) for k, v in bals.items()},
                "cheques": cheques_n,
            }

        return self._view(op)

    def list_top_usdt_balances(self, limit: int = 15) -> list[tuple[int, float, str | None]]:
        def op(data):
            rows = []
            for uid, u in data["users"].items():
                amt = float((u.get("balances") or {}).get("USDT", 0))
                rows.append((int(uid), amt, u.get("username")))
            rows.sort(key=lambda x: x[1], reverse=True)
            return rows[:limit]

        return self._view(op)

    def get_admin_stats(self) -> dict[str, Any]:
        now = time.time()
        day = 86400

        def op(data):
            users = data["users"]
            total = len(users)
            starts = sum(int(u.get("starts") or 0) for u in users.values())
            blocked = sum(1 for u in users.values() if int(u.get("is_blocked") or 0))
            bot_blocked = sum(1 for u in users.values() if int(u.get("bot_blocked") or 0))
            today = sum(1 for u in users.values() if now - float(u.get("created_at") or 0) < day)
            yesterday = sum(
                1
                for u in users.values()
                if day <= now - float(u.get("created_at") or 0) < 2 * day
            )
            week = sum(1 for u in users.values() if now - float(u.get("created_at") or 0) < 7 * day)
            month = sum(
                1 for u in users.values() if now - float(u.get("created_at") or 0) < 30 * day
            )
            cheques = list(data["cheques"].values())
            cheques_total = len(cheques)
            cheques_active = sum(1 for c in cheques if c.get("status") == "active")
            cheques_activated = sum(1 for c in cheques if c.get("status") == "activated")
            cheques_personal = sum(
                1 for c in cheques if (c.get("cheque_type") or "personal") == "personal"
            )
            cheques_multi = sum(1 for c in cheques if c.get("cheque_type") == "multi")
            claims = sum(
                len(v) for v in data.get("cheque_claims", {}).values() if isinstance(v, dict)
            )
            usdt_sum = sum(
                float((u.get("balances") or {}).get("USDT", 0)) for u in users.values()
            )
            invoices = list(data["invoices"].values())
            return {
                "total": total,
                "starts": starts,
                "blocked": blocked,
                "bot_blocked": bot_blocked,
                "today": today,
                "yesterday": yesterday,
                "week": week,
                "month": month,
                "cheques_total": cheques_total,
                "cheques_active": cheques_active,
                "cheques_activated": cheques_activated,
                "cheques_personal": cheques_personal,
                "cheques_multi": cheques_multi,
                "claims": claims,
                "usdt_sum": usdt_sum,
                "invoices_total": len(invoices),
                "invoices_active": sum(1 for i in invoices if i.get("status") == "active"),
                "invoices_paid": sum(1 for i in invoices if i.get("status") == "paid"),
            }

        return self._view(op)

    # ── cheques ────────────────────────────────────────────

    def create_cheque(
        self,
        creator_id: int | str,
        coin: str,
        amount: float,
        amount_fiat: float,
        description: str | None = None,
        bot_username: str | None = None,
        debit: bool = True,
        *,
        cheque_type: str = "personal",
        activations_total: int = 1,
        total_locked: float | None = None,
        bound_user_id: int | None = None,
        bound_username: str | None = None,
    ) -> dict[str, Any]:
        uid = str(creator_id)
        code = self._gen_code("", 12)
        coin = coin.upper()
        locked = float(total_locked if total_locked is not None else amount * activations_total)

        def op(data):
            nonlocal code
            while code in data["cheques"]:
                code = self._gen_code("", 12)

            if debit:
                u = data["users"].get(uid)
                if not u:
                    raise ValueError("user not found")
                bal = u.setdefault("balances", coins.default_balances())
                cur = float(bal.get(coin, 0.0))
                if cur + 1e-12 < locked:
                    raise ValueError("insufficient balance")
                bal[coin] = cur - locked

            cheque = {
                "code": code,
                "creator_id": int(uid),
                "coin": coin,
                "amount": float(amount),
                "amount_fiat": float(amount_fiat),
                "status": "active",
                "activator_id": None,
                "created_at": time.time(),
                "activated_at": None,
                "description": description or "",
                "inline_message_id": None,
                "bot_username": bot_username or "",
                "cheque_type": cheque_type,
                "activations_total": int(activations_total),
                "activations_used": 0,
                "bound_user_id": bound_user_id,
                "bound_username": bound_username,
                "notify_on": 1,
                "captcha_on": 1,
                "password": None,
                "total_locked": locked,
            }
            data["cheques"][code] = cheque
            return deepcopy(cheque)

        return self._mutate(op)

    def get_cheque(self, code: str) -> Optional[dict[str, Any]]:
        code = code.strip()
        for prefix in ("cq_", "t_", "mc_", "cheque_"):
            if code.startswith(prefix):
                code = code[len(prefix) :]
                break
        return self._view(lambda d: deepcopy(d["cheques"].get(code)))

    def list_cheques(self, creator_id: int | str | None = None) -> list[dict[str, Any]]:
        cid = str(creator_id) if creator_id is not None else None

        def op(data):
            items = []
            for ch in data["cheques"].values():
                if cid is None or str(ch.get("creator_id")) == cid:
                    items.append(deepcopy(ch))
            items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
            return items

        return self._view(op)

    def list_cheques_by_type(self, user_id: int | str, cheque_type: str) -> list[dict[str, Any]]:
        uid = int(user_id)

        def op(data):
            items = [
                deepcopy(ch)
                for ch in data["cheques"].values()
                if int(ch.get("creator_id") or 0) == uid
                and ch.get("status") == "active"
                and (ch.get("cheque_type") or "personal") == cheque_type
            ]
            items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
            return items

        return self._view(op)

    def list_active_cheques(self, user_id: int | str) -> list[dict[str, Any]]:
        uid = int(user_id)

        def op(data):
            return [
                deepcopy(ch)
                for ch in data["cheques"].values()
                if int(ch.get("creator_id") or 0) == uid and ch.get("status") == "active"
            ]

        return self._view(op)

    def count_active_cheques(
        self, user_id: int | str, cheque_type: str | None = None
    ) -> int:
        uid = int(user_id)

        def op(data):
            n = 0
            for ch in data["cheques"].values():
                if int(ch.get("creator_id") or 0) != uid:
                    continue
                if ch.get("status") != "active":
                    continue
                if cheque_type is not None and (ch.get("cheque_type") or "personal") != cheque_type:
                    continue
                n += 1
            return n

        return self._view(op)

    def list_recent_cheques(self, limit: int = 12) -> list[dict[str, Any]]:
        def op(data):
            items = [deepcopy(ch) for ch in data["cheques"].values()]
            items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
            return items[:limit]

        return self._view(op)

    def update_cheque(self, code: str, **fields) -> Optional[dict[str, Any]]:
        def op(data):
            ch = data["cheques"].get(code)
            if not ch:
                return None
            for k, v in fields.items():
                if k == "code":
                    continue
                ch[k] = v
            return deepcopy(ch)

        return self._mutate(op)

    def delete_cheque(self, code: str, refund: bool = True) -> Optional[dict[str, Any]]:
        def op(data):
            ch = data["cheques"].get(code)
            if not ch:
                return None
            out = deepcopy(ch)
            if refund and ch.get("status") == "active":
                per = float(ch["amount"])
                used = int(ch.get("activations_used") or 0)
                total_n = int(ch.get("activations_total") or 1)
                if (ch.get("cheque_type") or "personal") == "multi":
                    refund_amt = per * max(0, total_n - used)
                else:
                    refund_amt = per
                uid = str(ch["creator_id"])
                u = data["users"].get(uid)
                if u and refund_amt > 0:
                    bal = u.setdefault("balances", coins.default_balances())
                    coin = ch["coin"]
                    bal[coin] = float(bal.get(coin, 0.0)) + refund_amt
            del data["cheques"][code]
            data.get("cheque_claims", {}).pop(code, None)
            return out

        return self._mutate(op)

    def activate_cheque(self, code: str, activator_id: int | str) -> dict[str, Any]:
        aid = str(activator_id)
        code = code.strip()
        for prefix in ("cq_", "t_", "mc_", "cheque_"):
            if code.startswith(prefix):
                code = code[len(prefix) :]
                break

        def op(data):
            ch = data["cheques"].get(code)
            if not ch:
                raise ValueError("cheque not found")
            if ch.get("status") != "active":
                raise ValueError("already activated")

            if aid not in data["users"]:
                raise ValueError("user not found")

            # bound user check
            bound_id = ch.get("bound_user_id")
            bound_un = (ch.get("bound_username") or "").lstrip("@").lower()
            if bound_id and int(bound_id) != int(aid):
                raise ValueError("forbidden")
            if bound_un:
                act_un = (data["users"][aid].get("username") or "").lower()
                if act_un != bound_un and (not bound_id or int(bound_id) != int(aid)):
                    raise ValueError("forbidden")

            cheque_type = ch.get("cheque_type") or "personal"
            coin = ch["coin"]
            amount = float(ch["amount"])

            if cheque_type == "multi":
                claims = data.setdefault("cheque_claims", {}).setdefault(code, {})
                if aid in claims:
                    raise ValueError("already_claimed")
                used = int(ch.get("activations_used") or 0)
                total_n = int(ch.get("activations_total") or 1)
                if used >= total_n:
                    raise ValueError("already activated")
                claims[aid] = time.time()
                ch["activations_used"] = used + 1
                bal = data["users"][aid].setdefault("balances", coins.default_balances())
                bal[coin] = float(bal.get(coin, 0.0)) + amount
                if ch["activations_used"] >= total_n:
                    ch["status"] = "activated"
                    ch["activated_at"] = time.time()
                ch["activator_id"] = int(aid)
            else:
                bal = data["users"][aid].setdefault("balances", coins.default_balances())
                bal[coin] = float(bal.get(coin, 0.0)) + amount
                ch["status"] = "activated"
                ch["activator_id"] = int(aid)
                ch["activated_at"] = time.time()
                ch["activations_used"] = 1

            return deepcopy(ch)

        return self._mutate(op)

    # ── invoices ───────────────────────────────────────────

    def create_invoice(
        self,
        creator_id: int | str,
        amount_usd: float,
        comment: str | None = None,
        bot_username: str | None = None,
    ) -> dict[str, Any]:
        uid = str(creator_id)
        code = self._gen_code("IV", 10)

        def op(data):
            nonlocal code
            while code in data["invoices"]:
                code = self._gen_code("IV", 10)
            inv = {
                "code": code,
                "creator_id": int(uid),
                "amount_usd": float(amount_usd),
                "status": "active",
                "payer_id": None,
                "coin_paid": None,
                "amount_paid": None,
                "created_at": time.time(),
                "paid_at": None,
                "inline_message_id": None,
                "anonymous": False,
                "comment": comment or "",
                "bot_username": bot_username or "",
            }
            data["invoices"][code] = inv
            return deepcopy(inv)

        return self._mutate(op)

    def get_invoice(self, code: str) -> Optional[dict[str, Any]]:
        return self._view(lambda d: deepcopy(d["invoices"].get(code)))

    def list_invoices(self, creator_id: int | str | None = None) -> list[dict[str, Any]]:
        cid = str(creator_id) if creator_id is not None else None

        def op(data):
            items = []
            for inv in data["invoices"].values():
                if cid is None or str(inv.get("creator_id")) == cid:
                    items.append(deepcopy(inv))
            return items

        return self._view(op)

    def update_invoice(self, code: str, **fields) -> Optional[dict[str, Any]]:
        def op(data):
            inv = data["invoices"].get(code)
            if not inv:
                return None
            for k, v in fields.items():
                if k != "code":
                    inv[k] = v
            return deepcopy(inv)

        return self._mutate(op)

    def pay_invoice(
        self,
        code: str,
        payer_id: int | str,
        coin: str,
        amount_paid: float,
        anonymous: bool = False,
        comment: str | None = None,
    ) -> dict[str, Any]:
        pid = str(payer_id)
        coin = coin.upper()

        def op(data):
            inv = data["invoices"].get(code)
            if not inv:
                raise ValueError("invoice not found")
            if inv.get("status") != "active":
                raise ValueError("already paid")
            payer = data["users"].get(pid)
            if not payer:
                raise ValueError("payer not found")
            creator_id = str(inv["creator_id"])
            creator = data["users"].get(creator_id)
            if not creator:
                raise ValueError("creator not found")
            pbal = payer.setdefault("balances", coins.default_balances())
            cur = float(pbal.get(coin, 0.0))
            amt = float(amount_paid)
            if cur + 1e-12 < amt:
                raise ValueError("insufficient balance")
            pbal[coin] = cur - amt
            cbal = creator.setdefault("balances", coins.default_balances())
            cbal[coin] = float(cbal.get(coin, 0.0)) + amt
            inv["status"] = "paid"
            inv["payer_id"] = int(pid)
            inv["coin_paid"] = coin
            inv["amount_paid"] = amt
            inv["paid_at"] = time.time()
            inv["anonymous"] = bool(anonymous)
            if comment is not None:
                inv["comment"] = comment
            return deepcopy(inv)

        return self._mutate(op)

    # ── tracking links ─────────────────────────────────────

    def create_tracking_link(self, name: str) -> dict[str, Any]:
        slug = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

        def op(data):
            nonlocal slug
            while slug in data["tracking_links"]:
                slug = "".join(
                    secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8)
                )
            link = {
                "slug": slug,
                "name": name,
                "created_at": time.time(),
                "clicks": 0,
            }
            data["tracking_links"][slug] = link
            return deepcopy(link)

        return self._mutate(op)

    def list_tracking_links(self) -> list[dict[str, Any]]:
        def op(data):
            items = [deepcopy(v) for v in data["tracking_links"].values()]
            items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
            return items

        return self._view(op)

    def get_tracking_link(self, slug: str) -> Optional[dict[str, Any]]:
        return self._view(lambda d: deepcopy(d["tracking_links"].get(slug)))

    def delete_tracking_link(self, slug: str) -> None:
        def op(data):
            data["tracking_links"].pop(slug, None)
            data["tracking_hits"].pop(slug, None)

        self._mutate(op)

    def track_link_hit(self, slug: str, user_id: int | str) -> None:
        uid = str(user_id)

        def op(data):
            link = data["tracking_links"].get(slug)
            if not link:
                return
            hits = data.setdefault("tracking_hits", {}).setdefault(slug, {})
            if uid not in hits:
                hits[uid] = time.time()
                link["clicks"] = int(link.get("clicks") or 0) + 1

        self._mutate(op)

    # ── broadcasts ─────────────────────────────────────────

    def save_broadcast(self, payload: dict[str, Any]) -> str:
        bc_id = payload.get("id") or str(uuid.uuid4())[:8]

        def op(data):
            payload["id"] = bc_id
            data["broadcasts"][bc_id] = deepcopy(payload)
            return bc_id

        return self._mutate(op)

    def get_broadcast(self, bc_id: str) -> Optional[dict[str, Any]]:
        return self._view(lambda d: deepcopy(d["broadcasts"].get(bc_id)))

    def get_pending_broadcasts(self) -> list[dict[str, Any]]:
        def op(data):
            return [
                deepcopy(b)
                for b in data["broadcasts"].values()
                if b.get("status") == "scheduled"
            ]

        return self._view(op)

    def update_broadcast_status(self, bc_id: str, status: str, **extra) -> None:
        def op(data):
            b = data["broadcasts"].get(bc_id)
            if not b:
                return
            b["status"] = status
            b.update(extra)

        self._mutate(op)


db = Database()
