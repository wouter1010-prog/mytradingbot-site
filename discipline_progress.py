"""Process-first discipline score and daily streak for MyTradingBot R25A.

This module reads journal/process data and stores only explicit daily routine
marks. It never reads market prices, changes a trading gate, creates a setup,
or places an order.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DISCIPLINE_RELEASE = "R25A-PROCESS-FIRST"
STATE_SCHEMA = 1
DEFAULT_TIMEZONE = "Europe/Amsterdam"
GRADE_POINTS = {"A": 100.0, "B": 70.0, "C": 30.0}
_LOCK = threading.RLock()


def _tz(name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or DEFAULT_TIMEZONE))
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _aware_now(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _aware_now(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_datetime(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_now(parsed)


def _local_date(value: datetime, timezone_name: str) -> date:
    return _aware_now(value).astimezone(_tz(timezone_name)).date()


def empty_state() -> Dict[str, Any]:
    return {"schema_version": STATE_SCHEMA, "days": {}, "updated_at": None}


def load_state(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return empty_state()
    if not isinstance(value, dict):
        return empty_state()
    days = value.get("days") if isinstance(value.get("days"), dict) else {}
    clean_days: Dict[str, Dict[str, Any]] = {}
    for key, row in days.items():
        try:
            date.fromisoformat(str(key))
        except ValueError:
            continue
        if isinstance(row, dict):
            clean_days[str(key)] = {
                "day_start_completed_at": row.get("day_start_completed_at"),
                "no_trade_declared_at": row.get("no_trade_declared_at"),
            }
    return {"schema_version": STATE_SCHEMA, "days": clean_days, "updated_at": value.get("updated_at")}


def save_state(path: Path, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(value)
    payload["schema_version"] = STATE_SCHEMA
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _eligible_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_class = str(row.get("source_class") or "").upper()
        if row.get("test_data") is True or row.get("performance_eligible") is False or source_class in {"PAPER", "TESTDATA"}:
            continue
        result.append(dict(row))
    result.sort(key=_row_sort_key)
    return result


def _row_sort_key(row: Dict[str, Any]) -> Tuple[float, str]:
    milliseconds = row.get("updated_time_ms")
    try:
        if milliseconds not in (None, ""):
            return float(milliseconds), str(row.get("closed_at") or "")
    except (TypeError, ValueError):
        pass
    parsed = _parse_datetime(row.get("closed_at") or row.get("time") or row.get("at"))
    return (parsed.timestamp() * 1000 if parsed else 0.0, str(row.get("closed_at") or ""))


def _trade_dates(rows: Sequence[Dict[str, Any]], timezone_name: str) -> Set[date]:
    dates: Set[date] = set()
    for row in rows:
        for key in ("opened_at", "created_at", "closed_at", "time", "at", "updated_time_ms"):
            parsed = _parse_datetime(row.get(key))
            if parsed:
                dates.add(_local_date(parsed, timezone_name))
                break
    return dates


def _positions_open(positions: Sequence[Dict[str, Any]]) -> bool:
    for row in positions:
        if not isinstance(row, dict):
            continue
        value = row.get("size")
        try:
            if abs(float(value or 0)) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _completed_days(
    state: Dict[str, Any],
    trade_dates: Set[date],
    today: date,
    open_position_today: bool,
) -> Tuple[Set[date], Dict[str, Dict[str, bool]]]:
    completed: Set[date] = set()
    reasons: Dict[str, Dict[str, bool]] = {}
    for key, row in (state.get("days") or {}).items():
        try:
            day = date.fromisoformat(str(key))
        except ValueError:
            continue
        day_start = bool(row.get("day_start_completed_at"))
        no_trade = bool(row.get("no_trade_declared_at"))
        no_trade_valid = no_trade and day not in trade_dates and not (day == today and open_position_today)
        if day_start or no_trade_valid:
            completed.add(day)
        reasons[str(day)] = {"day_start": day_start, "no_trade": no_trade_valid, "no_trade_invalidated": no_trade and not no_trade_valid}
    return completed, reasons


def _consecutive_ending(completed: Set[date], end: date) -> int:
    count = 0
    cursor = end
    while cursor in completed:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _longest_streak(completed: Set[date]) -> int:
    if not completed:
        return 0
    longest = 0
    current = 0
    previous: Optional[date] = None
    for day in sorted(completed):
        current = current + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, current)
        previous = day
    return longest


def _grade_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    values = [GRADE_POINTS[str(row.get("process_grade") or "").upper()] for row in rows if str(row.get("process_grade") or "").upper() in GRADE_POINTS]
    if not values:
        return {"count": 0, "score": None, "trend": "insufficient", "recent_score": None, "previous_score": None, "delta": None}
    score = sum(values[-10:]) / len(values[-10:])
    recent = values[-5:]
    previous = values[-10:-5]
    if len(recent) >= 2 and len(previous) >= 2:
        recent_score = sum(recent) / len(recent)
        previous_score = sum(previous) / len(previous)
        delta = recent_score - previous_score
        trend = "improving" if delta >= 5 else "declining" if delta <= -5 else "stable"
    else:
        recent_score = sum(recent) / len(recent)
        previous_score = None
        delta = None
        trend = "insufficient"
    return {
        "count": len(values),
        "score": round(score, 1),
        "trend": trend,
        "recent_score": round(recent_score, 1),
        "previous_score": round(previous_score, 1) if previous_score is not None else None,
        "delta": round(delta, 1) if delta is not None else None,
    }


def _rules_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    values = [row.get("rules_followed") for row in rows if isinstance(row.get("rules_followed"), bool)]
    followed = sum(1 for value in values if value is True)
    return {
        "count": len(values),
        "followed": followed,
        "deviated": len(values) - followed,
        "pct": round(followed / len(values) * 100, 1) if values else None,
    }


def _routine_metrics(completed: Set[date], state: Dict[str, Any], today: date) -> Dict[str, Any]:
    parsed_days = []
    for key in (state.get("days") or {}):
        try:
            parsed_days.append(date.fromisoformat(str(key)))
        except ValueError:
            continue
    if not parsed_days:
        return {"observed_days": 0, "completed_days": 0, "pct": None}
    observed = min(14, max(1, (today - min(parsed_days)).days + 1))
    start = today - timedelta(days=observed - 1)
    count = sum(1 for day in completed if start <= day <= today)
    return {"observed_days": observed, "completed_days": count, "pct": round(count / observed * 100, 1)}


def _weighted_score(rules: Dict[str, Any], grades: Dict[str, Any], routine: Dict[str, Any]) -> Optional[int]:
    components = []
    if rules.get("pct") is not None:
        components.append((float(rules["pct"]), 0.45))
    if grades.get("score") is not None:
        components.append((float(grades["score"]), 0.35))
    if routine.get("pct") is not None:
        components.append((float(routine["pct"]), 0.20))
    if not components:
        return None
    total_weight = sum(weight for _, weight in components)
    return int(round(sum(value * weight for value, weight in components) / total_weight))


def _score_band(score: Optional[int]) -> str:
    if score is None:
        return "insufficient"
    if score >= 85:
        return "strong"
    if score >= 70:
        return "steady"
    if score >= 50:
        return "building"
    return "earn_back"


def record_day_start(path: Path, *, now: Optional[datetime] = None, timezone_name: str = DEFAULT_TIMEZONE) -> Dict[str, Any]:
    current = _aware_now(now)
    key = str(_local_date(current, timezone_name))
    with _LOCK:
        state = load_state(path)
        row = dict((state.get("days") or {}).get(key) or {})
        if not row.get("day_start_completed_at"):
            row["day_start_completed_at"] = _iso(current)
        row.setdefault("no_trade_declared_at", None)
        state.setdefault("days", {})[key] = row
        save_state(path, state)
    return row


def record_no_trade(
    path: Path,
    journal_rows: Sequence[Dict[str, Any]],
    open_positions: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    current = _aware_now(now)
    today = _local_date(current, timezone_name)
    rows = _eligible_rows(journal_rows)
    if _positions_open(open_positions):
        raise ValueError("Een bewuste kijkdag kan niet worden vastgelegd terwijl er een positie openstaat")
    if today in _trade_dates(rows, timezone_name):
        raise ValueError("Vandaag staat al handelsactiviteit in je dagboek; deze dag kan niet als no-trade worden vastgelegd")
    key = str(today)
    with _LOCK:
        state = load_state(path)
        row = dict((state.get("days") or {}).get(key) or {})
        row.setdefault("day_start_completed_at", None)
        if not row.get("no_trade_declared_at"):
            row["no_trade_declared_at"] = _iso(current)
        state.setdefault("days", {})[key] = row
        save_state(path, state)
    return row


def build_discipline_snapshot(
    path: Path,
    journal_rows: Sequence[Dict[str, Any]],
    open_positions: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> Dict[str, Any]:
    current = _aware_now(now)
    today = _local_date(current, timezone_name)
    state = load_state(path)
    rows = _eligible_rows(journal_rows)
    positions_open = _positions_open(open_positions)
    trade_dates = _trade_dates(rows, timezone_name)
    completed, reasons = _completed_days(state, trade_dates, today, positions_open)
    today_row = reasons.get(str(today), {"day_start": False, "no_trade": False, "no_trade_invalidated": False})
    today_complete = today in completed
    if today_complete:
        active_streak = _consecutive_ending(completed, today)
        streak_status = "earned_today"
    else:
        active_streak = _consecutive_ending(completed, today - timedelta(days=1))
        streak_status = "available_today" if active_streak > 0 else "earn_back" if completed else "start"
    rules = _rules_metrics(rows)
    grades = _grade_metrics(rows)
    routine = _routine_metrics(completed, state, today)
    score = _weighted_score(rules, grades, routine)
    no_trade_allowed = not positions_open and today not in trade_dates and not today_row.get("no_trade")
    return {
        "release": DISCIPLINE_RELEASE,
        "timezone": timezone_name,
        "local_date": str(today),
        "score": score,
        "score_band": _score_band(score),
        "rules": rules,
        "grades": grades,
        "routine": routine,
        "streak": {
            "current": active_streak,
            "longest": _longest_streak(completed),
            "today_complete": today_complete,
            "status": streak_status,
            "earned_by_day_start": bool(today_row.get("day_start")),
            "earned_by_no_trade": bool(today_row.get("no_trade")),
        },
        "today": {
            "day_start_completed": bool(today_row.get("day_start")),
            "no_trade_declared": bool(today_row.get("no_trade")),
            "no_trade_invalidated": bool(today_row.get("no_trade_invalidated")),
            "no_trade_allowed": no_trade_allowed,
            "trade_activity_present": today in trade_dates,
            "open_position": positions_open,
        },
        "sample": {
            "eligible_trades": len(rows),
            "rules_assessed": int(rules.get("count") or 0),
            "grades_assessed": int(grades.get("count") or 0),
            "routine_days_observed": int(routine.get("observed_days") or 0),
        },
        "updated_at": state.get("updated_at"),
        "read_only_to_trading_engine": True,
    }
