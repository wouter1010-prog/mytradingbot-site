"""Deterministic lifecycle controls for MyTradingBot v8.

Every position originates on the 3M execution layer. Break-even is only allowed after TP2 while the position is in profit. A position may later be managed
as a day- or swing-runner, but the original risk is locked and can never be increased
by a lifecycle promotion.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

STAGES = {"SCALP_ACTIVE", "DAY_RUNNER", "SWING_RUNNER", "CLOSED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: Any) -> bool:
    return bool(value)


def _fingerprint(setup: Dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "symbol": setup.get("symbol"),
            "direction": setup.get("direction"),
            "entry": setup.get("entry"),
            "stop": setup.get("stop_loss"),
            "origin": setup.get("origin_timeframe", "3M"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def create_record(setup: Dict[str, Any]) -> Dict[str, Any]:
    risk_pct = float(setup.get("initial_risk_pct", setup.get("risk_pct", 0)) or 0)
    return {
        "id": _fingerprint(setup),
        "symbol": setup.get("symbol"),
        "direction": setup.get("direction"),
        "entry": setup.get("entry"),
        "stop_loss": setup.get("stop_loss"),
        "take_profits": list(setup.get("take_profits") or []),
        "origin_timeframe": "3M",
        "stage": "SCALP_ACTIVE",
        "planned_horizon": str(setup.get("planned_horizon") or setup.get("trade_type") or "DAY").upper(),
        "initial_risk_pct": risk_pct,
        "current_risk_pct": risk_pct,
        "risk_locked": True,
        "stop_widened": False,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "history": [
            {
                "from": None,
                "to": "SCALP_ACTIVE",
                "at": utc_now(),
                "reason": "Trade is uitgevoerd vanuit de verplichte 3M-origin.",
            }
        ],
    }


def promotion_requirements(stage: str) -> List[str]:
    if stage == "SCALP_ACTIVE":
        return ["tp2_filled", "position_in_profit", "risk_reduced", "stop_not_widened", "structure_15m_intact", "htf_thesis_active"]
    if stage == "DAY_RUNNER":
        return ["runner_remaining", "stop_not_widened", "structure_4h_intact", "trend_1d_intact", "room_to_next_htf_zone"]
    return []


def evaluate(record: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    stage = str(record.get("stage") or "SCALP_ACTIVE").upper()
    if stage not in STAGES:
        stage = "SCALP_ACTIVE"
    target = "DAY_RUNNER" if stage == "SCALP_ACTIVE" else "SWING_RUNNER" if stage == "DAY_RUNNER" else None
    required = promotion_requirements(stage)
    missing = [key for key in required if not _bool(evidence.get(key))]
    eligible = bool(target and not missing and record.get("risk_locked", True) and not record.get("stop_widened", False))
    return {
        "eligible": eligible,
        "from": stage,
        "to": target,
        "required": required,
        "missing": missing,
        "risk_locked": bool(record.get("risk_locked", True)),
        "initial_risk_pct": record.get("initial_risk_pct"),
        "management_rule": "Stop pas na TP2 en alleen in winst naar break-even; nooit na TP1.",
        "message": (
            f"Promotie naar {target} is toegestaan zonder extra oorspronkelijk risico."
            if eligible
            else ("Geen volgende lifecyclefase beschikbaar." if not target else "Nog niet promoveren; mist: " + ", ".join(missing))
        ),
    }


def promote(record: Dict[str, Any], evidence: Dict[str, Any], *, confirmed_by_user: bool) -> Dict[str, Any]:
    result = evaluate(record, evidence)
    if not confirmed_by_user:
        raise ValueError("Lifecyclepromotie moet expliciet door de trader worden bevestigd")
    if not result["eligible"]:
        raise ValueError(result["message"])
    updated = copy.deepcopy(record)
    updated["stage"] = result["to"]
    updated["current_risk_pct"] = min(float(updated.get("current_risk_pct") or 0), float(updated.get("initial_risk_pct") or 0))
    updated["risk_locked"] = True
    updated["updated_at"] = utc_now()
    history = list(updated.get("history") or [])
    history.append({
        "from": result["from"],
        "to": result["to"],
        "at": utc_now(),
        "reason": result["message"],
        "evidence": {key: bool(evidence.get(key)) for key in result["required"]},
    })
    updated["history"] = history
    return updated


def close(record: Dict[str, Any], reason: str = "Positie gesloten") -> Dict[str, Any]:
    updated = copy.deepcopy(record)
    previous = str(updated.get("stage") or "SCALP_ACTIVE").upper()
    updated["stage"] = "CLOSED"
    updated["current_risk_pct"] = 0.0
    updated["updated_at"] = utc_now()
    history = list(updated.get("history") or [])
    history.append({"from": previous, "to": "CLOSED", "at": utc_now(), "reason": str(reason or "Positie gesloten")[:300]})
    updated["history"] = history
    return updated
