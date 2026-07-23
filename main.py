"""MyTradingBot Brain v8.2.2 — rustige multi-timeframe chart stack en veilige M3-uitvoering.

Fixed workflow:
    1D context -> 4H structure/location -> 15M setup -> 3M execution.

TradingView drawings remain the source of truth. Vision only proposes a draft;
only a user-reviewed layer is stored in the confirmed stack. Every timeframe is
stored independently, so a 3M sync can never overwrite 15M/4H/1D context.

The browser extension may prepare and read back a TradingView/Bybit ticket. This
backend never sends an order to Bybit and the extension never clicks the final
Buy/Sell/Submit/Confirm action.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from flask import Flask, Response, jsonify, request, send_file, g

import core_services as services
import beta_access
from knowledge_retrieval import prompt_lessons, rank_knowledge, source_cards
from coach_dossiers import coach_instruction, dossier_context, deterministic_dossier_answer, sanitise_coach_answer
from day_start_coach import build_bilingual_day_start, briefing_has_price_advice
from telegram_day_start import start_telegram_day_start_scheduler, telegram_day_start_status
from weekly_mentor import build_bilingual_weekly_mentor_report, start_weekly_mentor_scheduler, weekly_mentor_status
from account_guards import (
    ACCOUNT_GUARD_RELEASE,
    activate_commitment,
    build_account_guard_snapshot,
)
from journal_pattern_gates import (
    JOURNAL_PATTERN_GATE_RELEASE,
    activate_suggestion as activate_pattern_suggestion,
    apply_active_rules as apply_journal_pattern_rules,
    build_snapshot as build_journal_pattern_snapshot,
    deactivate_rule as deactivate_pattern_rule,
)
from discipline_progress import (
    DISCIPLINE_RELEASE,
    build_discipline_snapshot,
    record_day_start,
    record_no_trade,
)
from chart_sync import analyze_with_claude, crop_chart, decode_capture, encode_png, normalize_vision_result
from timeframe_stack import (
    PRIMARY_TIMEFRAMES,
    VERSION as ENGINE_VERSION,
    build_composite_map,
    build_decision,
    build_stack_health,
    empty_stack,
    ensure_stack,
    get_latest_layer,
    get_layer,
    layer_purpose,
    migrate_single_map,
    normalize_asset,
    normalize_layer,
    normalize_timeframe,
    public_stack,
    save_layer_in_stack,
)
from trade_lifecycle import close as close_lifecycle
from trade_lifecycle import create_record as create_lifecycle_record
from trade_lifecycle import evaluate as evaluate_lifecycle
from trade_lifecycle import promote as promote_lifecycle

VERSION = "8.2.2"
SCHEMA_VERSION = 86
KNOWLEDGE_RELEASE = "KB-R23-AUTO"
COACH_RELEASE = "R23-AUTO-LESSONS"
AUTOMATION_RELEASE = "R24A-TELEGRAM-DAYSTART"
COACH_LOOP_RELEASE = "R24B-POST-TRADE-COACH-LOOP"
WEEKLY_MENTOR_RELEASE = "R24C-WEEKLY-MENTOR"
PROCESS_FIRST_RELEASE = DISCIPLINE_RELEASE
ACCOUNT_GUARD_NAME = "account_guards_r25b.json"
JOURNAL_PATTERN_GATE_NAME = "journal_pattern_gates_r25c.json"
JOURNAL_PATTERN_RELEASE = JOURNAL_PATTERN_GATE_RELEASE
UX_RELEASE = "8.2.9"
TOKEN_MIN_LENGTH = 32
RISK_PROFILES: Dict[str, float] = {"scalp": 0.5, "day": 1.0, "swing": 2.0}
MAX_ACTIVITY = 1600
MAX_CHART_CACHE = 128
TEST_MODE = os.environ.get("MYTRADINGBOT_TEST_MODE", "0") == "1"
COACH_SHOW_SOURCES = os.environ.get("MYTRADINGBOT_COACH_SHOW_SOURCES", "0") == "1"

# One-release migration bridge: accept the previous secret name so Railway and
# the extension can be upgraded without an avoidable authentication outage.
API_TOKEN = (os.environ.get("MYTRADINGBOT_API_TOKEN") or os.environ.get("DOOPIECASH_API_TOKEN") or "").strip()
ALLOWED_ORIGINS = {
    item.strip().rstrip("/")
    for item in os.environ.get("MYTRADINGBOT_ALLOWED_ORIGINS", "").split(",")
    if item.strip()
}
DATA_DIR = Path(os.environ.get("DATA_DIR") or services.DATA_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)

MARKET_STACK_NAME = "market_stack_v8.json"
MARKET_STACK_LEGACY_NAMES = ("market_stack_v6.json", "market_stack_v51.json")
CHART_DRAFT_NAME = "chart_drafts_v8.json"
CHART_DRAFT_LEGACY_NAMES = ("chart_drafts_v6.json", "chart_drafts_v51.json", "chart_drafts_v5.json", "chart_draft_v5.json", "chart_draft_v4.json")
CHART_HISTORY_NAME = "chart_history_v8.json"
CHART_PREVIEW_NAME = "chart_previews_v8"
ACTIVITY_NAME = "activity_v8.json"
LIFECYCLE_NAME = "trade_lifecycle_v8.json"
SETTINGS_NAME = "cockpit_settings_v8.json"
FEEDBACK_NAME = "beta_feedback_v8.json"
PROFILE_NAME = "profile.json"
DISCIPLINE_NAME = "discipline_progress_r25a.json"

DASHBOARD_FILE = Path(__file__).with_name("mytradingbot-dashboard.html")
DASHBOARD_CSS_FILE = Path(__file__).with_name("dashboard.css")
DASHBOARD_JS_FILE = Path(__file__).with_name("dashboard.js")
METHODOLOGY_FILE = Path(__file__).with_name("mytradingbot_methodology.md")
METHOD_SOURCES_FILE = Path(__file__).with_name("methodology_sources.json")
KNOWLEDGE_CATALOG_FILE = Path(__file__).with_name("knowledge_sources.json")

PUBLIC_PATHS = {
    "/", "/dashboard", "/health", "/favicon.ico",
    "/assets/dashboard.css", "/assets/dashboard.js",
    "/api/v2/beta/public-config", "/api/v2/beta/redeem",
}
STATE_LOCK = threading.RLock()
RATE_LOCK = threading.Lock()
RATE_STATE: Dict[Tuple[str, str], List[float]] = {}
INSTRUMENT_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
INSTRUMENT_FAILURE_CACHE: Dict[str, float] = {}
PRICE_CACHE: Dict[str, Any] = {"prices": {}, "asset_at": {}, "attempted_at": {}}
PRICE_REFRESH_LOCK = threading.Lock()
PRICE_REFRESHING: set[str] = set()

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=12 * 1024 * 1024, JSON_SORT_KEYS=False)
KNOWLEDGE_WORKER = services.start_background_worker()
ACCOUNT_WORKER = services.start_account_worker()
TELEGRAM_DAY_START_WORKER = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_text(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def integer(value: Any, default: int = 0, minimum: int = 0, maximum: int = 999) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    value = finite(os.environ.get(name), default)
    return max(minimum, min(maximum, float(value if value is not None else default)))


COMMITMENT_MAX_DAILY_LOSS_PCT = env_float("MYTRADINGBOT_COMMITMENT_MAX_DAILY_LOSS_PCT", 2.0, 0.25, 10.0)
REVENGE_COOLDOWN_MINUTES = integer(os.environ.get("MYTRADINGBOT_REVENGE_COOLDOWN_MINUTES"), 30, 1, 1440)


def safe_load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def load_methodology_sources() -> Dict[str, Any]:
    value = safe_load_json(METHOD_SOURCES_FILE, {})
    if not isinstance(value, dict):
        return {"version": VERSION, "rules": [], "policies": {}}
    value.setdefault("version", VERSION)
    value.setdefault("rules", [])
    value.setdefault("policies", {})
    return value


def commercialization_status() -> Dict[str, Any]:
    """Expose an honest release gate for a commercial product."""
    return {
        "deployment_mode": "multi_workspace_private_beta",
        "private_beta_ready": True,
        "multi_workspace": True,
        "tester_invites": True,
        "tester_data_isolation": True,
        "automatic_final_click": False,
        "commercial_content_clean": False,
        "external_knowledge_rights_verified": False,
        "external_knowledge_ingestion_default": "disabled",
        "brand_clearance_completed": False,
        "chrome_store_approved": False,
        "independent_security_review_completed": False,
        "legal_review_completed": False,
        "billing_and_provisioning_ready": False,
        "database_migration_ready": False,
        "disaster_recovery_tested": False,
        "live_testnet_orders_verified": integer(os.environ.get("MYTRADINGBOT_VERIFIED_TESTNET_ORDERS"), 0, 0, 100000),
        "sale_ready": False,
        "sale_blockers": [
            "Doopie Cash-videokennis is alleen voor privégebruik gemarkeerd; schriftelijke commerciële gebruiksrechten ontbreken",
            "merknaam MyTradingBot moet juridisch worden vrijgegeven; er bestaan al gelijknamige tradingproducten",
            "bestandsopslag moet voor publieke SaaS naar transactionele tenant-opslag met back-ups en hersteltests",
            "Chrome Web Store review, privacyverklaring en onafhankelijke securitytest ontbreken",
            "juridische review voor risicoverklaring, voorwaarden, privacy en toepasselijke financiële regelgeving ontbreekt",
            "betalingen, automatische provisioning, account recovery, support-SLA en incidentproces ontbreken",
            "load-, herstart-, duplicaat- en meerdaagse stabiliteitstests met externe testers zijn nog niet volledig bewezen",
        ],
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK:
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOCK:
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def iso_age_seconds(value: Any) -> Optional[float]:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def token_from_request() -> str:
    explicit = (
        request.headers.get("X-MyTradingBot-Token", "").strip()
        or request.headers.get("X-DoopieCash-Token", "").strip()
    )
    if explicit:
        return explicit
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def resolve_principal(candidate: str) -> Optional[Dict[str, Any]]:
    try:
        return beta_access.resolve_token(candidate, API_TOKEN)
    except RuntimeError:
        return None


def current_principal() -> Dict[str, Any]:
    """Return the request principal, or the owner outside a request context.

    Core helpers are also exercised by offline tests and background jobs where
    Flask's request-local ``g`` object is unavailable. Falling back to owner in
    that specific context preserves the single-workspace runtime while keeping
    request authentication strict.
    """
    try:
        principal = getattr(g, "principal", None)
    except RuntimeError:
        principal = None
    if isinstance(principal, dict):
        return principal
    return {"workspace_id": "owner", "display_name": "Owner", "role": "owner", "mode": "live", "capabilities": ["*"]}


def is_owner() -> bool:
    return current_principal().get("role") == "owner"


def require_owner() -> Optional[Response]:
    if not is_owner():
        return jsonify(ok=False, error="Alleen de eigenaar kan deze beta-instelling wijzigen"), 403
    return None


def workspace_root() -> Path:
    principal = current_principal()
    if principal.get("role") == "owner":
        return DATA_DIR
    workspace_id = re.sub(r"[^a-z0-9-]", "", str(principal.get("workspace_id") or "tester").lower())[:64] or "tester"
    root = DATA_DIR / "workspaces" / workspace_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def workspace_file(name: str) -> Path:
    return workspace_root() / name


def workspace_profile() -> Dict[str, Any]:
    path = workspace_file(PROFILE_NAME)
    value = safe_load_json(path, {})
    principal = current_principal()
    if not isinstance(value, dict):
        value = {}
    value.setdefault("workspace_id", principal.get("workspace_id"))
    value.setdefault("display_name", principal.get("display_name"))
    value.setdefault("mode", principal.get("mode"))
    value.setdefault("manual_equity", 10000.0)
    return value


def save_workspace_profile(value: Dict[str, Any]) -> Dict[str, Any]:
    profile = workspace_profile()
    if "display_name" in value:
        profile["display_name"] = safe_text(value.get("display_name"), 80) or profile.get("display_name")
    if "manual_equity" in value:
        amount = finite(value.get("manual_equity"))
        if amount is None or amount <= 0 or amount > 100000000:
            raise ValueError("Handmatige rekeningwaarde moet positief zijn")
        profile["manual_equity"] = round(amount, 2)
    profile["updated_at"] = utc_now()
    atomic_write_json(workspace_file(PROFILE_NAME), profile)
    return profile


def rate_allowed(bucket: str, limit: int, seconds: int) -> bool:
    key = (request.remote_addr or "unknown", bucket)
    now = time.time()
    with RATE_LOCK:
        entries = [stamp for stamp in RATE_STATE.get(key, []) if now - stamp < seconds]
        if len(entries) >= limit:
            RATE_STATE[key] = entries
            return False
        entries.append(now)
        RATE_STATE[key] = entries
    return True


def origin_allowed(origin: str) -> bool:
    origin = origin.rstrip("/")
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    if origin.startswith("chrome-extension://"):
        return True
    return bool(re.fullmatch(r"https://([a-z0-9-]+\.)*tradingview\.com", origin, re.I))


@app.before_request
def auth_guard() -> Optional[Response]:
    if request.method == "OPTIONS":
        return Response(status=204)
    if request.path in PUBLIC_PATHS:
        g.principal = {"workspace_id": "public", "display_name": "Publiek", "role": "public", "mode": "public", "capabilities": []}
        return None
    if len(API_TOKEN) < TOKEN_MIN_LENGTH:
        return jsonify(ok=False, error=f"MYTRADINGBOT_API_TOKEN ontbreekt of is korter dan {TOKEN_MIN_LENGTH} tekens"), 503
    principal = resolve_principal(token_from_request())
    if not principal:
        return jsonify(ok=False, error="Niet geautoriseerd of beta-toegang ingetrokken"), 401
    g.principal = principal
    if request.method == "GET" and request.path in {"/reset", "/process", "/check"}:
        return jsonify(ok=False, error="Oude muterende GET-route uitgeschakeld; gebruik de beveiligde POST-route"), 410
    return None


@app.after_request
def security_headers(response: Response) -> Response:
    origin = request.headers.get("Origin", "")
    if origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin.rstrip("/")
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-MyTradingBot-Token, X-DoopieCash-Token"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.path.startswith("/api/") or request.path in {"/", "/dashboard", "/assets/dashboard.css", "/assets/dashboard.js", "/health"}:
        response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-cache")
    response.headers["X-MyTradingBot-Version"] = VERSION
    if request.path in {"/", "/dashboard"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    return response


# ---------------------------------------------------------------------------
# Persistent multi-timeframe state


def load_market_stack() -> Dict[str, Any]:
    value = safe_load_json(workspace_file(MARKET_STACK_NAME), None)
    if isinstance(value, dict) and isinstance(value.get("assets"), dict):
        return ensure_stack(value)
    old = next((safe_load_json(workspace_file(name), None) for name in MARKET_STACK_LEGACY_NAMES if workspace_file(name).exists()), None)
    if isinstance(old, dict) and isinstance(old.get("assets"), dict):
        migrated = ensure_stack(old)
        atomic_write_json(workspace_file(MARKET_STACK_NAME), migrated)
        return migrated
    if is_owner():
        legacy_map = safe_load_json(Path(services.USER_LEVELS), {})
        migrated = migrate_single_map(legacy_map)
        if migrated.get("assets"):
            atomic_write_json(workspace_file(MARKET_STACK_NAME), migrated)
            return migrated
    return empty_stack()


def save_market_layer(layer: Dict[str, Any]) -> Dict[str, Any]:
    stack = save_layer_in_stack(load_market_stack(), layer)
    atomic_write_json(workspace_file(MARKET_STACK_NAME), stack)
    return stack


def load_chart_drafts() -> Dict[str, Any]:
    value = safe_load_json(workspace_file(CHART_DRAFT_NAME), None)
    if isinstance(value, dict) and isinstance(value.get("assets"), dict):
        return ensure_stack(value)
    for path in [workspace_file(name) for name in CHART_DRAFT_LEGACY_NAMES]:
        old = safe_load_json(path, None)
        if not isinstance(old, dict):
            continue
        if isinstance(old.get("assets"), dict):
            migrated = ensure_stack(old)
            atomic_write_json(workspace_file(CHART_DRAFT_NAME), migrated)
            return migrated
        if isinstance(old.get("zones"), list) and old.get("zones"):
            candidate = dict(old)
            candidate.setdefault("source_timeframe", old.get("chart_timeframe") or old.get("timeframe") or "4H")
            try:
                layer = normalize_layer(candidate, strict=False)
            except ValueError:
                continue
            revision = safe_text(old.get("revision") or old.get("sync_id"), 120) or str(uuid.uuid4())
            layer.update({
                "source": "legacy-chart-draft",
                "confirmed": False,
                "reviewed": False,
                "review_status": "needs_review",
                "revision": revision,
                "sync_id": revision,
                "image_hash": old.get("image_hash") or old.get("screenshot_hash"),
                "diff": old.get("diff") if isinstance(old.get("diff"), dict) else {},
                "warnings": list(old.get("warnings") or []) + ["Gemigreerde v5-draft: controleer deze timeframe-laag opnieuw."],
                "at": old.get("at") or utc_now(),
            })
            migrated = save_layer_in_stack(empty_stack(), layer)
            atomic_write_json(workspace_file(CHART_DRAFT_NAME), migrated)
            return migrated
    return empty_stack()


def save_chart_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    stack = save_layer_in_stack(load_chart_drafts(), draft)
    atomic_write_json(workspace_file(CHART_DRAFT_NAME), stack)
    return stack


def preview_path(asset: Any, timeframe: Any) -> Path:
    safe_asset = normalize_asset(asset)
    safe_tf = re.sub(r"[^A-Z0-9]", "", normalize_timeframe(timeframe)) or "UNKNOWN"
    return workspace_file(CHART_PREVIEW_NAME) / f"{safe_asset}_{safe_tf}.png"


def chart_public(layer: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(layer, dict):
        return None
    out = dict(layer)
    out["age_seconds"] = round(iso_age_seconds(out.get("last_seen_at") or out.get("at")) or 0.0, 1)
    out["source_timeframe"] = normalize_timeframe(out.get("source_timeframe") or out.get("chart_timeframe"))
    out["purpose"] = layer_purpose(out["source_timeframe"])
    out["preview_available"] = preview_path(out.get("asset"), out["source_timeframe"]).exists()
    out["preview_url"] = f"/api/v1/chart/preview/{normalize_asset(out.get('asset'))}/{out['source_timeframe']}"
    out.pop("raw_model_output", None)
    return out


def public_drafts(value: Any) -> Dict[str, Any]:
    stack = public_stack(value)
    for row in (stack.get("assets") or {}).values():
        if not isinstance(row, dict):
            continue
        for tf, layer in (row.get("layers") or {}).items():
            if isinstance(layer, dict):
                layer.update(chart_public(layer) or {})
                layer["preview_url"] = f"/api/v1/chart/preview/{normalize_asset(layer.get('asset'))}/{normalize_timeframe(tf)}"
    return stack


def load_chart_cache() -> List[Dict[str, Any]]:
    value = safe_load_json(workspace_file(CHART_HISTORY_NAME), [])
    return [row for row in value if isinstance(row, dict)][-MAX_CHART_CACHE:] if isinstance(value, list) else []


def save_chart_cache(item: Dict[str, Any]) -> None:
    with STATE_LOCK:
        marker = f"{item.get('hash')}|{normalize_asset(item.get('asset'))}|{normalize_timeframe(item.get('timeframe'))}"
        rows = [
            row for row in load_chart_cache()
            if f"{row.get('hash')}|{normalize_asset(row.get('asset'))}|{normalize_timeframe(row.get('timeframe'))}" != marker
        ]
        rows.append(item)
        atomic_write_json(workspace_file(CHART_HISTORY_NAME), rows[-MAX_CHART_CACHE:])


def find_chart_cache(image_hash: str, asset: Any, timeframe: Any) -> Optional[Dict[str, Any]]:
    asset_name = normalize_asset(asset)
    tf = normalize_timeframe(timeframe)
    for row in reversed(load_chart_cache()):
        if (
            hmac.compare_digest(str(row.get("hash") or ""), image_hash)
            and normalize_asset(row.get("asset")) == asset_name
            and normalize_timeframe(row.get("timeframe")) == tf
            and isinstance(row.get("draft"), dict)
        ):
            return dict(row["draft"])
    return None


# ---------------------------------------------------------------------------
# Activity, journal, knowledge, account


def load_activity_log() -> List[Dict[str, Any]]:
    paths = [workspace_file(ACTIVITY_NAME)]
    if is_owner():
        paths = [DATA_DIR / name for name in ("activity_v4.json", "activity_v5.json", "activity_v51.json", "activity_v6.json", ACTIVITY_NAME)]
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        value = safe_load_json(path, [])
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            marker = safe_text(item.get("id"), 120) or "|".join(safe_text(item.get(key), 120) for key in ("type", "symbol", "at", "note")) or f"{path.name}:{index}"
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
    merged.sort(key=lambda item: str(item.get("at") or ""))
    return merged[-MAX_ACTIVITY:]


def append_activity(event: Dict[str, Any]) -> Dict[str, Any]:
    with STATE_LOCK:
        rows = load_activity_log()
        event_id = safe_text(event.get("id"), 120) or str(uuid.uuid4())
        existing = next((row for row in rows if str(row.get("id")) == event_id), None)
        if existing:
            return existing
        trade_type = safe_text(event.get("trade_type"), 20).lower()
        if trade_type not in RISK_PROFILES:
            trade_type = ""
        clean = {
            "id": event_id,
            "type": safe_text(event.get("type"), 50),
            "symbol": safe_text(event.get("symbol"), 24).upper(),
            "asset": normalize_asset(event.get("asset") or event.get("symbol")) if (event.get("asset") or event.get("symbol")) else "",
            "timeframe": normalize_timeframe(event.get("timeframe")) if event.get("timeframe") else "",
            "direction": safe_text(event.get("direction"), 12).lower(),
            "trade_type": trade_type,
            "setup_type": safe_text(event.get("setup_type"), 40).lower(),
            "trigger_type": safe_text(event.get("trigger_type"), 40).lower(),
            "relation_to_context": safe_text(event.get("relation_to_context"), 60).upper(),
            "setup_grade": safe_text(event.get("setup_grade"), 4).upper(),
            "risk_pct": RISK_PROFILES.get(trade_type),
            "entry": finite(event.get("entry")),
            "stop_loss": finite(event.get("stop_loss")),
            "take_profits": [finite(value) for value in event.get("take_profits", []) if finite(value) is not None][:3],
            "qty": finite(event.get("qty")),
            "equity": finite(event.get("equity")),
            "risk_usd": finite(event.get("risk_usd")),
            "leverage": finite(event.get("leverage")),
            "ticket_verified": bool(event.get("ticket_verified", False)),
            "note": safe_text(event.get("note"), 500),
            "at": safe_text(event.get("at"), 80) or utc_now(),
        }
        rows.append(clean)
        # Store only the v6 subset; the reader merges previous histories.
        own = safe_load_json(workspace_file(ACTIVITY_NAME), [])
        own = own if isinstance(own, list) else []
        own.append(clean)
        atomic_write_json(workspace_file(ACTIVITY_NAME), own[-MAX_ACTIVITY:])
        return clean


def normalise_journal_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Expose coverage-aware performance metrics and stable dashboard aliases."""
    out = dict(stats or {})
    records = integer(out.get("records", out.get("trades")), 0, 0, 1_000_000)
    wins = integer(out.get("wins"), 0, 0, records)
    losses = integer(out.get("losses"), 0, 0, records)
    breakeven = max(0, records - wins - losses)
    sample_label = out.get("sample_label") or (
        "betrouwbaarder" if records >= 100 else "in opbouw" if records >= 30
        else "te kleine steekproef" if records >= 10 else "onvoldoende trades" if records else "geen data"
    )
    out.update(
        records=records, trades=records, total=records, wins=wins, losses=losses, breakeven=breakeven,
        sample_sufficient=records >= 30, sample_reliable=records >= 100, sample_label=sample_label,
    )
    if records <= 0:
        out.update(winrate=None, winrate_display="—", profit_factor=None, profit_factor_infinite=False, profit_factor_display="—")
    else:
        winrate = finite(out.get("winrate"))
        if winrate is None:
            winrate = round(wins / records * 100, 2)
        out["winrate"] = winrate
        out["winrate_display"] = f"{wins}/{records} · {round(winrate)}%"
        if records < 10:
            out["profit_factor_display"] = "Nog onvoldoende records"
        elif out.get("profit_factor_infinite"):
            out["profit_factor_display"] = "∞ · nog geen verliesrecord"
        elif finite(out.get("profit_factor")) is not None:
            out["profit_factor_display"] = str(round(float(out["profit_factor"]), 2)).replace(".", ",")
        else:
            out["profit_factor_display"] = "—"
    out["snapshot_coverage_pct"] = finite(out.get("snapshot_coverage"), 0.0)
    out["source_coverage_pct"] = finite(out.get("source_coverage"), 0.0)
    out["percentage_metrics_available"] = bool(out.get("percentage_metrics_available"))
    return out

def normalise_journal_rows(rows: Any, deepdives: Any = None) -> List[Dict[str, Any]]:
    """Return a stable, UI-safe journal schema.

    Bybit's closed-PnL ``side`` is the closing side: Sell closes a long and Buy
    closes a short. Exposing that value directly made the journal show the wrong
    direction. The dashboard now receives an explicit position direction and a
    matching deepdive when available.
    """
    source_rows = rows if isinstance(rows, list) else []
    dive_rows = deepdives if isinstance(deepdives, list) else []
    dives_by_id = {
        str(item.get("_id")): item
        for item in dive_rows
        if isinstance(item, dict) and item.get("_id") not in (None, "")
    }
    out: List[Dict[str, Any]] = []
    for item in source_rows:
        if not isinstance(item, dict):
            continue
        side = safe_text(item.get("side"), 12).lower()
        explicit_direction = safe_text(item.get("direction"), 12).lower()
        direction = explicit_direction if explicit_direction in {"long", "short"} else (
            "long" if side == "sell" else "short" if side == "buy" else "unknown"
        )
        pnl = finite(item.get("pnl"), 0.0) or 0.0
        entry_price = finite(item.get("entry") or item.get("avgEntryPrice"))
        exit_price = finite(item.get("exit") or item.get("avgExitPrice"))
        direction_consistency = "unavailable"
        direction_consistency_reason = "Instap, uitstap of richting ontbreekt"
        if direction in {"long", "short"} and entry_price is not None and exit_price is not None and pnl != 0:
            expected_move = (exit_price - entry_price) * (1 if direction == "long" else -1)
            tolerance = max(abs(entry_price) * 1e-8, 1e-8)
            if abs(expected_move) <= tolerance:
                direction_consistency = "unavailable"
                direction_consistency_reason = "Prijsverschil is te klein voor een betrouwbare richtingcontrole"
            elif (expected_move > 0) == (pnl > 0):
                direction_consistency = "verified"
                direction_consistency_reason = "Richting, prijsverloop en resultaat zijn onderling consistent"
            else:
                direction_consistency = "mismatch"
                direction_consistency_reason = "Resultaatteken past niet bij richting × (uitstap − instap); bronrecord handmatig controleren"
        pnl_pct = finite(item.get("pnl_pct"))
        equity_snapshot = finite(item.get("equity_snapshot"))
        if pnl_pct is None and equity_snapshot and equity_snapshot > 0:
            pnl_pct = round(pnl / equity_snapshot * 100, 4)
        trade_id = safe_text(item.get("_id") or item.get("orderId") or item.get("execId"), 120)
        dive = dives_by_id.get(trade_id, {})
        grade = safe_text(dive.get("proces_grade") or item.get("proces_grade"), 4).upper()
        result = "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven"
        source_class = services.journal_source_class(item)
        source_label = safe_text(item.get("source_label"), 100) or services.SOURCE_LABELS.get(source_class, "ONBEKEND")
        out.append({
            "id": trade_id,
            "source": safe_text(item.get("source"), 60),
            "source_class": source_class,
            "source_label": source_label,
            "origin_class": safe_text(item.get("origin_class"), 40) or "UNKNOWN",
            "origin_label": safe_text(item.get("origin_label"), 80) or "HERKOMST ONBEKEND",
            "verified_source": source_class == "BYBIT_VERIFIED",
            "performance_eligible": source_class not in {"PAPER", "TESTDATA"},
            "test_data": source_class == "TESTDATA" or item.get("test_data") is True,
            "record_kind": safe_text(item.get("record_kind"), 40) or ("BYBIT_CLOSE_RECORD" if source_class == "BYBIT_VERIFIED" else "JOURNAL_RECORD"),
            "pnl_basis": safe_text(item.get("pnl_basis"), 60) or ("BYBIT_CLOSED_PNL_NET" if source_class == "BYBIT_VERIFIED" else "JOURNAL_PNL"),
            "symbol": safe_text(item.get("symbol") or item.get("asset"), 32).upper(),
            "asset": normalize_asset(item.get("symbol") or item.get("asset") or "BTC"),
            "direction": direction,
            "close_side": side,
            "entry": entry_price,
            "exit": exit_price,
            "direction_consistency": direction_consistency,
            "direction_consistency_reason": direction_consistency_reason,
            "direction_verified": direction_consistency == "verified",
            "pnl": round(pnl, 8),
            "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
            "equity_snapshot": equity_snapshot,
            "equity_snapshot_basis": safe_text(item.get("equity_snapshot_basis"), 60),
            "closed_at": safe_text(item.get("closed_at") or item.get("time") or item.get("at"), 80),
            "updated_time_ms": finite(item.get("updated_time_ms") or item.get("updatedTime")),
            "result": result,
            "trade_type": safe_text(item.get("trade_type"), 20).lower(),
            "origin_timeframe": normalize_timeframe(item.get("origin_timeframe") or "3M"),
            "setup_type": safe_text(item.get("setup_type") or item.get("setup"), 40).lower(),
            "trigger_type": safe_text(item.get("trigger_type"), 40).lower(),
            "relation_to_context": safe_text(item.get("relation_to_context"), 60).upper(),
            "setup_grade": safe_text(item.get("setup_grade"), 4).upper(),
            "risk_pct": finite(item.get("risk_pct")),
            "stop_loss": finite(item.get("stop_loss") or item.get("sl")),
            "take_profits": [finite(value) for value in (item.get("take_profits") or []) if finite(value) is not None][:3],
            "qty": finite(item.get("qty") or item.get("size")),
            "closed_size": finite(item.get("closed_size") or item.get("closedSize") or item.get("qty")),
            "fill_count": integer(item.get("fill_count") or item.get("fillCount"), 0, 0, 100000),
            "leverage": finite(item.get("leverage")),
            "raw_order_id": safe_text(item.get("raw_order_id") or item.get("orderId"), 120),
            "planned_risk_usd": finite(item.get("planned_risk_usd") or item.get("risk_usd")),
            "r_multiple": finite(item.get("r_multiple") or item.get("realized_r")),
            "r_breach_alarm": bool(item.get("r_breach_alarm")),
            "r_breach_reason": safe_text(item.get("r_breach_reason"), 300),
            "open_fee": finite(item.get("open_fee") or item.get("openFee")),
            "close_fee": finite(item.get("close_fee") or item.get("closeFee")),
            "fees": finite(item.get("fees"), 0.0),
            "funding": finite(item.get("funding"), 0.0),
            "slippage": finite(item.get("slippage"), 0.0),
            "fees_included_in_pnl": bool(item.get("fees_included_in_pnl", source_class == "BYBIT_VERIFIED")),
            "funding_included_in_pnl": bool(item.get("funding_included_in_pnl", source_class == "BYBIT_VERIFIED")),
            "cost_fields_complete": bool(item.get("cost_fields_complete", False)),
            "mae_r": finite(item.get("mae_r")),
            "mfe_r": finite(item.get("mfe_r")),
            "rules_followed": item.get("rules_followed") if isinstance(item.get("rules_followed"), bool) else None,
            "process_grade": grade if grade in {"A", "B", "C"} else "",
            "deepdive_id": safe_text(item.get("deepdive_id") or dive.get("_id"), 120),
            "process_judgement": safe_text(dive.get("oordeel") or item.get("process_judgement"), 300),
            "lesson": safe_text(dive.get("les") or item.get("lesson"), 600),
            "thesis": safe_text(item.get("thesis") or item.get("reason"), 600),
            "management": safe_text(item.get("management") or item.get("actions"), 600),
            "lifecycle": safe_text(item.get("lifecycle"), 40),
            "snapshot_refs": item.get("snapshot_refs") if isinstance(item.get("snapshot_refs"), dict) else {},
            "snapshot_available": bool(equity_snapshot and equity_snapshot > 0),
        })
    return out


def journal_curve(rows: Any) -> List[Dict[str, Any]]:
    """Return a net-USDT curve and a non-imputed percentage series.

    Missing historic percentages remain ``null``; they are never silently
    treated as a zero-return trade.
    """
    running_usd = 0.0
    running_pct = 0.0
    points: List[Dict[str, Any]] = []
    source = [row for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict)]
    source.sort(key=lambda row: (finite(row.get("updated_time_ms")) or 0, safe_text(row.get("closed_at"), 80)))
    for index, row in enumerate(source):
        running_usd += finite(row.get("pnl"), 0.0) or 0.0
        trade_pct = finite(row.get("pnl_pct"))
        if trade_pct is not None:
            running_pct += trade_pct
        points.append({
            "index": index + 1,
            "at": safe_text(row.get("closed_at"), 80),
            "pnl": round(running_usd, 8),
            "pnl_pct": round(running_pct, 4) if trade_pct is not None else None,
            "percentage_observed": trade_pct is not None,
            "source_class": safe_text(row.get("source_class"), 30),
        })
    return points


def account_payload() -> Dict[str, Any]:
    principal = current_principal()
    if principal.get("role") != "owner":
        profile = workspace_profile()
        return {
            "ok": True,
            "configured": False,
            "mode": "paper",
            "equity": finite(profile.get("manual_equity"), 10000.0),
            "equity_source": "tester_manual",
            "equity_fresh": True,
            "equity_age_seconds": 0,
            "positions": [],
            "updated_at": utc_now(),
            "notice": "Beta-testmodus: geen echte Bybit-accountgegevens en geen live ordervrijgave.",
        }
    configured = bool(services.BYBIT_API_KEY and services.BYBIT_API_SECRET)
    equity = services.get_equity() if configured else None
    cache_at = float((getattr(services, "_EQUITY_CACHE", {}) or {}).get("at", 0) or 0)
    age = max(0.0, time.time() - cache_at) if cache_at else None
    equity_fresh = bool(equity is not None and age is not None and age <= 600)
    positions = services.get_open_positions() if configured else []
    return {
        "ok": True,
        "configured": configured,
        "mode": "live",
        "equity": equity,
        "equity_source": "bybit_read_only" if equity_fresh else "bybit_cached_stale" if equity is not None else None,
        "equity_fresh": equity_fresh,
        "equity_age_seconds": round(age, 1) if age is not None else None,
        "positions": positions,
        "updated_at": utc_now(),
    }


def _refresh_public_prices(targets: List[str]) -> None:
    try:
        values = services.get_prices(targets)
        now = time.time()
        with PRICE_REFRESH_LOCK:
            prices = PRICE_CACHE.setdefault("prices", {})
            asset_at = PRICE_CACHE.setdefault("asset_at", {})
            for key, value in (values or {}).items():
                target = normalize_asset(key)
                clean = finite(value)
                if clean and clean > 0:
                    prices[target] = float(clean)
                    asset_at[target] = now
    except Exception as exc:  # pragma: no cover - network dependent
        services.log.warning("Openbare prijsverversing mislukt: %s", exc)
    finally:
        with PRICE_REFRESH_LOCK:
            PRICE_REFRESHING.difference_update(targets)


def market_prices(force: bool = False, asset: Any = None) -> Dict[str, float]:
    """Return a positive public market price without a false first-poll failure.

    The previous implementation always returned the cache immediately and only
    refreshed in a background thread. On a cold process this made the first
    cockpit/extension poll say that no price existed even though Bybit was
    reachable. A cold or >90-second stale cache is now refreshed synchronously
    once; ordinary 15-second refreshes stay asynchronous.
    """
    if TEST_MODE:
        return {"BTC": 65000.0, "ETH": 3500.0}
    now = time.time()
    targets = [normalize_asset(asset)] if asset else ["BTC", "ETH"]
    with PRICE_REFRESH_LOCK:
        prices = PRICE_CACHE.setdefault("prices", {})
        asset_at = PRICE_CACHE.setdefault("asset_at", {})
        attempted_at = PRICE_CACHE.setdefault("attempted_at", {})
        needed: List[str] = []
        for target in targets:
            age = now - float(asset_at.get(target) or 0)
            fresh = finite(prices.get(target)) and age < 15
            recently_attempted = now - float(attempted_at.get(target) or 0) < 30
            if (force or (not fresh and not recently_attempted)) and target not in PRICE_REFRESHING:
                needed.append(target)
                attempted_at[target] = now
                PRICE_REFRESHING.add(target)
        result = {target: float(prices[target]) for target in targets if finite(prices.get(target)) and float(prices[target]) > 0}
        oldest_age = max((now - float(asset_at.get(target) or 0) for target in targets), default=float("inf"))
    # Cold start and execution-stale prices are resolved in this request so all
    # clients receive the same answer. Routine refreshes remain non-blocking.
    wait_for_price = bool(needed and (not result or oldest_age > 90))
    if needed:
        if wait_for_price:
            _refresh_public_prices(needed)
        else:
            threading.Thread(target=_refresh_public_prices, args=(needed,), name="mytradingbot-price-refresh", daemon=True).start()
    if wait_for_price:
        with PRICE_REFRESH_LOCK:
            prices = PRICE_CACHE.setdefault("prices", {})
            result = {target: float(prices[target]) for target in targets if finite(prices.get(target)) and float(prices[target]) > 0}
    return result


def latest_chart_price_state(asset: Any) -> Optional[Dict[str, Any]]:
    asset_name = normalize_asset(asset)
    draft_stack = load_chart_drafts()
    layer_root = ((draft_stack.get("assets") or {}).get(asset_name) or {}).get("layers") or {}
    candidates: List[Tuple[str, float]] = []
    for layer in layer_root.values():
        if not isinstance(layer, dict):
            continue
        value = finite((layer.get("chart_context") or {}).get("current_price"))
        at = safe_text(layer.get("at"), 80)
        if value and value > 0:
            candidates.append((at, value))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    at, value = candidates[-1]
    try:
        dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        age = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        age = None
    layer = next((item for item in layer_root.values() if isinstance(item, dict) and safe_text(item.get("at"), 80) == at), {})
    context = layer.get("chart_context") if isinstance(layer.get("chart_context"), dict) else {}
    return {
        "ok": True,
        "price": value,
        "source": "TradingView laatste opname",
        "source_detail": safe_text(context.get("current_price_source"), 80) or "tradingview-dom",
        "observed_at": at,
        "age_seconds": round(age, 1) if age is not None else None,
        "stale": age is None or age > 300,
        "authoritative": False,
    }


def get_current_price(asset: Any, account: Optional[Dict[str, Any]] = None) -> Optional[float]:
    state = current_price_status(asset, account)
    return finite(state.get("price")) if state.get("ok") and not state.get("stale") else None


def current_price_status(asset: Any, account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return one explicit price truth shared by cockpit, popup and side panel."""
    asset_name = normalize_asset(asset)
    now = time.time()
    chart_state = latest_chart_price_state(asset_name)
    observations: List[Dict[str, Any]] = []
    if chart_state:
        observations.append({key: chart_state.get(key) for key in ("source", "source_detail", "price", "age_seconds", "stale", "observed_at")})

    for position in (account or {}).get("positions", []):
        mark = finite(position.get("mark") or position.get("markPrice") or position.get("mark_price"))
        if normalize_asset(position.get("symbol")) == asset_name and mark and mark > 0:
            state = {"ok": True, "price": mark, "source": "Bybit positie-markprijs", "source_kind": "bybit_position", "age_seconds": 0, "stale": False, "authoritative": True, "observations": observations}
            return state

    if chart_state and not chart_state.get("stale"):
        return {**chart_state, "source_kind": "tradingview_capture", "observations": observations}

    if current_principal().get("role") == "owner":
        prices = market_prices(asset=asset_name)
        live = finite(prices.get(asset_name))
        if live and live > 0:
            age = max(0.0, now - float((PRICE_CACHE.get("asset_at") or {}).get(asset_name) or now))
            observations.append({"source": "Bybit openbare markprijs", "price": live, "age_seconds": round(age, 1), "stale": age > 90})
            return {"ok": True, "price": live, "source": "Bybit openbare markprijs", "source_kind": "bybit_public", "age_seconds": round(age, 1), "stale": age > 90, "authoritative": True, "observations": observations}

    if current_principal().get("role") != "owner":
        return chart_state or {"ok": False, "price": None, "source": None, "source_kind": None, "age_seconds": None, "stale": True, "authoritative": False, "observations": observations, "reason": "Synchroniseer eerst een grafiek met een geldige prijs"}
    if chart_state:
        return {**chart_state, "reason": "De laatste grafiekprijs is te oud en Bybit kon niet worden bevestigd", "observations": observations}
    return {"ok": False, "price": None, "source": None, "source_kind": None, "age_seconds": None, "stale": True, "authoritative": False, "observations": observations, "reason": "Geen geldige positieve marktprijs beschikbaar"}


def knowledge_source_status() -> Dict[str, Any]:
    folder = Path(services.STRUCTURED)
    files = list(folder.glob("*.json")) if folder.exists() else []
    rows: List[Tuple[str, str, Dict[str, Any]]] = []
    for path in files:
        item = safe_load_json(path, {})
        if isinstance(item, dict):
            rows.append((services.eff_date(item), path.stem, item))
    rows.sort(key=lambda row: str(row[0] or ""), reverse=True)
    catalog = safe_load_json(KNOWLEDGE_CATALOG_FILE, {})
    catalog_counts = catalog.get("counts") if isinstance(catalog, dict) else {}
    catalog_counts = catalog_counts if isinstance(catalog_counts, dict) else {}
    queue = services.load_knowledge_queue()
    queue_ids = {str(row.get("id")) for row in queue if isinstance(row, dict)}
    processed_ids = services.load_processed()
    source_state = services.load_knowledge_source_state()
    excluded_ids = {video_id for video_id, row in source_state.items() if row.get("status") == "excluded_no_transcript"}
    retryable_ids = {video_id for video_id, row in source_state.items() if row.get("status") == "retryable_error"}
    pending = len([video_id for video_id in queue_ids if video_id and video_id not in processed_ids and video_id not in excluded_ids])
    events = services.ingestion_events(250)
    latest_event = events[-1] if events else {}
    failed = [row for row in events if row.get("status") == "failed"]
    latest = rows[0] if rows else (None, None, {})
    worker = services.knowledge_worker_status()
    public_feed = worker.get("public_feed") or {}
    processor_active = bool(services.ENABLE_KNOWLEDGE_INGESTION and not services.DISABLE_BACKGROUND_WORKERS and (queue_ids or services.YT_CHANNEL_ID))
    return {
        "last_video_date": latest[0],
        "last_video_id": latest[1],
        "last_video_title": safe_text((latest[2] or {}).get("_title") or (latest[2] or {}).get("video_title") or "", 220),
        "last_source_url": safe_text((latest[2] or {}).get("_source_url"), 600),
        "stored_lessons": sum(len(item.get("knowledge") or []) if isinstance(item.get("knowledge"), list) else 1 for _, _, item in rows),
        "stored_videos": len(rows),
        "processed": len(processed_ids),
        "queue": pending,
        "queue_total": len(queue_ids),
        "processor_active": processor_active,
        "source_account": "YouTube-kanaalbewaking actief" if processor_active and services.ENABLE_PUBLIC_YOUTUBE_RSS and services.YT_CHANNEL_ID else "geen actieve openbare kanaalbewaking",
        "external_platform_access": "openbare YouTube RSS + owner-only handmatige queue",
        "rss_enabled": bool(services.ENABLE_PUBLIC_YOUTUBE_RSS),
        "channel_id_configured": bool(services.YT_CHANNEL_ID),
        "last_rss_check_at": public_feed.get("last_checked_at"),
        "last_auto_fetched_at": public_feed.get("last_auto_fetched_at"),
        "last_auto_video_id": public_feed.get("last_auto_video_id"),
        "last_auto_video_title": public_feed.get("last_auto_video_title"),
        "last_auto_video_date": public_feed.get("last_auto_video_date"),
        "rss_last_error": public_feed.get("last_error"),
        "worker_running": bool(worker.get("running")),
        "status": "ACTIEF" if processor_active else "HANDMATIG / GESTOPT",
        "last_attempt_at": latest_event.get("at"),
        "last_attempt_status": latest_event.get("status"),
        "last_error": safe_text(failed[-1].get("error"), 600) if failed else None,
        "failed_count": len(failed),
        "excluded_no_transcript": len(excluded_ids),
        "retryable_sources": len(retryable_ids),
        "target_verified_videos": (
            integer(catalog_counts.get("target_verified_transcripts"), 0, 0, 10000)
            if catalog_counts.get("target_verified_transcripts") is not None else None
        ),
        "catalog_total": integer(catalog_counts.get("total_unique"), len(queue_ids), 0, 10000),
        "catalog_live_urls": integer(catalog_counts.get("live_urls"), 0, 0, 10000),
        "catalog_known_excluded": integer(catalog_counts.get("preexcluded"), 0, 0, 10000),
        "catalog_candidates": len(queue_ids),
        "dynamic_quarantine": bool(catalog_counts.get("dynamic_quarantine", True)),
        "extractor_version": safe_text((latest[2] or {}).get("_extractor_version"), 40) or "onbekend",
        "warning": None if processor_active else "Kennisimport staat commercieel veilig uit. Schakel die alleen in voor content waarvoor je aantoonbaar gebruiksrechten hebt.",
    }

def get_instrument(symbol: str) -> Dict[str, Any]:
    symbol = re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())
    if not re.fullmatch(r"[A-Z0-9]{5,20}", symbol):
        raise ValueError("ongeldig symbool")
    now = time.time()
    cached = INSTRUMENT_CACHE.get(symbol)
    if cached and now - cached[0] < 3600:
        return cached[1]
    if now - float(INSTRUMENT_FAILURE_CACHE.get(symbol) or 0) < 30:
        raise RuntimeError("Bybit instruments-info tijdelijk niet bereikbaar; probeer over enkele seconden opnieuw")
    last_error = ""
    INSTRUMENT_FAILURE_CACHE[symbol] = now
    for base in ("https://api.bybit.com", "https://api.bytick.com"):
        try:
            response = requests.get(
                base + "/v5/market/instruments-info",
                params={"category": "linear", "symbol": symbol},
                timeout=(1.5, 2.5),
            )
            data = response.json()
            row = ((data.get("result") or {}).get("list") or [None])[0]
            if row:
                lot = row.get("lotSizeFilter") or {}
                price = row.get("priceFilter") or {}
                lev = row.get("leverageFilter") or {}
                result = {
                    "symbol": symbol,
                    "qty_step": float(lot.get("qtyStep") or 0),
                    "min_qty": float(lot.get("minOrderQty") or 0),
                    "min_notional": float(lot.get("minNotionalValue") or 0),
                    "tick_size": float(price.get("tickSize") or 0),
                    "min_leverage": float(lev.get("minLeverage") or 1),
                    "max_leverage": float(lev.get("maxLeverage") or 0),
                    "leverage_step": float(lev.get("leverageStep") or 0.01),
                    "source": base,
                }
                INSTRUMENT_CACHE[symbol] = (now, result)
                INSTRUMENT_FAILURE_CACHE.pop(symbol, None)
                return result
        except Exception as exc:  # network path
            last_error = str(exc)
    raise RuntimeError("Bybit instruments-info niet bereikbaar" + (f": {last_error}" if last_error else ""))


def knowledge_feed(limit: int = 100) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    static = safe_load_json(METHOD_SOURCES_FILE, {})
    for rule in static.get("rules", []) if isinstance(static, dict) else []:
        if not isinstance(rule, dict):
            continue
        rows.append({
            "id": safe_text(rule.get("id"), 120),
            "date": safe_text(rule.get("date"), 20),
            "title": safe_text(rule.get("title") or "Regel", 220),
            "type": safe_text(rule.get("category") or "methodiek", 40),
            "summary": safe_text(rule.get("statement"), 1200),
            "source_label": safe_text(rule.get("source_label") or "ONBEVESTIGD", 40).upper(),
            "source_title": safe_text(rule.get("source_title"), 240),
            "source_url": safe_text(rule.get("source_url"), 600),
            "official_status": safe_text(rule.get("official_status"), 40),
            "confidence": integer(rule.get("confidence"), 0, 0, 100),
            "provenance": "static-methodology",
        })
    folder = Path(services.STRUCTURED)
    files = list(folder.glob("*.json")) if folder.exists() else []
    for path in files:
        item = safe_load_json(path, {})
        if not isinstance(item, dict):
            continue
        knowledge = item.get("knowledge")
        if isinstance(knowledge, list) and knowledge:
            for row in knowledge:
                if not isinstance(row, dict):
                    continue
                rows.append({
                    "id": safe_text(row.get("id") or f"{path.stem}:{len(rows)}", 120),
                    "date": safe_text(row.get("source_date") or services.eff_date(item), 20),
                    "title": safe_text(row.get("title") or item.get("_title") or "Les", 220),
                    "type": safe_text(row.get("category") or item.get("video_type") or "kennis", 40),
                    "summary": safe_text(row.get("summary") or row.get("statement") or "", 1200),
                    "source_label": safe_text(row.get("source_label") or "EXTERNE-BRON", 40).upper(),
                    "source_title": safe_text(row.get("source_title") or item.get("_title"), 240),
                    "source_url": safe_text(row.get("source_url") or item.get("_source_url"), 600),
                    "official_status": safe_text(row.get("official_status") or "unconfirmed", 40),
                    "confidence": integer(row.get("confidence"), 0, 0, 100),
                    "evidence": safe_text(row.get("evidence"), 1000),
                    "extractor_version": safe_text(row.get("extractor_version") or item.get("_extractor_version"), 40),
                    "tags": [safe_text(value, 80) for value in (row.get("tags") or []) if safe_text(value, 80)][:20],
                    "timeframes": [safe_text(value, 20) for value in (row.get("timeframes") or []) if safe_text(value, 20)][:8],
                    "applies_when": safe_text(row.get("applies_when"), 800),
                    "avoid_when": safe_text(row.get("avoid_when"), 800),
                    "rights_status": safe_text(row.get("rights_status") or item.get("_rights_status"), 100),
                    "commercial_use_allowed": bool(row.get("commercial_use_allowed", item.get("_commercial_use_allowed", False))),
                    "provenance": "video-extraction",
                })
        else:
            rows.append({
                "id": path.stem,
                "date": services.eff_date(item),
                "title": safe_text(item.get("_title") or item.get("video_title") or item.get("title") or path.stem, 220),
                "type": safe_text(item.get("video_type") or "kennis", 40),
                "summary": safe_text(item.get("summary") or item.get("analysis") or "", 900),
                "source_label": "LEGACY-IMPORT",
                "source_title": safe_text(item.get("_title") or path.stem, 240),
                "source_url": safe_text(item.get("_source_url"), 600),
                "official_status": "unconfirmed",
                "confidence": 0,
                "provenance": "legacy-structured",
            })
    rows.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("title") or "")), reverse=True)
    return rows[:max(1, min(500, limit))]



# ---------------------------------------------------------------------------
# Chart analysis and decisions


EXPECTED_INSTRUMENT = os.environ.get("MYTRADINGBOT_EXPECTED_INSTRUMENT", "BYBIT:BTCUSDT.P").strip().upper()


def normalize_instrument_identity(value: Any) -> str:
    raw = safe_text(value, 100).upper().replace(" ", "")
    raw = raw.replace("PERPETUALCONTRACT", "").replace("PERP", ".P")
    if ":" not in raw and raw.startswith("BTCUSDT"):
        raw = "BYBIT:" + raw
    if raw == "BYBIT:BTCUSDT":
        raw = "BYBIT:BTCUSDT.P"
    return raw


def validate_instrument(value: Any) -> Dict[str, Any]:
    actual = normalize_instrument_identity(value)
    expected = normalize_instrument_identity(EXPECTED_INSTRUMENT)
    ok = actual == expected
    return {
        "ok": ok, "actual": actual or "ONBEKEND", "expected": expected,
        "reason": "Instrument komt overeen" if ok else f"Actieve chart {actual or 'onbekend'} komt niet overeen met {expected}",
    }


def chart_context(raw: Any) -> Dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    symbol = safe_text(item.get("symbol"), 80)
    instrument = validate_instrument(symbol)
    if not instrument["ok"]:
        raise ValueError(f"INSTRUMENT KOMT NIET OVEREEN: {instrument['reason']}. Synchronisatie is geblokkeerd.")
    timeframe = normalize_timeframe(item.get("timeframe"))
    if timeframe not in PRIMARY_TIMEFRAMES:
        raise ValueError("Gebruik exact 1D, 4H, 15M of 3M")
    viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
    rect = item.get("chart_rect") if isinstance(item.get("chart_rect"), dict) else {}
    return {
        "symbol": symbol,
        "instrument": instrument,
        "timeframe": timeframe,
        "url": safe_text(item.get("url"), 600),
        "page_title": safe_text(item.get("page_title"), 200),
        "trigger": safe_text(item.get("trigger"), 50) or "manual",
        "current_price": finite(item.get("current_price")),
        "current_price_source": safe_text(item.get("current_price_source"), 80) or "tradingview-dom",
        "captured_at": safe_text(item.get("captured_at"), 80) or utc_now(),
        "viewport": {"width": finite(viewport.get("width")), "height": finite(viewport.get("height"))},
        "chart_rect": {
            "x": finite(rect.get("x")), "y": finite(rect.get("y")),
            "width": finite(rect.get("width")), "height": finite(rect.get("height")),
        },
    }


def perform_chart_sync(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    if not rate_allowed("chart", limit=80, seconds=3600):
        raise RuntimeError("RATE_LIMIT: Te veel chartsynchronisaties; wacht even")
    image_data = payload.get("image")
    if not image_data:
        raise ValueError("screenshot ontbreekt")
    context = chart_context(payload.get("context"))
    image = decode_capture(str(image_data))
    chart, crop_meta = crop_chart(image, context)
    raw_png, encoded, image_hash = encode_png(chart)
    asset = normalize_asset(context.get("symbol"))
    timeframe = normalize_timeframe(context.get("timeframe"))

    cached = None if payload.get("reanalyze") else find_chart_cache(image_hash, asset, timeframe)
    if cached:
        cached.update(last_seen_at=utc_now(), cache_hit=True)
        save_chart_draft(cached)
        atomic_write_bytes(preview_path(asset, timeframe), raw_png)
        append_activity({
            "type": "chart_unchanged", "symbol": f"{asset}USDT", "asset": asset, "timeframe": timeframe,
            "note": f"Ongewijzigde {timeframe}-chart herkend uit cache",
        })
        return cached, True

    if not services.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY ontbreekt; chart-vision kan niet draaien")
    raw_result = analyze_with_claude(
        api_key=services.ANTHROPIC_API_KEY,
        model=os.environ.get("MYTRADINGBOT_VISION_MODEL", "claude-sonnet-4-6"),
        image_base64=encoded,
        context=context,
    )
    previous = get_latest_layer(load_chart_drafts(), asset=asset, timeframe=timeframe) or get_layer(load_market_stack(), asset, timeframe) or {}
    draft = normalize_vision_result(raw_result, context=context, image_hash=image_hash, crop_meta=crop_meta, previous=previous)
    draft.update(sync_id=draft.get("revision"), zones_detected=len(draft.get("zones") or []), last_seen_at=utc_now())
    save_chart_draft(draft)
    atomic_write_bytes(preview_path(asset, timeframe), raw_png)
    save_chart_cache({"hash": image_hash, "asset": asset, "timeframe": timeframe, "at": utc_now(), "draft": draft})
    append_activity({
        "type": "chart_synced", "symbol": f"{asset}USDT", "asset": asset, "timeframe": timeframe,
        "note": f"{len(draft.get('zones') or [])} zone(s) gelezen · {draft.get('overall_confidence', 0)}% zekerheid",
    })
    return draft, False


def active_asset(explicit: Any = None) -> str:
    if explicit:
        return normalize_asset(explicit)
    latest = (load_market_stack().get("latest") or {})
    if latest.get("asset"):
        return normalize_asset(latest["asset"])
    latest_draft = (load_chart_drafts().get("latest") or {})
    return normalize_asset(latest_draft.get("asset") or "BTC")


def decision_payload(asset: Any = None, account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    asset_name = active_asset(asset)
    account = account or account_payload()
    price_state = current_price_status(asset_name, account)
    price = price_state.get("price") if price_state.get("ok") and not price_state.get("stale") else None
    decision = build_decision(
        load_market_stack(),
        asset=asset_name,
        current_price=price,
        risk_profiles=RISK_PROFILES,
        draft_stack_value=load_chart_drafts(),
    )
    generated_at = utc_now()
    decision["price_status"] = price_state
    decision["state_generated_at"] = generated_at
    state_basis = {
        "asset": asset_name,
        "price": price_state.get("price"),
        "price_source": price_state.get("source_kind") or price_state.get("source"),
        "price_stale": price_state.get("stale"),
        "gate": (decision.get("execution_gate") or {}).get("status"),
        "synced": decision.get("synced_count"),
        "confirmed": decision.get("confirmed_count"),
        "setup_id": (decision.get("setup") or {}).get("setup_id"),
    }
    decision["state_id"] = hashlib.sha256(json.dumps(state_basis, sort_keys=True, default=str).encode()).hexdigest()[:16]
    decision["instrument"] = {"canonical": EXPECTED_INSTRUMENT, "asset": asset_name}
    if not price_state.get("ok") or price_state.get("stale"):
        gate = decision.setdefault("execution_gate", {})
        gate.update(status="WAIT_PRICE", label="PRIJSBRON CONTROLEREN", orderable=False, reason=price_state.get("reason") or "De marktprijs ontbreekt of is te oud. Ticketvoorbereiding is geblokkeerd.")
        decision["setup"] = None
    decision["account"] = {
        "equity": account.get("equity"),
        "equity_fresh": account.get("equity_fresh"),
        "equity_age_seconds": account.get("equity_age_seconds"),
        "mode": account.get("mode"),
    }
    if current_principal().get("role") != "owner":
        gate = decision.setdefault("execution_gate", {})
        gate.update(status="PAPER_MODE", label="TESTMODUS", orderable=False, reason="Deze beta-werkruimte is volledig geïsoleerd en bereidt geen echt orderticket voor.")
        decision["paper_mode"] = True
    return decision


def apply_account_guard(latest: Dict[str, Any], guard: Dict[str, Any]) -> Dict[str, Any]:
    """Only tighten the existing cockpit gate; never make it more permissive."""
    latest["account_guard"] = guard
    if guard.get("ticket_blocked"):
        gate = latest.setdefault("execution_gate", {})
        gate["underlying_status"] = gate.get("status")
        gate["underlying_reason"] = gate.get("reason")
        gate.update(
            status=guard.get("gate_status") or "COMMITMENT_BLOCKED",
            label="COMMITMENT MODE",
            orderable=False,
            reason=guard.get("reason") or "Een vrijwillig accounthek houdt het ticket dicht.",
        )
    basis = {
        "prior": latest.get("state_id"),
        "guard": guard.get("gate_status"),
        "blocked": bool(guard.get("ticket_blocked")),
        "buffer": guard.get("buffer_remaining_usdt"),
        "cooldown": guard.get("cooldown_until"),
    }
    latest["state_id"] = hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return latest


def deterministic_coaching(question: str, latest: Dict[str, Any]) -> str:
    gate = latest.get("execution_gate") or {}
    setup = latest.get("setup") or {}
    chain = latest.get("decision_chain") or []
    chain_text = " → ".join(f"{row.get('timeframe')} {row.get('status')}" for row in chain)
    if not setup:
        return f"Niet forceren. Huidige keten: {chain_text}. {gate.get('reason') or 'Vul de ontbrekende timeframe-laag aan.'}"
    failed = gate.get("failed") or []
    if failed:
        return f"De 3M-kanteling is alleen een kandidaat. Los eerst op: {', '.join(failed)}. Verander de stop nooit om een grotere positie te krijgen."
    return (
        f"{setup.get('direction', '').upper()}-instap vanaf 3m is mechanisch klaar bij een bevestigde {setup.get('parent_zone', {}).get('source_timeframe')} zone. "
        f"Risico {setup.get('risk_pct')}% staat vast. Controleer instap, Level-2-stop, drie doelen, Isolated, One-Way en de teruglezing van het orderticket; klik daarna zelf de orderknop."
    )


def load_lifecycles() -> Dict[str, Any]:
    value = safe_load_json(workspace_file(LIFECYCLE_NAME), {"records": {}, "updated_at": utc_now()})
    if not isinstance(value, dict) or not isinstance(value.get("records"), dict):
        return {"records": {}, "updated_at": utc_now()}
    return value


def save_lifecycles(value: Dict[str, Any]) -> None:
    value["updated_at"] = utc_now()
    atomic_write_json(workspace_file(LIFECYCLE_NAME), value)


def journal_paths() -> Tuple[Path, Path]:
    if is_owner():
        return Path(services.JOURNAL), Path(services.DEEPDIVES)
    return workspace_file("journal.json"), workspace_file("deepdives.json")


def workspace_journal_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Tester performance is explicitly simulated and never mixed with owner data.
    return services.compute_journal_stats(rows, include_simulated=True)


def journal_bundle() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    journal_path, deepdives_path = journal_paths()
    raw = safe_load_json(journal_path, [])
    deepdives = safe_load_json(deepdives_path, [])
    rows = normalise_journal_rows(raw, deepdives)
    stats = normalise_journal_stats(services.journal_stats()) if is_owner() else normalise_journal_stats(workspace_journal_stats(rows))
    return rows, deepdives if isinstance(deepdives, list) else [], stats


def build_weekly_mentor_payload() -> Dict[str, Any]:
    """Build a source-free weekly reflection from existing persisted data only."""
    rows, deepdives, _ = journal_bundle()
    payload = build_bilingual_weekly_mentor_report(rows, deepdives, knowledge_feed(500))
    payload["weekly_mentor_release"] = WEEKLY_MENTOR_RELEASE
    return payload


def overview_payload(asset: Any = None) -> Dict[str, Any]:
    asset_name = active_asset(asset)
    account = account_payload()
    latest = decision_payload(asset_name, account)
    stack = public_stack(load_market_stack())
    drafts = public_drafts(load_chart_drafts())
    composite = build_composite_map(load_market_stack(), asset_name)
    journal_rows, deepdives, stats = journal_bundle()
    discipline = build_discipline_snapshot(
        workspace_file(DISCIPLINE_NAME),
        journal_rows,
        account.get("positions") or [],
    )
    account_guard = build_account_guard_snapshot(
        workspace_file(ACCOUNT_GUARD_NAME),
        journal_rows,
        account.get("positions") or [],
        account.get("equity"),
        default_loss_limit_pct=COMMITMENT_MAX_DAILY_LOSS_PCT,
        cooldown_minutes=REVENGE_COOLDOWN_MINUTES,
    ) if is_owner() else {
        "release": ACCOUNT_GUARD_RELEASE, "active": False, "ticket_blocked": False,
        "read_only_to_bybit": True, "owner_only": True,
    }
    apply_account_guard(latest, account_guard)
    journal_pattern_gates = build_journal_pattern_snapshot(
        workspace_file(JOURNAL_PATTERN_GATE_NAME), journal_rows, deepdives
    ) if is_owner() else {
        "release": JOURNAL_PATTERN_RELEASE, "open_suggestions": [], "active_rules": [],
        "owner_action_required": True, "read_only_to_bybit": True, "owner_only": True,
    }
    apply_journal_pattern_rules(latest, journal_pattern_gates.get("active_rules") or [])
    if journal_pattern_gates.get("active_rules"):
        basis = {
            "prior": latest.get("state_id"),
            "journal_rules": [rule.get("id") for rule in journal_pattern_gates.get("active_rules") or []],
            "matched": [rule.get("id") for rule in ((latest.get("journal_pattern_gate") or {}).get("matched_rules") or [])],
        }
        latest["state_id"] = hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return {
        "ok": True,
        "version": VERSION,
        "principal": current_principal(),
        "profile": workspace_profile(),
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "asset": asset_name,
        "workflow": list(PRIMARY_TIMEFRAMES),
        "latest": latest,
        "account": account,
        "market_stack": stack,
        "chart_drafts": drafts,
        "composite_map": composite,
        "market_map": composite,
        "stack_health": build_stack_health(load_market_stack(), asset_name, load_chart_drafts()),
        "journal": {
            "summary": services.journal_summary() if is_owner() else (f"{len(journal_rows)} beta-testtrades" if journal_rows else "nog geen beta-testtrades"),
            "stats": stats,
            "trades": journal_rows[-250:],
            "curve": journal_curve(journal_rows[-250:]),
            "deepdives": deepdives[-100:] if isinstance(deepdives, list) else [],
        },
        "knowledge": knowledge_feed(120),
        "knowledge_source": knowledge_source_status(),
        "knowledge_ingestion": list(reversed(services.ingestion_events(100))),
        "coach_release": COACH_RELEASE,
        "weekly_mentor_release": WEEKLY_MENTOR_RELEASE,
        "process_first_release": PROCESS_FIRST_RELEASE,
        "discipline": discipline,
        "account_guard_release": ACCOUNT_GUARD_RELEASE,
        "account_guard": account_guard,
        "journal_pattern_release": JOURNAL_PATTERN_RELEASE,
        "journal_pattern_gates": journal_pattern_gates,
        "ux_release": UX_RELEASE,
        "methodology_sources": load_methodology_sources(),
        "activity": list(reversed(load_activity_log()[-160:])),
        "lifecycles": load_lifecycles(),
        "risk_profiles": RISK_PROFILES,
        "risk_policy_source": "OPERATORBELEID",
        "commercialization": commercialization_status(),
        "services": {
            "knowledge_worker": bool(KNOWLEDGE_WORKER) if is_owner() else False,
            "account_watcher": services.account_worker_status() if is_owner() else {"running": False, "mode": "paper"},
            "journal_writer": bool(ACCOUNT_WORKER) if is_owner() else False,
            "telegram_watcher": bool(ACCOUNT_WORKER and services.TELEGRAM_TOKEN and services.TELEGRAM_CHAT_ID) if is_owner() else False,
            "telegram_day_start": telegram_day_start_status() if is_owner() else {"enabled": False, "running": False},
            "post_trade_coach_loop": services.post_trade_coach_loop_status() if is_owner() else {"enabled": False, "outgoing_only": True},
            "weekly_mentor": weekly_mentor_status() if is_owner() else {"enabled": False, "outgoing_only": True, "latest_report": None},
        },
        "state_id": latest.get("state_id"),
        "updated_at": latest.get("state_generated_at") or utc_now(),
    }


# ---------------------------------------------------------------------------
# HTML / assets / health


@app.get("/")
@app.get("/dashboard")
def dashboard() -> Response:
    if not DASHBOARD_FILE.exists():
        return Response("dashboard niet gevonden", status=404, mimetype="text/plain")
    return send_file(DASHBOARD_FILE, mimetype="text/html", max_age=0)


@app.get("/assets/dashboard.css")
def dashboard_css() -> Response:
    return send_file(DASHBOARD_CSS_FILE, mimetype="text/css", max_age=0)


@app.get("/assets/dashboard.js")
def dashboard_js() -> Response:
    return send_file(DASHBOARD_JS_FILE, mimetype="application/javascript", max_age=0)


@app.get("/health")
def health() -> Response:
    # Public operational health only: no account, trade or workspace details.
    owner_stack = safe_load_json(DATA_DIR / MARKET_STACK_NAME, empty_stack())
    owner_drafts = safe_load_json(DATA_DIR / CHART_DRAFT_NAME, empty_stack())
    owner_asset = active_asset()
    stack_health = build_stack_health(owner_stack, owner_asset, owner_drafts)
    return jsonify(
        ok=True,
        version=VERSION,
        engine_version=ENGINE_VERSION,
        schema_version=SCHEMA_VERSION,
        capture_complete=bool(stack_health.get("capture_complete")),
        synced_timeframes=int(stack_health.get("synced_count") or 0),
        verified_timeframes=int(stack_health.get("confirmed_count") or 0),
        token_configured=bool(API_TOKEN),
        token_valid_length=len(API_TOKEN) >= TOKEN_MIN_LENGTH,
        token_min_length=TOKEN_MIN_LENGTH,
        chart_sync_configured=bool(services.ANTHROPIC_API_KEY),
        private_beta_ready=True,
        multi_workspace=True,
        workflow=list(PRIMARY_TIMEFRAMES),
        knowledge_worker=bool(KNOWLEDGE_WORKER),
        knowledge_release=KNOWLEDGE_RELEASE,
        coach_release=COACH_RELEASE,
        automation_release=AUTOMATION_RELEASE,
        coach_loop_release=COACH_LOOP_RELEASE,
        weekly_mentor_release=WEEKLY_MENTOR_RELEASE,
        ux_release=UX_RELEASE,
        account_watcher=services.account_worker_status(),
        telegram_day_start=telegram_day_start_status(),
        post_trade_coach_loop=services.post_trade_coach_loop_status(),
        weekly_mentor=weekly_mentor_status(),
        process_first_release=PROCESS_FIRST_RELEASE,
        account_guard_release=ACCOUNT_GUARD_RELEASE,
        journal_pattern_release=JOURNAL_PATTERN_RELEASE,
        time=utc_now(),
    )


# ---------------------------------------------------------------------------
# API


@app.get("/api/v2/beta/public-config")
def beta_public_config() -> Response:
    return jsonify(
        ok=True, version=VERSION, private_beta=True, invite_required=True,
        data_disclosure={
            "chart_screenshots":"Worden versleuteld via HTTPS naar de gekozen cockpit gestuurd voor zone-analyse.",
            "financial_data":"Alleen de eigenaar gebruikt de server-side Bybit read-only koppeling; testers starten in paper-modus.",
            "authentication":"Toegangstokens worden server-side uitsluitend gehasht opgeslagen.",
            "final_click":"De extensie klikt nooit zelfstandig op Buy, Sell, Place order of Confirm.",
        },
    )


@app.post("/api/v2/beta/redeem")
def beta_redeem() -> Response:
    if not rate_allowed("beta-redeem", limit=20, seconds=3600):
        return jsonify(ok=False, error="Te veel pogingen; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    try:
        result = beta_access.redeem_invite(
            safe_text(payload.get("code"), 120), safe_text(payload.get("display_name"), 80), consent=bool(payload.get("consent"))
        )
        return jsonify(ok=True, **result)
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.get("/api/v2/beta/me")
def beta_me() -> Response:
    return jsonify(ok=True, principal=current_principal(), profile=workspace_profile(), commercialization=commercialization_status())


@app.get("/api/v2/beta/testers")
def beta_testers() -> Response:
    denied = require_owner()
    if denied:
        return denied
    return jsonify(ok=True, testers=beta_access.list_testers(), invites=beta_access.list_invites())


@app.post("/api/v2/beta/invites")
def beta_invites_create() -> Response:
    denied = require_owner()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        expires_minutes = payload.get("expires_minutes")
        expires_hours = payload.get("expires_hours")
        expires_days = payload.get("expires_days")
        invite = beta_access.create_invite(
            safe_text(payload.get("label"), 80) or "Beta tester",
            expires_minutes=(integer(expires_minutes, 1, 1, 129600) if expires_minutes is not None else None),
            expires_hours=(integer(expires_hours, 1, 1, 2160) if expires_hours is not None else None),
            expires_days=(integer(expires_days, 14, 1, 90) if expires_days is not None else None),
            max_uses=integer(payload.get("max_uses"), 1, 1, 20),
            mode=safe_text(payload.get("mode"), 20) or "tester",
        )
        return jsonify(ok=True, invite=invite)
    except (ValueError, RuntimeError) as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/v2/beta/invites/revoke")
def beta_invite_revoke() -> Response:
    denied = require_owner()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    invite_id = safe_text(payload.get("invite_id"), 80)
    if not invite_id or not beta_access.revoke_invite(invite_id):
        return jsonify(ok=False, error="Uitnodiging niet gevonden of al ingetrokken"), 404
    return jsonify(ok=True, revoked=True, invite_id=invite_id)


@app.post("/api/v2/beta/testers/revoke")
def beta_tester_revoke() -> Response:
    denied = require_owner()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    session_id = safe_text(payload.get("session_id"), 80)
    if not session_id or not beta_access.revoke_tester(session_id):
        return jsonify(ok=False, error="Tester niet gevonden"), 404
    return jsonify(ok=True)


@app.get("/api/v2/profile")
def beta_profile_get() -> Response:
    return jsonify(ok=True, principal=current_principal(), profile=workspace_profile())


@app.post("/api/v2/profile")
def beta_profile_save() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(ok=True, profile=save_workspace_profile(payload))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/v2/beta/feedback")
def beta_feedback() -> Response:
    payload = request.get_json(silent=True) or {}
    category = safe_text(payload.get("category"), 30).lower() or "algemeen"
    message = safe_text(payload.get("message"), 4000)
    if len(message) < 5:
        return jsonify(ok=False, error="Beschrijf je feedback iets uitgebreider"), 400
    path = workspace_file(FEEDBACK_NAME)
    rows = safe_load_json(path, [])
    if not isinstance(rows, list):
        rows = []
    item = {
        "id": str(uuid.uuid4()), "at": utc_now(), "category": category, "message": message,
        "page": safe_text(payload.get("page"), 300), "version": VERSION,
        "principal": {"workspace_id": current_principal().get("workspace_id"), "display_name": current_principal().get("display_name")},
    }
    rows.append(item)
    atomic_write_json(path, rows[-500:])
    return jsonify(ok=True, feedback=item)


@app.get("/api/v2/beta/export")
def beta_export() -> Response:
    root = workspace_root()
    export = {"version": VERSION, "exported_at": utc_now(), "principal": current_principal(), "files": {}}
    for name in (PROFILE_NAME, MARKET_STACK_NAME, CHART_DRAFT_NAME, ACTIVITY_NAME, LIFECYCLE_NAME, "journal.json", "deepdives.json", FEEDBACK_NAME):
        path = root / name
        if path.exists() and path.is_file():
            export["files"][name] = safe_load_json(path, None)
    return jsonify(ok=True, export=export)


@app.post("/api/v2/beta/delete-my-data")
def beta_delete_my_data() -> Response:
    if is_owner():
        return jsonify(ok=False, error="Eigenaarsdata kan niet via deze beta-route worden gewist"), 403
    payload = request.get_json(silent=True) or {}
    if safe_text(payload.get("confirm"), 40).lower() != "verwijder mijn beta-data":
        return jsonify(ok=False, error='Typ exact "verwijder mijn beta-data"'), 400
    root = workspace_root()
    token = token_from_request()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    beta_access.revoke_current_token(token)
    return jsonify(ok=True, deleted=True)


@app.post("/api/v2/journal/test-entry")
def beta_test_journal_entry() -> Response:
    if is_owner():
        return jsonify(ok=False, error="Gebruik deze route alleen in beta-testmodus"), 403
    payload = request.get_json(silent=True) or {}
    pnl = finite(payload.get("pnl"), 0.0) or 0.0
    equity = finite(workspace_profile().get("manual_equity"), 10000.0) or 10000.0
    row = {
        "id": str(uuid.uuid4()), "symbol": "BTCUSDT", "direction": safe_text(payload.get("direction"), 10).lower() or "long",
        "entry": finite(payload.get("entry"), 64000.0), "exit": finite(payload.get("exit"), 64100.0),
        "pnl": round(pnl, 2), "pnl_pct": round(pnl/equity*100, 4), "equity_snapshot": equity,
        "closed_at": utc_now(), "result": "win" if pnl > 0 else "loss" if pnl < 0 else "breakeven",
        "origin_timeframe": "3M", "setup_type": "beta-test", "trade_type": "day", "rules_followed": True,
        "process_grade": "A", "lesson": "Gesimuleerde beta-testtrade; geen echte order.",
        "source": "PAPER-BETA", "source_class": "PAPER", "source_label": "PAPER",
        "record_kind": "PAPER_CLOSE_RECORD", "pnl_basis": "PAPER_SIMULATION", "paper": True, "test_data": True,
    }
    journal_path, _ = journal_paths()
    rows = safe_load_json(journal_path, [])
    if not isinstance(rows, list): rows = []
    rows.append(row)
    atomic_write_json(journal_path, rows[-500:])
    return jsonify(ok=True, trade=row)


@app.get("/api/v1/config")
def api_config() -> Response:
    return jsonify(
        ok=True,
        version=VERSION,
        schema_version=SCHEMA_VERSION,
        principal=current_principal(),
        profile=workspace_profile(),
        chart_sync=True,
        knowledge_release=KNOWLEDGE_RELEASE,
        coach_release=COACH_RELEASE,
        ux_release=UX_RELEASE,
        expected_instruments=[{"provider":"BYBIT","symbol":"BTCUSDT.P","canonical":"BYBIT:BTCUSDT.P"}],
        privacy={"screenshots":True,"financial_data":is_owner(),"human_review":False,"purpose":"grafiekcontrole, discipline en veilige ticketvoorbereiding"},
        workflow=list(PRIMARY_TIMEFRAMES),
        layer_purposes={tf: layer_purpose(tf) for tf in PRIMARY_TIMEFRAMES},
        diagnostics={
            "backend": True,
            "token": True,
            "bybit_read_only": bool(services.BYBIT_API_KEY and services.BYBIT_API_SECRET) if is_owner() else False,
            "account_mode": "live" if is_owner() else "paper",
            "workspace_isolated": True,
            "price_mapping": "BTC->BTCUSDT",
            "knowledge_worker": bool(KNOWLEDGE_WORKER) if is_owner() else False,
            "account_watcher": services.account_worker_status() if is_owner() else {"running": False, "mode": "paper"},
            "journal_writer": bool(ACCOUNT_WORKER) if is_owner() else False,
            "telegram_watcher": bool(ACCOUNT_WORKER and services.TELEGRAM_TOKEN and services.TELEGRAM_CHAT_ID) if is_owner() else False,
            "telegram_day_start": telegram_day_start_status() if is_owner() else {"enabled": False, "running": False},
            "post_trade_coach_loop": services.post_trade_coach_loop_status() if is_owner() else {"enabled": False, "outgoing_only": True},
            "weekly_mentor": weekly_mentor_status() if is_owner() else {"enabled": False, "outgoing_only": True, "latest_report": None},
            "journal_pattern_gates": {"release": JOURNAL_PATTERN_RELEASE, "owner_action_required": True, "read_only_to_bybit": True},
            "legacy_runtime_loaded": False,
            "legacy_runtime": False,
            "side_check": True,
            "ticket_readback": True,
            "break_even_policy": "NA_TP2_EN_IN_WINST",
            "final_click": False,
        },
        risk_profiles=RISK_PROFILES,
        risk_policy_source="OPERATORBELEID",
        methodology_sources=load_methodology_sources(),
        commercialization=commercialization_status(),
        execution_origin="3M",
        final_order_click=False,
    )


@app.get("/api/v1/latest")
def api_latest() -> Response:
    return jsonify(decision_payload(request.args.get("asset")))


@app.get("/api/v1/account")
def api_account() -> Response:
    return jsonify(account_payload())


@app.get("/api/v1/instrument/<symbol>")
def api_instrument(symbol: str) -> Response:
    try:
        return jsonify(ok=True, instrument=get_instrument(symbol))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(ok=False, error=str(exc)), 503


@app.get("/api/v1/stack")
@app.get("/api/v1/market-stack")
@app.get("/api/v2/market-stack")
def api_stack() -> Response:
    asset_name = active_asset(request.args.get("asset"))
    return jsonify(
        ok=True,
        asset=asset_name,
        stack=public_stack(load_market_stack()),
        composite_map=build_composite_map(load_market_stack(), asset_name),
        latest=decision_payload(asset_name),
        stack_health=build_stack_health(load_market_stack(), asset_name, load_chart_drafts()),
    )


@app.get("/api/v1/market-map")
def api_market_map_get() -> Response:
    asset_name = active_asset(request.args.get("asset"))
    return jsonify(
        ok=True,
        market_map=build_composite_map(load_market_stack(), asset_name),
        market_stack=public_stack(load_market_stack()),
        chart_drafts=public_drafts(load_chart_drafts()),
    )


@app.post("/api/v1/layer")
def api_layer_save() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        layer = normalize_layer(payload.get("layer") if isinstance(payload.get("layer"), dict) else payload, strict=True)
        stack = save_market_layer(layer)
        append_activity({
            "type": "layer_confirmed", "symbol": layer["symbol"], "asset": layer["asset"], "timeframe": layer["source_timeframe"],
            "note": f"{len(layer.get('zones') or [])} zone(s) handmatig bevestigd",
        })
        return jsonify(ok=True, layer=layer, stack=public_stack(stack), latest=decision_payload(layer["asset"]))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/v1/market-map")
def api_market_map_save_compat() -> Response:
    return api_layer_save()


@app.post("/api/v1/chart/analyze")
@app.post("/api/v2/chart-sync")
def api_chart_analyze() -> Response:
    try:
        draft, cached = perform_chart_sync(request.get_json(silent=True) or {})
        asset = normalize_asset(draft.get("asset"))
        return jsonify(
            ok=True,
            draft=chart_public(draft),
            cache_hit=cached,
            stack_health=build_stack_health(load_market_stack(), asset, load_chart_drafts()),
            latest=decision_payload(asset),
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except RuntimeError as exc:
        message = str(exc)
        status = 429 if message.startswith("RATE_LIMIT:") else 503
        return jsonify(ok=False, error=message.replace("RATE_LIMIT:", "").strip()), status
    except Exception as exc:  # external API / image path
        services.log.exception("chart-sync v6 fout")
        return jsonify(ok=False, error=str(exc)), 500


@app.get("/api/v1/chart-draft")
def api_chart_draft_compat() -> Response:
    asset = request.args.get("asset")
    timeframe = request.args.get("timeframe")
    draft = get_latest_layer(load_chart_drafts(), asset=asset, timeframe=timeframe) if asset and timeframe else get_latest_layer(load_chart_drafts())
    return jsonify(ok=True, draft=chart_public(draft), chart_drafts=public_drafts(load_chart_drafts()))


@app.get("/api/v1/chart/drafts")
def api_chart_drafts() -> Response:
    return jsonify(ok=True, chart_drafts=public_drafts(load_chart_drafts()))


@app.get("/api/v1/chart/draft/<asset>/<timeframe>")
def api_chart_draft(asset: str, timeframe: str) -> Response:
    tf = normalize_timeframe(timeframe)
    if tf not in PRIMARY_TIMEFRAMES:
        return jsonify(ok=False, error="ongeldig timeframe"), 400
    draft = get_layer(load_chart_drafts(), asset, tf)
    if not draft:
        return jsonify(ok=False, error="Nog geen draft voor deze timeframe"), 404
    return jsonify(ok=True, draft=chart_public(draft))


@app.get("/api/v1/chart-state")
def api_chart_state() -> Response:
    asset_name = active_asset(request.args.get("asset"))
    return jsonify(
        ok=True,
        asset=asset_name,
        chart_drafts=public_drafts(load_chart_drafts()),
        market_stack=public_stack(load_market_stack()),
        latest=decision_payload(asset_name),
        stack_health=build_stack_health(load_market_stack(), asset_name, load_chart_drafts()),
    )


@app.get("/api/v1/chart/preview/<asset>/<timeframe>")
def api_chart_preview(asset: str, timeframe: str) -> Response:
    tf = normalize_timeframe(timeframe)
    if tf not in PRIMARY_TIMEFRAMES:
        return jsonify(ok=False, error="ongeldig timeframe"), 400
    path = preview_path(asset, tf)
    if not path.exists():
        return jsonify(ok=False, error="Nog geen chartpreview voor deze timeframe"), 404
    return send_file(path, mimetype="image/png", max_age=0)


@app.get("/api/v1/chart-preview")
def api_chart_preview_compat() -> Response:
    asset = request.args.get("asset") or active_asset()
    timeframe = request.args.get("timeframe")
    if not timeframe:
        latest = (load_chart_drafts().get("latest") or {})
        timeframe = latest.get("timeframe") or "3M"
    return api_chart_preview(str(asset), str(timeframe))


@app.post("/api/v1/chart/confirm")
def api_chart_confirm() -> Response:
    payload = request.get_json(silent=True) or {}
    source = payload.get("layer") if isinstance(payload.get("layer"), dict) else payload
    asset = normalize_asset(source.get("asset") or payload.get("asset"))
    timeframe = normalize_timeframe(source.get("source_timeframe") or source.get("chart_timeframe") or source.get("timeframe") or payload.get("timeframe"))
    revision = safe_text(source.get("source_sync_id") or source.get("sync_id") or source.get("revision") or payload.get("source_sync_id"), 120)
    if timeframe not in PRIMARY_TIMEFRAMES:
        return jsonify(ok=False, error="Gebruik exact 1D, 4H, 15M of 3M"), 400
    draft = get_layer(load_chart_drafts(), asset, timeframe)
    if not draft:
        return jsonify(ok=False, error="Geen chartdraft gevonden voor deze asset/timeframe"), 404
    latest_revision = str(draft.get("revision") or draft.get("sync_id") or "")
    if not revision or not hmac.compare_digest(revision, latest_revision):
        return jsonify(ok=False, error="Deze chartversie is niet meer de nieuwste voor dit timeframe. Synchroniseer of open de review opnieuw."), 409
    try:
        candidate = dict(source)
        candidate.update(
            asset=asset, symbol=f"{asset}USDT", source_timeframe=timeframe, chart_timeframe=timeframe,
            source_sync_id=revision, reviewed=True, confirmed=True,
        )
        layer = normalize_layer(candidate, strict=True)
        stack = save_market_layer(layer)
        confirmed_draft = dict(draft)
        confirmed_draft.update(review_status="confirmed", confirmed=True, confirmed_at=utc_now())
        save_chart_draft(confirmed_draft)
        append_activity({
            "type": "chart_confirmed", "symbol": layer["symbol"], "asset": asset, "timeframe": timeframe,
            "note": f"{timeframe}-laag bevestigd · {len(layer.get('zones') or [])} zone(s)",
        })
        return jsonify(ok=True, layer=layer, stack=public_stack(stack), latest=decision_payload(asset))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.get("/api/v1/overview")
@app.get("/api/v2/overview")
def api_overview() -> Response:
    return jsonify(overview_payload(request.args.get("asset")))


@app.get("/api/v1/knowledge")
def api_knowledge() -> Response:
    limit = integer(request.args.get("limit"), 50, 1, 150)
    query = safe_text(request.args.get("q"), 800)
    rows = knowledge_feed(500)
    if query:
        rows = rank_knowledge(query, rows, limit=limit)
    else:
        rows = rows[:limit]
    return jsonify(ok=True, query=query or None, items=rows, source_count=len({row.get("source_url") or row.get("source_title") for row in rows}))


@app.get("/api/v1/knowledge/ingestion")
def api_knowledge_ingestion() -> Response:
    limit = integer(request.args.get("limit"), 100, 1, 500)
    return jsonify(ok=True, status=knowledge_source_status(), events=list(reversed(services.ingestion_events(limit))))


@app.post("/api/v1/knowledge/queue")
def api_knowledge_queue() -> Response:
    denied = require_owner()
    if denied:
        return denied
    if not rate_allowed("knowledge-queue", limit=30, seconds=3600):
        return jsonify(ok=False, error="Te veel kennislinks; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    link = safe_text(payload.get("url") or payload.get("video_id"), 800)
    try:
        result = services.enqueue_knowledge_video(
            link, title=safe_text(payload.get("title"), 240),
            source_label="PLATINUM-MANUAL", ingestion_source="PLATINUM_MANUAL",
            rights_status="operator_private_use_unconfirmed", commercial_use_allowed=False,
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    status_code = 202 if result.get("queued") else 200
    return jsonify(ok=True, result=result, status=knowledge_source_status()), status_code


@app.get("/api/v1/commercialization")
def api_commercialization() -> Response:
    return jsonify(ok=True, **commercialization_status())


@app.get("/api/v1/activity")
def api_activity() -> Response:
    limit = integer(request.args.get("limit"), 100, 1, 500)
    return jsonify(ok=True, events=list(reversed(load_activity_log()[-limit:])))


@app.post("/api/v1/activity")
def api_activity_add() -> Response:
    payload = request.get_json(silent=True) or {}
    event_type = safe_text(payload.get("type"), 50).lower()
    allowed = {
        "prepared", "submitted", "cancelled", "tp1_prepared", "tp2_prepared", "tp3_prepared",
        "ticket_failed", "layer_confirmed", "chart_synced", "chart_sync_failed", "chart_confirmed",
        "chart_unchanged", "fill_detected", "lifecycle_created", "lifecycle_promoted", "lifecycle_closed",
    }
    if event_type not in allowed:
        return jsonify(ok=False, error="ongeldig activity type"), 400
    payload["type"] = event_type
    if event_type in {"prepared", "submitted"}:
        # Persist only server-derived ticket classification. The journal can
        # later detect patterns without trusting a browser-supplied label.
        latest = decision_payload(payload.get("asset") or payload.get("symbol"))
        setup = latest.get("setup") if isinstance(latest.get("setup"), dict) else {}
        setup_15m = setup.get("setup_15m") if isinstance(setup.get("setup_15m"), dict) else {}
        payload.update(
            setup_type=setup_15m.get("type"),
            trigger_type=setup.get("trigger_type"),
            relation_to_context=setup.get("relation_to_context"),
            setup_grade=setup.get("grade"),
        )
    return jsonify(ok=True, event=append_activity(payload))


@app.get("/api/v1/journal")
def api_journal() -> Response:
    rows, deepdives, stats = journal_bundle()
    return jsonify(
        ok=True,
        summary=services.journal_summary() if is_owner() else (f"{len(rows)} beta-testtrades" if rows else "nog geen beta-testtrades"),
        stats=stats,
        trades=rows,
        curve=journal_curve(rows),
        deepdives=deepdives,
        activity=list(reversed(load_activity_log()[-160:])),
    )


@app.post("/api/v1/coach")
def api_coach() -> Response:
    if not rate_allowed("coach", limit=30, seconds=3600):
        return jsonify(ok=False, error="Te veel coachvragen; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    question = safe_text(payload.get("question"), 1800)
    if not question:
        return jsonify(ok=False, error="vraag ontbreekt"), 400
    latest = decision_payload(payload.get("asset"))
    language = safe_text(payload.get("language") or workspace_profile().get("language") or "nl", 10).lower()

    # Primary layer: Fable's curated, deduplicated dossiers. Supplemental layer:
    # short extracted video lessons. Video material can never outrank the fixed
    # methodology, operator policy, product safety, or the selected dossiers.
    primary = dossier_context(question, latest=latest, limit=3)
    ranked_knowledge = rank_knowledge(question, knowledge_feed(500), latest=latest, limit=6)
    visible_sources = source_cards(ranked_knowledge) if COACH_SHOW_SOURCES else []

    if not services.ANTHROPIC_API_KEY:
        answer = deterministic_dossier_answer(
            question, latest, primary.get("text") or "", ranked_knowledge, language=language
        )
        return jsonify(ok=True, answer=answer, source="curated_knowledge_mechanical", sources=visible_sources)
    try:
        from anthropic import Anthropic
        methodology = METHODOLOGY_FILE.read_text(encoding="utf-8")[:22000] if METHODOLOGY_FILE.exists() else ""
        instruction = coach_instruction()[:18000]
        _, _, coach_stats = journal_bundle()
        operational_context = json.dumps({
            "decision": latest,
            "journal": coach_stats,
            "profile": workspace_profile(),
        }, ensure_ascii=False)[:22000]
        supplemental = json.dumps(prompt_lessons(ranked_knowledge), ensure_ascii=False)[:12000]
        primary_text = safe_text(primary.get("text"), 30000)
        client = Anthropic(api_key=services.ANTHROPIC_API_KEY)
        answer_language = "Engels" if language.startswith("en") else "Nederlands"
        message = client.messages.create(
            model=os.environ.get("MYTRADINGBOT_COACH_MODEL", "claude-sonnet-4-6"),
            max_tokens=1200,
            system=(
                "Je bent de MyTradingBot-disciplinecoach. De volgende volgorde is bindend: "
                "(1) uitvoerbaar OPERATORBELEID en PRODUCTVEILIGHEID, (2) vaste productmethodiek, "
                "(3) de coach-instructie en geselecteerde primaire dossiers, (4) aanvullende videolessen. "
                "Een lagere laag kan nooit een hogere laag overschrijven. De cockpit blijft de enige actuele waarheid; "
                "maak nooit zelf een actuele setup, entry, stop of target en geef geen voorspellingen of garanties. "
                "De vaste keten is 1D context, 4H locatie/structuur, 15M setup en 3M uitvoering. "
                "Risico staat vast op 0,5% scalp, 1% day en 2% swing. Een ticket onder 3R is niet orderbaar. "
                "Na TP1 blijft de technische stop staan; break-even mag pas na TP2 en alleen als de resterende positie in winst staat. "
                "Praat als een ervaren mentor die deze kennis zelf beheerst. Noem nooit bronnen, dossiers, modules, seminars, video's, "
                "transcripten, bronnummers of citations in het antwoord. Gebruik geen [1]-achtige verwijzingen. "
                f"Antwoord concreet in het {answer_language}.\n\n"
                f"COACH-INSTRUCTIE (ondergeschikt aan productmethodiek bij conflict):\n{instruction}\n\n"
                f"PRODUCTMETHODIEK (bindend):\n{methodology}"
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"PRIMAIRE GESELECTEERDE DOSSIERS:\n{primary_text}\n\n"
                    f"AANVULLENDE KORTE VIDEOLESSEN (alleen gebruiken als ze niet conflicteren):\n{supplemental}\n\n"
                    f"COCKPIT- EN DAGBOEKDATA:\n{operational_context}\n\n"
                    f"VRAAG:\n{question}"
                ),
            }],
        )
        answer = sanitise_coach_answer("".join(getattr(block, "text", "") for block in message.content if getattr(block, "type", "") == "text").strip())
        return jsonify(ok=True, answer=answer, source="grounded_curated_knowledge", sources=visible_sources)
    except Exception as exc:
        answer = deterministic_dossier_answer(
            question, latest, primary.get("text") or "", ranked_knowledge, language=language
        )
        return jsonify(ok=True, answer=answer, source="curated_knowledge_fallback", sources=visible_sources, warning=str(exc))


def build_day_start_payload(asset: Any = None) -> Dict[str, Any]:
    """Build the same read-only day-start payload for HTTP and the scheduler."""
    overview = overview_payload(asset)
    day_start_query = "dagstart range confirmatie discipline sweep momentum no trade"
    ranked = rank_knowledge(day_start_query, knowledge_feed(500), latest=overview.get("latest") or {}, limit=12)
    video_lessons = [row for row in ranked if row.get("provenance") == "video-extraction"][:3]
    supplemental = video_lessons or ranked[:3]
    result = build_bilingual_day_start(overview, supplemental_lessons=prompt_lessons(supplemental))
    if any(briefing_has_price_advice(value) for value in (result.get("briefings") or {}).values()):
        raise RuntimeError("Dagstart kon niet veilig worden opgebouwd")
    return {**result, "coach_release": COACH_RELEASE, "automation_release": AUTOMATION_RELEASE, "ux_release": UX_RELEASE}


@app.post("/api/v1/commitment/activate")
def api_commitment_activate() -> Response:
    denied = require_owner()
    if denied:
        return denied
    if not rate_allowed("commitment-activate", limit=8, seconds=3600):
        return jsonify(ok=False, error="Te veel Commitment Mode-wijzigingen; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    if payload.get("active") is False or payload.get("disable") is True:
        return jsonify(ok=False, error="Commitment Mode kan vandaag niet worden uitgezet; morgen kies je opnieuw"), 409
    account = account_payload()
    if not account.get("equity_fresh"):
        return jsonify(ok=False, error="Een verse rekeningwaarde is nodig om Commitment Mode te vergrendelen"), 409
    try:
        commitment = activate_commitment(
            workspace_file(ACCOUNT_GUARD_NAME),
            equity=float(account.get("equity")),
            requested_loss_limit_pct=float(payload.get("daily_loss_limit_pct") or COMMITMENT_MAX_DAILY_LOSS_PCT),
            max_loss_limit_pct=COMMITMENT_MAX_DAILY_LOSS_PCT,
        )
    except (TypeError, ValueError) as exc:
        return jsonify(ok=False, error=str(exc)), 409
    journal_rows, _, _ = journal_bundle()
    snapshot = build_account_guard_snapshot(
        workspace_file(ACCOUNT_GUARD_NAME), journal_rows, account.get("positions") or [], account.get("equity"),
        default_loss_limit_pct=COMMITMENT_MAX_DAILY_LOSS_PCT, cooldown_minutes=REVENGE_COOLDOWN_MINUTES,
    )
    append_activity({"type":"commitment_mode_activated", "note":f"Commitment Mode vergrendeld op {commitment.get('daily_loss_limit_pct')}% dagbuffer en maximaal één positie"})
    return jsonify(ok=True, account_guard=snapshot)


@app.post("/api/v1/pattern-gates/activate")
def api_pattern_gate_activate() -> Response:
    """Owner-only human click: convert one open suggestion into a blocker."""
    denied = require_owner()
    if denied:
        return denied
    if not rate_allowed("pattern-gate-activate", limit=10, seconds=3600):
        return jsonify(ok=False, error="Te veel poortwijzigingen; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    suggestion_id = safe_text(payload.get("suggestion_id"), 120)
    if not suggestion_id:
        return jsonify(ok=False, error="Suggestie-id ontbreekt"), 400
    try:
        rule = activate_pattern_suggestion(
            workspace_file(JOURNAL_PATTERN_GATE_NAME), suggestion_id,
            actor=current_principal().get("display_name") or "owner",
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    append_activity({
        "type": "journal_pattern_rule_activated",
        "note": f"Extra dagboekpoort geactiveerd: {rule.get('reason')}",
    })
    rows, deepdives, _ = journal_bundle()
    snapshot = build_journal_pattern_snapshot(workspace_file(JOURNAL_PATTERN_GATE_NAME), rows, deepdives)
    return jsonify(ok=True, rule=rule, journal_pattern_gates=snapshot)


@app.post("/api/v1/pattern-gates/deactivate")
def api_pattern_gate_deactivate() -> Response:
    """Conscious owner-only removal with confirmation, reason and audit log."""
    denied = require_owner()
    if denied:
        return denied
    if not rate_allowed("pattern-gate-deactivate", limit=6, seconds=3600):
        return jsonify(ok=False, error="Te veel poortwijzigingen; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    rule_id = safe_text(payload.get("rule_id"), 120)
    reason = safe_text(payload.get("reason"), 800)
    confirmed = safe_text(payload.get("confirm"), 40).upper() == "DEACTIVEER REGEL"
    try:
        rule = deactivate_pattern_rule(
            workspace_file(JOURNAL_PATTERN_GATE_NAME), rule_id,
            actor=current_principal().get("display_name") or "owner",
            reason=reason, confirmed=confirmed,
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    append_activity({
        "type": "journal_pattern_rule_deactivated",
        "note": f"Dagboekpoort bewust gedeactiveerd · reden: {reason}",
    })
    rows, deepdives, _ = journal_bundle()
    snapshot = build_journal_pattern_snapshot(workspace_file(JOURNAL_PATTERN_GATE_NAME), rows, deepdives)
    return jsonify(ok=True, rule=rule, journal_pattern_gates=snapshot)


@app.post("/api/v1/day-start")
def api_day_start() -> Response:
    """Build a source-free, scenario-based day-start briefing.

    This route reads the same overview payload as the cockpit. A successful,
    non-blocked manual briefing records only the daily discipline routine. It
    cannot mutate any chart, gate, lifecycle, journal record or order state.
    """
    if not rate_allowed("day-start", limit=12, seconds=3600):
        return jsonify(ok=False, error="Te veel dagstartverzoeken; probeer later opnieuw"), 429
    payload = request.get_json(silent=True) or {}
    try:
        result = build_day_start_payload(payload.get("asset"))
        if not result.get("blocked"):
            record_day_start(workspace_file(DISCIPLINE_NAME))
        return jsonify(result)
    except RuntimeError as exc:
        return jsonify(ok=False, error=str(exc)), 503


@app.post("/api/v1/discipline/no-trade")
def api_discipline_no_trade() -> Response:
    """Record a conscious no-trade day without touching any trading gate."""
    if not rate_allowed("discipline-no-trade", limit=6, seconds=3600):
        return jsonify(ok=False, error="Te veel verzoeken; probeer later opnieuw"), 429
    rows, _, _ = journal_bundle()
    account = account_payload()
    try:
        record_no_trade(
            workspace_file(DISCIPLINE_NAME),
            rows,
            account.get("positions") or [],
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    snapshot = build_discipline_snapshot(
        workspace_file(DISCIPLINE_NAME),
        rows,
        account.get("positions") or [],
    )
    append_activity({"type": "discipline_no_trade", "note": "Bewuste no-trade-dag vastgelegd"})
    return jsonify(ok=True, discipline=snapshot)


@app.get("/api/v1/lifecycle")
def api_lifecycle_get() -> Response:
    return jsonify(ok=True, lifecycles=load_lifecycles())


@app.post("/api/v1/lifecycle")
def api_lifecycle_post() -> Response:
    payload = request.get_json(silent=True) or {}
    action = safe_text(payload.get("action"), 20).lower()
    data = load_lifecycles()
    records = data["records"]
    try:
        if action == "create":
            latest = decision_payload(payload.get("asset"))
            setup = latest.get("setup") or {}
            if not latest.get("execution_gate", {}).get("orderable") or not setup.get("risk_locked") or setup.get("origin_timeframe") != "3M":
                raise ValueError("Alleen een mechanisch vrijgegeven 3M-setup kan een lifecycle starten")
            record = create_lifecycle_record(setup)
            records[record["id"]] = record
            save_lifecycles(data)
            append_activity({"type": "lifecycle_created", "symbol": record.get("symbol"), "note": "Lifecycle gestart als SCALP_ACTIVE"})
            return jsonify(ok=True, record=record)
        record_id = safe_text(payload.get("id"), 80)
        record = records.get(record_id)
        if not isinstance(record, dict):
            return jsonify(ok=False, error="lifecycle niet gevonden"), 404
        if action == "evaluate":
            return jsonify(ok=True, evaluation=evaluate_lifecycle(record, payload.get("evidence") or {}))
        if action == "promote":
            updated = promote_lifecycle(record, payload.get("evidence") or {}, confirmed_by_user=bool(payload.get("confirmed_by_user")))
            records[record_id] = updated
            save_lifecycles(data)
            append_activity({"type": "lifecycle_promoted", "symbol": updated.get("symbol"), "note": f"Lifecycle naar {updated.get('stage')}"})
            return jsonify(ok=True, record=updated)
        if action == "close":
            updated = close_lifecycle(record, safe_text(payload.get("reason"), 300) or "Positie gesloten")
            records[record_id] = updated
            save_lifecycles(data)
            append_activity({"type": "lifecycle_closed", "symbol": updated.get("symbol"), "note": updated.get("history", [{}])[-1].get("reason")})
            return jsonify(ok=True, record=updated)
        return jsonify(ok=False, error="actie moet create, evaluate, promote of close zijn"), 400
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400


@app.post("/api/v1/process")
def api_process() -> Response:
    denied = require_owner()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    video_id = safe_text(payload.get("video_id"), 20)
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return jsonify(ok=False, error="ongeldige YouTube video-id"), 400
    title = safe_text(payload.get("title"), 200) or "Handmatig verwerkt"
    video_date = safe_text(payload.get("date"), 10) or datetime.now(timezone.utc).date().isoformat()
    done = services.load_processed()
    if video_id in done:
        done.discard(video_id)
        services.unmark_processed(video_id)
    ok = services.process_video({"id": video_id, "title": title, "video_date": video_date})
    result = safe_load_json(Path(services.STRUCTURED) / f"{video_id}.json", {})
    return jsonify(ok=ok, setup=result.get("setup"), title=result.get("_title"))


@app.post("/api/v1/reset")
def api_reset() -> Response:
    payload = request.get_json(silent=True) or {}
    if str(payload.get("confirm") or "").lower() != "wissen":
        return jsonify(ok=False, error='Stuur {"confirm":"wissen"} om het dagboek te wissen'), 400
    now_ms = int(time.time() * 1000)
    journal_path, _ = journal_paths()
    if is_owner():
        atomic_write_json(Path(services.JOURNAL_RESET), {"at_ms": now_ms})
    atomic_write_json(journal_path, [])
    append_activity({"type": "cancelled", "note": "Orderdagboek handmatig gereset"})
    return jsonify(ok=True, at_ms=now_ms)


# ---------------------------------------------------------------------------
# Compatibility routes for existing v5 clients; all remain token-protected.


@app.get("/latest")
@app.get("/livesetup")
def latest_compat() -> Response:
    return jsonify(decision_payload(request.args.get("asset")))


@app.get("/position")
def position_compat() -> Response:
    account = account_payload()
    return jsonify(ok=True, posities=account.get("positions") or [])


@app.get("/journal")
def journal_compat() -> Response:
    return api_journal()


@app.get("/deepdives")
def deepdives_compat() -> Response:
    _, deepdives_path = journal_paths()
    value = safe_load_json(deepdives_path, [])
    return jsonify(value if isinstance(value, list) else [])


@app.post("/readchart")
def readchart_compat() -> Response:
    return api_chart_analyze()


# Start only after every read-only payload helper is defined. The env gate is
# off by default, so a normal deploy never sends an unsolicited briefing.
TELEGRAM_DAY_START_WORKER = start_telegram_day_start_scheduler(
    lambda: build_day_start_payload(None),
    services.telegram,
    DATA_DIR,
    telegram_configured=bool(services.TELEGRAM_TOKEN and services.TELEGRAM_CHAT_ID),
)

WEEKLY_MENTOR_WORKER = start_weekly_mentor_scheduler(
    build_weekly_mentor_payload,
    services.telegram,
    DATA_DIR,
    telegram_configured=bool(services.TELEGRAM_TOKEN and services.TELEGRAM_CHAT_ID),
)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
