"""Journal-driven owner-confirmed cockpit gates for MyTradingBot R25C.

This module closes the reflection loop without giving the journal authority over
trading. It may detect patterns and create suggestions, but only an explicit
owner action can activate or deactivate a rule. Active rules are additive
cockpit blockers: they may only change ``orderable`` from true to false and can
never open, relax, or rewrite an existing engine gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

JOURNAL_PATTERN_GATE_RELEASE = "R25C-JOURNAL-PATTERN-GATES"
STATE_SCHEMA = 1
_LOCK = threading.RLock()

_ALLOWED_DIMENSIONS = {
    "relation_to_context": {
        "COUNTERTREND_HTF_REACTION", "WITH_TREND", "HTF_ZONE_REVERSAL",
        "RANGE_ROTATION", "BREAKOUT", "BREAKDOWN",
    },
    "trigger_type": {"local_reversal", "sweep_reclaim", "breakout_retest", "continuation"},
    "setup_type": {"reversal", "breakout", "continuation", "range_rotation", "compression"},
    "trade_type": {"scalp", "day", "swing"},
    "direction": {"long", "short"},
}
_DIMENSION_PRIORITY = {"relation_to_context": 0, "setup_type": 1, "trigger_type": 2, "trade_type": 3, "direction": 4}


def _utc_now(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return _utc_now(value).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return _utc_now(value)
    try:
        return _utc_now(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _empty() -> Dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA,
        "suggestions": {},
        "rules": {},
        "audit": [],
        "telegram_claims": {},
        "updated_at": None,
    }


def load_state(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(value, dict):
        return _empty()
    base = _empty()
    for key in ("suggestions", "rules", "telegram_claims"):
        if isinstance(value.get(key), dict):
            base[key] = value[key]
    if isinstance(value.get("audit"), list):
        base["audit"] = value["audit"][-2000:]
    base["updated_at"] = value.get("updated_at")
    return base


def save_state(path: Path, state: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["schema_version"] = STATE_SCHEMA
    payload["updated_at"] = _iso()
    payload["audit"] = list(payload.get("audit") or [])[-2000:]
    payload["telegram_claims"] = dict(list((payload.get("telegram_claims") or {}).items())[-5000:])
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _audit(state: Dict[str, Any], event: str, *, actor: str, reason: str, suggestion_id: str = "", rule_id: str = "", now: Optional[datetime] = None) -> None:
    state.setdefault("audit", []).append({
        "event": event,
        "at": _iso(now),
        "actor": _clean(actor, 80) or "system",
        "reason": _clean(reason, 800),
        "suggestion_id": _clean(suggestion_id, 120) or None,
        "rule_id": _clean(rule_id, 120) or None,
    })


def _trade_id(row: Dict[str, Any], index: int = 0) -> str:
    return _clean(row.get("_id") or row.get("id") or row.get("orderId") or row.get("raw_order_id") or f"row-{index}", 160)


def _eligible(row: Dict[str, Any]) -> bool:
    source = _clean(row.get("source_class"), 40).upper()
    return not (row.get("test_data") is True or row.get("performance_eligible") is False or source in {"PAPER", "TESTDATA"})


def _grade(row: Dict[str, Any], deepdive: Dict[str, Any]) -> str:
    # Pattern evidence is about post-trade process quality. An orderable ticket
    # can correctly have setup grade A while its executed process is graded B/C.
    # Prefer the deepdive/process grade; setup grade is only a migration fallback.
    value = _clean(
        deepdive.get("proces_grade") or row.get("proces_grade") or row.get("process_grade") or row.get("setup_grade"),
        4,
    ).upper()
    return value if value in {"A", "B", "C"} else ""


def _metadata(row: Dict[str, Any], deepdive: Dict[str, Any]) -> Dict[str, str]:
    text = " ".join(_clean(value, 1200).lower() for value in (
        row.get("process_judgement"), row.get("lesson"), deepdive.get("oordeel"),
        deepdive.get("wat_kan_beter"), deepdive.get("les"),
    ))
    relation = _clean(row.get("relation_to_context"), 60).upper()
    if relation not in _ALLOWED_DIMENSIONS["relation_to_context"]:
        if any(term in text for term in ("tegen trend", "tegen-trend", "countertrend", "counter-trend")):
            relation = "COUNTERTREND_HTF_REACTION"
        else:
            relation = ""
    values = {
        "relation_to_context": relation,
        "trigger_type": _clean(row.get("trigger_type"), 50).lower(),
        "setup_type": _clean(row.get("setup_type"), 50).lower(),
        "trade_type": _clean(row.get("trade_type"), 20).lower(),
        "direction": _clean(row.get("direction"), 12).lower(),
    }
    return {key: value for key, value in values.items() if value in _ALLOWED_DIMENSIONS[key]}


def _label(dimension: str, value: str, grade: str, english: bool = False) -> str:
    labels = {
        "relation_to_context": {
            "COUNTERTREND_HTF_REACTION": ("tegen-trendreacties", "counter-trend reactions"),
            "WITH_TREND": ("met-de-trend-setups", "with-trend setups"),
            "HTF_ZONE_REVERSAL": ("HTF-zone-omkeringen", "HTF-zone reversals"),
            "RANGE_ROTATION": ("rangerotaties", "range rotations"),
            "BREAKOUT": ("uitbraken", "breakouts"),
            "BREAKDOWN": ("neerwaartse uitbraken", "breakdowns"),
        },
        "trigger_type": {
            "local_reversal": ("lokale kantelingen", "local reversals"),
            "sweep_reclaim": ("sweep-en-reclaim-signalen", "sweep-and-reclaim signals"),
            "breakout_retest": ("uitbraak-hertests", "breakout retests"),
            "continuation": ("vervolgsignalen", "continuation signals"),
        },
        "setup_type": {
            "reversal": ("omkeer-setups", "reversal setups"),
            "breakout": ("uitbraak-setups", "breakout setups"),
            "continuation": ("vervolg-setups", "continuation setups"),
            "range_rotation": ("rangerotatie-setups", "range-rotation setups"),
            "compression": ("compressie-setups", "compression setups"),
        },
        "trade_type": {"scalp": ("scalps", "scalps"), "day": ("daytrades", "day trades"), "swing": ("swingtrades", "swing trades")},
        "direction": {"long": ("longs", "longs"), "short": ("shorts", "shorts")},
    }
    pair = labels.get(dimension, {}).get(value, (value.replace("_", " "), value.replace("_", " ")))
    core = pair[1] if english else pair[0]
    return f"{grade}-{core}" if grade else core


def _pattern_key(dimension: str, value: str, grade: str) -> str:
    return f"{dimension}:{value}|grade:{grade or '*'}"


def _rule_id(pattern_key: str, suggestion_id: str) -> str:
    return "rule-" + hashlib.sha256(f"{pattern_key}|{suggestion_id}".encode()).hexdigest()[:16]


def _suggestion_id(pattern_key: str, evidence_ids: Sequence[str]) -> str:
    fingerprint = pattern_key + "|" + "|".join(sorted(evidence_ids))
    return "suggestion-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


def detect_patterns(
    journal_rows: Iterable[Dict[str, Any]],
    deepdives: Iterable[Dict[str, Any]],
    *,
    min_repetitions: int = 4,
    min_loss_rate: float = 0.65,
) -> List[Dict[str, Any]]:
    """Pure read-only pattern detection. It never creates or activates rules."""
    minimum = max(3, min(20, int(min_repetitions or 4)))
    required_rate = max(0.5, min(1.0, float(min_loss_rate or 0.65)))
    dives = {_trade_id(row): row for row in deepdives if isinstance(row, dict)}
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for index, row in enumerate(journal_rows):
        if not isinstance(row, dict) or not _eligible(row):
            continue
        trade_id = _trade_id(row, index)
        dive = dives.get(trade_id, {})
        grade = _grade(row, dive)
        if grade not in {"B", "C"}:
            continue
        pnl = _finite(row.get("pnl") if row.get("pnl") is not None else row.get("closedPnl"))
        if pnl is None:
            continue
        metadata = _metadata(row, dive)
        for dimension, value in metadata.items():
            groups.setdefault((dimension, value, grade), []).append({
                "trade_id": trade_id,
                "symbol": _clean(row.get("symbol"), 32),
                "closed_at": _clean(row.get("closed_at") or row.get("time") or row.get("at"), 80),
                "pnl": round(pnl, 8),
                "grade": grade,
            })
    found: List[Dict[str, Any]] = []
    for (dimension, value, grade), rows in groups.items():
        losses = [row for row in rows if row["pnl"] < 0]
        loss_rate = len(losses) / len(rows) if rows else 0.0
        if len(losses) < minimum or loss_rate + 1e-12 < required_rate:
            continue
        evidence = losses[-12:]
        pattern_key = _pattern_key(dimension, value, grade)
        found.append({
            "pattern_key": pattern_key,
            "dimension": dimension,
            "value": value,
            "grade": grade,
            "sample_count": len(rows),
            "loss_count": len(losses),
            "loss_rate": round(loss_rate, 4),
            "evidence": evidence,
            "evidence_trade_ids": [row["trade_id"] for row in evidence],
            "label_nl": _label(dimension, value, grade, False),
            "label_en": _label(dimension, value, grade, True),
        })
    found.sort(key=lambda row: (-row["loss_count"], -row["loss_rate"], _DIMENSION_PRIORITY.get(row["dimension"], 99), row["pattern_key"]))
    # The same losing trades often carry several labels (relation, trigger,
    # trade type). Show the owner the most specific suggestion instead of five
    # differently worded copies of identical evidence.
    unique: List[Dict[str, Any]] = []
    evidence_sets: set[Tuple[str, ...]] = set()
    for row in found:
        fingerprint = tuple(sorted(row.get("evidence_trade_ids") or []))
        if fingerprint in evidence_sets:
            continue
        evidence_sets.add(fingerprint)
        unique.append(row)
    return unique[:5]


def refresh_suggestions(
    path: Path,
    journal_rows: Iterable[Dict[str, Any]],
    deepdives: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    min_repetitions: Optional[int] = None,
    min_loss_rate: Optional[float] = None,
    ttl_days: Optional[int] = None,
) -> Dict[str, Any]:
    current = _utc_now(now)
    minimum = int(min_repetitions or os.environ.get("MYTRADINGBOT_PATTERN_MIN_REPETITIONS", "4"))
    loss_rate = float(min_loss_rate or os.environ.get("MYTRADINGBOT_PATTERN_MIN_LOSS_RATE", "0.65"))
    ttl = max(1, min(90, int(ttl_days or os.environ.get("MYTRADINGBOT_PATTERN_SUGGESTION_TTL_DAYS", "14"))))
    detected = detect_patterns(journal_rows, deepdives, min_repetitions=minimum, min_loss_rate=loss_rate)
    created: List[Dict[str, Any]] = []
    with _LOCK:
        state = load_state(path)
        suggestions = state.setdefault("suggestions", {})
        rules = state.setdefault("rules", {})
        changed = False
        for suggestion in suggestions.values():
            if not isinstance(suggestion, dict) or suggestion.get("status") != "open":
                continue
            expires_at = _parse_time(suggestion.get("expires_at"))
            if expires_at and current >= expires_at:
                suggestion["status"] = "expired"
                suggestion["expired_at"] = _iso(current)
                _audit(state, "suggestion_expired", actor="system", reason="Suggestie verliep zonder regelwijziging", suggestion_id=str(suggestion.get("id") or ""), now=current)
                changed = True
        active_patterns = {
            str(rule.get("pattern_key"))
            for rule in rules.values()
            if isinstance(rule, dict) and rule.get("active") is True
        }
        open_patterns = {
            str(row.get("pattern_key"))
            for row in suggestions.values()
            if isinstance(row, dict) and row.get("status") == "open"
        }
        for pattern in detected:
            if pattern["pattern_key"] in active_patterns or pattern["pattern_key"] in open_patterns:
                continue
            suggestion_id = _suggestion_id(pattern["pattern_key"], pattern["evidence_trade_ids"])
            if suggestion_id in suggestions:
                continue
            proposed = {
                "rule_type": "block_exact_ticket_pattern",
                "criteria": {
                    "dimension": pattern["dimension"],
                    "value": pattern["value"],
                },
                "evidence_grade": pattern["grade"],
                "effect": "orderable_true_to_false_only",
            }
            item = {
                "id": suggestion_id,
                **pattern,
                "status": "open",
                "created_at": _iso(current),
                "expires_at": _iso(current + timedelta(days=ttl)),
                "proposed_rule": proposed,
                "message_nl": f"Je verloor {pattern['loss_count']} van {pattern['sample_count']} beoordeelde {pattern['label_nl']}. Tijdelijk blokkeren?",
                "message_en": f"You lost {pattern['loss_count']} of {pattern['sample_count']} reviewed {pattern['label_en']}. Block this pattern temporarily?",
            }
            suggestions[suggestion_id] = item
            _audit(state, "suggestion_created", actor="system", reason=item["message_nl"], suggestion_id=suggestion_id, now=current)
            created.append(dict(item))
            changed = True
        if changed:
            save_state(path, state)
        return {"created": created, "state": state}


def activate_suggestion(path: Path, suggestion_id: str, *, actor: str = "owner", now: Optional[datetime] = None) -> Dict[str, Any]:
    current = _utc_now(now)
    with _LOCK:
        state = load_state(path)
        suggestion = (state.get("suggestions") or {}).get(str(suggestion_id))
        if not isinstance(suggestion, dict):
            raise ValueError("Poortsuggestie niet gevonden")
        if suggestion.get("status") != "open":
            raise ValueError("Alleen een open suggestie kan worden geactiveerd")
        expires_at = _parse_time(suggestion.get("expires_at"))
        if expires_at and current >= expires_at:
            suggestion["status"] = "expired"
            suggestion["expired_at"] = _iso(current)
            _audit(state, "suggestion_expired", actor="system", reason="Activatie geweigerd: suggestie was verlopen", suggestion_id=suggestion_id, now=current)
            save_state(path, state)
            raise ValueError("Deze suggestie is verlopen en heeft geen regel gewijzigd")
        proposed = suggestion.get("proposed_rule") if isinstance(suggestion.get("proposed_rule"), dict) else {}
        if proposed.get("rule_type") != "block_exact_ticket_pattern" or proposed.get("effect") != "orderable_true_to_false_only":
            raise ValueError("Onveilige of onbekende regelsoort geweigerd")
        criteria = proposed.get("criteria") if isinstance(proposed.get("criteria"), dict) else {}
        dimension = str(criteria.get("dimension") or "")
        value = str(criteria.get("value") or "")
        evidence_grade = str(proposed.get("evidence_grade") or suggestion.get("grade") or "").upper()
        if value not in _ALLOWED_DIMENSIONS.get(dimension, set()) or evidence_grade not in {"B", "C"}:
            raise ValueError("Onveilige of onvolledige regelcriteria geweigerd")
        rule_id = _rule_id(str(suggestion.get("pattern_key") or ""), suggestion_id)
        if any(
            isinstance(rule, dict) and rule.get("active") and
            (rule.get("criteria") or {}).get("dimension") == dimension and
            (rule.get("criteria") or {}).get("value") == value
            for rule in (state.get("rules") or {}).values()
        ):
            raise ValueError("Voor dit ticketpatroon is al een actieve regel aanwezig")
        rule = {
            "id": rule_id,
            "active": True,
            "rule_type": "block_exact_ticket_pattern",
            "effect": "orderable_true_to_false_only",
            "pattern_key": suggestion.get("pattern_key"),
            "criteria": {"dimension": dimension, "value": value},
            "evidence_grade": evidence_grade,
            "reason": f"Op basis van jouw dagboek: {suggestion.get('loss_count')} verliezen op {suggestion.get('label_nl')}",
            "evidence_trade_ids": list(suggestion.get("evidence_trade_ids") or []),
            "source_suggestion_id": suggestion_id,
            "activated_at": _iso(current),
            "activated_by": _clean(actor, 80) or "owner",
            "deactivated_at": None,
            "deactivated_by": None,
            "deactivation_reason": None,
        }
        state.setdefault("rules", {})[rule_id] = rule
        suggestion["status"] = "activated"
        suggestion["activated_at"] = _iso(current)
        suggestion["rule_id"] = rule_id
        _audit(state, "rule_activated", actor=actor, reason=rule["reason"], suggestion_id=suggestion_id, rule_id=rule_id, now=current)
        save_state(path, state)
        return dict(rule)


def deactivate_rule(path: Path, rule_id: str, *, actor: str, reason: str, confirmed: bool, now: Optional[datetime] = None) -> Dict[str, Any]:
    if not confirmed:
        raise ValueError("Bevestiging ontbreekt; de regel blijft actief")
    clean_reason = _clean(reason, 800)
    if len(clean_reason) < 10:
        raise ValueError("Geef een zichtbare reden van minimaal 10 tekens")
    current = _utc_now(now)
    with _LOCK:
        state = load_state(path)
        rule = (state.get("rules") or {}).get(str(rule_id))
        if not isinstance(rule, dict):
            raise ValueError("Poortregel niet gevonden")
        if rule.get("active") is not True:
            raise ValueError("Deze regel is al uitgeschakeld")
        rule["active"] = False
        rule["deactivated_at"] = _iso(current)
        rule["deactivated_by"] = _clean(actor, 80) or "owner"
        rule["deactivation_reason"] = clean_reason
        _audit(state, "rule_deactivated", actor=actor, reason=clean_reason, suggestion_id=str(rule.get("source_suggestion_id") or ""), rule_id=rule_id, now=current)
        save_state(path, state)
        return dict(rule)


def _setup_value(setup: Dict[str, Any], dimension: str) -> str:
    if dimension == "setup_type":
        nested = setup.get("setup_15m") if isinstance(setup.get("setup_15m"), dict) else {}
        return _clean(setup.get("setup_type") or nested.get("type"), 50).lower()
    if dimension == "relation_to_context":
        return _clean(setup.get("relation_to_context"), 60).upper()
    if dimension in {"trigger_type", "trade_type", "direction"}:
        return _clean(setup.get(dimension), 50).lower()
    return ""


def match_rule(rule: Dict[str, Any], latest: Dict[str, Any]) -> bool:
    if not isinstance(rule, dict) or rule.get("active") is not True:
        return False
    if rule.get("rule_type") != "block_exact_ticket_pattern" or rule.get("effect") != "orderable_true_to_false_only":
        return False
    setup = latest.get("setup") if isinstance(latest.get("setup"), dict) else {}
    if not setup:
        return False
    criteria = rule.get("criteria") if isinstance(rule.get("criteria"), dict) else {}
    dimension = str(criteria.get("dimension") or "")
    expected = str(criteria.get("value") or "")
    actual = _setup_value(setup, dimension)
    return bool(actual == expected)


def apply_active_rules(latest: Dict[str, Any], rules: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply only additive blockers. Existing blocked gates are never opened."""
    matched = [dict(rule) for rule in rules if match_rule(rule, latest)]
    latest["journal_pattern_gate"] = {
        "release": JOURNAL_PATTERN_GATE_RELEASE,
        "matched_rules": matched,
        "matched_count": len(matched),
        "read_only_to_bybit": True,
        "effect": "orderable_true_to_false_only",
    }
    if not matched:
        return latest
    gate = latest.setdefault("execution_gate", {})
    gate.setdefault("additional_blockers", [])
    for rule in matched:
        blocker = {"source": JOURNAL_PATTERN_GATE_RELEASE, "rule_id": rule.get("id"), "reason": rule.get("reason")}
        if blocker not in gate["additional_blockers"]:
            gate["additional_blockers"].append(blocker)
    if gate.get("orderable") is True:
        gate["underlying_status"] = gate.get("status")
        gate["underlying_reason"] = gate.get("reason")
        gate.update(
            status="JOURNAL_PATTERN_BLOCK",
            label="DAGBOEKREGEL ACTIEF",
            orderable=False,
            reason=str(matched[0].get("reason") or "Een door jou geactiveerde dagboekregel houdt dit ticket dicht."),
        )
    return latest


def build_snapshot(
    path: Path,
    journal_rows: Iterable[Dict[str, Any]],
    deepdives: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    result = refresh_suggestions(path, journal_rows, deepdives, now=now)
    state = result["state"]
    suggestions = [dict(row) for row in (state.get("suggestions") or {}).values() if isinstance(row, dict)]
    rules = [dict(row) for row in (state.get("rules") or {}).values() if isinstance(row, dict)]
    suggestions.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    rules.sort(key=lambda row: str(row.get("activated_at") or ""), reverse=True)
    return {
        "release": JOURNAL_PATTERN_GATE_RELEASE,
        "suggestions": suggestions[:50],
        "open_suggestions": [row for row in suggestions if row.get("status") == "open"],
        "active_rules": [row for row in rules if row.get("active") is True],
        "inactive_rules": [row for row in rules if row.get("active") is not True],
        "audit": list(reversed(state.get("audit") or []))[:100],
        "minimum_repetitions": max(3, min(20, int(os.environ.get("MYTRADINGBOT_PATTERN_MIN_REPETITIONS", "4")))),
        "telegram_enabled": os.environ.get("MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM", "0") == "1",
        "owner_action_required": True,
        "rules_never_auto_activate": True,
        "suggestions_expire_rules_do_not": True,
        "read_only_to_bybit": True,
    }


def notify_created_suggestions(path: Path, suggestions: Sequence[Dict[str, Any]], sender: Callable[[str], bool]) -> int:
    """Notify only suggestions created in the current close-event call: no backlog."""
    if os.environ.get("MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM", "0") != "1":
        return 0
    sent = 0
    for suggestion in suggestions:
        suggestion_id = str(suggestion.get("id") or "")
        if not suggestion_id:
            continue
        with _LOCK:
            state = load_state(path)
            claims = state.setdefault("telegram_claims", {})
            if suggestion_id in claims:
                continue
            claims[suggestion_id] = {"claimed_at": _iso(), "status": "claimed"}
            save_state(path, state)
        message = (
            "🧭 Nieuwe dagboek-poortsuggestie\n"
            f"{suggestion.get('message_nl')}\n"
            f"Bewijs: {suggestion.get('loss_count')} verliezen in {suggestion.get('sample_count')} beoordeelde trades.\n"
            "Er is niets automatisch geactiveerd. Alleen jij kunt deze extra cockpitblokkade bewust aanzetten."
        )
        try:
            ok = bool(sender(message[:3900]))
        except Exception:
            ok = False
        with _LOCK:
            state = load_state(path)
            claim = state.setdefault("telegram_claims", {}).setdefault(suggestion_id, {})
            claim["status"] = "sent" if ok else "failed_without_retry"
            claim["finished_at"] = _iso()
            save_state(path, state)
        if ok:
            sent += 1
    return sent


def refresh_from_files_and_notify(state_path: Path, journal_path: Path, deepdives_path: Path, sender: Callable[[str], bool]) -> int:
    try:
        journal = json.loads(Path(journal_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        journal = []
    try:
        deepdives = json.loads(Path(deepdives_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        deepdives = []
    result = refresh_suggestions(state_path, journal if isinstance(journal, list) else [], deepdives if isinstance(deepdives, list) else [])
    return notify_created_suggestions(state_path, result.get("created") or [], sender)
