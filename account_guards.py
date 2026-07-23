"""One-way account discipline gates for MyTradingBot R25B.

This module is a cockpit-only guard layer. It reads persisted journal/account
state and may only make an existing ticket gate stricter. It never contacts an
exchange, changes an order, creates a setup, or relaxes a trading rule.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ACCOUNT_GUARD_RELEASE = "R25B-COMMITMENT-GUARDS"
STATE_SCHEMA = 1
DEFAULT_TIMEZONE = "Europe/Amsterdam"
_LOCK = threading.RLock()


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TIMEZONE))
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _now(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current


def _iso(value: datetime) -> str:
    return _now(value).astimezone(timezone.utc).isoformat()


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _now(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return _now(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _empty() -> Dict[str, Any]:
    return {"schema_version": STATE_SCHEMA, "days": {}, "r_breach_claims": {}, "updated_at": None}


def load_state(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(value, dict):
        return _empty()
    days = value.get("days") if isinstance(value.get("days"), dict) else {}
    claims = value.get("r_breach_claims") if isinstance(value.get("r_breach_claims"), dict) else {}
    return {"schema_version": STATE_SCHEMA, "days": days, "r_breach_claims": claims, "updated_at": value.get("updated_at")}


def save_state(path: Path, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(value)
    payload["schema_version"] = STATE_SCHEMA
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Keep only recent day-state and bounded alert claims.
    day_keys = sorted((payload.get("days") or {}).keys())[-90:]
    payload["days"] = {key: payload["days"][key] for key in day_keys}
    claim_items = sorted((payload.get("r_breach_claims") or {}).items(), key=lambda item: str((item[1] or {}).get("claimed_at") or ""))[-5000:]
    payload["r_breach_claims"] = dict(claim_items)
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def _today(now: datetime, timezone_name: str) -> date:
    return _now(now).astimezone(_tz(timezone_name)).date()


def _day_row(state: Dict[str, Any], day: date) -> Dict[str, Any]:
    days = state.setdefault("days", {})
    row = days.setdefault(day.isoformat(), {})
    return row if isinstance(row, dict) else {}


def activate_commitment(
    path: Path,
    *,
    equity: float,
    requested_loss_limit_pct: float,
    max_loss_limit_pct: float,
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    """Activate or tighten today's commitment; it can never be loosened."""
    equity_value = _finite(equity)
    requested = _finite(requested_loss_limit_pct)
    maximum = _finite(max_loss_limit_pct)
    if equity_value is None or equity_value <= 0:
        raise ValueError("Een verse positieve rekeningwaarde is nodig om Commitment Mode te activeren")
    if requested is None or requested <= 0:
        raise ValueError("De dagverlieslimiet moet positief zijn")
    if maximum is None or maximum <= 0:
        maximum = 2.0
    if requested > maximum + 1e-9:
        raise ValueError(f"De dagverlieslimiet mag niet hoger zijn dan {maximum:g}%")
    current = _now(now)
    day = _today(current, timezone_name)
    with _LOCK:
        state = load_state(path)
        row = _day_row(state, day)
        commitment = row.get("commitment") if isinstance(row.get("commitment"), dict) else {}
        if commitment.get("active"):
            existing = _finite(commitment.get("daily_loss_limit_pct")) or maximum
            if requested > existing + 1e-9:
                raise ValueError("Commitment Mode kan vandaag alleen strenger worden; een ruimere limiet is geblokkeerd")
            commitment["daily_loss_limit_pct"] = round(min(existing, requested), 4)
            commitment["tightened_at"] = _iso(current) if requested < existing - 1e-9 else commitment.get("tightened_at")
        else:
            commitment = {
                "active": True,
                "activated_at": _iso(current),
                "daily_loss_limit_pct": round(requested, 4),
                "baseline_equity": round(equity_value, 8),
                "max_positions": 1,
            }
        row["commitment"] = commitment
        row.setdefault("max_loss_used_usdt", 0.0)
        save_state(path, state)
        return dict(commitment)


def record_stop_out(
    path: Path,
    *,
    event_id: str,
    symbol: str,
    occurred_at: Optional[datetime] = None,
    cooldown_minutes: int = 30,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    """Record an observed stop-out. A later call can only extend the cooldown."""
    current = _now(occurred_at)
    day = _today(current, timezone_name)
    duration = max(1, min(24 * 60, int(cooldown_minutes or 30)))
    candidate_until = current + timedelta(minutes=duration)
    with _LOCK:
        state = load_state(path)
        row = _day_row(state, day)
        seen = {str(value) for value in (row.get("stop_out_ids") or [])}
        existing_until = _parse_time(row.get("cooldown_until"))
        is_new = not event_id or str(event_id) not in seen
        if event_id and is_new:
            seen.add(str(event_id))
            row["stop_out_ids"] = sorted(seen)[-5000:]
            row["last_stop_out"] = {"event_id": str(event_id), "symbol": str(symbol or "")[:32], "at": _iso(current)}
        # Duplicate execution IDs never restart or extend an earlier cooldown.
        if is_new and (existing_until is None or candidate_until > existing_until):
            row["cooldown_until"] = _iso(candidate_until)
        save_state(path, state)
        return {"cooldown_until": row.get("cooldown_until"), "new_event": bool(is_new)}


def claim_r_breach(path: Path, *, trade_id: str, r_multiple: float, occurred_at: Optional[datetime] = None) -> bool:
    """Claim an R<-1 outgoing alert before the network call; never backfill."""
    if not trade_id or (_finite(r_multiple) is None) or float(r_multiple) >= -1.0:
        return False
    with _LOCK:
        state = load_state(path)
        claims = state.setdefault("r_breach_claims", {})
        if str(trade_id) in claims:
            return False
        claims[str(trade_id)] = {"r_multiple": round(float(r_multiple), 4), "claimed_at": _iso(_now(occurred_at))}
        save_state(path, state)
        return True


def _eligible_trade(row: Dict[str, Any]) -> bool:
    source = str(row.get("source_class") or "").upper()
    return not (row.get("test_data") is True or row.get("performance_eligible") is False or source in {"PAPER", "TESTDATA"})


def _trade_local_date(row: Dict[str, Any], timezone_name: str) -> Optional[date]:
    for key in ("closed_at", "time", "at", "updated_time_ms"):
        parsed = _parse_time(row.get(key))
        if parsed:
            return parsed.astimezone(_tz(timezone_name)).date()
    return None


def _position_count(positions: Sequence[Dict[str, Any]]) -> int:
    count = 0
    for row in positions:
        if not isinstance(row, dict):
            continue
        size = _finite(row.get("size")) or 0.0
        if abs(size) > 0:
            count += 1
    return count


def build_account_guard_snapshot(
    path: Path,
    journal_rows: Iterable[Dict[str, Any]],
    positions: Sequence[Dict[str, Any]],
    equity: Optional[float],
    *,
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
    default_loss_limit_pct: float = 2.0,
    cooldown_minutes: int = 30,
    persist_peak: bool = True,
) -> Dict[str, Any]:
    current = _now(now)
    zone = _tz(timezone_name)
    local_day = current.astimezone(zone).date()
    next_reset = datetime.combine(local_day + timedelta(days=1), datetime.min.time(), zone)
    rows = [row for row in journal_rows if isinstance(row, dict) and _eligible_trade(row)]
    today_rows = [row for row in rows if _trade_local_date(row, timezone_name) == local_day]
    realized_net = sum(_finite(row.get("pnl")) or 0.0 for row in today_rows)
    open_pnl = sum(_finite(row.get("pnl")) or 0.0 for row in positions if isinstance(row, dict))
    current_loss = max(0.0, -(realized_net + min(0.0, open_pnl)))
    equity_value = _finite(equity)

    with _LOCK:
        state = load_state(path)
        row = _day_row(state, local_day)
        commitment = row.get("commitment") if isinstance(row.get("commitment"), dict) else {}
        active = bool(commitment.get("active"))
        baseline = _finite(commitment.get("baseline_equity")) if active else equity_value
        limit_pct = _finite(commitment.get("daily_loss_limit_pct")) if active else _finite(default_loss_limit_pct)
        if limit_pct is None or limit_pct <= 0: limit_pct = 2.0
        limit_usdt = baseline * limit_pct / 100.0 if baseline and baseline > 0 else None
        peak = max(_finite(row.get("max_loss_used_usdt")) or 0.0, current_loss)
        if active and persist_peak and peak > (_finite(row.get("max_loss_used_usdt")) or 0.0) + 1e-9:
            row["max_loss_used_usdt"] = round(peak, 8)
            save_state(path, state)
        used = peak if active else current_loss
        remaining = max(0.0, limit_usdt - used) if limit_usdt is not None else None
        remaining_ratio = max(0.0, min(100.0, remaining / limit_usdt * 100.0)) if remaining is not None and limit_usdt and limit_usdt > 0 else None
        cooldown_until = _parse_time(row.get("cooldown_until"))
        cooldown_active = bool(cooldown_until and cooldown_until > current)
        position_count = _position_count(positions)
        day_stop = bool(active and limit_usdt is not None and used >= limit_usdt - 1e-9)
        position_block = bool(active and position_count >= int(commitment.get("max_positions") or 1))
        cooldown_block = bool(active and cooldown_active)
        gate_status = "COMMITMENT_DAY_STOP" if day_stop else "COMMITMENT_MAX_POSITION" if position_block else "REVENGE_COOLDOWN" if cooldown_block else "COMMITMENT_ACTIVE" if active else "COMMITMENT_OFF"
        reason = (
            "De dagbuffer is opgebruikt. Commitment Mode houdt nieuwe tickets dicht tot de volgende Amsterdamse kalenderdag."
            if day_stop else
            "Er staat al één positie open. Commitment Mode laat vandaag geen tweede positie toe."
            if position_block else
            "Afkoelperiode na een stop-out. Wacht rustig tot de timer is verlopen voordat je opnieuw beoordeelt."
            if cooldown_block else
            "Commitment Mode is actief: dagstop en maximaal één positie zijn voor vandaag vergrendeld."
            if active else
            "Commitment Mode is uit. Activeer hem vrijwillig om de dagstop en maximaal één positie voor vandaag te vergrendelen."
        )
        return {
            "release": ACCOUNT_GUARD_RELEASE,
            "local_date": local_day.isoformat(),
            "timezone": timezone_name,
            "active": active,
            "one_way": True,
            "can_deactivate_today": False if active else None,
            "daily_loss_limit_pct": round(limit_pct, 4),
            "daily_loss_limit_usdt": round(limit_usdt, 2) if limit_usdt is not None else None,
            "buffer_remaining_usdt": round(remaining, 2) if remaining is not None else None,
            "buffer_remaining_pct": round(remaining_ratio, 1) if remaining_ratio is not None else None,
            "buffer_state": "empty" if day_stop else "low" if remaining_ratio is not None and remaining_ratio <= 35 else "healthy" if remaining_ratio is not None else "unknown",
            "positions_open": position_count,
            "max_positions": 1,
            "cooldown_active": cooldown_active,
            "cooldown_until": _iso(cooldown_until) if cooldown_until else None,
            "cooldown_seconds_remaining": max(0, int((cooldown_until - current).total_seconds())) if cooldown_active and cooldown_until else 0,
            "last_stop_out": row.get("last_stop_out") if isinstance(row.get("last_stop_out"), dict) else None,
            "day_stop": day_stop,
            "position_block": position_block,
            "ticket_blocked": bool(day_stop or position_block or cooldown_block),
            "gate_status": gate_status,
            "reason": reason,
            "next_reset_at": next_reset.astimezone(timezone.utc).isoformat(),
            "telegram_r_breach_enabled": os.environ.get("MYTRADINGBOT_ENABLE_R_BREACH_TELEGRAM", "0") == "1",
            "read_only_to_bybit": True,
        }
