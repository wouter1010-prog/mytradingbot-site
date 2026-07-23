"""Deterministic multi-timeframe decision engine for MyTradingBot v8.

The engine treats TradingView drawings as the source of truth and stores each
chart timeframe independently.  The fixed workflow is:

    1D context -> 4H structure/location -> 15M setup -> 3M execution.

The 3M chart is deliberately used to detect the *first local turn* at a higher
-timeframe location.  A bullish 3M reversal after a bearish approach into HTF
support is therefore expected behaviour, not a timeframe conflict.  Likewise,
a bearish 3M reversal after a bullish approach into HTF resistance is valid.

Vision can suggest zones and a trigger, but only user-reviewed layers can feed
this module.  The module never clicks or sends an order.
"""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = "8.2.2"
SCHEMA_VERSION = 86
PRIMARY_TIMEFRAMES: Tuple[str, ...] = ("1D", "4H", "15M", "3M")
REVIEW_VALID_HOURS: Dict[str, float] = {"1D": 96.0, "4H": 36.0, "15M": 12.0, "3M": 2.0}
LAYER_PURPOSE: Dict[str, str] = {
    "1D": "CONTEXT",
    "4H": "STRUCTURE",
    "15M": "SETUP",
    "3M": "EXECUTION",
}
TRIGGER_TYPES = {
    "none",
    "local_reversal",
    "sweep_reclaim",
    "breakout_retest",
    "continuation",
}
TRIGGER_DIRECTIONS = {"long", "short", "unknown"}
SETUP_TYPES = {"none", "reversal", "breakout", "continuation", "range_rotation", "compression"}
TREND_VALUES = {"up", "down", "range", "unknown"}
ZONE_STATES = {"active", "watching", "invalidated"}
ZONE_INTENTS = {"structure", "entry", "target", "range_boundary"}
LIFECYCLE_STAGES = ("SCALP_ORIGIN", "DAY_RUNNER", "SWING_RUNNER", "CLOSED")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def integer(value: Any, default: int = 0, minimum: int = 0, maximum: int = 999) -> int:
    try:
        out = int(round(float(value)))
    except (TypeError, ValueError):
        out = default
    return max(minimum, min(maximum, out))


def text(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def normalize_asset(value: Any) -> str:
    raw = text(value, 80).upper()
    if ":" in raw:
        raw = raw.rsplit(":", 1)[-1]
    raw = raw.replace(".P", "").replace("PERPETUAL", "").replace("PERP", "")
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    for suffix in ("USDT", "USDC", "BUSD", "USD", "EUR", "BTC"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw[:12] or "BTC"


def normalize_timeframe(value: Any) -> str:
    raw = text(value, 24).upper().replace(" ", "")
    aliases = {
        "D": "1D", "DAY": "1D", "DAILY": "1D", "1440": "1D",
        "240": "4H", "4HR": "4H", "4HOUR": "4H",
        "15": "15M", "15MIN": "15M", "15MINUTE": "15M",
        "3": "3M", "3MIN": "3M", "3MINUTE": "3M",
    }
    if raw in aliases:
        return aliases[raw]
    match = re.fullmatch(r"(\d+)(S|M|H|D|W|MO)", raw)
    if match:
        return f"{int(match.group(1))}{match.group(2)}"
    if raw.isdigit():
        minutes = int(raw)
        if minutes == 1440:
            return "1D"
        if minutes % 60 == 0 and minutes >= 60:
            return f"{minutes // 60}H"
        return f"{minutes}M"
    return raw[:12] or "UNKNOWN"


def layer_purpose(timeframe: Any) -> str:
    return LAYER_PURPOSE.get(normalize_timeframe(timeframe), "AUXILIARY")


def normalize_trend(value: Any) -> str:
    raw = text(value, 40).lower()
    aliases = {
        "uptrend": "up", "bullish": "up", "bull": "up",
        "downtrend": "down", "bearish": "down", "bear": "down",
        "sideways": "range", "ranging": "range", "neutral": "range",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in TREND_VALUES else "unknown"


def normalize_trade_type(value: Any) -> str:
    raw = text(value, 30).lower()
    if raw in {"scalp", "scalping"}:
        return "scalp"
    if raw in {"swing", "swingtrade", "swing_trade"}:
        return "swing"
    return "day"


def normalize_setup(raw: Any, *, timeframe: Any = "15M", strict: bool = False) -> Dict[str, Any]:
    """Normalize the local 15M setup without treating it as an execution trigger."""
    item = raw if isinstance(raw, dict) else {}
    setup_type = text(item.get("type"), 40).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "local_reversal": "reversal",
        "sweep_reclaim": "reversal",
        "breakout_retest": "breakout",
        "breakdown": "breakout",
        "pullback": "continuation",
        "range": "range_rotation",
    }
    setup_type = aliases.get(setup_type, setup_type)
    if setup_type not in SETUP_TYPES:
        setup_type = "none"

    direction = text(item.get("direction"), 20).lower()
    direction = {"buy": "long", "bullish": "long", "sell": "short", "bearish": "short"}.get(direction, direction)
    if direction not in TRIGGER_DIRECTIONS:
        direction = "unknown"

    detected = bool(item.get("detected")) or setup_type != "none"
    confirmed = bool(item.get("confirmed"))
    reviewed = bool(item.get("reviewed", confirmed))
    confidence = integer(item.get("confidence"), 0, 0, 100)
    evidence = text(item.get("evidence") or item.get("reason"), 700)

    if not detected:
        setup_type = "none"
        direction = "unknown"

    if strict and normalize_timeframe(timeframe) == "15M" and detected:
        if setup_type == "none":
            raise ValueError("15M-setup heeft geen geldig type")
        if direction not in {"long", "short"}:
            raise ValueError("15M-setuprichting moet long of short zijn")
        if not confirmed or not reviewed:
            raise ValueError("Bevestig expliciet dat de 15M-setup is gecontroleerd")
        if not evidence:
            raise ValueError("Beschrijf kort welke lokale 15M-structuur zichtbaar is")

    return {
        "detected": detected,
        "confirmed": confirmed,
        "reviewed": reviewed,
        "type": setup_type,
        "direction": direction,
        "confidence": confidence,
        "evidence": evidence,
    }


def normalize_trigger(raw: Any, *, timeframe: Any = "3M", strict: bool = False) -> Dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    trigger_type = text(item.get("type"), 40).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "reversal": "local_reversal",
        "trend_reversal": "local_reversal",
        "kanteling": "local_reversal",
        "sweep": "sweep_reclaim",
        "reclaim": "sweep_reclaim",
        "breakout": "breakout_retest",
        "breakdown": "breakout_retest",
        "breakout_and_retest": "breakout_retest",
        "pullback": "continuation",
    }
    trigger_type = aliases.get(trigger_type, trigger_type)
    if trigger_type not in TRIGGER_TYPES:
        trigger_type = "none"

    direction = text(item.get("direction"), 20).lower()
    direction = {"buy": "long", "bullish": "long", "sell": "short", "bearish": "short"}.get(direction, direction)
    if direction not in TRIGGER_DIRECTIONS:
        direction = "unknown"

    detected = bool(item.get("detected")) or trigger_type != "none"
    confirmed = bool(item.get("confirmed"))
    reviewed = bool(item.get("reviewed", confirmed))
    local_before = normalize_trend(item.get("local_trend_before") or item.get("trend_before"))
    approach = normalize_trend(item.get("approach_direction"))
    confidence = integer(item.get("confidence"), 0, 0, 100)
    evidence = text(item.get("evidence") or item.get("reason"), 700)

    price = finite(item.get("price") or item.get("trigger_price"))
    break_level = finite(item.get("break_level"))
    retest_level = finite(item.get("retest_level"))
    sweep_level = finite(item.get("sweep_level"))
    ticket_requested = bool(item.get("ticket_requested"))
    entry_zone_id = text(item.get("entry_zone_id"), 80) or None
    stop_loss = finite(item.get("stop_loss") or item.get("ticket_stop"))
    if stop_loss is not None and stop_loss <= 0:
        stop_loss = None

    flags = item.get("evidence_flags") if isinstance(item.get("evidence_flags"), dict) else {}
    # V6 uses short, chart-facing evidence names.  Legacy v5.1 names are
    # accepted during migration so a deploy never silently loses a review.
    normalized_flags = {
        "zone_reaction": bool(flags.get("zone_reaction") or flags.get("zone_reaction_confirmed") or item.get("zone_reaction")),
        "sweep": bool(flags.get("sweep") or flags.get("sweep_confirmed") or item.get("sweep_confirmed")),
        "reclaim": bool(flags.get("reclaim") or flags.get("reclaim_confirmed") or item.get("reclaim_confirmed")),
        "structure_break": bool(flags.get("structure_break") or flags.get("structure_break_confirmed") or item.get("structure_break_confirmed")),
        "close": bool(flags.get("close") or flags.get("close_confirmed") or item.get("close_confirmed")),
        "retest": bool(flags.get("retest") or flags.get("retest_confirmed") or item.get("retest_confirmed")),
        "pullback": bool(flags.get("pullback") or flags.get("pullback_confirmed") or item.get("pullback_confirmed")),
        "momentum_resume": bool(flags.get("momentum_resume") or flags.get("momentum_shift") or flags.get("continuation_confirmed") or item.get("momentum_shift")),
    }

    if not detected:
        trigger_type = "none"
        direction = "unknown"

    if strict and normalize_timeframe(timeframe) == "3M" and detected:
        if trigger_type == "none":
            raise ValueError("3M-trigger heeft geen geldig type")
        if direction not in {"long", "short"}:
            raise ValueError("3M-triggerrichting moet long of short zijn")
        if not confirmed or not reviewed:
            raise ValueError("Bevestig expliciet dat de 3M-trigger op de chart is gecontroleerd")
        if not evidence:
            raise ValueError("Beschrijf kort wat de 3M-kanteling, sweep of breakout bevestigt")
        if price is None or price <= 0:
            raise ValueError("3M-triggerprijs ontbreekt")
        if ticket_requested:
            if not entry_zone_id:
                raise ValueError("Kies de concrete instapzone voor dit ticket")
            if stop_loss is None:
                raise ValueError("Vul één technische stop in voor dit concrete ticket")
            if direction == "long" and stop_loss >= price:
                raise ValueError("Bij een long moet de technische stop onder de signaalprijs liggen")
            if direction == "short" and stop_loss <= price:
                raise ValueError("Bij een short moet de technische stop boven de signaalprijs liggen")

    return {
        "detected": detected,
        "confirmed": confirmed,
        "reviewed": reviewed,
        "type": trigger_type,
        "direction": direction,
        "local_trend_before": local_before,
        "approach_direction": approach,
        "price": round(price, 8) if price and price > 0 else None,
        "break_level": round(break_level, 8) if break_level and break_level > 0 else None,
        "retest_level": round(retest_level, 8) if retest_level and retest_level > 0 else None,
        "sweep_level": round(sweep_level, 8) if sweep_level and sweep_level > 0 else None,
        "confidence": confidence,
        "evidence": evidence,
        "evidence_flags": normalized_flags,
        "ticket_requested": ticket_requested,
        "entry_zone_id": entry_zone_id,
        "stop_loss": round(stop_loss, 8) if stop_loss is not None else None,
    }


def trigger_confirmation_count(trigger: Dict[str, Any]) -> Tuple[int, List[str]]:
    flags = trigger.get("evidence_flags") if isinstance(trigger.get("evidence_flags"), dict) else {}
    trigger_type = trigger.get("type")
    if trigger_type == "local_reversal":
        keys = ("zone_reaction", "structure_break", "retest", "momentum_resume")
    elif trigger_type == "sweep_reclaim":
        keys = ("zone_reaction", "sweep", "reclaim", "structure_break")
    elif trigger_type == "breakout_retest":
        keys = ("structure_break", "close", "retest", "momentum_resume")
    elif trigger_type == "continuation":
        keys = ("pullback", "momentum_resume", "retest")
    else:
        keys = ()
    found = [key for key in keys if bool(flags.get(key))]
    return len(found), found


def normalize_zone(raw: Any, *, timeframe: Any, strict: bool = False) -> Dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    top = finite(item.get("top"))
    bottom = finite(item.get("bottom"))
    if top is None or bottom is None or top <= 0 or bottom <= 0:
        raise ValueError("Zone top en bottom moeten geldige positieve prijzen zijn")
    top, bottom = max(top, bottom), min(top, bottom)

    role = text(item.get("role", item.get("rol")), 20).lower()
    role = {"steun": "support", "weerstand": "resistance", "green": "support", "red": "resistance", "groen": "support", "rood": "resistance"}.get(role, role)
    if role not in {"support", "resistance", "unknown"}:
        role = "unknown"
    if strict and role == "unknown":
        raise ValueError("Iedere bevestigde zone moet support of resistance zijn")

    source_tf = normalize_timeframe(item.get("timeframe") or item.get("source_timeframe") or timeframe)
    if strict and source_tf == "UNKNOWN":
        raise ValueError("Zone-timeframe ontbreekt")

    intent = text(item.get("intent") or item.get("zone_intent") or "structure", 30).lower()
    if intent not in ZONE_INTENTS:
        intent = "structure"

    invalidation = finite(item.get("invalidation", item.get("invalidatie")))
    if invalidation is not None and invalidation <= 0:
        invalidation = None
    if invalidation is not None:
        if role == "support" and invalidation >= bottom:
            raise ValueError("Support-invalidatie moet onder de zone liggen")
        if role == "resistance" and invalidation <= top:
            raise ValueError("Resistance-invalidatie moet boven de zone liggen")

    state = text(item.get("thesis_state") or item.get("state") or "active", 20).lower()
    if state not in ZONE_STATES:
        state = "active"
    reviewed = bool(item.get("reviewed", strict))
    if strict and not reviewed:
        raise ValueError("Iedere zone moet expliciet als gecontroleerd zijn gemarkeerd")
    reason = text(item.get("reason", item.get("reden")), 500)
    if strict and len(reason) < 3:
        raise ValueError("Iedere bevestigde zone heeft een concrete reden nodig")

    confidence = integer(item.get("confidence"), 100 if strict else 0, 0, 100)
    invalidation_source = text(item.get("invalidation_source"), 40)
    if not invalidation_source:
        invalidation_source = "user-confirmed" if invalidation is not None and strict else "missing"

    return {
        "id": text(item.get("id"), 80) or str(uuid.uuid4()),
        "top": round(top, 8),
        "bottom": round(bottom, 8),
        "kind": "level" if abs(top - bottom) <= max(abs(top), 1.0) * 1e-9 else "zone",
        "role": role,
        "rol": role,
        "timeframe": source_tf,
        "source_timeframe": source_tf,
        "purpose": text(item.get("purpose"), 30).upper() or layer_purpose(source_tf),
        "intent": intent,
        "reason": reason,
        "label": text(item.get("label"), 160),
        "color": text(item.get("color"), 40),
        "invalidation": round(invalidation, 8) if invalidation is not None else None,
        "invalidation_source": invalidation_source,
        "confirmations": integer(item.get("confirmations"), 0, 0, 20),
        "tests": integer(item.get("tests"), 0, 0, 99),
        "confidence": confidence,
        "reviewed": reviewed,
        "active": bool(item.get("active", True)),
        "thesis_state": state,
        "parent_zone_id": text(item.get("parent_zone_id"), 80) or None,
        "source": text(item.get("source"), 60) or ("user-confirmed" if strict else "tradingview-vision"),
        "review_fields": list(item.get("review_fields") or []),
    }


def normalize_layer(payload: Any, *, strict: bool = True) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    asset = normalize_asset(data.get("asset") or data.get("symbol"))
    inferred_tf = data.get("source_timeframe") or data.get("chart_timeframe") or data.get("timeframe")
    if not inferred_tf:
        zone_tfs = [normalize_timeframe(z.get("timeframe")) for z in data.get("zones", []) if isinstance(z, dict) and z.get("timeframe")]
        inferred_tf = Counter(zone_tfs).most_common(1)[0][0] if zone_tfs else "UNKNOWN"
    timeframe = normalize_timeframe(inferred_tf)
    if strict and timeframe == "UNKNOWN":
        raise ValueError("Bron-timeframe ontbreekt")

    raw_zones = data.get("zones")
    if not isinstance(raw_zones, list) or not raw_zones:
        raise ValueError("Minimaal één getekende zone of level is vereist")
    zones = [normalize_zone(zone, timeframe=timeframe, strict=strict) for zone in raw_zones]

    low = finite(data.get("range_low"))
    high = finite(data.get("range_high"))
    if low is not None and high is not None:
        low, high = min(low, high), max(low, high)
        if low <= 0 or high <= low:
            low = high = None
    elif low is not None or high is not None:
        low = high = None

    setup = normalize_setup(data.get("setup"), timeframe=timeframe, strict=strict and timeframe == "15M")
    if timeframe != "15M":
        setup = normalize_setup({}, timeframe=timeframe, strict=False)
    trigger = normalize_trigger(data.get("trigger"), timeframe=timeframe, strict=strict and timeframe == "3M")
    if timeframe != "3M":
        trigger = normalize_trigger({}, timeframe=timeframe, strict=False)
    elif trigger.get("ticket_requested"):
        selected = next((zone for zone in zones if zone.get("id") == trigger.get("entry_zone_id")), None)
        if selected is None:
            raise ValueError("De gekozen instapzone bestaat niet meer in deze 3M-laag")
        selected["intent"] = "entry"
        selected["invalidation"] = trigger.get("stop_loss")
        selected["invalidation_source"] = "ticket-specific"
    else:
        # A market map is not an order ticket. No map zone carries a trade stop;
        # legacy entry labels are demoted until the trader explicitly arms one
        # concrete setup.
        for zone in zones:
            if zone.get("intent") == "entry":
                zone["intent"] = "structure"
            zone["invalidation"] = None
            zone["invalidation_source"] = "not-required"
    source_sync_id = text(data.get("source_sync_id") or data.get("sync_id") or data.get("revision"), 120) or None
    confirmed = bool(data.get("confirmed", strict))
    reviewed = bool(data.get("reviewed", strict))
    if strict and not reviewed:
        raise ValueError("Bevestig dat deze timeframe-laag is gecontroleerd")

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "chart-confirmed" if source_sync_id else "manual-confirmed",
        "confirmed": confirmed,
        "reviewed": reviewed,
        "asset": asset,
        "symbol": f"{asset}USDT",
        "source_timeframe": timeframe,
        "chart_timeframe": timeframe,
        "purpose": layer_purpose(timeframe),
        "trend": normalize_trend(data.get("trend")),
        "approach_direction": normalize_trend(data.get("approach_direction")),
        "range_low": round(low, 8) if low is not None else None,
        "range_high": round(high, 8) if high is not None else None,
        "range_source": text(data.get("range_source"), 60) or ("confirmed" if low is not None else "missing"),
        "range_confidence": integer(data.get("range_confidence"), 100 if low is not None and strict else 0, 0, 100),
        "overall_confidence": integer(data.get("overall_confidence"), 100 if strict else 0, 0, 100),
        "trade_type": normalize_trade_type(data.get("trade_type")),
        "setup": setup,
        "trigger": trigger,
        "zones": zones,
        "levels": sorted({float(p) for zone in zones for p in (zone["top"], zone["bottom"])}, reverse=True),
        "source_sync_id": source_sync_id,
        "warnings": [text(item, 300) for item in data.get("warnings", []) if text(item, 300)],
        "context_note": text(data.get("context_note"), 700),
        "provenance": {
            "kind": "tradingview-chart" if source_sync_id else "manual",
            "reviewed_by_user": reviewed,
            "reviewed_at": utc_now() if strict else None,
        },
        "at": text(data.get("at"), 80) or utc_now(),
        "confirmed_at": utc_now() if strict else None,
        "order_ready": False,
    }


def empty_stack() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "assets": {}, "latest": None, "updated_at": utc_now()}


def ensure_stack(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return empty_stack()
    return {
        "schema_version": SCHEMA_VERSION,
        "assets": value.get("assets") if isinstance(value.get("assets"), dict) else {},
        "latest": value.get("latest") if isinstance(value.get("latest"), dict) else None,
        "updated_at": text(value.get("updated_at"), 80) or utc_now(),
    }


def save_layer_in_stack(stack_value: Any, layer: Dict[str, Any], *, latest: bool = True) -> Dict[str, Any]:
    stack = ensure_stack(stack_value)
    asset = normalize_asset(layer.get("asset"))
    tf = normalize_timeframe(layer.get("source_timeframe") or layer.get("chart_timeframe"))
    assets = dict(stack.get("assets") or {})
    asset_row = dict(assets.get(asset) or {})
    layers = dict(asset_row.get("layers") or {})
    layers[tf] = layer
    asset_row.update({"asset": asset, "symbol": f"{asset}USDT", "layers": layers, "updated_at": utc_now()})
    assets[asset] = asset_row
    stack["assets"] = assets
    if latest:
        stack["latest"] = {
            "asset": asset,
            "timeframe": tf,
            "revision": layer.get("revision") or layer.get("sync_id") or layer.get("source_sync_id"),
            "at": layer.get("at") or utc_now(),
        }
    stack["updated_at"] = utc_now()
    return stack


def get_layer(stack_value: Any, asset: Any, timeframe: Any) -> Optional[Dict[str, Any]]:
    stack = ensure_stack(stack_value)
    row = (stack.get("assets") or {}).get(normalize_asset(asset))
    if not isinstance(row, dict):
        return None
    layer = (row.get("layers") or {}).get(normalize_timeframe(timeframe))
    return layer if isinstance(layer, dict) else None


def get_latest_layer(stack_value: Any, *, asset: Any = None, timeframe: Any = None) -> Optional[Dict[str, Any]]:
    stack = ensure_stack(stack_value)
    asset_name = normalize_asset(asset) if asset else None
    tf_name = normalize_timeframe(timeframe) if timeframe else None
    if asset_name and tf_name:
        return get_layer(stack, asset_name, tf_name)

    latest = stack.get("latest") if isinstance(stack.get("latest"), dict) else {}
    if latest:
        latest_asset = normalize_asset(latest.get("asset"))
        latest_tf = normalize_timeframe(latest.get("timeframe"))
        if (not asset_name or latest_asset == asset_name) and (not tf_name or latest_tf == tf_name):
            layer = get_layer(stack, latest_asset, latest_tf)
            if layer:
                return layer

    newest: Optional[Dict[str, Any]] = None
    for key, asset_row in (stack.get("assets") or {}).items():
        if asset_name and normalize_asset(key) != asset_name:
            continue
        if not isinstance(asset_row, dict):
            continue
        for tf, layer in (asset_row.get("layers") or {}).items():
            if tf_name and normalize_timeframe(tf) != tf_name:
                continue
            if not isinstance(layer, dict):
                continue
            if newest is None or text(layer.get("at"), 80) > text(newest.get("at"), 80):
                newest = layer
    return newest


def confirmed_layers(stack_value: Any, asset: Any) -> Dict[str, Dict[str, Any]]:
    stack = ensure_stack(stack_value)
    row = (stack.get("assets") or {}).get(normalize_asset(asset), {})
    layers = row.get("layers") if isinstance(row, dict) and isinstance(row.get("layers"), dict) else {}
    return {
        normalize_timeframe(tf): layer
        for tf, layer in layers.items()
        if isinstance(layer, dict) and layer.get("confirmed") and layer.get("reviewed")
    }


def stored_layers(stack_value: Any, asset: Any) -> Dict[str, Dict[str, Any]]:
    """Return every stored layer for an asset, regardless of review state."""
    stack = ensure_stack(stack_value)
    row = (stack.get("assets") or {}).get(normalize_asset(asset), {})
    layers = row.get("layers") if isinstance(row, dict) and isinstance(row.get("layers"), dict) else {}
    return {
        normalize_timeframe(tf): layer
        for tf, layer in layers.items()
        if isinstance(layer, dict)
    }


def _layer_timestamp(layer: Optional[Dict[str, Any]]) -> float:
    if not layer:
        return 0.0
    for key in ("at", "last_seen_at", "confirmed_at"):
        value = layer.get(key)
        if not value:
            continue
        try:
            stamp = datetime.fromisoformat(text(value, 80).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.timestamp()
        except Exception:
            continue
    return 0.0


def _draft_pending(draft: Optional[Dict[str, Any]], confirmed: Optional[Dict[str, Any]]) -> bool:
    """Whether a chart draft is newer than the last user-verified layer."""
    if not draft:
        return False
    if not confirmed:
        return True
    revision = text(draft.get("revision") or draft.get("sync_id"), 120)
    confirmed_revision = text(confirmed.get("source_sync_id") or confirmed.get("sync_id"), 120)
    if revision and confirmed_revision and revision == confirmed_revision:
        return False
    return _layer_timestamp(draft) >= _layer_timestamp(confirmed)




def _relative_distance(a: Optional[float], b: Optional[float]) -> float:
    if a is None or b is None:
        return float("inf")
    scale = max(abs(float(a)), abs(float(b)), 1.0)
    return abs(float(a) - float(b)) / scale


def _zone_match(a: Dict[str, Any], b: Dict[str, Any], tolerance_pct: float = 0.0035) -> bool:
    """Return whether two vision zones describe the same practical level.

    Vision boxes can move a few pixels between captures.  A repeat capture must
    not revoke a human review for harmless geometry jitter.
    """
    if text(a.get("role"), 20).lower() != text(b.get("role"), 20).lower():
        return False
    a_top, a_bottom = finite(a.get("top")), finite(a.get("bottom"))
    b_top, b_bottom = finite(b.get("top")), finite(b.get("bottom"))
    if None in {a_top, a_bottom, b_top, b_bottom}:
        return False
    a_mid = (a_top + a_bottom) / 2
    b_mid = (b_top + b_bottom) / 2
    a_width = max(abs(a_top - a_bottom), abs(a_mid) * 0.00025)
    b_width = max(abs(b_top - b_bottom), abs(b_mid) * 0.00025)
    scale = max(abs(a_mid), abs(b_mid), 1.0)
    width_tolerance_pct = max(a_width, b_width) * 2.0 / scale
    # Ponytail: cap vision drift at 1%; only recalibrate per asset with measured evidence.
    allowed_pct = max(tolerance_pct, min(width_tolerance_pct, 0.01))
    return _relative_distance(a_mid, b_mid) <= allowed_pct


def material_change_reason(confirmed: Optional[Dict[str, Any]], draft: Optional[Dict[str, Any]]) -> Optional[str]:
    """Explain whether a new capture needs another human review.

    Reviews are sticky.  A new screenshot only invalidates the matching layer
    when its trading meaning changed, not merely because a new revision id was
    generated.
    """
    if not confirmed or not draft:
        return "eerste controle vereist"
    tf = normalize_timeframe(draft.get("source_timeframe") or draft.get("chart_timeframe"))
    old_trend = normalize_trend(confirmed.get("trend"))
    new_trend = normalize_trend(draft.get("trend"))
    if old_trend != new_trend and "unknown" not in {old_trend, new_trend}:
        return f"trend veranderde van {old_trend} naar {new_trend}"
    old_approach = normalize_trend(confirmed.get("approach_direction"))
    new_approach = normalize_trend(draft.get("approach_direction"))
    if old_approach != new_approach and "unknown" not in {old_approach, new_approach}:
        return f"lokale beweging veranderde van {old_approach} naar {new_approach}"

    for key in ("range_low", "range_high"):
        old = finite(confirmed.get(key))
        new = finite(draft.get(key))
        if (old is None) != (new is None):
            return "rangegrens toegevoegd of verwijderd"
        if old is not None and new is not None and _relative_distance(old, new) > 0.005:
            return "rangegrens verschoof materieel"

    old_zones = [z for z in (confirmed.get("zones") or []) if isinstance(z, dict) and z.get("active", True)]
    new_zones = [z for z in (draft.get("zones") or []) if isinstance(z, dict) and z.get("active", True)]
    unmatched_old = 0
    used = set()
    for old in old_zones:
        match_index = next((i for i, new in enumerate(new_zones) if i not in used and _zone_match(old, new)), None)
        if match_index is None:
            unmatched_old += 1
        else:
            used.add(match_index)
    unmatched_new = max(0, len(new_zones) - len(used))
    # A single disappeared or materially moved zone can change the whole map.
    # Harmless pixel jitter is already handled by _zone_match; unmatched zones
    # therefore always require a new human review.
    if unmatched_old or unmatched_new:
        return "belangrijke zone toegevoegd, verwijderd of verplaatst"

    if tf == "15M":
        old_setup = normalize_setup(confirmed.get("setup"), timeframe="15M", strict=False)
        new_setup = normalize_setup(draft.get("setup"), timeframe="15M", strict=False)
        for key in ("detected", "type", "direction"):
            if old_setup.get(key) != new_setup.get(key):
                return "15M-opbouw veranderde"
    if tf == "3M":
        old_trigger = normalize_trigger(confirmed.get("trigger"), timeframe="3M", strict=False)
        new_trigger = normalize_trigger(draft.get("trigger"), timeframe="3M", strict=False)
        for key in ("detected", "type", "direction", "ticket_requested"):
            if old_trigger.get(key) != new_trigger.get(key):
                return "3M-signaal veranderde"
    return None


def carry_review_forward(confirmed: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the reviewed map while refreshing its capture timestamp/revision."""
    carried = dict(confirmed)
    carried["at"] = draft.get("at") or draft.get("last_seen_at") or utc_now()
    carried["last_seen_at"] = draft.get("last_seen_at") or draft.get("at") or utc_now()
    carried["source_sync_id"] = draft.get("revision") or draft.get("sync_id") or confirmed.get("source_sync_id")
    carried["overall_confidence"] = draft.get("overall_confidence", confirmed.get("overall_confidence"))
    carried["warnings"] = list(draft.get("warnings") or confirmed.get("warnings") or [])
    carried["review_carried_forward"] = True
    carried["review_carried_at"] = utc_now()
    carried["review_reason"] = "ongewijzigde handelskaart; eerdere controle blijft geldig"
    return carried


def review_age_hours(layer: Optional[Dict[str, Any]]) -> float:
    """Age of the last actual human review, never the latest chart capture."""
    if not layer:
        return float("inf")
    provenance = layer.get("provenance") if isinstance(layer.get("provenance"), dict) else {}
    raw = provenance.get("reviewed_at") or layer.get("confirmed_at") or layer.get("at")
    try:
        stamp = datetime.fromisoformat(text(raw, 80).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 3600)
    except Exception:
        return float("inf")


def review_expiry_reason(timeframe: Any, layer: Optional[Dict[str, Any]]) -> Optional[str]:
    tf = normalize_timeframe(timeframe)
    limit = REVIEW_VALID_HOURS.get(tf)
    age = review_age_hours(layer)
    if limit is not None and age > limit:
        return f"menselijke controle is ouder dan {limit:g} uur"
    return None


def resolve_layers(
    stack_value: Any,
    draft_stack_value: Any,
    asset: Any,
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, str]]:
    """Resolve the latest visible layer and its state per timeframe.

    A successful chart sync counts as *present*.  A separate user review only
    controls whether that layer may feed an executable ticket.  This avoids the
    old and confusing situation where four successful syncs still appeared as
    an incomplete map.
    """
    stored_verified = confirmed_layers(stack_value, asset)
    drafts = stored_layers(draft_stack_value, asset)
    verified: Dict[str, Dict[str, Any]] = dict(stored_verified)
    available: Dict[str, Dict[str, Any]] = {}
    states: Dict[str, str] = {}
    for tf in PRIMARY_TIMEFRAMES:
        confirmed = stored_verified.get(tf)
        draft = drafts.get(tf)
        pending = _draft_pending(draft, confirmed)
        expired_reason = review_expiry_reason(tf, confirmed) if confirmed else None
        if pending and draft and confirmed:
            reason = material_change_reason(confirmed, draft)
            if reason is None and expired_reason is None:
                carried = carry_review_forward(confirmed, draft)
                available[tf] = carried
                verified[tf] = carried
                states[tf] = "VERIFIED"
            else:
                candidate = dict(draft)
                candidate["review_reason"] = reason or expired_reason
                candidate["review_expired"] = bool(expired_reason and reason is None)
                available[tf] = candidate
                states[tf] = "SYNCED"
        elif pending and draft:
            candidate = dict(draft)
            candidate["review_reason"] = "eerste controle vereist"
            available[tf] = candidate
            states[tf] = "SYNCED"
        elif confirmed:
            if expired_reason:
                candidate = dict(draft or confirmed)
                candidate["review_reason"] = expired_reason
                candidate["review_expired"] = True
                available[tf] = candidate
                states[tf] = "SYNCED"
            else:
                available[tf] = confirmed
                states[tf] = "VERIFIED"
        elif draft:
            candidate = dict(draft)
            candidate["review_reason"] = "eerste controle vereist"
            available[tf] = candidate
            states[tf] = "SYNCED"
        else:
            states[tf] = "MISSING"
    return available, verified, states


def layer_age_hours(layer: Optional[Dict[str, Any]]) -> float:
    if not layer:
        return float("inf")
    try:
        # Freshness concerns the latest chart capture. A valid human review can
        # be carried forward across equivalent captures.
        stamp = datetime.fromisoformat(text(layer.get("at") or layer.get("last_seen_at") or layer.get("confirmed_at"), 80).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 3600)
    except Exception:
        return float("inf")


def public_stack(stack_value: Any) -> Dict[str, Any]:
    stack = ensure_stack(stack_value)
    out = ensure_stack(stack)
    assets: Dict[str, Any] = {}
    for asset, row in (stack.get("assets") or {}).items():
        if not isinstance(row, dict):
            continue
        layers: Dict[str, Any] = {}
        for tf, layer in (row.get("layers") or {}).items():
            if not isinstance(layer, dict):
                continue
            item = dict(layer)
            item["age_hours"] = round(layer_age_hours(item), 2)
            item.pop("raw_model_output", None)
            layers[normalize_timeframe(tf)] = item
        assets[asset] = {**row, "layers": layers}
    out["assets"] = assets
    return out


def build_stack_health(stack_value: Any, asset: Any, draft_stack_value: Any = None) -> Dict[str, Any]:
    """Return a compact operational health view for the fixed 1D/4H/15M/3M chain."""
    asset_name = normalize_asset(asset)
    available, verified, states = resolve_layers(stack_value, draft_stack_value or empty_stack(), asset_name)
    freshness_limits = REVIEW_VALID_HOURS
    rows: List[Dict[str, Any]] = []
    for tf in PRIMARY_TIMEFRAMES:
        layer = available.get(tf)
        age = layer_age_hours(layer)
        review_age = review_age_hours(verified.get(tf) or layer)
        present = layer is not None
        fresh = present and age <= freshness_limits[tf]
        confirmed = states.get(tf) == "VERIFIED" and tf in verified
        rows.append({
            "timeframe": tf,
            "purpose": layer_purpose(tf),
            "present": present,
            "synced": present,
            "confirmed": confirmed,
            "review_needed": present and not confirmed,
            "state": states.get(tf, "MISSING"),
            "fresh": fresh,
            "age_hours": round(age, 2) if present else None,
            "review_age_hours": round(review_age, 2) if present and math.isfinite(review_age) else None,
            "review_fresh": confirmed and review_age <= REVIEW_VALID_HOURS[tf],
            "zones": len(layer.get("zones", [])) if layer else 0,
            "trend": layer.get("trend", "unknown") if layer else "unknown",
            "setup_detected": bool((layer or {}).get("setup", {}).get("detected")) if tf == "15M" else None,
            "trigger_detected": bool((layer or {}).get("trigger", {}).get("detected")) if tf == "3M" else None,
        })
    return {
        "asset": asset_name,
        "complete": all(row["present"] for row in rows),
        "capture_complete": all(row["present"] for row in rows),
        "verified_complete": all(row["confirmed"] for row in rows),
        "fresh": all(row["fresh"] for row in rows),
        "synced_count": sum(1 for row in rows if row["present"]),
        "confirmed_count": sum(1 for row in rows if row["confirmed"]),
        "required_count": len(PRIMARY_TIMEFRAMES),
        "missing_timeframes": [row["timeframe"] for row in rows if not row["present"]],
        "review_timeframes": [row["timeframe"] for row in rows if row["review_needed"]],
        "layers": rows,
        "updated_at": utc_now(),
    }


def zone_mid(zone: Dict[str, Any]) -> float:
    return (float(zone.get("top") or 0) + float(zone.get("bottom") or 0)) / 2


def zone_width(zone: Dict[str, Any]) -> float:
    mid = max(abs(zone_mid(zone)), 1.0)
    return max(abs(float(zone.get("top") or 0) - float(zone.get("bottom") or 0)), mid * 0.00025)


def zone_distance_pct(price: float, zone: Dict[str, Any]) -> float:
    if price <= 0:
        return float("inf")
    top, bottom = float(zone.get("top") or 0), float(zone.get("bottom") or 0)
    if bottom <= price <= top:
        return 0.0
    nearest = bottom if price < bottom else top
    return abs(price - nearest) / price * 100


def zones_overlap(a: Dict[str, Any], b: Dict[str, Any], tolerance_factor: float = 1.2) -> bool:
    a_mid, b_mid = zone_mid(a), zone_mid(b)
    tolerance = max(zone_width(a), zone_width(b)) * tolerance_factor
    return abs(a_mid - b_mid) <= tolerance or not (float(a["top"]) < float(b["bottom"]) or float(b["top"]) < float(a["bottom"]))


def _zone_relation(child: Dict[str, Any], parent: Dict[str, Any]) -> str:
    if zones_overlap(child, parent, 1.6):
        return "NESTED_SAME_ROLE" if child.get("role") == parent.get("role") else "NESTED_ROLE_FLIP"
    return "NEAR_PARENT"


def link_parent_child(layers: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    links: Dict[str, List[Dict[str, Any]]] = {"15M": [], "3M": []}
    parent_order = {"15M": ("4H", "1D"), "3M": ("15M", "4H", "1D")}
    for child_tf, parent_tfs in parent_order.items():
        child_layer = layers.get(child_tf)
        if not child_layer:
            continue
        for child in child_layer.get("zones", []):
            if not isinstance(child, dict) or not child.get("active", True):
                continue
            explicit = child.get("parent_zone_id")
            candidates: List[Tuple[int, float, Dict[str, Any], str]] = []
            for rank, parent_tf in enumerate(parent_tfs):
                for parent in (layers.get(parent_tf) or {}).get("zones", []):
                    if not isinstance(parent, dict) or not parent.get("active", True):
                        continue
                    if explicit and parent.get("id") == explicit:
                        candidates.append((-1, 0.0, parent, parent_tf))
                        continue
                    distance = abs(zone_mid(child) - zone_mid(parent)) / max(abs(zone_mid(parent)), 1.0) * 100
                    tolerance = max(0.8 if parent_tf == "1D" else 0.5, zone_width(parent) / max(abs(zone_mid(parent)), 1.0) * 100 * 2.0)
                    if zones_overlap(child, parent, 1.8) or distance <= tolerance:
                        candidates.append((rank, distance, parent, parent_tf))
            if not candidates:
                continue
            candidates.sort(key=lambda item: (item[0], item[1]))
            _, distance, parent, parent_tf = candidates[0]
            links[child_tf].append({
                "child_zone_id": child.get("id"),
                "child_timeframe": child_tf,
                "parent_zone_id": parent.get("id"),
                "parent_timeframe": parent_tf,
                "relation": _zone_relation(child, parent),
                "distance_pct": round(distance, 4),
            })
    return links


def find_parent_zone(layers: Dict[str, Dict[str, Any]], reference_price: float) -> Optional[Dict[str, Any]]:
    candidates: List[Tuple[int, float, Dict[str, Any]]] = []
    for tf_rank, tf in enumerate(("4H", "1D")):
        layer = layers.get(tf)
        if not layer:
            continue
        for zone in layer.get("zones", []):
            if not isinstance(zone, dict) or not zone.get("active", True):
                continue
            distance = zone_distance_pct(reference_price, zone)
            tolerance = max(0.55 if tf == "4H" else 0.95, zone_width(zone) / max(reference_price, 1.0) * 100 * 2.0)
            if distance <= tolerance:
                candidates.append((tf_rank, distance, {**zone, "source_timeframe": tf}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _nearest_zone(zones: Sequence[Dict[str, Any]], reference: float, role: Optional[str] = None) -> Optional[Dict[str, Any]]:
    candidates = [zone for zone in zones if isinstance(zone, dict) and zone.get("active", True)]
    if role:
        candidates = [zone for zone in candidates if zone.get("role", zone.get("rol")) == role]
    if not candidates:
        return None
    return min(candidates, key=lambda zone: abs(zone_mid(zone) - reference))


def _find_child_context(layers: Dict[str, Dict[str, Any]], parent: Dict[str, Any], reference: float) -> Optional[Dict[str, Any]]:
    zones = [zone for zone in (layers.get("15M") or {}).get("zones", []) if isinstance(zone, dict) and zone.get("active", True)]
    linked = [zone for zone in zones if zone.get("parent_zone_id") == parent.get("id") or zones_overlap(zone, parent, 1.8)]
    pool = linked or zones
    if not pool:
        return None
    candidate = min(pool, key=lambda zone: abs(zone_mid(zone) - reference))
    distance = zone_distance_pct(reference, candidate)
    tolerance = max(0.32, zone_width(candidate) / max(reference, 1.0) * 100 * 2.0)
    return {**candidate, "source_timeframe": "15M"} if distance <= tolerance or zones_overlap(candidate, parent, 1.8) else None


def _dedupe_targets(items: Iterable[Tuple[float, str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for value, tf, zone_id in items:
        if value <= 0:
            continue
        if any(abs(value - row["price"]) / max(abs(value), 1.0) <= 0.00035 for row in out):
            continue
        out.append({"price": round(value, 8), "timeframe": tf, "zone_id": zone_id})
    return out


def collect_targets(layers: Dict[str, Dict[str, Any]], direction: str, entry: float) -> List[Dict[str, Any]]:
    rows: List[Tuple[float, str, str]] = []
    for tf in ("3M", "15M", "4H", "1D"):
        for zone in (layers.get(tf) or {}).get("zones", []):
            if not isinstance(zone, dict) or not zone.get("active", True):
                continue
            role = zone.get("role", zone.get("rol"))
            if direction == "long" and role == "resistance":
                value = float(zone.get("bottom") or 0)
                if value > entry:
                    rows.append((value, tf, text(zone.get("id"), 80)))
            elif direction == "short" and role == "support":
                value = float(zone.get("top") or 0)
                if 0 < value < entry:
                    rows.append((value, tf, text(zone.get("id"), 80)))
    rows.sort(key=lambda item: item[0], reverse=direction == "short")
    return _dedupe_targets(rows)


def role_label(value: Any) -> str:
    return {"support": "steun", "resistance": "weerstand", "unknown": "onbekend"}.get(text(value, 30).lower(), text(value, 30).lower() or "onbekend")


def setup_label(value: Any) -> str:
    return {
        "none": "nog geen opbouw",
        "reversal": "omkering",
        "breakout": "uitbraak",
        "continuation": "vervolg",
        "range_rotation": "rangerotatie",
        "compression": "compressie",
    }.get(text(value, 40).lower(), text(value, 40).replace("_", " ") or "onbekend")


def trigger_label(value: Any) -> str:
    return {
        "none": "nog geen signaal",
        "local_reversal": "lokale kanteling",
        "sweep_reclaim": "sweep en reclaim",
        "breakout_retest": "uitbraak en hertest",
        "continuation": "vervolg na terugtest",
    }.get(text(value, 40).lower(), text(value, 40).replace("_", " ") or "onbekend")


def _relation(direction: str, trigger_type: str, parent: Dict[str, Any], layers: Dict[str, Dict[str, Any]]) -> str:
    if trigger_type == "breakout_retest":
        return "BREAKOUT" if direction == "long" else "BREAKDOWN"
    parent_role = parent.get("role", parent.get("rol"))
    trends = [layers.get(tf, {}).get("trend") for tf in ("1D", "4H")]
    known = [trend for trend in trends if trend in {"up", "down"}]
    dominant = known[0] if known and len(set(known)) == 1 else None
    expected = "up" if direction == "long" else "down"
    if dominant == expected:
        return "WITH_TREND"
    if (direction == "long" and parent_role == "support") or (direction == "short" and parent_role == "resistance"):
        return "COUNTERTREND_HTF_REACTION" if dominant and dominant != expected else "HTF_ZONE_REVERSAL"
    return "RANGE_ROTATION"


def _chain_item(
    tf: str,
    layer: Optional[Dict[str, Any]],
    *,
    status: str,
    detail: str,
    confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    verified = bool(layer and layer.get("confirmed") and layer.get("reviewed")) if confirmed is None else bool(confirmed)
    return {
        "timeframe": tf,
        "purpose": layer_purpose(tf),
        "status": status,
        "synced": bool(layer),
        "confirmed": verified,
        "review_needed": bool(layer) and not verified,
        "trend": layer.get("trend", "unknown") if layer else "unknown",
        "approach_direction": layer.get("approach_direction", "unknown") if layer else "unknown",
        "zones": len(layer.get("zones", [])) if layer else 0,
        "age_hours": round(layer_age_hours(layer), 2) if layer else None,
        "detail": detail,
    }


def _base_payload(asset: str, risk_profiles: Dict[str, float], chain: List[Dict[str, Any]], status: str, label: str, reason: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "asset": asset,
        "symbol": f"{asset}USDT",
        "setup": None,
        "execution_gate": {
            "status": status,
            "label": label,
            "orderable": False,
            "reason": reason,
            "checks": [],
            "failed": [],
        },
        "decision_chain": chain,
        "risk_profiles": risk_profiles,
        "standing_setups": [],
        "updated_at": utc_now(),
    }


def _check(key: str, label: str, ok: bool, detail: str, *, critical: bool = True) -> Dict[str, Any]:
    return {"key": key, "label": label, "ok": bool(ok), "detail": detail, "critical": critical}


def _side_and_staleness_check(
    *,
    direction: str,
    trigger_type: str,
    current_price: float,
    entry: float,
    parent: Dict[str, Any],
    thesis_invalidation: Optional[float],
    first_target: Optional[float],
    trigger: Dict[str, Any],
) -> Tuple[bool, str]:
    """Prevent stale/spook setups while preserving valid 3M reversals.

    A local reversal may deliberately oppose the incoming move. The hard boundary is
    therefore not HTF-vs-M3 direction, but the actual price side:
    - a buy-limit entry may not sit above the live price;
    - a sell-limit entry may not sit below the live price;
    - the HTF thesis invalidation may not already be breached;
    - the first target may not already have been reached before ticket preparation;
    - price outside the parent zone requires an explicit sweep/reclaim or role-flip.
    """
    if direction not in {"long", "short"}:
        return False, "richting ontbreekt"
    if not all(math.isfinite(value) for value in (current_price, entry)):
        return False, "actuele prijs of instap is ongeldig"

    tolerance = max(abs(current_price) * 0.00015, 1e-9)
    if direction == "long" and entry > current_price + tolerance:
        return False, f"long-instap {entry} ligt boven actuele prijs {current_price}; de markt is al onder de voorgestelde instap"
    if direction == "short" and entry < current_price - tolerance:
        return False, f"short-instap {entry} ligt onder actuele prijs {current_price}; de markt is al boven de voorgestelde instap"

    if thesis_invalidation is not None:
        if direction == "long" and current_price <= thesis_invalidation:
            return False, f"actuele prijs {current_price} staat op/onder thesis-invalidatie {thesis_invalidation}"
        if direction == "short" and current_price >= thesis_invalidation:
            return False, f"actuele prijs {current_price} staat op/boven thesis-invalidatie {thesis_invalidation}"

    if first_target is not None:
        if direction == "long" and current_price >= first_target - tolerance:
            return False, f"TP1 {first_target} is al bereikt of gepasseerd; de instap is verlopen"
        if direction == "short" and current_price <= first_target + tolerance:
            return False, f"TP1 {first_target} is al bereikt of gepasseerd; de instap is verlopen"

    parent_bottom = finite(parent.get("bottom"))
    parent_top = finite(parent.get("top"))
    flags = trigger.get("evidence_flags") if isinstance(trigger.get("evidence_flags"), dict) else {}
    reclaim_ok = bool(flags.get("reclaim") or flags.get("retest") or flags.get("close"))
    if trigger_type != "breakout_retest" and parent_bottom is not None and parent_top is not None:
        if direction == "long" and current_price < parent_bottom - tolerance and not reclaim_ok:
            return False, "prijs staat onder de HTF-steun zonder bevestigde herovering"
        if direction == "short" and current_price > parent_top + tolerance and not reclaim_ok:
            return False, "prijs staat boven de HTF-weerstand zonder bevestigde herovering"

    return True, f"prijszijde geldig: live {current_price} · instap {entry}"


def build_decision(
    stack_value: Any,
    *,
    asset: Any,
    current_price: Optional[float],
    risk_profiles: Dict[str, float],
    draft_stack_value: Any = None,
) -> Dict[str, Any]:
    """Build a safe top-down decision without a naive HTF-vs-M3 direction rule."""
    asset_name = normalize_asset(asset)
    layers, verified_layers, layer_states = resolve_layers(stack_value, draft_stack_value or empty_stack(), asset_name)
    links = link_parent_child(layers)
    chain: List[Dict[str, Any]] = []
    for tf in PRIMARY_TIMEFRAMES:
        layer = layers.get(tf)
        if layer:
            is_verified = layer_states.get(tf) == "VERIFIED" and tf in verified_layers
            detail = f"{len(layer.get('zones', []))} zone(s) {'gecontroleerd' if is_verified else 'gesynchroniseerd'}"
            if tf == "15M":
                setup_info = normalize_setup(layer.get("setup"), timeframe="15M", strict=False)
                detail += f" · {setup_label(setup_info.get('type')) if setup_info.get('detected') else 'opbouw nog in ontwikkeling'}"
            if tf == "3M":
                trigger = normalize_trigger(layer.get("trigger"), timeframe="3M", strict=False)
                detail += f" · {trigger_label(trigger.get('type')) if trigger.get('detected') else 'nog geen signaal'}"
            chain.append(_chain_item(tf, layer, status="VERIFIED" if is_verified else "SYNCED", detail=detail, confirmed=is_verified))
        else:
            detail = {
                "1D": "Synchroniseer de Daily-context",
                "4H": "Synchroniseer de 4H-structuur",
                "15M": "Synchroniseer de lokale 15M-opbouw",
                "3M": "Synchroniseer de 3M voor de eerste lokale trendkanteling",
            }[tf]
            chain.append(_chain_item(tf, None, status="MISSING", detail=detail))

    missing = [tf for tf in PRIMARY_TIMEFRAMES if tf not in layers]
    if missing:
        label = "NOG 1 GRAFIEKLAAG" if len(missing) == 1 else f"NOG {len(missing)} GRAFIEKLAGEN"
        payload = _base_payload(
            asset_name,
            risk_profiles,
            chain,
            "WAIT_SYNC",
            label,
            "Synchroniseer nog: " + ", ".join(missing) + ". Een geslaagde synchronisatie telt direct mee; handmatige controle is pas nodig vóór orderticketvoorbereiding.",
        )
        payload.update(
            capture_complete=False,
            verified_complete=False,
            synced_count=len(PRIMARY_TIMEFRAMES) - len(missing),
            confirmed_count=sum(1 for tf in PRIMARY_TIMEFRAMES if layer_states.get(tf) == "VERIFIED"),
            missing_timeframes=missing,
            review_timeframes=[tf for tf in PRIMARY_TIMEFRAMES if layer_states.get(tf) == "SYNCED"],
        )
        return payload

    pending_review = [tf for tf in PRIMARY_TIMEFRAMES if layer_states.get(tf) != "VERIFIED"]
    if pending_review:
        # Review only what can change a decision. Repeated equivalent captures
        # keep their prior approval. 1D/4H structure changes block immediately;
        # 15M and 3M are reviewed just-in-time when a setup/trigger actually
        # appears. This preserves fail-closed execution without forcing a full
        # four-chart form after every refresh.
        htf_pending = [tf for tf in ("1D", "4H") if tf in pending_review]
        if htf_pending:
            first_review = htf_pending[0]
            reason = text((layers.get(first_review) or {}).get("review_reason"), 240) or "de kaart veranderde materieel"
            payload = _base_payload(
                asset_name,
                risk_profiles,
                chain,
                "REVIEW_STACK",
                f"CONTROLEER {first_review}",
                f"Alleen {first_review} moet opnieuw worden bekeken: {reason}. Ongewijzigde charts blijven goedgekeurd.",
            )
            payload.update(
                capture_complete=True,
                verified_complete=False,
                synced_count=4,
                confirmed_count=4 - len(pending_review),
                missing_timeframes=[],
                review_timeframes=pending_review,
                blocking_review_timeframes=htf_pending,
                review_policy="MATERIAL_CHANGE_ONLY",
                setup_15m=normalize_setup((layers.get("15M") or {}).get("setup"), timeframe="15M", strict=False),
                trigger_3m=normalize_trigger((layers.get("3M") or {}).get("trigger"), timeframe="3M", strict=False),
            )
            return payload

        if "15M" in pending_review:
            setup_candidate = normalize_setup((layers.get("15M") or {}).get("setup"), timeframe="15M", strict=False)
            if setup_candidate.get("detected"):
                reason = text((layers.get("15M") or {}).get("review_reason"), 240) or "de lokale opbouw veranderde"
                payload = _base_payload(
                    asset_name, risk_profiles, chain, "REVIEW_15M_SETUP", "CONTROLEER 15M-SETUP",
                    f"Er is een nieuwe 15M-opbouw gezien. Controleer alleen deze laag: {reason}.",
                )
                payload.update(capture_complete=True, verified_complete=False, synced_count=4,
                               confirmed_count=4-len(pending_review), missing_timeframes=[],
                               review_timeframes=pending_review, blocking_review_timeframes=["15M"],
                               review_policy="JUST_IN_TIME", setup_15m=setup_candidate,
                               trigger_3m=normalize_trigger((layers.get("3M") or {}).get("trigger"), timeframe="3M", strict=False))
                return payload
            payload = _base_payload(
                asset_name, risk_profiles, chain, "WAIT_15M_SETUP", "WACHT OP 15M-SETUP",
                "De 15M-chart is ververst, maar er is nog geen concrete opbouw. Je hoeft hem nu niet handmatig te controleren.",
            )
            payload.update(capture_complete=True, verified_complete=False, synced_count=4,
                           confirmed_count=4-len(pending_review), missing_timeframes=[],
                           review_timeframes=pending_review, blocking_review_timeframes=[],
                           review_policy="JUST_IN_TIME", setup_15m=setup_candidate,
                           trigger_3m=normalize_trigger((layers.get("3M") or {}).get("trigger"), timeframe="3M", strict=False))
            return payload

        if "3M" in pending_review:
            trigger_candidate = normalize_trigger((layers.get("3M") or {}).get("trigger"), timeframe="3M", strict=False)
            if trigger_candidate.get("detected") or trigger_candidate.get("ticket_requested"):
                reason = text((layers.get("3M") or {}).get("review_reason"), 240) or "het lokale signaal veranderde"
                payload = _base_payload(
                    asset_name, risk_profiles, chain, "REVIEW_3M_TRIGGER", "CONTROLEER 3M-SIGNAAL",
                    f"Er is een nieuw lokaal instapsignaal gezien. Controleer alleen de 3M-trigger: {reason}.",
                )
                payload.update(capture_complete=True, verified_complete=False, synced_count=4,
                               confirmed_count=4-len(pending_review), missing_timeframes=[],
                               review_timeframes=pending_review, blocking_review_timeframes=["3M"],
                               review_policy="JUST_IN_TIME", setup_15m=normalize_setup((verified_layers.get("15M") or {}).get("setup"), timeframe="15M", strict=False),
                               trigger_3m=trigger_candidate)
                return payload
            payload = _base_payload(
                asset_name, risk_profiles, chain, "WAIT_3M_TRIGGER", "WACHT OP 3M-SIGNAAL",
                "De 3M-chart beweegt, maar er is nog geen concrete lokale kanteling. Je hoeft hem nu niet handmatig te controleren.",
            )
            payload.update(capture_complete=True, verified_complete=False, synced_count=4,
                           confirmed_count=4-len(pending_review), missing_timeframes=[],
                           review_timeframes=pending_review, blocking_review_timeframes=[],
                           review_policy="JUST_IN_TIME", setup_15m=normalize_setup((verified_layers.get("15M") or {}).get("setup"), timeframe="15M", strict=False),
                           trigger_3m=trigger_candidate)
            return payload

    # From this point onward every decision-relevant layer is reviewed.
    layers = verified_layers
    links = link_parent_child(layers)
    if not layers.get("15M"):
        return _base_payload(asset_name, risk_profiles, chain, "WAIT_15M", "WACHT OP 15M", "HTF-context is aanwezig. Open 15m om te zien hoe prijs de zone benadert en de lokale handelsopzet bouwt.")
    m15_setup = normalize_setup(layers["15M"].get("setup"), timeframe="15M", strict=False)
    if not m15_setup.get("detected"):
        payload = _base_payload(asset_name, risk_profiles, chain, "WAIT_15M_SETUP", "WACHT OP 15M-SETUP", "De HTF-kaart staat. Op 15m is nog geen lokale omkering, uitbraak, vervolgbeweging of rangerotatie bevestigd. De locatie blijft op wacht; er is niets afgekeurd.")
        payload["setup_15m"] = m15_setup
        return payload
    if not m15_setup.get("confirmed") or not m15_setup.get("reviewed") or m15_setup.get("direction") not in {"long", "short"}:
        payload = _base_payload(asset_name, risk_profiles, chain, "REVIEW_15M_SETUP", "CONTROLEER 15M-SETUP", "De grafiekanalyse ziet een mogelijke 15m-opbouw. Controleer type, richting en bewijs voordat de 3m-uitvoering wordt vrijgegeven.")
        payload["setup_15m"] = m15_setup
        return payload
    if not layers.get("3M"):
        payload = _base_payload(asset_name, risk_profiles, chain, "WAIT_3M", "WACHT OP 3M", "De 1D/4H/15m-keten staat. Open 3m om de eerste lokale trendkanteling, liquiditeitsprik met herovering, uitbraak met hertest of vervolgbeweging te lezen.")
        payload["setup_15m"] = m15_setup
        return payload
    if not current_price or current_price <= 0:
        return _base_payload(asset_name, risk_profiles, chain, "WAIT_PRICE", "WACHT OP PRIJS", "Geen betrouwbare actuele prijs beschikbaar. De kaart blijft intact, maar het ticket blijft dicht.")

    m3 = layers["3M"]
    trigger = normalize_trigger(m3.get("trigger"), timeframe="3M", strict=False)
    reference = float(trigger.get("price") or current_price)
    parent = find_parent_zone(layers, reference)
    if not parent:
        payload = _base_payload(asset_name, risk_profiles, chain, "WAIT_HTF_LOCATION", "WACHT OP HTF-LOCATIE", "3m is gelezen, maar de prijs ligt niet aantoonbaar bij een bevestigde 4H- of 1D-zone.")
        payload["price"] = current_price
        payload["parent_links"] = links
        return payload

    child = _find_child_context(layers, parent, reference)
    parent_role = parent.get("role", parent.get("rol"))
    breakout_through_parent = bool(
        trigger.get("type") == "breakout_retest"
        and (
            (trigger.get("direction") == "long" and parent_role == "resistance")
            or (trigger.get("direction") == "short" and parent_role == "support")
        )
    )
    if parent.get("thesis_state") == "invalidated" and not breakout_through_parent:
        payload = _base_payload(asset_name, risk_profiles, chain, "SETUP_INVALIDATED", "THESIS ONGELDIG", "De relevante HTF-zone is expliciet geïnvalideerd. Een lokale M3-kanteling herstelt die thesis niet.")
        payload.update(price=current_price, parent_zone=parent, setup_zone_15m=child, parent_links=links)
        return payload

    if not trigger.get("detected") or trigger.get("type") == "none":
        payload = _base_payload(asset_name, risk_profiles, chain, "WAIT_3M_TURN", "WACHT OP 3M-KANTELING", "Prijs staat bij een HTF-zone. Er is nog geen lokale 3m-kanteling, sweep/reclaim, uitbraak/hertest of vervolgbeweging. De handelsopzet is in ontwikkeling, niet afgekeurd.")
        payload.update(price=current_price, parent_zone=parent, setup_zone_15m=child, parent_links=links)
        return payload

    if not trigger.get("confirmed") or not trigger.get("reviewed") or trigger.get("direction") not in {"long", "short"}:
        payload = _base_payload(asset_name, risk_profiles, chain, "REVIEW_3M_TRIGGER", "CONTROLEER 3M-TRIGGER", "De chartanalyse ziet een mogelijk 3m-signaal. Controleer type, richting, lokale trend ervoor, bewijs en signaalprijs.")
        payload.update(price=current_price, parent_zone=parent, setup_zone_15m=child, trigger=trigger, parent_links=links)
        return payload

    if not trigger.get("ticket_requested"):
        payload = _base_payload(asset_name, risk_profiles, chain, "TRIGGER_CONFIRMED", "3M-SIGNAAL BEVESTIGD", "De lokale 3m-kanteling is gecontroleerd. Er is bewust nog geen orderticket aangevraagd; kies pas bij een echte trade één instapzone en één technische stop.")
        payload.update(price=current_price, parent_zone=parent, setup_zone_15m=child, trigger=trigger, parent_links=links)
        return payload

    direction = trigger["direction"]
    trigger_type = trigger["type"]
    relation = _relation(direction, trigger_type, parent, layers)
    m15_direction_ok = m15_setup.get("direction") == direction

    expected_before = "down" if direction == "long" else "up"
    before = trigger.get("local_trend_before")
    reversal_logic_ok = True
    reversal_note = "Niet van toepassing op een uitbraak"
    if trigger_type in {"local_reversal", "sweep_reclaim", "continuation"}:
        reversal_logic_ok = before == expected_before
        reversal_note = (
            f"lokale {before}-trend kantelt naar {direction}"
            if reversal_logic_ok
            else f"voor een {direction}-kanteling moet de lokale trend ervoor {expected_before} zijn; nu {before}"
        )

    if trigger_type == "breakout_retest":
        context_relation_ok = (direction == "long" and parent_role == "resistance") or (direction == "short" and parent_role == "support")
    else:
        context_relation_ok = (direction == "long" and parent_role == "support") or (direction == "short" and parent_role == "resistance")

    confirmation_count, confirmation_flags = trigger_confirmation_count(trigger)
    trigger_confirmations_ok = confirmation_count >= 2

    desired_role = "support" if direction == "long" else "resistance"
    m3_zones = [zone for zone in m3.get("zones", []) if isinstance(zone, dict) and zone.get("active", True)]
    requested_zone_id = trigger.get("entry_zone_id")
    execution_zone = next((zone for zone in m3_zones if zone.get("id") == requested_zone_id), None)
    if execution_zone is None:
        payload = _base_payload(asset_name, risk_profiles, chain, "TICKET_INPUT_REQUIRED", "KIES INSTAPZONE", "De 3m-trigger is bevestigd, maar het gekozen orderticket verwijst niet naar een bestaande instapzone.")
        payload.update(price=current_price, parent_zone=parent, setup_zone_15m=child, trigger=trigger, parent_links=links)
        return payload
    entry = float(trigger.get("price") or (execution_zone.get("top") if direction == "long" else execution_zone.get("bottom")) or reference)
    stop = finite(trigger.get("stop_loss"))

    # HTF zones define context boundaries, not a second user-entered stop.
    # The only trade stop is the ticket-specific 3M technical stop above.
    if trigger_type == "breakout_retest":
        expected_child_role = "support" if direction == "long" else "resistance"
        child_role = child.get("role", child.get("rol")) if child else None
        htf_invalidation_ok = bool(child and child_role == expected_child_role)
        explicit_boundary = finite(child.get("invalidation")) if child else None
        thesis_invalidation = explicit_boundary or (finite(child.get("bottom" if direction == "long" else "top")) if child else None)
        source_label = "15M expliciete grens" if explicit_boundary is not None else "15M zonegrens"
        thesis_invalidation_detail = f"{source_label} {thesis_invalidation}" if htf_invalidation_ok else "15M rolwisselzone ontbreekt"
    else:
        htf_invalidation_ok = parent_role in {"support", "resistance"}
        explicit_boundary = finite(parent.get("invalidation"))
        thesis_invalidation = explicit_boundary or finite(parent.get("bottom" if direction == "long" else "top"))
        source_label = "HTF expliciete grens" if explicit_boundary is not None else "HTF-zonegrens"
        thesis_invalidation_detail = f"{source_label} {thesis_invalidation}" if htf_invalidation_ok else "HTF-zone ontbreekt"
    geometry_ok = stop is not None and ((direction == "long" and stop < entry) or (direction == "short" and stop > entry))

    targets = collect_targets(layers, direction, entry)
    target_prices = [row["price"] for row in targets[:3]]
    risk = abs(entry - stop) if geometry_ok and stop is not None else 0.0
    rr_values = [round(abs(target - entry) / risk, 2) for target in target_prices] if risk > 0 else []
    rr_max = max(rr_values) if rr_values else 0.0
    enough_targets = len(target_prices) >= 3
    rr_ok = rr_max >= 3.0
    side_ok, side_detail = _side_and_staleness_check(
        direction=direction,
        trigger_type=trigger_type,
        current_price=float(current_price),
        entry=float(entry),
        parent=parent,
        thesis_invalidation=thesis_invalidation,
        first_target=target_prices[0] if target_prices else None,
        trigger=trigger,
    )

    structure = layers["4H"]
    range_low = finite(structure.get("range_low"))
    range_high = finite(structure.get("range_high"))
    range_position = None
    range_known = bool(range_low and range_high and range_high > range_low)
    range_ok = False
    if range_known:
        range_position = (entry - range_low) / (range_high - range_low) * 100
        if trigger_type == "breakout_retest":
            range_ok = True
        else:
            range_ok = range_position <= 40 if direction == "long" else range_position >= 60

    child_ok = child is not None
    freshness_limits = REVIEW_VALID_HOURS
    freshness_checks = {tf: layer_age_hours(layers.get(tf)) <= limit for tf, limit in freshness_limits.items()}
    freshness_ok = all(freshness_checks.values())

    checks = [
        _check("htf_location", "HTF-locatie", True, f"{parent.get('source_timeframe')} {parent_role} · {parent.get('bottom')}–{parent.get('top')}"),
        _check("htf_thesis", "HTF-thesis actief", parent.get("thesis_state") != "invalidated" or breakout_through_parent, "uitbraak door de oude rol" if breakout_through_parent else parent.get("thesis_state", "actief")),
        _check("htf_invalidation", "HTF-zonegrens geldig", htf_invalidation_ok, thesis_invalidation_detail),
        _check("m15_context", "15m-zone bij dezelfde HTF-locatie", child_ok, f"15M {child.get('role')} {child.get('bottom')}–{child.get('top')}" if child else "geen 15M child-zone gekoppeld"),
        _check("m15_setup", "15m-opbouw bevestigd", bool(m15_setup.get("confirmed") and m15_setup.get("reviewed") and m15_direction_ok), f"{setup_label(m15_setup.get('type'))} {m15_setup.get('direction')}"),
        _check("m3_trigger", "3m-signaal bevestigd", True, f"{trigger_label(trigger_type)} {direction}"),
        _check("m3_confirmations", "Minimaal 2 triggerbewijzen", trigger_confirmations_ok, f"{confirmation_count}: {', '.join(confirmation_flags) or 'geen'}"),
        _check("local_turn", "Lokale trendkanteling klopt", reversal_logic_ok, reversal_note),
        _check("context_relation", "Trigger past bij HTF-zone", context_relation_ok, relation),
        _check("price_side", "Prijszijde en geldigheid", side_ok, side_detail),
        _check("m3_stop", "Technische ticketstop geldig", geometry_ok, f"Stop {stop}" if stop else "Stop voor dit ticket ontbreekt"),
        _check("targets", "3 tegengestelde zones", enough_targets, f"{len(target_prices)} doelzone(s) gevonden"),
        _check("rr", "R:R ≥ 1:3", rr_ok, f"max {rr_max:.2f}R"),
        _check("range", "4H-rangecontext", range_ok, "uitbraakregime" if trigger_type == "breakout_retest" else (f"instap op {range_position:.1f}%" if range_position is not None else "4H-range ontbreekt")),
        _check("freshness", "Tijdframeketen actueel", freshness_ok, " · ".join(f"{tf} {layer_age_hours(layers[tf]):.1f}u" for tf in PRIMARY_TIMEFRAMES)),
    ]

    all_critical = all(item["ok"] for item in checks if item.get("critical"))
    orderable = all_critical
    core_candidate = bool(trigger.get("confirmed") and context_relation_ok and geometry_ok)
    failed = [item["label"] for item in checks if not item["ok"]]
    if orderable:
        grade = "A"
        status = "ENTRY_READY"
        label = "INSTAP KLAAR"
        reason = f"3m {trigger_label(trigger_type)} bevestigd bij {parent.get('source_timeframe')} {role_label(parent_role)}. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig."
    elif not rr_ok:
        # Een setup onder 3R is geen B-kandidaat maar een harde no-trade volgens
        # het vastgelegde gebruikersbeleid. Dit voorkomt dat een te lage R:R
        # visueel alsnog als bijna-orderbaar wordt gepresenteerd.
        grade = "C"
        status = "NO_TRADE"
        label = "GEEN TRADE"
        reason = f"R:R-poort geblokkeerd: maximaal {rr_max:.2f}R, minimaal 3.00R vereist."
    else:
        grade = "B" if core_candidate else "C"
        status = "ENTRY_CANDIDATE"
        label = "INSTAPKANDIDAAT"
        reason = "De lokale 3M-kanteling is gevonden, maar eerst oplossen: " + ", ".join(failed)

    trade_type = normalize_trade_type(m3.get("trade_type") or layers["15M"].get("trade_type") or structure.get("trade_type"))
    risk_pct = float(risk_profiles.get(trade_type, 1.0))
    setup = {
        "direction": direction,
        "asset": asset_name,
        "symbol": f"{asset_name}USDT",
        "entry": round(entry, 8),
        "stop_loss": round(stop, 8) if stop is not None else None,
        "htf_thesis_invalidation": round(thesis_invalidation, 8) if thesis_invalidation is not None else None,
        "take_profit": target_prices[2] if len(target_prices) >= 3 else (target_prices[-1] if target_prices else None),
        "take_profits": target_prices,
        "target_sources": targets[:3],
        "target_distribution": [33.33, 33.33, 33.34],
        "rr_per_tp": rr_values,
        "rr_max": rr_max,
        "rr_ok": rr_ok,
        "trade_type": trade_type,
        "risk_pct": risk_pct,
        "initial_risk_pct": risk_pct,
        "risk_policy_source": "OPERATORBELEID",
        "risk_locked": True,
        "origin_timeframe": "3M",
        "lifecycle": "SCALP_ORIGIN",
        "planned_horizon": trade_type.upper(),
        "setup_15m": m15_setup,
        "trigger": trigger,
        "trigger_type": trigger_type,
        "trigger_confirmation_count": confirmation_count,
        "relation_to_context": relation,
        "parent_zone": parent,
        "setup_zone_15m": child,
        "execution_zone": execution_zone,
        "parent_links": links,
        "range_position": round(range_position, 2) if range_position is not None else None,
        "grade": grade,
        "status": "entry_ready" if orderable else ("no_trade" if not rr_ok else "candidate"),
        "confidence": "hoog" if orderable else "controle",
        "rationale": (
            f"{direction.upper()} via bevestigde 3m {trigger_label(trigger_type)} bij {parent.get('source_timeframe')} {role_label(parent_role)}. "
            "De 3M-kanteling mag bewust tegen de binnenkomende lokale beweging ingaan; alleen zone-thesis, prijsgeometrie en controlebewijzen zijn harde grenzen."
        ),
        "management_policy": {
            "break_even": "pas na TP2, terwijl de positie aantoonbaar in winst staat",
            "break_even_source": "OPERATORBELEID",
            "stop_widening": "nooit toegestaan",
        },
        "lifecycle_policy": {
            "origin": "SCALP_ORIGIN",
            "day_runner": "alleen na TP2, risicoreductie, positie in winst en geldige 15M-structuur",
            "swing_runner": "alleen na geldige 4H/1D-structuur; nooit extra oorspronkelijk risico",
        },
    }
    gate = {"status": status, "label": label, "orderable": orderable, "reason": reason, "checks": checks, "failed": failed}
    return {
        "ok": True,
        "version": VERSION,
        "asset": asset_name,
        "symbol": f"{asset_name}USDT",
        "price": current_price,
        "trend": structure.get("trend", "unknown"),
        "setup": setup,
        "execution_gate": gate,
        "decision_chain": chain,
        "risk_profiles": risk_profiles,
        "standing_setups": [setup],
        "market_stack_at": max(text(layer.get("confirmed_at") or layer.get("at"), 80) for layer in layers.values()),
        "parent_links": links,
        "updated_at": utc_now(),
    }


def build_composite_map(stack_value: Any, asset: Any) -> Optional[Dict[str, Any]]:
    asset_name = normalize_asset(asset)
    layers = confirmed_layers(stack_value, asset_name)
    if not layers:
        return None
    zones: List[Dict[str, Any]] = []
    for tf in PRIMARY_TIMEFRAMES:
        for zone in (layers.get(tf) or {}).get("zones", []):
            if isinstance(zone, dict):
                zones.append({**zone, "source_timeframe": tf, "purpose": layer_purpose(tf)})
    structure = layers.get("4H") or layers.get("1D") or next(iter(layers.values()))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "multi-timeframe-confirmed",
        "confirmed": all(tf in layers for tf in ("1D", "4H")),
        "reviewed": True,
        "asset": asset_name,
        "symbol": f"{asset_name}USDT",
        "trend": structure.get("trend", "unknown"),
        "range_low": structure.get("range_low"),
        "range_high": structure.get("range_high"),
        "trade_type": normalize_trade_type((layers.get("3M") or structure).get("trade_type")),
        "zones": zones,
        "layers": layers,
        "parent_links": link_parent_child(layers),
        "timeframes": [tf for tf in PRIMARY_TIMEFRAMES if tf in layers],
        "at": max(text(layer.get("confirmed_at") or layer.get("at"), 80) for layer in layers.values()),
    }


def validate_lifecycle_transition(current: Any, requested: Any, *, risk_reduced: bool, structure_15m_valid: bool, structure_4h_valid: bool) -> Dict[str, Any]:
    current_stage = text(current, 30).upper() or "SCALP_ORIGIN"
    requested_stage = text(requested, 30).upper()
    if current_stage not in LIFECYCLE_STAGES or requested_stage not in LIFECYCLE_STAGES:
        raise ValueError("Ongeldige lifecycle-status")
    if current_stage == "CLOSED":
        raise ValueError("Een gesloten lifecycle kan niet opnieuw worden geopend")
    allowed = {
        "SCALP_ORIGIN": {"DAY_RUNNER", "CLOSED"},
        "DAY_RUNNER": {"SWING_RUNNER", "CLOSED"},
        "SWING_RUNNER": {"CLOSED"},
    }
    if requested_stage not in allowed.get(current_stage, set()):
        raise ValueError(f"Overgang {current_stage} → {requested_stage} is niet toegestaan")
    if requested_stage == "DAY_RUNNER" and not (risk_reduced and structure_15m_valid):
        raise ValueError("Day-runner vereist aantoonbare risicoreductie en geldige 15M-structuur")
    if requested_stage == "SWING_RUNNER" and not (risk_reduced and structure_15m_valid and structure_4h_valid):
        raise ValueError("Swing-runner vereist risicoreductie en geldige 15M- én 4H-structuur")
    return {
        "from": current_stage,
        "to": requested_stage,
        "risk_reduced": bool(risk_reduced),
        "structure_15m_valid": bool(structure_15m_valid),
        "structure_4h_valid": bool(structure_4h_valid),
        "at": utc_now(),
        "risk_may_increase": False,
    }


def migrate_single_map(single_map: Any) -> Dict[str, Any]:
    if not isinstance(single_map, dict) or not single_map.get("confirmed") or not single_map.get("zones"):
        return empty_stack()
    tf_candidates = [normalize_timeframe(zone.get("timeframe")) for zone in single_map.get("zones", []) if isinstance(zone, dict)]
    timeframe = normalize_timeframe(single_map.get("chart_timeframe") or single_map.get("source_timeframe") or (Counter(tf_candidates).most_common(1)[0][0] if tf_candidates else "4H"))
    payload = dict(single_map)
    payload.update(source_timeframe=timeframe, chart_timeframe=timeframe, reviewed=True, confirmed=True)
    try:
        layer = normalize_layer(payload, strict=False)
    except ValueError:
        return empty_stack()
    layer.update(source="legacy-v5-migrated", confirmed=True, reviewed=True, confirmed_at=single_map.get("at") or utc_now())
    return save_layer_in_stack(empty_stack(), layer)
