"""TradingView chart capture and vision normalisation for MyTradingBot v8.

The module deliberately separates fuzzy observation from deterministic trading logic.
Claude may read coloured drawings from a screenshot, but every returned field is
normalised, confidence-scored and marked for human review before it can become an
orderable market map.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageOps

from timeframe_stack import PRIMARY_TIMEFRAMES, layer_purpose, normalize_setup, normalize_timeframe, normalize_trigger

MAX_CAPTURE_BYTES = 9 * 1024 * 1024
MAX_CAPTURE_PIXELS = 32_000_000
MAX_MODEL_WIDTH = 2200
MAX_MODEL_HEIGHT = 1700
MAX_ZONES = 40


VISION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "asset": {"type": "string"},
        "chart_timeframe": {"type": "string"},
        "trend": {"type": "string", "enum": ["up", "down", "range", "unknown"]},
        "approach_direction": {"type": "string", "enum": ["up", "down", "range", "unknown"]},
        "setup": {
            "type": "object",
            "properties": {
                "detected": {"type": "boolean"},
                "type": {"type": "string", "enum": ["none", "reversal", "breakout", "continuation", "range_rotation", "compression"]},
                "direction": {"type": "string", "enum": ["long", "short", "unknown"]},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"}
            },
            "required": ["detected", "type", "direction", "confidence", "evidence"],
            "additionalProperties": False
        },
        "trigger": {
            "type": "object",
            "properties": {
                "detected": {"type": "boolean"},
                "type": {"type": "string", "enum": ["none", "local_reversal", "sweep_reclaim", "breakout_retest", "continuation"]},
                "direction": {"type": "string", "enum": ["long", "short", "unknown"]},
                "local_trend_before": {"type": "string", "enum": ["up", "down", "range", "unknown"]},
                "price": {"type": "number"},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"},
                "evidence_flags": {
                    "type": "object",
                    "properties": {
                        "structure_break_confirmed": {"type": "boolean"},
                        "close_confirmed": {"type": "boolean"},
                        "retest_confirmed": {"type": "boolean"},
                        "sweep_confirmed": {"type": "boolean"},
                        "reclaim_confirmed": {"type": "boolean"},
                        "momentum_shift": {"type": "boolean"},
                        "pullback_confirmed": {"type": "boolean"},
                        "continuation_confirmed": {"type": "boolean"}
                    },
                    "required": ["structure_break_confirmed", "close_confirmed", "retest_confirmed", "sweep_confirmed", "reclaim_confirmed", "momentum_shift", "pullback_confirmed", "continuation_confirmed"],
                    "additionalProperties": False
                }
            },
            "required": ["detected", "type", "direction", "local_trend_before", "price", "confidence", "evidence", "evidence_flags"],
            "additionalProperties": False
        },
        "range_low": {"type": "number"},
        "range_high": {"type": "number"},
        "range_confidence": {"type": "number"},
        "overall_confidence": {"type": "number"},
        "zones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "top": {"type": "number"},
                    "bottom": {"type": "number"},
                    "role": {"type": "string", "enum": ["support", "resistance", "unknown"]},
                    "color": {"type": "string"},
                    "label": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "intent": {"type": "string", "enum": ["structure", "entry", "target", "range_boundary"]},
                    "reason": {"type": "string"},
                    "invalidation": {"type": "number"},
                    "invalidation_detected": {"type": "boolean"},
                    "confirmations": {"type": "integer"},
                    "tests": {"type": "integer"},
                    "confidence": {"type": "number"}
                },
                "required": ["top", "bottom", "role", "color", "label", "timeframe", "intent", "reason", "invalidation", "invalidation_detected", "confirmations", "tests", "confidence"],
                "additionalProperties": False
            }
        },
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["asset", "chart_timeframe", "trend", "approach_direction", "setup", "trigger", "range_low", "range_high", "range_confidence", "overall_confidence", "zones", "warnings"],
    "additionalProperties": False
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _integer(value: Any, default: int = 0, minimum: int = 0, maximum: int = 99) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _confidence(value: Any) -> int:
    return _integer(value, 0, 0, 100)


_WARNING_RULES = (
    (("timeframe", "setup", "trigger"), "Deze grafieklaag wordt alleen gebruikt voor context; setup- en triggerdetectie zijn hier niet van toepassing."),
    (("purple", "ambiguous"), "Een paarse zone heeft geen betrouwbare rol. Controleer handmatig of dit steun, weerstand of alleen context is."),
    (("purple", "zone"), "Een paarse zone is zichtbaar, maar de rol is niet betrouwbaar af te leiden. Controleer deze handmatig."),
    (("price", "axis"), "Een of meer prijzen zijn afgelezen langs de prijsas en kunnen licht afwijken. Controleer de gemarkeerde waarden."),
    (("right", "axis"), "Een of meer prijzen zijn afgelezen langs de prijsas en kunnen licht afwijken. Controleer de gemarkeerde waarden."),
    (("current price", "near"), "De actuele prijs ligt dicht bij een zichtbare zone of rangegrens. Controleer de exacte ligging handmatig."),
    (("resistance", "overhead"), "Er liggen meerdere weerstandsgebieden boven de actuele prijs."),
    (("support", "below"), "Er liggen meerdere steungebieden onder de actuele prijs."),
    (("invalidation", "missing"), "Een Level-2-invalidatie ontbreekt en moet exact worden ingevoerd en gecontroleerd."),
    (("level-2", "missing"), "Een Level-2-invalidatie ontbreekt en moet exact worden ingevoerd en gecontroleerd."),
    (("cropped",), "Een deel van de grafiek of prijsas is afgedekt. Controleer de gemarkeerde prijzen extra zorgvuldig."),
    (("covered",), "Een deel van de grafiek of prijsas is afgedekt. Controleer de gemarkeerde prijzen extra zorgvuldig."),
)


def _normalise_warning(value: Any) -> str:
    """Translate model prose into a small, stable Dutch warning vocabulary.

    Unknown prose is never silently discarded, but is explicitly marked as a raw
    observation so it cannot be mistaken for a deterministic rule.
    """
    text = _text(value, 360)
    if not text:
        return ""
    low = text.lower()
    for tokens, message in _WARNING_RULES:
        if all(token in low for token in tokens):
            return message
    dutch_markers = ("geen ", "een ", "de ", "het ", "prijs ", "zone ", "range ", "waarschuwing")
    if low.startswith(dutch_markers):
        return text[:300]
    return ("Ruwe visionwaarneming — controle vereist: " + text)[:360]


def clean_asset(value: Any) -> str:
    """Convert TradingView symbols such as BYBIT:BTCUSDT.P to BTC."""
    text = _text(value, 80).upper()
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    text = text.replace(".P", "").replace("PERPETUAL", "").replace("PERP", "")
    text = re.sub(r"[^A-Z0-9]", "", text)
    for suffix in ("USDT", "USDC", "BUSD", "USD", "EUR", "BTC"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text[:12] or "BTC"


def decode_capture(image_data: str) -> Image.Image:
    payload = str(image_data or "")
    if "," in payload:
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:  # noqa: BLE001 - converted to a user-facing validation error
        raise ValueError("Ongeldige screenshot-base64") from exc
    if not raw:
        raise ValueError("Screenshot ontbreekt")
    if len(raw) > MAX_CAPTURE_BYTES:
        raise ValueError("Screenshot is te groot")
    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        image.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Screenshot kon niet als afbeelding worden gelezen") from exc
    if image.width * image.height > MAX_CAPTURE_PIXELS:
        raise ValueError("Screenshot bevat te veel pixels")
    if image.width < 320 or image.height < 240:
        raise ValueError("Screenshot is te klein voor chartanalyse")
    return image.convert("RGB")


def crop_chart(image: Image.Image, context: Dict[str, Any]) -> Tuple[Image.Image, Dict[str, Any]]:
    """Crop the visible browser capture to the chart rectangle supplied by the content script.

    `captureVisibleTab` may return device-pixel dimensions while DOM measurements are CSS
    pixels. Scale factors are therefore derived from the actual image and viewport instead
    of trusting devicePixelRatio.
    """
    context = context if isinstance(context, dict) else {}
    viewport = context.get("viewport") if isinstance(context.get("viewport"), dict) else {}
    rect = context.get("chart_rect") if isinstance(context.get("chart_rect"), dict) else {}
    viewport_width = _finite(viewport.get("width"))
    viewport_height = _finite(viewport.get("height"))
    x = _finite(rect.get("x"), -1)
    y = _finite(rect.get("y"), -1)
    width = _finite(rect.get("width"))
    height = _finite(rect.get("height"))

    crop_meta: Dict[str, Any] = {
        "source_width": image.width,
        "source_height": image.height,
        "used_chart_rect": False,
    }
    if viewport_width > 0 and viewport_height > 0 and x >= 0 and y >= 0 and width >= 300 and height >= 220:
        scale_x = image.width / viewport_width
        scale_y = image.height / viewport_height
        left = max(0, int(math.floor(x * scale_x)))
        top = max(0, int(math.floor(y * scale_y)))
        right = min(image.width, int(math.ceil((x + width) * scale_x)))
        bottom = min(image.height, int(math.ceil((y + height) * scale_y)))
        if right - left >= 300 and bottom - top >= 220:
            chart = image.crop((left, top, right, bottom))
            crop_meta.update(
                used_chart_rect=True,
                crop_box=[left, top, right, bottom],
                scale_x=round(scale_x, 4),
                scale_y=round(scale_y, 4),
            )
        else:
            chart = image
    else:
        chart = image

    if chart.width > MAX_MODEL_WIDTH or chart.height > MAX_MODEL_HEIGHT:
        chart.thumbnail((MAX_MODEL_WIDTH, MAX_MODEL_HEIGHT), Image.Resampling.LANCZOS)
        crop_meta["resized"] = True
    else:
        crop_meta["resized"] = False
    crop_meta.update(width=chart.width, height=chart.height)
    return chart, crop_meta


def encode_png(image: Image.Image) -> Tuple[bytes, str, str]:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    raw = output.getvalue()
    return raw, base64.b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()


def _prompt(context: Dict[str, Any]) -> str:
    symbol = _text(context.get("symbol"), 80) or "onbekend"
    timeframe = _text(context.get("timeframe"), 24) or "onbekend"
    page_title = _text(context.get("page_title"), 180)
    return f"""
Je analyseert een gecropte screenshot van het actieve TradingView-chartpaneel voor MyTradingBot.

CONTEXT UIT DE BROWSER
- symboolhint: {symbol}
- timeframehint: {timeframe}
- paginatitel: {page_title}

OPDRACHT
1. Lees uitsluitend handmatig getekende GEKLEURDE horizontale rechthoeken/zones en expliciete gekleurde invalidatielijnen.
2. Negeer volledig: grijze gridlijnen, candles, volume, indicatorlijnen, orderlijnen, de actuele-prijsstippellijn, crosshair en UI-randen.
3. Groen/turquoise = support. Rood/roze = resistance. Voor andere kleuren gebruik je role=unknown tenzij label/context de rol ondubbelzinnig maakt.
4. Lees top en bottom zo exact mogelijk af tegen de rechter prijsas. Gebruik 0 wanneer een getal werkelijk niet betrouwbaar zichtbaar is; verzin nooit een prijs.
5. range_low/range_high alleen invullen als de zichtbare chart of expliciete gekleurde grenzen dit ondersteunen. Anders 0.
6. invalidation alleen als een expliciet getekende invalidatielijn of ondubbelzinnige label zichtbaar is. Anders invalidation=0 en invalidation_detected=false.
7. timeframe: gebruik altijd de browser-timeframehint als bronlaag. Een label mag alleen als extra controle dienen; zones uit deze capture horen bij dezelfde bron-timeframe.
8. confirmations en tests mogen alleen zichtbare, duidelijke reacties/touches tellen. Bij twijfel 0.
9. confidence is 0-100 per zone en overall. Lager bij afgedekte prijsas, overlappende UI, vaag kleurgebruik of twijfel over prijzen.
10. Neem maximaal {MAX_ZONES} echte gebruikerszones op.
11. Bepaal approach_direction als de lokale beweging waarmee prijs de relevante zichtbare zone benadert: up, down, range of unknown.
12. ALLEEN op 15M: beoordeel of een lokale setup zichtbaar is. Gebruik setup.type=reversal, breakout, continuation, range_rotation of compression. Dit is alleen een voorstel en nooit automatisch bevestigd.
13. ALLEEN op 3M: herken een vroege lokale execution-event indien aantoonbaar zichtbaar:
    - local_reversal: lokale trendkanteling; bullish na een lokale dalende beweging richting de zone of bearish na een lokale stijgende beweging richting de zone;
    - sweep_reclaim: sweep gevolgd door aantoonbare reclaim;
    - breakout_retest: breakout/breakdown met close buiten het level en een retest;
    - continuation: lokale pullback gevolgd door aantoonbare hervatting.
14. Vul trigger.evidence_flags letterlijk in. Zet alleen true wanneer zichtbaar: structure_break_confirmed, close_confirmed, retest_confirmed, sweep_confirmed, reclaim_confirmed, momentum_shift, pullback_confirmed, continuation_confirmed.
15. Een 3M reversal tegen de binnenkomende lokale beweging is juist gewenst bij HTF support/resistance en is GEEN timeframeconflict.
16. Bij twijfel: setup/trigger detected=false, type=none, direction=unknown. Verzin nooit een setup of trigger.
17. Zet zone.intent standaard op structure. Alleen een ondubbelzinnig gelabelde uitvoeringszone op 3M mag entry zijn; verzin dit niet.
18. Op andere timeframes dan 15M: setup.detected=false. Op andere timeframes dan 3M: trigger.detected=false.
19. Geen commentary buiten de JSON.
""".strip()


def analyze_with_claude(
    *,
    api_key: str,
    model: str,
    image_base64: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Run Claude vision with JSON-schema output and a compatibility fallback."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": image_base64},
        },
        {"type": "text", "text": _prompt(context)},
    ]
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": 2600,
        "temperature": 0,
        "messages": [{"role": "user", "content": content}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": VISION_SCHEMA,
            }
        },
    }
    try:
        response = client.messages.create(**kwargs)
    except TypeError:
        # Older SDK compatibility. The same schema is appended to the prompt and the
        # deterministic normaliser below still refuses malformed output.
        kwargs.pop("output_config", None)
        content[-1]["text"] += "\n\nJSON-SCHEMA:\n" + json.dumps(VISION_SCHEMA, ensure_ascii=False)
        response = client.messages.create(**kwargs)
    if getattr(response, "stop_reason", None) in {"refusal", "max_tokens"}:
        raise RuntimeError(f"Vision stopte met reden: {response.stop_reason}")
    text = "".join(getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Vision gaf geen geldige JSON terug")
        return json.loads(text[start : end + 1])


def _zone_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    high = min(float(a["top"]), float(b["top"]))
    low = max(float(a["bottom"]), float(b["bottom"]))
    overlap = max(0.0, high - low)
    width = max(float(a["top"]) - float(a["bottom"]), float(b["top"]) - float(b["bottom"]), 1e-12)
    return overlap / width


def _merge_zones(zones: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for zone in sorted(zones, key=lambda item: float(item["top"]), reverse=True):
        match = next(
            (
                item
                for item in merged
                if item.get("role") == zone.get("role")
                and item.get("role") != "unknown"
                and _zone_overlap(item, zone) >= 0.65
            ),
            None,
        )
        if match is None:
            merged.append(dict(zone))
            continue
        match["top"] = round(max(float(match["top"]), float(zone["top"])), 8)
        match["bottom"] = round(min(float(match["bottom"]), float(zone["bottom"])), 8)
        match["confidence"] = max(int(match.get("confidence", 0)), int(zone.get("confidence", 0)))
        match["tests"] = max(int(match.get("tests", 0)), int(zone.get("tests", 0)))
        match["confirmations"] = max(int(match.get("confirmations", 0)), int(zone.get("confirmations", 0)))
        labels = [part for part in [match.get("label"), zone.get("label")] if part]
        match["label"] = " / ".join(dict.fromkeys(labels))[:120]
        if match.get("invalidation_source") != "detected" and zone.get("invalidation_source") == "detected":
            match["invalidation"] = zone.get("invalidation")
            match["invalidation_source"] = "detected"
    return merged[:MAX_ZONES]


def normalize_vision_result(
    raw: Dict[str, Any],
    *,
    context: Dict[str, Any],
    image_hash: str,
    crop_meta: Dict[str, Any],
    previous: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    browser_symbol = _text(context.get("symbol"), 80)
    asset = clean_asset(browser_symbol or raw.get("asset"))
    browser_timeframe = normalize_timeframe(context.get("timeframe"))
    model_timeframe = normalize_timeframe(raw.get("chart_timeframe"))
    chart_timeframe = browser_timeframe if browser_timeframe in PRIMARY_TIMEFRAMES else model_timeframe
    trend = _text(raw.get("trend"), 16).lower()
    if trend not in {"up", "down", "range", "unknown"}:
        trend = "unknown"

    zones: List[Dict[str, Any]] = []
    for index, item in enumerate(raw.get("zones") or []):
        if not isinstance(item, dict):
            continue
        top = _finite(item.get("top"))
        bottom = _finite(item.get("bottom"))
        if top <= 0 or bottom <= 0:
            continue
        top, bottom = max(top, bottom), min(top, bottom)
        if top - bottom < 0:
            continue
        role = _text(item.get("role"), 16).lower()
        if role not in {"support", "resistance", "unknown"}:
            role = "unknown"
        confidence = _confidence(item.get("confidence"))
        timeframe = chart_timeframe
        intent = _text(item.get("intent"), 30).lower()
        if intent not in {"structure", "entry", "target", "range_boundary"}:
            intent = "structure"
        if chart_timeframe == "3M" and intent == "entry":
            # Vision may identify a nearby zone, but it may never arm a ticket.
            intent = "structure"
        label = _text(item.get("label"), 120)
        reason = _text(item.get("reason"), 300)
        if not reason:
            human_role = {"support": "support", "resistance": "resistance", "unknown": "gekleurde"}[role]
            reason = f"Handmatig getekende {human_role}-zone uit TradingView"
            if label:
                reason += f": {label}"
        detected_invalidation = bool(item.get("invalidation_detected"))
        invalidation = _finite(item.get("invalidation")) if detected_invalidation else 0.0
        geometry_valid = (
            (role == "support" and 0 < invalidation < bottom)
            or (role == "resistance" and invalidation > top)
        )
        if not geometry_valid:
            # Never invent a Level-2 invalidation. A chart screenshot can auto-fill
            # the coloured zone, but an orderable stop must be explicitly visible
            # or entered and reviewed by the trader.
            invalidation = 0.0
            invalidation_source = "missing"
        else:
            invalidation_source = "detected"

        confirmations = _integer(item.get("confirmations"), 0, 0, 10)
        tests = _integer(item.get("tests"), 0, 0, 99)
        review_fields = ["top", "bottom"]
        if role == "unknown":
            review_fields.append("role")
        if invalidation_source != "detected":
            review_fields.append("invalidation")
        if not timeframe:
            review_fields.append("timeframe")
        if confidence < 75:
            review_fields.extend(["confirmations", "tests"])
        zones.append(
            {
                "id": str(uuid.uuid4()),
                "top": round(top, 8),
                "bottom": round(bottom, 8),
                "kind": "level" if abs(top - bottom) <= max(abs(top), 1.0) * 1e-9 else "zone",
                "role": role,
                "rol": role,
                "color": _text(item.get("color"), 30),
                "label": label,
                "timeframe": timeframe,
                "source_timeframe": chart_timeframe,
                "purpose": layer_purpose(chart_timeframe),
                "intent": intent,
                "reason": reason,
                "invalidation": round(invalidation, 8) if invalidation > 0 else None,
                "invalidation_source": invalidation_source,
                "confirmations": confirmations,
                "tests": tests,
                "confidence": confidence,
                "review_fields": sorted(set(review_fields)),
                "active": True,
                "source": "tradingview-vision",
                "source_label": "TRADINGVIEW-CHART",
                "provenance": {"kind": "chart_capture", "image_hash": image_hash, "timeframe": chart_timeframe},
            }
        )
    zones = _merge_zones(zones)

    range_low = _finite(raw.get("range_low"))
    range_high = _finite(raw.get("range_high"))
    range_source = "vision"
    range_confidence = _confidence(raw.get("range_confidence"))
    if range_low <= 0 or range_high <= range_low:
        # A tradable range must be explicitly visible or manually confirmed.
        # Do not derive it from the outermost zones: that would turn a vision guess
        # into a mechanical 0-40/40-60/60-100 gate.
        range_low = 0.0
        range_high = 0.0
        range_source = "missing"
        range_confidence = 0

    approach_direction = _text(raw.get("approach_direction"), 16).lower()
    if approach_direction not in {"up", "down", "range", "unknown"}:
        approach_direction = "unknown"

    setup = normalize_setup(raw.get("setup"), timeframe=chart_timeframe, strict=False)
    setup["confirmed"] = False
    setup["reviewed"] = False
    if chart_timeframe != "15M":
        setup.update(detected=False, type="none", direction="unknown", confidence=0, evidence="")

    trigger = normalize_trigger(raw.get("trigger"), timeframe=chart_timeframe, strict=False)
    # Vision output is always a proposal. The trader must confirm it in the cockpit.
    trigger["confirmed"] = False
    trigger["reviewed"] = False
    if chart_timeframe != "3M":
        trigger.update(detected=False, type="none", direction="unknown", price=None, confidence=0, evidence="")
        trigger["evidence_flags"] = {name: False for name in ("structure_break_confirmed", "close_confirmed", "retest_confirmed", "sweep_confirmed", "reclaim_confirmed", "momentum_shift", "pullback_confirmed", "continuation_confirmed")}

    # Vision may suggest a 3M trigger, but a routine chart sync never turns a
    # map zone into an order entry and never asks for a stop. Ticket selection
    # happens only after explicit user opt-in in the cockpit.

    warnings = [_normalise_warning(item) for item in raw.get("warnings") or [] if _normalise_warning(item)]
    if not zones:
        warnings.append("Geen betrouwbare gekleurde TradingView-zones gevonden.")
    if range_source != "vision":
        warnings.append("Range was niet expliciet leesbaar. Vul 4H range-low en range-high handmatig in of teken duidelijke rangegrenzen.")
    if any(zone.get("role") == "unknown" for zone in zones):
        warnings.append("Minimaal één gekleurde zone heeft nog geen betrouwbare support/resistance-rol.")
    if chart_timeframe == "15M" and setup.get("detected"):
        warnings.append("Vision ziet een mogelijke 15M-setup. Controleer richting, type en evidence voordat deze actief wordt.")
    if chart_timeframe == "3M" and trigger.get("detected"):
        warnings.append("Vision ziet een mogelijke 3M-trigger. Controleer iedere evidence-vlag; de lokale kanteling wordt nooit automatisch orderbaar.")

    overall_confidence = _confidence(raw.get("overall_confidence"))
    if zones:
        zone_average = sum(int(zone.get("confidence", 0)) for zone in zones) / len(zones)
        overall_confidence = int(round((overall_confidence + zone_average) / 2)) if overall_confidence else int(round(zone_average))
    if range_source != "vision":
        overall_confidence = min(overall_confidence, 68)
    if not zones:
        overall_confidence = 0

    revision = str(uuid.uuid4())
    draft: Dict[str, Any] = {
        "schema_version": 71,
        "revision": revision,
        "source": "tradingview-vision",
        "source_label": "TRADINGVIEW-CHART",
        "provenance": {"kind": "chart_capture", "image_hash": image_hash, "browser_symbol": browser_symbol, "timeframe": chart_timeframe},
        "confirmed": False,
        "review_status": "needs_review",
        "asset": asset,
        "symbol": f"{asset}USDT",
        "chart_timeframe": chart_timeframe,
        "source_timeframe": chart_timeframe,
        "purpose": layer_purpose(chart_timeframe),
        "approach_direction": approach_direction,
        "setup": setup,
        "trigger": trigger,
        "range_low": round(range_low, 8) if range_low > 0 else None,
        "range_high": round(range_high, 8) if range_high > 0 else None,
        "range_source": range_source,
        "range_confidence": range_confidence,
        "trend": trend,
        "trade_type": "day",
        "origin_timeframe": "3M" if chart_timeframe == "3M" else None,
        "zones": zones,
        "levels": sorted({p for zone in zones for p in (zone["top"], zone["bottom"])}, reverse=True),
        "overall_confidence": overall_confidence,
        "warnings": list(dict.fromkeys(warnings)),
        "image_hash": image_hash,
        "chart_context": {
            "symbol": browser_symbol,
            "timeframe": browser_timeframe,
            "url": _text(context.get("url"), 500),
            "page_title": _text(context.get("page_title"), 180),
            "trigger": _text(context.get("trigger"), 40),
            "current_price": _finite(context.get("current_price")) or None,
            "current_price_source": _text(context.get("current_price_source"), 80) or "tradingview-dom",
            "captured_at": _text(context.get("captured_at"), 80),
        },
        "crop": crop_meta,
        "at": utc_now(),
        "order_ready": False,
    }
    draft["diff"] = compute_diff(previous or {}, draft)
    return draft


def _zone_mid(zone: Dict[str, Any]) -> float:
    return (float(zone.get("top") or 0) + float(zone.get("bottom") or 0)) / 2


def _match_zone(zone: Dict[str, Any], candidates: List[Dict[str, Any]], used: set[int]) -> Optional[int]:
    role = zone.get("role", zone.get("rol"))
    mid = _zone_mid(zone)
    width = max(float(zone.get("top") or 0) - float(zone.get("bottom") or 0), abs(mid) * 0.0005, 1e-8)
    best: Tuple[float, Optional[int]] = (float("inf"), None)
    for index, candidate in enumerate(candidates):
        if index in used:
            continue
        candidate_role = candidate.get("role", candidate.get("rol"))
        if role != candidate_role:
            continue
        distance = abs(mid - _zone_mid(candidate))
        candidate_width = max(float(candidate.get("top") or 0) - float(candidate.get("bottom") or 0), abs(mid) * 0.0005, 1e-8)
        tolerance = max(width, candidate_width) * 1.6
        if distance <= tolerance and distance < best[0]:
            best = (distance, index)
    return best[1]


def compute_diff(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    old_zones = [item for item in previous.get("zones", []) if isinstance(item, dict)] if isinstance(previous, dict) else []
    new_zones = [item for item in current.get("zones", []) if isinstance(item, dict)] if isinstance(current, dict) else []
    used: set[int] = set()
    added: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for zone in new_zones:
        match_index = _match_zone(zone, old_zones, used)
        if match_index is None:
            added.append(zone)
            continue
        used.add(match_index)
        old = old_zones[match_index]
        price_delta = max(abs(float(zone.get("top") or 0) - float(old.get("top") or 0)), abs(float(zone.get("bottom") or 0) - float(old.get("bottom") or 0)))
        reference = max(abs(_zone_mid(zone)), 1.0)
        if price_delta / reference > 0.00035 or zone.get("role") != old.get("role", old.get("rol")):
            changed.append({"before": old, "after": zone})
    removed = [zone for index, zone in enumerate(old_zones) if index not in used]
    range_changed = False
    if previous:
        old_low, old_high = _finite(previous.get("range_low")), _finite(previous.get("range_high"))
        new_low, new_high = _finite(current.get("range_low")), _finite(current.get("range_high"))
        reference = max(new_high, old_high, 1.0)
        range_changed = max(abs(new_low - old_low), abs(new_high - old_high)) / reference > 0.0005
    return {
        "added": len(added),
        "changed": len(changed),
        "removed": len(removed),
        "range_changed": range_changed,
        "summary": f"{len(added)} toegevoegd · {len(changed)} gewijzigd · {len(removed)} verwijderd",
    }
