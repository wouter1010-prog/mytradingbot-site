"""Deterministic day-start coach for MyTradingBot.

This module is presentation and coaching logic only. It reads the already-built
overview payload and never mutates the market stack, trade lifecycle, risk policy
or execution gate. It deliberately produces scenarios instead of trade advice.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

TIMEFRAMES = ("1D", "4H", "15M", "3M")
MIDRANGE_LOW = 40.0
MIDRANGE_HIGH = 60.0


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any, limit: int = 800) -> str:
    return str(value or "").strip()[:limit]


def _normal(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value).lower()).strip()


def _layer_rows(overview: Dict[str, Any]) -> List[Dict[str, Any]]:
    health = overview.get("stack_health") or {}
    rows = health.get("layers") or []
    return [row for row in rows if isinstance(row, dict)]


def _layer_map(overview: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _layer_rows(overview)
    return {str(row.get("timeframe") or "").upper(): row for row in rows}


def _confirmed_layers(overview: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    market = overview.get("market_map") or overview.get("composite_map") or {}
    layers = market.get("layers") if isinstance(market, dict) else {}
    return {str(key).upper(): value for key, value in (layers or {}).items() if isinstance(value, dict)}


def _trend(value: Any, language: str) -> str:
    normal = _normal(value)
    english = language.startswith("en")
    mapping = {
        "up": ("stijgend", "rising"),
        "bullish": ("stijgend", "rising"),
        "down": ("dalend", "falling"),
        "bearish": ("dalend", "falling"),
        "range": ("zijwaarts", "ranging"),
        "sideways": ("zijwaarts", "ranging"),
        "unknown": ("onbekend", "unknown"),
        "": ("onbekend", "unknown"),
    }
    pair = mapping.get(normal, (normal or "onbekend", normal or "unknown"))
    return pair[1] if english else pair[0]


def _review_block(overview: Dict[str, Any]) -> Tuple[bool, List[str]]:
    health = overview.get("stack_health") or {}
    rows = _layer_rows(overview)
    missing = [str(row.get("timeframe")) for row in rows if not row.get("present")]
    stale = [str(row.get("timeframe")) for row in rows if row.get("present") and not row.get("fresh")]
    unverified = [str(row.get("timeframe")) for row in rows if row.get("present") and row.get("confirmed") is False]
    expired_review = [str(row.get("timeframe")) for row in rows if row.get("present") and row.get("review_fresh") is False]
    if not health.get("capture_complete") or missing:
        return True, missing or list(health.get("missing_timeframes") or [])
    if stale or not health.get("fresh"):
        return True, stale
    if unverified or expired_review:
        return True, list(dict.fromkeys(unverified + expired_review))
    gate = ((overview.get("latest") or {}).get("execution_gate") or {})
    if str(gate.get("status") or "") == "REVIEW_STACK":
        return True, list((overview.get("latest") or {}).get("blocking_review_timeframes") or [])
    return False, []


def _range_context(overview: Dict[str, Any]) -> Dict[str, Any]:
    latest = overview.get("latest") or {}
    price = _finite(((latest.get("price_status") or {}).get("price")))
    market = overview.get("market_map") or overview.get("composite_map") or {}
    low = _finite((market or {}).get("range_low"))
    high = _finite((market or {}).get("range_high"))
    position = None
    if price is not None and low is not None and high is not None and high > low:
        position = (price - low) / (high - low) * 100.0
    if position is None:
        setup_position = _finite(((latest.get("setup") or {}).get("range_position")))
        position = setup_position
    if position is None:
        bucket = "unknown"
    elif position < MIDRANGE_LOW:
        bucket = "lower"
    elif position <= MIDRANGE_HIGH:
        bucket = "middle"
    else:
        bucket = "upper"
    return {"position_pct": round(position, 1) if position is not None else None, "bucket": bucket}


def _zones(overview: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    layers = _confirmed_layers(overview)
    out: List[Dict[str, Any]] = []
    for timeframe in ("4H", "1D", "15M", "3M"):
        for zone in (layers.get(timeframe) or {}).get("zones") or []:
            if not isinstance(zone, dict) or _normal(zone.get("role")) != role:
                continue
            out.append({**zone, "source_timeframe": timeframe})
    return out


def _has_sweep_context(overview: Dict[str, Any]) -> bool:
    latest = overview.get("latest") or {}
    trigger = (latest.get("setup") or {}).get("trigger") or latest.get("trigger_3m") or {}
    text = " ".join([
        _text(trigger.get("type")),
        _text(trigger.get("evidence")),
        _text(((latest.get("execution_gate") or {}).get("reason"))),
    ]).lower()
    return any(term in text for term in ("sweep", "liquid", "stop hunt", "stop-hunt", "stophunt"))


def _recent_rows(overview: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    rows = [row for row in ((overview.get("journal") or {}).get("trades") or []) if isinstance(row, dict)]
    rows.sort(key=lambda row: _text(row.get("closed_at") or row.get("time") or row.get("at")))
    return rows[-limit:]


def _current_loss_streak(rows: Sequence[Dict[str, Any]]) -> int:
    streak = 0
    for row in reversed(rows):
        pnl = _finite(row.get("pnl")) or 0.0
        if pnl < 0:
            streak += 1
            continue
        break
    return streak


def _recent_midrange_pattern(rows: Sequence[Dict[str, Any]]) -> int:
    count = 0
    for row in rows[-5:]:
        blob = " ".join(_text(row.get(key)) for key in ("lesson", "thesis", "process_judgement", "management")).lower()
        if "midrange" in blob or "midden" in blob or "middle of the range" in blob:
            count += 1
    return count


def _recent_process_deviation(rows: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for row in rows[-5:] if row.get("rules_followed") is False or str(row.get("process_grade") or "").upper() == "C")


def _local_time_context(now: Optional[datetime] = None) -> Dict[str, Any]:
    zone = ZoneInfo("Europe/Amsterdam")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(zone)

    def delta_to(hour: int, minute: int) -> int:
        target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < local:
            target += timedelta(days=1)
        return int((target - local).total_seconds() // 60)

    return {
        "weekday": local.strftime("%A"),
        "local_iso": local.isoformat(),
        "minutes_to_1530": delta_to(15, 30),
        "minutes_to_0200": delta_to(2, 0),
    }


def day_start_dossier_numbers(context: Dict[str, Any]) -> List[str]:
    numbers = ["03", "04", "15"]
    if context.get("sweep_context"):
        numbers.append("10")
    if int(context.get("current_loss_streak") or 0) >= 2:
        numbers.extend(["12", "14"])
    elif int(context.get("process_deviation_count") or 0) > 0:
        numbers.append("12")
    seen: set[str] = set()
    return [number for number in numbers if not (number in seen or seen.add(number))]


def build_day_start_context(overview: Dict[str, Any], now: Optional[datetime] = None, supplemental_lessons: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    blocked, blocking_layers = _review_block(overview)
    rows = _recent_rows(overview)
    account = overview.get("account") or {}
    positions = [row for row in (account.get("positions") or []) if isinstance(row, dict)]
    layers = _layer_map(overview)
    lessons = [row for row in (supplemental_lessons or []) if isinstance(row, dict)]
    first_lesson = lessons[0] if lessons else {}
    context = {
        "blocked": blocked,
        "blocking_layers": blocking_layers,
        "capture_complete": bool((overview.get("stack_health") or {}).get("capture_complete")),
        "fresh": bool((overview.get("stack_health") or {}).get("fresh")),
        "layer_trends": {tf: _text((layers.get(tf) or {}).get("trend") or "unknown") for tf in TIMEFRAMES},
        "range": _range_context(overview),
        "support_available": bool(_zones(overview, "support")),
        "resistance_available": bool(_zones(overview, "resistance")),
        "sweep_context": _has_sweep_context(overview),
        "open_position": positions[0] if positions else None,
        "lifecycles": overview.get("lifecycles") or {},
        "recent_trades": rows,
        "current_loss_streak": _current_loss_streak(rows),
        "midrange_pattern_count": _recent_midrange_pattern(rows),
        "process_deviation_count": _recent_process_deviation(rows),
        "journal_stats": (overview.get("journal") or {}).get("stats") or {},
        "time": _local_time_context(now),
        "gate_status": _text((((overview.get("latest") or {}).get("execution_gate") or {}).get("status"))),
        "knowledge_focus": {
            "lesson_id": _text(first_lesson.get("lesson_id") or first_lesson.get("id"), 160),
            "type": _text(first_lesson.get("type") or first_lesson.get("category"), 60).lower(),
            "tags": [str(value).lower()[:80] for value in (first_lesson.get("tags") or []) if str(value).strip()][:12],
        } if first_lesson else {},
        "knowledge_lesson_ids": [_text(row.get("lesson_id") or row.get("id"), 160) for row in lessons if _text(row.get("lesson_id") or row.get("id"), 160)],
    }
    context["dossier_numbers"] = day_start_dossier_numbers(context)
    return context


def _position_management(context: Dict[str, Any], language: str) -> Optional[Dict[str, str]]:
    position = context.get("open_position")
    if not isinstance(position, dict):
        return None
    lifecycles = ((context.get("lifecycles") or {}).get("records") or {})
    symbol = _text(position.get("symbol")).upper()
    record = next((row for row in lifecycles.values() if isinstance(row, dict) and _text(row.get("symbol")).upper() == symbol and _text(row.get("stage")).upper() != "CLOSED"), None)
    stage = _text((record or {}).get("stage")).upper()
    english = language.startswith("en")
    if stage in {"DAY_RUNNER", "SWING_RUNNER"}:
        rule = (
            "TP2 has been confirmed in the lifecycle. You may only move the stop manually into profit while the remaining position is still profitable; never widen it."
            if english else
            "TP2 is in de lifecycle bevestigd. Je mag de stop alleen handmatig in profit zetten zolang het restant nog in winst staat; nooit verruimen."
        )
    else:
        rule = (
            "Keep the technical stop where it belongs. TP1 changes nothing; only after TP2, and only while the remaining position is profitable, may you move the stop manually into profit."
            if english else
            "Laat de technische stop staan. TP1 verandert niets; pas na TP2, en alleen zolang het restant in winst staat, mag je de stop handmatig in profit zetten."
        )
    return {
        "title": "Position management first" if english else "Eerst je lopende positie",
        "body": rule,
    }


def _where_we_are(context: Dict[str, Any], language: str) -> List[str]:
    english = language.startswith("en")
    trends = context.get("layer_trends") or {}
    first = (
        f"1D is {_trend(trends.get('1D'), language)}, 4H is {_trend(trends.get('4H'), language)}, and 15M/3M are {_trend(trends.get('15M'), language)} / {_trend(trends.get('3M'), language)}."
        if english else
        f"1D is {_trend(trends.get('1D'), language)}, 4H is {_trend(trends.get('4H'), language)} en 15M/3M zijn {_trend(trends.get('15M'), language)} / {_trend(trends.get('3M'), language)}."
    )
    range_ctx = context.get("range") or {}
    pct = range_ctx.get("position_pct")
    bucket = range_ctx.get("bucket")
    if pct is None:
        second = "The exact range position is not reliable yet, so location remains a check, not a conclusion." if english else "De exacte plek in de range is nog niet betrouwbaar, dus locatie blijft een controlepunt en geen conclusie."
    elif bucket == "middle":
        second = f"Price is around {pct:.1f}% of the 4H range: midrange, so doing nothing is the default." if english else f"Prijs staat rond {pct:.1f}% van de 4H-range: midrange, dus niets doen is de standaard."
    elif bucket == "lower":
        second = f"Price is around {pct:.1f}% of the 4H range: the lower part, where only a confirmed long scenario may earn attention." if english else f"Prijs staat rond {pct:.1f}% van de 4H-range: de onderkant, waar alleen een bevestigde longscenario aandacht mag krijgen."
    else:
        second = f"Price is around {pct:.1f}% of the 4H range: the upper part, where only a confirmed short scenario may earn attention." if english else f"Prijs staat rond {pct:.1f}% van de 4H-range: de bovenkant, waar alleen een bevestigd shortscenario aandacht mag krijgen."
    return [first, second]


def _scenarios(context: Dict[str, Any], language: str) -> List[Dict[str, str]]:
    english = language.startswith("en")
    out: List[Dict[str, str]] = []
    bucket = (context.get("range") or {}).get("bucket")
    support = bool(context.get("support_available"))
    resistance = bool(context.get("resistance_available"))

    if support and bucket in {"lower", "middle", "unknown"}:
        out.append({
            "if": "IF price reaches a confirmed 4H support zone and momentum stalls" if english else "ALS prijs een bevestigde 4H-steunzone bereikt en het momentum stokt",
            "then": "THEN assess a possible long idea through A-B-C; this is still not a trade" if english else "DAN beoordeel je via A-B-C of er een longidee ontstaat; dit is nog steeds geen trade",
            "invalidated": "This scenario expires if the zone no longer holds on a full candle close." if english else "Dit scenario vervalt wanneer de zone op een volledige candle-close niet meer houdt.",
        })
    if resistance and bucket in {"upper", "middle", "unknown"}:
        out.append({
            "if": "IF price reaches a confirmed 4H resistance zone and momentum stalls" if english else "ALS prijs een bevestigde 4H-weerstandszone bereikt en het momentum stokt",
            "then": "THEN assess a possible short idea through A-B-C; this is still not a trade" if english else "DAN beoordeel je via A-B-C of er een shortidee ontstaat; dit is nog steeds geen trade",
            "invalidated": "This scenario expires if the zone no longer holds on a full candle close." if english else "Dit scenario vervalt wanneer de zone op een volledige candle-close niet meer houdt.",
        })
    if support or resistance:
        boundary = "relevant range boundary" if english else "relevante rangegrens"
        out.append({
            "if": f"IF price closes decisively through the {boundary}" if english else f"ALS prijs overtuigend door de {boundary} sluit",
            "then": "THEN do nothing until a retest proves that the break holds" if english else "DAN doe je niets totdat een hertest bewijst dat de uitbraak houdt",
            "invalidated": "This scenario expires if price returns inside the range without holding the retest." if english else "Dit scenario vervalt wanneer prijs zonder houdende hertest terug de range in komt.",
        })
    return out[:3]


def _no_trade(context: Dict[str, Any], language: str) -> Dict[str, Any]:
    english = language.startswith("en")
    bucket = (context.get("range") or {}).get("bucket")
    if bucket == "middle":
        reason = "price is in the middle of the 4H range and neither extreme has earned a decision" if english else "prijs midden in de 4H-range staat en geen van beide uitersten een beslissing heeft verdiend"
        prominent = True
    elif not context.get("support_available") and not context.get("resistance_available"):
        reason = "there is no confirmed decision zone to work from" if english else "er geen bevestigde besliszone beschikbaar is"
        prominent = True
    else:
        reason = "none of the conditional scenarios may complete" if english else "geen van de voorwaardelijke scenario's compleet hoeft te worden"
        prominent = False
    body = (
        f"There is a real chance today is a watching day because {reason}. That is a process win, not a loss."
        if english else
        f"Grote kans dat vandaag een kijkdag is omdat {reason}. Dat is proceswinst, geen verlies."
    )
    return {"title": "The no-trade scenario" if english else "Het geen-trade-scenario", "body": body, "prominent": prominent}


def _process_focus(context: Dict[str, Any], language: str) -> Dict[str, str]:
    english = language.startswith("en")
    streak = int(context.get("current_loss_streak") or 0)
    midrange = int(context.get("midrange_pattern_count") or 0)
    deviations = int(context.get("process_deviation_count") or 0)
    if streak >= 2:
        body = (
            f"You are on a {streak}-record losing streak. No revenge, no immediate re-entry: only one fully written A-B-C process may earn attention, and a rule deviation ends the session."
            if english else
            f"Je zit op een verliesreeks van {streak} sluitingsrecords. Geen revenge en geen directe herkansing: alleen een volledig uitgeschreven A-B-C-proces krijgt aandacht, en bij een regelafwijking stopt de sessie."
        )
    elif midrange >= 2:
        body = "Your recent notes repeatedly mention midrange. Today you only work from the extremes; the middle is observation." if english else "In je recente notities komt midrange meerdere keren terug. Vandaag werk je alleen vanaf de uitersten; het midden is observatie."
    elif deviations:
        body = "Your recent process contains a rule deviation. Before any action, write down A, B and C and name the invalidation in words." if english else "Je recente proces bevat een regelafwijking. Schrijf vóór iedere actie A, B en C uit en benoem de invalidatie in woorden."
    else:
        body = "Your focus is simple: location first, then loss of momentum, then candle-close confirmation. A scenario without C is waiting." if english else "Je focus is eenvoudig: eerst locatie, dan momentum eruit, daarna confirmatie op candle-close. Een scenario zonder C is wachten."
    timing = context.get("time") or {}
    if int(timing.get("minutes_to_1530") or 9999) <= 60:
        body += " The 15:30 window is close; observe the reaction and do not anticipate it." if english else " Het 15:30-moment is dichtbij; observeer de reactie en loop er niet op vooruit."
    elif int(timing.get("minutes_to_0200") or 9999) <= 60:
        body += " The 02:00 window is close; let the move print before interpreting it." if english else " Het 02:00-moment is dichtbij; laat de beweging eerst ontstaan voordat je haar interpreteert."
    knowledge = context.get("knowledge_focus") or {}
    category = _normal(knowledge.get("type"))
    tags = set(knowledge.get("tags") or [])
    focus_term = next((tag for tag in knowledge.get("tags") or [] if re.fullmatch(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ -]{2,40}", tag)), "")
    if category in {"mindset", "psychologie", "discipline"} or tags & {"discipline", "geduld", "patience", "revenge"}:
        body += " Knowledge focus: protect the quality of your next decision, not the number of trades." if english else " Kennisfocus: bescherm de kwaliteit van je volgende beslissing, niet het aantal trades."
    elif category in {"entry", "confirmatie", "confirmation", "execution"} or tags & {"confirmatie", "confirmation", "trigger", "entry"}:
        body += " Knowledge focus: location is only A; wait for B and C before treating anything as actionable." if english else " Kennisfocus: locatie is alleen A; wacht op B en C voordat iets uitvoerbaar wordt."
    elif category in {"risk", "risico", "management"} or tags & {"risk", "risico", "management", "stop"}:
        body += " Knowledge focus: keep risk and management mechanical; a new lesson never changes the cockpit limits." if english else " Kennisfocus: houd risico en management mechanisch; een nieuwe les verandert de cockpitlimieten nooit."
    elif category in {"zone", "context", "range", "structuur"} or tags & {"zone", "range", "context", "structuur"}:
        body += " Knowledge focus: read location first and accept that the middle of the range may offer no decision." if english else " Kennisfocus: lees eerst de locatie en accepteer dat het midden van de range geen beslissing hoeft te geven."
    if focus_term:
        body += (f" Today's lens: {focus_term}; use it only as an observation aid, never as a standalone signal." if english else f" Kijklens vandaag: {focus_term}; gebruik dit alleen als observatiehulp, nooit als zelfstandig signaal.")
    return {"title": "Your process focus today" if english else "Jouw procesfocus vandaag", "body": body}


def _checklist(language: str) -> List[str]:
    if language.startswith("en"):
        return [
            "Is this a well-confirmed idea at the start of a move, or am I chasing?",
            "Am I late in the move or already pressing into the next resistance/support?",
            "Am I already near the next higher-timeframe level, meaning patience is the correct action?",
        ]
    return [
        "Ligt dit goed geconfirmeerd aan het begin van de beweging, of jaag ik prijs achterna?",
        "Ben ik laat in de beweging of druk ik al tegen de volgende steun/weerstand aan?",
        "Zit ik al bij het opvolgende higher-timeframe-level, waardoor geduld de juiste actie is?",
    ]


def _blocked_briefing(context: Dict[str, Any], language: str) -> Dict[str, Any]:
    english = language.startswith("en")
    layers = ", ".join(context.get("blocking_layers") or []) or ("one or more layers" if english else "een of meer lagen")
    return {
        "language": language,
        "blocked": True,
        "title": "Refresh your charts first" if english else "Vernieuw eerst je charts",
        "reason": (
            f"The day-start coach will not build scenarios because {layers} is missing, stale or requires a material review. Read only those charts again; then return."
            if english else
            f"De dagstart-coach maakt geen scenario's omdat {layers} ontbreekt, verouderd is of een materiële hercontrole vraagt. Lees alleen die charts opnieuw en kom daarna terug."
        ),
        "action": "Refresh charts" if english else "Charts vernieuwen",
        "sections": [],
    }


def build_day_start_briefing(context: Dict[str, Any], language: str = "nl") -> Dict[str, Any]:
    language = "en" if str(language).lower().startswith("en") else "nl"
    if context.get("blocked"):
        return _blocked_briefing(context, language)
    management = _position_management(context, language)
    sections: List[Dict[str, Any]] = []
    if management:
        sections.append({"key": "position_management", **management})
    sections.extend([
        {"key": "where_we_are", "title": "Where we are" if language == "en" else "Waar staan we", "lines": _where_we_are(context, language)},
        {"key": "scenarios", "title": "Scenarios" if language == "en" else "Scenario's", "items": _scenarios(context, language)},
        {"key": "no_trade", **_no_trade(context, language)},
        {"key": "process_focus", **_process_focus(context, language)},
        {"key": "checklist", "title": "Three day-start questions" if language == "en" else "De drie dagstart-toetsvragen", "items": _checklist(language)},
    ])
    return {
        "language": language,
        "blocked": False,
        "title": "Your day-start briefing" if language == "en" else "Jouw dagstart-briefing",
        "subtitle": "Scenarios, never predictions. No trade is a valid outcome." if language == "en" else "Scenario's, nooit voorspellingen. Geen trade is een volwaardige uitkomst.",
        "sections": sections,
    }


def build_bilingual_day_start(overview: Dict[str, Any], now: Optional[datetime] = None, supplemental_lessons: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    context = build_day_start_context(overview, now=now, supplemental_lessons=supplemental_lessons)
    return {
        "ok": True,
        "blocked": bool(context.get("blocked")),
        "briefings": {
            "nl": build_day_start_briefing(context, "nl"),
            "en": build_day_start_briefing(context, "en"),
        },
        "context": {
            "dossier_count": len(context.get("dossier_numbers") or []),
            "range_position_pct": (context.get("range") or {}).get("position_pct"),
            "range_bucket": (context.get("range") or {}).get("bucket"),
            "open_position": bool(context.get("open_position")),
            "current_loss_streak": int(context.get("current_loss_streak") or 0),
            "generated_at": (context.get("time") or {}).get("local_iso"),
            "knowledge_lesson_ids": context.get("knowledge_lesson_ids") or [],
        },
    }


def briefing_has_price_advice(briefing: Dict[str, Any]) -> bool:
    """Guard used by tests and the route before returning a briefing.

    Percentages and clock times are allowed. Concrete price advice after entry,
    stop or target language is not.
    """
    blob = str(briefing)
    pattern = re.compile(r"\b(?:entry|instap|stop(?:-loss)?|target|doel|tp\d?)\b[^\n]{0,40}\b\d{3,}(?:[.,]\d+)?\b", re.I)
    return bool(pattern.search(blob))
