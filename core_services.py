"""Core infrastructure for MyTradingBot v8.

This module intentionally contains no setup-generation engine. TradingView zones are
owned by ``timeframe_stack.py`` and remain the only source for an orderable setup.
The services below are limited to:
- atomic persistence;
- read-only Bybit/account data;
- public market prices;
- journal analytics;
- knowledge/video ingestion with explicit provenance.

It replaces the old runtime dependency on ``legacy_brain.py``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import feedparser
import requests

from account_guards import claim_r_breach, record_stop_out
from journal_pattern_gates import refresh_from_files_and_notify

from post_trade_coach_loop import (
    configure_post_trade_coach_loop,
    enrich_post_trade_analysis,
    flush_post_trade_coach_loop,
    post_trade_coach_loop_status as _post_trade_coach_loop_status,
    queue_post_trade_coach_loop,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("mytradingbot-v8")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
TRANSCRIPTS = DATA_DIR / "transcripts"
STRUCTURED = DATA_DIR / "structured"
PROCESSED = DATA_DIR / "processed.json"
JOURNAL = DATA_DIR / "journal.json"
JOURNAL_RESET = DATA_DIR / "journal_reset.json"
DEEPDIVES = DATA_DIR / "deepdives.json"
USER_LEVELS = DATA_DIR / "user_levels.json"
INGESTION_LOG = DATA_DIR / "knowledge_ingestion.json"
KNOWLEDGE_SOURCE_STATE = DATA_DIR / "knowledge_source_state.json"
PUBLIC_FEED_STATE = DATA_DIR / "knowledge_public_feed.json"
PACKAGED_KNOWLEDGE_QUEUE = Path(__file__).with_name("queue.json")
KNOWLEDGE_QUEUE = Path(os.environ.get("MYTRADINGBOT_KNOWLEDGE_QUEUE") or (DATA_DIR / "knowledge_queue.json"))
SEEN_EXEC = DATA_DIR / "seen_exec_v7.json"
TP_PROGRESS = DATA_DIR / "tp_progress_v7.json"
MANUAL_ALERTS = DATA_DIR / "manual_position_alerts_v8.json"
ACCOUNT_GUARD_STATE = DATA_DIR / "account_guards_r25b.json"
JOURNAL_PATTERN_GATE_STATE = DATA_DIR / "journal_pattern_gates_r25c.json"

for folder in (DATA_DIR, TRANSCRIPTS, STRUCTURED):
    folder.mkdir(parents=True, exist_ok=True)

configure_post_trade_coach_loop(
    DATA_DIR,
    structured_dir=STRUCTURED,
    methodology_file=Path(__file__).with_name("methodology_sources.json"),
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY", "").strip()
YT_CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET", "").strip()
BYBIT_BASE = os.environ.get("BYBIT_READONLY_BASE", "https://api.bytick.com").rstrip("/")
CHECK_EVERY_SEC = int(os.environ.get("CHECK_EVERY_SEC", str(60 * 60)))
ACCOUNT_WATCH_INTERVAL_SEC = max(20, int(os.environ.get("ACCOUNT_WATCH_INTERVAL_SEC", "60")))
DISABLE_BACKGROUND_WORKERS = os.environ.get("DISABLE_BACKGROUND_WORKERS", "0") == "1"
ENABLE_KNOWLEDGE_INGESTION = os.environ.get("MYTRADINGBOT_ENABLE_KNOWLEDGE_INGESTION", "0") == "1"
ENABLE_PUBLIC_YOUTUBE_RSS = os.environ.get("MYTRADINGBOT_ENABLE_PUBLIC_YOUTUBE_RSS", "1") == "1"
ENABLE_R_BREACH_TELEGRAM = os.environ.get("MYTRADINGBOT_ENABLE_R_BREACH_TELEGRAM", "0") == "1"
REVENGE_COOLDOWN_MINUTES = max(1, min(1440, int(os.environ.get("MYTRADINGBOT_REVENGE_COOLDOWN_MINUTES", "30"))))

_LOCK = threading.RLock()
_KNOWLEDGE_WAKE = threading.Event()
_PROCESSING_VIDEO_IDS: set[str] = set()
_KNOWLEDGE_WORKER_STATE: Dict[str, Any] = {
    "enabled": False, "running": False, "last_success": None, "last_error": None,
    "backlog_processed": 0, "rss_discovered": 0,
}
_EQUITY_CACHE: Dict[str, Any] = {"v": None, "at": 0.0}
_POSITION_CACHE: Dict[str, Any] = {"v": [], "at": 0.0}
_ACCOUNT_WORKER_STATE: Dict[str, Any] = {
    "enabled": False, "running": False, "last_success": None, "last_error": None,
    "journal_writes": 0, "telegram_sent": 0, "seen_executions": 0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _load(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _atomic_dump(path: Path | str, value: Any, **kwargs: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, **kwargs)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def load_processed() -> set[str]:
    value = _load(PROCESSED, [])
    return {str(item) for item in value} if isinstance(value, list) else set()


def mark_processed(video_id: str) -> None:
    with _LOCK:
        values = load_processed()
        values.add(str(video_id))
        _atomic_dump(PROCESSED, sorted(values), indent=2)


def unmark_processed(video_id: str) -> None:
    with _LOCK:
        values = load_processed()
        values.discard(str(video_id))
        _atomic_dump(PROCESSED, sorted(values), indent=2)


def norm_date(value: Any) -> str:
    raw = str(value or "").strip()
    match = re.match(r"(\d{2})-(\d{2})-(\d{4})", raw)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return ""


def _queue_dates() -> Dict[str, str]:
    queue_path = KNOWLEDGE_QUEUE if KNOWLEDGE_QUEUE.exists() else PACKAGED_KNOWLEDGE_QUEUE
    value = _load(queue_path, [])
    if not isinstance(value, list):
        return {}
    return {str(row.get("id")): norm_date(row.get("date")) for row in value if isinstance(row, dict)}


QUEUE_DATES = _queue_dates()


def eff_date(item: Dict[str, Any]) -> str:
    return str(item.get("_video_date") or QUEUE_DATES.get(str(item.get("_id") or "")) or item.get("_processed_at") or "")[:10]


# ------------------------------------------------------------------ market/account

def get_prices(assets: Optional[Iterable[str]] = None) -> Dict[str, float]:
    """Read only the requested public market prices with short fail-closed timeouts.

    A cockpit request must never wait tens of seconds because an external ticker is
    unreachable. Callers pass the active asset so BTC requests do not also fetch ETH.
    """
    requested = []
    for raw in (assets or ("BTC", "ETH")):
        asset = re.sub(r"[^A-Z0-9]", "", str(raw or "").upper()).removesuffix("USDT")[:16]
        if asset and asset not in requested:
            requested.append(asset)
    out: Dict[str, float] = {}
    endpoints = (
        "https://api.bybit.com/v5/market/tickers",
        "https://api.bytick.com/v5/market/tickers",
    )
    for asset in requested:
        symbol = f"{asset}USDT"
        value: Optional[float] = None
        for endpoint in endpoints:
            try:
                response = requests.get(
                    endpoint,
                    params={"category": "linear", "symbol": symbol},
                    timeout=(1.5, 2.5),
                )
                row = ((response.json().get("result") or {}).get("list") or [])[0]
                value = finite(row.get("markPrice") or row.get("lastPrice"))
                if value and value > 0:
                    break
            except Exception as exc:  # pragma: no cover - network dependent
                log.warning("Prijs %s via %s niet beschikbaar: %s", symbol, endpoint, exc)
        if not value:
            try:
                response = requests.get(
                    f"https://api.coinbase.com/v2/prices/{asset}-USD/spot",
                    timeout=(1.5, 2.5),
                )
                value = finite(((response.json().get("data") or {}).get("amount")))
            except Exception as exc:  # pragma: no cover - network dependent
                log.warning("Coinbase prijs %s niet beschikbaar: %s", asset, exc)
        if value and value > 0:
            out[asset] = float(value)
    return out


def _bybit_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not (BYBIT_API_KEY and BYBIT_API_SECRET):
        return {}
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    query = "&".join(f"{key}={params[key]}" for key in params)
    payload = timestamp + BYBIT_API_KEY + recv_window + query
    signature = hmac.new(BYBIT_API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
    }
    response = requests.get(BYBIT_BASE + path, params=params, headers=headers, timeout=15)
    try:
        return response.json()
    except Exception:
        log.error("Bybit %s gaf geen JSON (HTTP %s)", path, response.status_code)
        return {}


def get_equity(force: bool = False) -> Optional[float]:
    if not (BYBIT_API_KEY and BYBIT_API_SECRET):
        return None
    now = time.time()
    if not force and _EQUITY_CACHE["v"] is not None and now - float(_EQUITY_CACHE["at"] or 0) < 300:
        return finite(_EQUITY_CACHE["v"])
    for account_type in ("UNIFIED", "CONTRACT"):
        try:
            data = _bybit_get("/v5/account/wallet-balance", {"accountType": account_type})
            rows = ((data.get("result") or {}).get("list") or [])
            if rows:
                value = finite(rows[0].get("totalEquity") or rows[0].get("totalWalletBalance"))
                if value and value > 0:
                    _EQUITY_CACHE.update(v=value, at=now)
                    return value
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("Equity via %s niet beschikbaar: %s", account_type, exc)
    return finite(_EQUITY_CACHE["v"])


def get_open_positions(force: bool = False) -> List[Dict[str, Any]]:
    if not (BYBIT_API_KEY and BYBIT_API_SECRET):
        return []
    now = time.time()
    if not force and now - float(_POSITION_CACHE["at"] or 0) < 30:
        return list(_POSITION_CACHE.get("v") or [])
    try:
        data = _bybit_get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"})
        result: List[Dict[str, Any]] = []
        for row in ((data.get("result") or {}).get("list") or []):
            size = finite(row.get("size"), 0.0) or 0.0
            if size <= 0:
                continue
            result.append({
                "symbol": str(row.get("symbol") or "")[:32],
                "side": str(row.get("side") or "")[:12],
                "size": size,
                "entry": finite(row.get("avgPrice")),
                "mark": finite(row.get("markPrice")),
                "pnl": finite(row.get("unrealisedPnl"), 0.0),
                "stop_loss": finite(row.get("stopLoss")),
                "take_profit": finite(row.get("takeProfit")),
                "leverage": finite(row.get("leverage")),
                "liq": finite(row.get("liqPrice")),
            })
        _POSITION_CACHE.update(v=result, at=now)
        return result
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("Open posities niet beschikbaar: %s", exc)
        return list(_POSITION_CACHE.get("v") or [])


def get_instrument(symbol: str) -> Dict[str, Any]:
    clean = re.sub(r"[^A-Z0-9]", "", str(symbol or "").upper())[:24]
    if not clean:
        raise ValueError("ongeldig instrument")
    endpoints = ("https://api.bybit.com", "https://api.bytick.com")
    for endpoint in endpoints:
        try:
            response = requests.get(
                endpoint + "/v5/market/instruments-info",
                params={"category": "linear", "symbol": clean},
                timeout=10,
            )
            rows = ((response.json().get("result") or {}).get("list") or [])
            if not rows:
                continue
            row = rows[0]
            lot = row.get("lotSizeFilter") or {}
            price = row.get("priceFilter") or {}
            leverage = row.get("leverageFilter") or {}
            return {
                "symbol": clean,
                "qty_step": finite(lot.get("qtyStep"), 0.001),
                "min_qty": finite(lot.get("minOrderQty"), 0.001),
                "min_notional": finite(lot.get("minNotionalValue"), 5.0),
                "tick_size": finite(price.get("tickSize"), 0.1),
                "min_leverage": finite(leverage.get("minLeverage"), 1.0),
                "max_leverage": finite(leverage.get("maxLeverage"), 100.0),
                "leverage_step": finite(leverage.get("leverageStep"), 0.01),
                "source": endpoint,
            }
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("Instrument %s via %s niet beschikbaar: %s", clean, endpoint, exc)
    raise RuntimeError("instrumentgegevens niet beschikbaar")



# ------------------------------------------------------------------ notifications and account watcher

def telegram(text: str) -> bool:
    """Send an optional Telegram notification without ever failing the worker."""
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": str(text)[:3900]},
            timeout=15,
        )
        ok = response.ok
        if ok:
            _ACCOUNT_WORKER_STATE["telegram_sent"] = int(_ACCOUNT_WORKER_STATE.get("telegram_sent") or 0) + 1
        else:
            log.warning("Telegram HTTP %s: %s", response.status_code, response.text[:200])
        return ok
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("Telegram niet beschikbaar: %s", exc)
        return False


def post_trade_coach_loop_status() -> Dict[str, Any]:
    return _post_trade_coach_loop_status()


def account_worker_status() -> Dict[str, Any]:
    state = dict(_ACCOUNT_WORKER_STATE)
    state.update(
        configured=bool(BYBIT_API_KEY and BYBIT_API_SECRET),
        telegram_configured=bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        interval_seconds=ACCOUNT_WATCH_INTERVAL_SEC,
        post_trade_coach_loop=post_trade_coach_loop_status(),
    )
    return state

def _event_time(row: Dict[str, Any]) -> str:
    raw = finite(row.get("updatedTime") or row.get("execTime") or row.get("createdTime"))
    if raw and raw > 10_000_000_000:
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc).isoformat()
    return utc_now()


def _closed_trade_id(row: Dict[str, Any]) -> str:
    return str(row.get("orderId") or row.get("execId") or row.get("updatedTime") or "").strip()


SOURCE_LABELS = {
    "BYBIT_VERIFIED": "BYBIT GEVERIFIEERD",
    "LEGACY_IMPORT": "LEGACY-IMPORT",
    "PAPER": "PAPER",
    "TESTDATA": "TESTDATA",
    "UNKNOWN": "ONBEKEND",
}

ORIGIN_LABELS = {
    "MYTRADINGBOT_TICKET": "MYTRADINGBOT-TICKET",
    "MANUAL_OPEN": "HANDMATIG GEOPEND",
    "UNKNOWN": "HERKOMST ONBEKEND",
}


def journal_source_class(item: Dict[str, Any]) -> str:
    """Classify a journal row without inventing provenance.

    Unknown historic rows stay unknown. They remain visible in the journal, but
    are explicitly separated from paper/test rows and from API-verified Bybit
    close records.
    """
    raw = str(item.get("source_class") or item.get("source") or "").strip().upper()
    if item.get("test_data") is True or "TEST" in raw or "FIXTURE" in raw or "DEMO" in raw:
        return "TESTDATA"
    if item.get("paper") is True or "PAPER" in raw or "SIMULAT" in raw:
        return "PAPER"
    if raw in {"BYBIT_VERIFIED", "BYBIT GEVERIFIEERD"} or raw.startswith("BYBIT"):
        return "BYBIT_VERIFIED"
    if raw in {"LEGACY_IMPORT", "LEGACY-IMPORT"} or "LEGACY" in raw or "IMPORT" in raw:
        return "LEGACY_IMPORT"
    return "UNKNOWN"


def journal_source_label(item: Dict[str, Any]) -> str:
    return SOURCE_LABELS[journal_source_class(item)]


def _parse_iso_timestamp(value: Any) -> float:
    try:
        stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    except (TypeError, ValueError):
        return 0.0


def _recent_ticket_activity(row: Dict[str, Any], *, max_age_hours: float = 168.0) -> Optional[Dict[str, Any]]:
    """Find a recent verified MyTradingBot ticket matching this Bybit trade.

    The watcher cannot trust a browser-side claim by itself.  It only treats a
    trade as product-prepared when the persisted activity log contains a recent
    ``submitted`` event with a verified ticket and matching symbol/direction.
    """
    symbol = str(row.get("symbol") or "").upper()
    direction = _position_direction(row)
    entry = finite(row.get("avgEntryPrice") or row.get("execPrice") or row.get("entry"))
    event_time_raw = finite(row.get("updatedTime") or row.get("execTime") or row.get("createdTime"))
    event_time = event_time_raw / 1000 if event_time_raw and event_time_raw > 10_000_000_000 else time.time()
    candidates: List[Dict[str, Any]] = []
    for name in ("activity_v8.json", "activity_v6.json", "activity_v51.json", "activity_v5.json", "activity_v4.json"):
        value = _load(DATA_DIR / name, [])
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    for item in reversed(candidates):
        if str(item.get("type") or "").lower() != "submitted" or item.get("ticket_verified") is not True:
            continue
        if str(item.get("symbol") or "").upper() != symbol:
            continue
        item_direction = str(item.get("direction") or "").lower()
        if direction in {"long", "short"} and item_direction and item_direction != direction:
            continue
        activity_time = _parse_iso_timestamp(item.get("at"))
        if activity_time and (activity_time > event_time + 300 or event_time - activity_time > max_age_hours * 3600):
            continue
        activity_entry = finite(item.get("entry"))
        if entry is not None and activity_entry is not None and abs(entry - activity_entry) / max(abs(entry), 1.0) > 0.004:
            continue
        return item
    return None


def trade_origin(row: Dict[str, Any]) -> Dict[str, str]:
    origin_class = "MYTRADINGBOT_TICKET" if _recent_ticket_activity(row) else "MANUAL_OPEN"
    return {"class": origin_class, "label": ORIGIN_LABELS[origin_class]}


def _planned_risk_context(row: Dict[str, Any]) -> Dict[str, Any]:
    activity = _recent_ticket_activity(row)
    risk_usd = finite((activity or {}).get("risk_usd"))
    pnl = finite(row.get("closedPnl"), 0.0) or 0.0
    r_multiple = pnl / risk_usd if risk_usd is not None and risk_usd > 0 else None
    return {
        "activity": activity,
        "planned_risk_usd": round(risk_usd, 8) if risk_usd is not None and risk_usd > 0 else None,
        "r_multiple": round(r_multiple, 6) if r_multiple is not None else None,
        "r_breach_alarm": bool(r_multiple is not None and r_multiple < -1.0),
    }


def _journal_time_key(item: Dict[str, Any]) -> Tuple[int, str]:
    raw_ms = finite(item.get("updated_time_ms") or item.get("updatedTime") or item.get("closed_at_ms"))
    if raw_ms is not None:
        return (0, f"{int(raw_ms):020d}")
    raw = str(item.get("closed_at") or item.get("time") or item.get("at") or "")
    return (1, raw)


def log_closed_trade(row: Dict[str, Any]) -> bool:
    """Persist an authoritative Bybit closed-PnL row exactly once.

    This is the fuel line for the journal. It is intentionally independent from
    Telegram and from the LLM so a notification or coaching failure can never
    suppress bookkeeping.
    """
    trade_id = _closed_trade_id(row)
    if not trade_id:
        return False
    pnl = finite(row.get("closedPnl"), 0.0) or 0.0
    equity_snapshot = get_equity(force=True)
    with _LOCK:
        journal = _load(JOURNAL, [])
        journal = journal if isinstance(journal, list) else []
        if any(str(item.get("_id")) == trade_id for item in journal if isinstance(item, dict)):
            return False
        reset_at = finite((_load(JOURNAL_RESET, {}) or {}).get("at_ms"), 0.0) or 0.0
        row_time = finite(row.get("updatedTime"), 0.0) or 0.0
        if reset_at and row_time and row_time < reset_at:
            return False
        direction = _position_direction(row)
        open_fee_raw = finite(row.get("openFee"))
        close_fee_raw = finite(row.get("closeFee"))
        funding_raw = finite(row.get("fundingFee"))
        origin = trade_origin(row)
        risk_context = _planned_risk_context(row)
        item = {
            "_id": trade_id,
            "source": "BYBIT-CLOSED-PNL",
            "source_class": "BYBIT_VERIFIED",
            "source_label": f"BYBIT GEVERIFIEERD · {origin['label']}",
            "origin_class": origin["class"],
            "origin_label": origin["label"],
            "verified_source": True,
            "test_data": False,
            "record_kind": "BYBIT_CLOSE_RECORD",
            "pnl_basis": "BYBIT_CLOSED_PNL_NET",
            "fees_included_in_pnl": True,
            "funding_included_in_pnl": True,
            "symbol": str(row.get("symbol") or "")[:32],
            "side": str(row.get("side") or "")[:12],
            "direction": direction,
            "entry": finite(row.get("avgEntryPrice")),
            "exit": finite(row.get("avgExitPrice")),
            "qty": finite(row.get("qty") or row.get("closedSize")),
            "closed_size": finite(row.get("closedSize") or row.get("qty")),
            "fill_count": int(finite(row.get("fillCount"), 0.0) or 0),
            "leverage": finite(row.get("leverage")),
            "pnl": round(pnl, 8),
            "equity_snapshot": round(float(equity_snapshot), 8) if equity_snapshot else None,
            "equity_snapshot_basis": "POST_CLOSE_ACCOUNT_EQUITY" if equity_snapshot else None,
            "pnl_pct": round(pnl / float(equity_snapshot) * 100, 6) if equity_snapshot else None,
            "open_fee": round(abs(open_fee_raw), 8) if open_fee_raw is not None else None,
            "close_fee": round(abs(close_fee_raw), 8) if close_fee_raw is not None else None,
            "fees": round(abs(open_fee_raw or 0.0) + abs(close_fee_raw or 0.0), 8),
            "funding": round(funding_raw, 8) if funding_raw is not None else None,
            "cost_fields_complete": open_fee_raw is not None and close_fee_raw is not None,
            "time": _event_time(row),
            "updated_time_ms": int(row_time) if row_time else None,
            "raw_order_id": str(row.get("orderId") or "")[:100],
            "planned_risk_usd": risk_context.get("planned_risk_usd"),
            "risk_pct": finite((risk_context.get("activity") or {}).get("risk_pct")),
            "stop_loss": finite((risk_context.get("activity") or {}).get("stop_loss")),
            "trade_type": str((risk_context.get("activity") or {}).get("trade_type") or "")[:20],
            "origin_timeframe": str((risk_context.get("activity") or {}).get("timeframe") or "3M")[:8],
            "setup_type": str((risk_context.get("activity") or {}).get("setup_type") or "")[:40],
            "trigger_type": str((risk_context.get("activity") or {}).get("trigger_type") or "")[:40],
            "relation_to_context": str((risk_context.get("activity") or {}).get("relation_to_context") or "")[:60],
            "setup_grade": str((risk_context.get("activity") or {}).get("setup_grade") or "")[:4].upper(),
            "r_multiple": risk_context.get("r_multiple"),
            "r_breach_alarm": bool(risk_context.get("r_breach_alarm")),
            "r_breach_reason": "R < -1: controleer of de technische stop is verruimd of de uitvoering materieel afweek" if risk_context.get("r_breach_alarm") else None,
        }
        journal.append(item)
        _atomic_dump(JOURNAL, journal[-5000:], indent=2)
    _ACCOUNT_WORKER_STATE["journal_writes"] = int(_ACCOUNT_WORKER_STATE.get("journal_writes") or 0) + 1
    return True


def _load_methodology_excerpt() -> str:
    try:
        return Path(__file__).with_name("mytradingbot_methodology.md").read_text(encoding="utf-8")[:10000]
    except OSError:
        return ""


def analyze_closed_trade(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create an optional process deep-dive; never blocks the journal writer."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import Anthropic
        pnl = finite(row.get("closedPnl"), 0.0) or 0.0
        equity = get_equity()
        pct = pnl / equity * 100 if equity else None
        direction = _position_direction(row)
        prompt = (
            "Analyseer uitsluitend het PROCES van deze afgeronde trade. Een winst kan een slecht proces zijn "
            "en een verlies kan een goed proces zijn. Verzin geen ontbrekende chartfeiten. "
            "Gebruik Nederlands en geef uitsluitend JSON met: uitkomst, proces_grade (A/B/C), oordeel, "
            "wat_ging_goed, wat_kan_beter, les, source_label. Zet source_label op POST-TRADE-COACH.\n\n"
            f"Methodiek:\n{_load_methodology_excerpt()}\n\n"
            f"Trade: {direction.upper()} {row.get('symbol')} · entry {row.get('avgEntryPrice')} · "
            f"exit {row.get('avgExitPrice')} · PnL {pnl:+.2f} USDT"
            + (f" ({pct:+.3f}% account)" if pct is not None else "")
        )
        message = Anthropic(api_key=ANTHROPIC_API_KEY).messages.create(
            model=os.environ.get("MYTRADINGBOT_COACH_MODEL", "claude-sonnet-4-6"),
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(getattr(block, "text", "") for block in message.content if getattr(block, "type", "") == "text")
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        value = json.loads(match.group(0))
        if not isinstance(value, dict):
            return None
        value["source_label"] = "POST-TRADE-COACH"
        return value
    except Exception as exc:  # pragma: no cover - external model
        log.warning("Post-trade analyse niet beschikbaar: %s", exc)
        return None


def save_deepdive(row: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    trade_id = _closed_trade_id(row)
    if not trade_id or not isinstance(analysis, dict):
        return False
    with _LOCK:
        items = _load(DEEPDIVES, [])
        items = items if isinstance(items, list) else []
        existing = next((item for item in items if isinstance(item, dict) and str(item.get("_id")) == trade_id), None)
        if existing:
            _attach_deepdive_to_journal(trade_id, existing)
            return False
        item = {
            **analysis,
            "_id": trade_id,
            "symbol": str(row.get("symbol") or "")[:32],
            "direction": _position_direction(row),
            "pnl": round(finite(row.get("closedPnl"), 0.0) or 0.0, 8),
            "time": utc_now(),
            "source_label": str(analysis.get("source_label") or "POST-TRADE-COACH")[:40],
        }
        items.append(item)
        _atomic_dump(DEEPDIVES, items[-1000:], indent=2)
        _attach_deepdive_to_journal(trade_id, item)
    return True


def _attach_deepdive_to_journal(trade_id: str, analysis: Dict[str, Any]) -> bool:
    """Persist the process grade on the same journal row as the deepdive.

    Joining at read time remains supported, but storing the link here prevents a
    temporary or migrated deepdive file from making an already graded trade look
    like ``not assessed`` in another client.
    """
    with _LOCK:
        rows = _load(JOURNAL, [])
        if not isinstance(rows, list):
            return False
        changed = False
        for item in rows:
            if not isinstance(item, dict) or str(item.get("_id")) != trade_id:
                continue
            item["deepdive_id"] = trade_id
            item["proces_grade"] = str(analysis.get("proces_grade") or "")[:4].upper()
            item["process_judgement"] = str(analysis.get("oordeel") or "")[:500]
            item["lesson"] = str(analysis.get("les") or "")[:1200]
            changed = True
            break
        if changed:
            _atomic_dump(JOURNAL, rows[-5000:], indent=2)
        return changed


def _execution_kind(row: Dict[str, Any]) -> str:
    stop_type = str(row.get("stopOrderType") or "").lower()
    identifiers = (str(row.get("orderLinkId") or "") + " " + str(row.get("orderId") or "")).lower()
    if "takeprofit" in stop_type or "-tp" in identifiers or "tp1" in identifiers or "tp2" in identifiers or "tp3" in identifiers:
        return "tp"
    if "stoploss" in stop_type or ("stop" in stop_type and "takeprofit" not in stop_type) or "-sl" in identifiers:
        return "sl"
    if (finite(row.get("closedSize"), 0.0) or 0.0) > 0:
        return "exit"
    return "entry"


def _tp_progress(row: Dict[str, Any]) -> int:
    key = f"{row.get('symbol','?')}:{row.get('positionIdx','0')}"
    order_id = str(row.get("orderId") or row.get("execId") or "")
    with _LOCK:
        state = _load(TP_PROGRESS, {})
        state = state if isinstance(state, dict) else {}
        orders = [str(value) for value in (state.get(key) or [])]
        if order_id and order_id not in orders:
            orders.append(order_id)
        state[key] = orders[-20:]
        _atomic_dump(TP_PROGRESS, state, indent=2)
    return len(orders)


def _clear_tp_progress(symbol: str, position_idx: Any = None) -> None:
    with _LOCK:
        state = _load(TP_PROGRESS, {})
        if not isinstance(state, dict):
            return
        prefix = f"{symbol}:"
        for key in list(state):
            if key.startswith(prefix) and (position_idx is None or key == f"{symbol}:{position_idx}"):
                state.pop(key, None)
        _atomic_dump(TP_PROGRESS, state, indent=2)


def _position_snapshot_message() -> str:
    """Return an authoritative read-only snapshot after an entry fill."""
    try:
        positions = get_open_positions(force=True)
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("Positiesnapshot niet beschikbaar: %s", exc)
        return ""
    if not positions:
        return "📊 Geen open positie meer."
    lines: List[str] = []
    for position in positions:
        direction = "LONG" if str(position.get("side") or "").lower() == "buy" else "SHORT"
        lines.append(
            f"{direction} {position.get('size','?')} {position.get('symbol','?')} @ {position.get('entry','?')} "
            f"· SL {position.get('stop_loss') or '-'} · TP {position.get('take_profit') or '-'} · {position.get('leverage') or '?'}x"
        )
    return "📊 Huidige open positie(s):\n" + "\n".join(lines)


def _aggregate_execution_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse Bybit partial fills into one deterministic order event."""
    groups: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = _execution_kind(row)
        order_id = str(row.get("orderId") or row.get("orderLinkId") or row.get("execId") or "")
        key = (order_id, kind, str(row.get("symbol") or ""), str(row.get("side") or ""))
        if key not in groups:
            groups[key] = dict(row)
            groups[key]["partial_fill_count"] = 0
            groups[key]["_qty_total"] = 0.0
            groups[key]["_notional_total"] = 0.0
            groups[key]["exec_ids"] = []
            order.append(key)
        aggregate = groups[key]
        qty = finite(row.get("execQty"), 0.0) or 0.0
        price = finite(row.get("execPrice"), 0.0) or 0.0
        aggregate["partial_fill_count"] += 1
        aggregate["_qty_total"] += qty
        aggregate["_notional_total"] += qty * price
        if row.get("execId"):
            aggregate["exec_ids"].append(str(row.get("execId")))
        if finite(row.get("execTime"), 0.0) and (finite(row.get("execTime"), 0.0) or 0.0) > (finite(aggregate.get("execTime"), 0.0) or 0.0):
            aggregate["execTime"] = row.get("execTime")
    result: List[Dict[str, Any]] = []
    for key in order:
        aggregate = groups[key]
        qty = aggregate.pop("_qty_total")
        notional = aggregate.pop("_notional_total")
        aggregate["execQty"] = round(qty, 12)
        aggregate["execPrice"] = round(notional / qty, 8) if qty > 0 else aggregate.get("execPrice")
        result.append(aggregate)
    return result


def _manual_position_alert(row: Dict[str, Any]) -> bool:
    """Send one non-blocking process mirror for a position opened outside MyTradingBot."""
    if _recent_ticket_activity(row):
        return False
    order_id = str(row.get("orderId") or row.get("orderLinkId") or row.get("execId") or "")
    if not order_id:
        return False
    with _LOCK:
        alerted = {str(value) for value in (_load(MANUAL_ALERTS, []) or [])}
        if order_id in alerted:
            return False
        alerted.add(order_id)
        _atomic_dump(MANUAL_ALERTS, sorted(alerted)[-5000:], indent=2)
    positions = get_open_positions(force=True)
    symbol = str(row.get("symbol") or "")
    position = next((item for item in positions if str(item.get("symbol") or "") == symbol), None)
    direction = "LONG" if str((position or {}).get("side") or row.get("side") or "").lower() == "buy" else "SHORT"
    entry = finite((position or {}).get("entry") or row.get("execPrice"))
    stop = finite((position or {}).get("stop_loss"))
    target = finite((position or {}).get("take_profit"))
    leverage = finite((position or {}).get("leverage"))
    rr: Optional[float] = None
    if entry is not None and stop is not None and target is not None and abs(entry - stop) > 0:
        rr = abs(target - entry) / abs(entry - stop)
    observations: List[str] = []
    if stop is None:
        observations.append("geen stop zichtbaar")
    if target is None:
        observations.append("geen doel zichtbaar")
    if rr is not None and rr < 3:
        observations.append(f"R:R {rr:.2f} is lager dan 3R")
    details = [f"instap {entry:g}" if entry is not None else "instap onbekend"]
    if stop is not None:
        details.append(f"stop {stop:g}")
    if target is not None:
        details.append(f"doel {target:g}")
    if leverage is not None:
        details.append(f"{leverage:g}x leverage")
    mirror = " · ".join(observations) if observations else "geen direct meetbare afwijking in stop en R:R"
    return telegram(
        f"🪞 Handmatig geopende positie gezien · {direction} {symbol}\n"
        f"{' · '.join(details)}\n"
        f"Proces-spiegel: {mirror}. Bewust? MyTradingBot blokkeert niets; jij houdt de eindbeslissing."
    )


def notify_execution(row: Dict[str, Any], *, include_snapshot: bool = True) -> Dict[str, Any]:
    """Classify one new read-only execution and send the appropriate message.

    The function never changes a position or stop. It only reports what Bybit
    returned. TP1 explicitly keeps the technical stop; TP2 only permits a
    manual break-even move when the remaining position is actually profitable.
    """
    kind = _execution_kind(row)
    symbol = str(row.get("symbol") or "?")
    side = str(row.get("side") or "?")
    qty = row.get("execQty")
    price = row.get("execPrice")
    fills = max(1, int(finite(row.get("partial_fill_count"), 1.0) or 1))
    fill_suffix = f" · {fills} deelvullingen" if fills > 1 else ""
    event: Dict[str, Any] = {"kind": kind, "symbol": symbol, "side": side, "qty": qty, "price": price, "partial_fill_count": fills}
    if kind == "tp":
        count = _tp_progress(row)
        display_count = min(max(count, 1), 3)
        positions = get_open_positions(force=True)
        position = next((item for item in positions if item.get("symbol") == symbol), None)
        in_profit = bool(position and (finite(position.get("pnl"), 0.0) or 0.0) > 0)
        event.update(tp_number=display_count, position_in_profit=in_profit)
        if display_count == 1:
            telegram(
                f"🎯 TP1 geraakt · {symbol} @ {price} ({qty}){fill_suffix}\n"
                "Stop blijft technisch staan; break-even is nog NIET toegestaan."
            )
        else:
            suffix = (
                "Break-even is nu handmatig toegestaan."
                if in_profit
                else "Wacht met break-even tot de resterende positie aantoonbaar in winst staat."
            )
            telegram(
                f"🎯 TP{display_count} geraakt · {symbol} @ {price} ({qty}){fill_suffix}\n"
                f"{suffix} De stop wordt nooit automatisch aangepast."
            )
    elif kind == "sl":
        _clear_tp_progress(symbol, row.get("positionIdx"))
        stop_event_id = str(row.get("orderId") or row.get("execId") or ",".join(row.get("exec_ids") or []) or f"{symbol}:{row.get('execTime') or ''}")
        cooldown = record_stop_out(
            ACCOUNT_GUARD_STATE, event_id=stop_event_id, symbol=symbol,
            occurred_at=datetime.fromisoformat(_event_time(row)), cooldown_minutes=REVENGE_COOLDOWN_MINUTES,
        )
        event["revenge_cooldown_until"] = cooldown.get("cooldown_until")
        telegram(
            f"🛑 Stop-loss geraakt · {symbol} {side} {qty} @ {price}{fill_suffix}\n"
            f"Geen revenge-trade; de cockpit toont {REVENGE_COOLDOWN_MINUTES} minuten afkoeltijd en blokkeert alleen wanneer Commitment Mode actief is."
        )
    elif kind == "entry":
        telegram(f"✅ Order gevuld / positie vergroot · {symbol} {side} {qty} @ {price}{fill_suffix}")
        if include_snapshot:
            snapshot = _position_snapshot_message()
            if snapshot:
                telegram(snapshot)
    else:
        # Closed-PnL is the authoritative close event.  Suppressing this generic
        # execution message prevents one close from producing two Telegram alerts.
        event["telegram_suppressed"] = True
    return event


def process_execution_rows(rows: Iterable[Dict[str, Any]], seen: set[str], *, first_cycle: bool) -> List[Dict[str, Any]]:
    """Process only unseen executions; startup backlog is stored but never announced."""
    new_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        exec_id = str(row.get("execId") or "")
        if not exec_id or exec_id in seen:
            continue
        seen.add(exec_id)
        new_rows.append(row)
    if not first_cycle:
        entry_seen = False
        for row in _aggregate_execution_rows(reversed(new_rows)):
            event = notify_execution(row, include_snapshot=False)
            if event.get("kind") == "entry":
                entry_seen = True
                _manual_position_alert(row)
        if entry_seen:
            snapshot = _position_snapshot_message()
            if snapshot:
                telegram(snapshot)
    return new_rows


def process_closed_pnl_rows(rows: Iterable[Dict[str, Any]], *, first_cycle: bool) -> int:
    """Write authoritative closes and feed the optional outgoing coach loop.

    No new market polling is introduced: pending coach messages are retried only
    when the existing read-only account watcher completes another close cycle.
    """
    inserted_count = 0
    for row in reversed(list(rows)):
        if not isinstance(row, dict) or not log_closed_trade(row):
            continue
        inserted_count += 1
        _clear_tp_progress(str(row.get("symbol") or ""))
        if first_cycle:
            continue
        pnl = finite(row.get("closedPnl"), 0.0) or 0.0
        equity = get_equity()
        pct_text = f" ({pnl / equity * 100:+.3f}% account)" if equity else ""
        telegram(f"🏁 Trade gesloten · {_position_direction(row).upper()} {row.get('symbol')} · {pnl:+.2f} USDT{pct_text}")
        risk_context = _planned_risk_context(row)
        if ENABLE_R_BREACH_TELEGRAM and risk_context.get("r_breach_alarm"):
            trade_id = _closed_trade_id(row)
            if claim_r_breach(ACCOUNT_GUARD_STATE, trade_id=trade_id, r_multiple=float(risk_context["r_multiple"])):
                telegram(
                    f"⚠️ R < -1 alarm · {row.get('symbol')} · {float(risk_context['r_multiple']):.2f}R\n"
                    "Deze trade sloot slechter dan het vooraf opgeslagen risico. Controleer in het dagboek of de stop is verruimd, slippage/fees afweken of de uitvoering niet volgens plan verliep. Geen nieuw signaal; alleen procescontrole."
                )
        analysis = analyze_closed_trade(row)
        if analysis:
            analysis = enrich_post_trade_analysis(row, analysis)
        if analysis and save_deepdive(row, analysis):
            queued = queue_post_trade_coach_loop(row, analysis)
            if not queued:
                telegram(
                    f"🔎 Deepdive · proces {analysis.get('proces_grade','?')}\n"
                    f"Goed: {analysis.get('wat_ging_goed','')}\n"
                    f"Beter: {analysis.get('wat_kan_beter','')}\n"
                    f"Les: {analysis.get('les','')}"
                )
        # The existing close event is the only trigger. Suggestions may be
        # created and optionally announced, but rules are never activated here.
        refresh_from_files_and_notify(JOURNAL_PATTERN_GATE_STATE, JOURNAL, DEEPDIVES, telegram)
    if not first_cycle:
        flush_post_trade_coach_loop(telegram)
    return inserted_count

def watch_account() -> None:  # pragma: no cover - operational worker
    """Read-only Bybit fill/close watcher -> journal, deep-dives and Telegram."""
    if not (BYBIT_API_KEY and BYBIT_API_SECRET):
        _ACCOUNT_WORKER_STATE.update(enabled=False, running=False, last_error="Bybit read-only sleutel ontbreekt")
        log.info("Account-watcher uit: geen Bybit read-only sleutel")
        return
    _ACCOUNT_WORKER_STATE.update(enabled=True, running=True, last_error=None)
    seen = {str(value) for value in (_load(SEEN_EXEC, []) or [])}
    first_cycle = not bool(seen)
    log.info("Account-watcher v8.2.2 gestart (alleen-lezen)")
    while True:
        try:
            executions = _bybit_get("/v5/execution/list", {"category": "linear", "limit": "50"})
            rows = ((executions.get("result") or {}).get("list") or [])
            process_execution_rows(rows, seen, first_cycle=first_cycle)
            _atomic_dump(SEEN_EXEC, sorted(seen)[-10000:], indent=2)
            _ACCOUNT_WORKER_STATE["seen_executions"] = len(seen)

            closed = _bybit_get("/v5/position/closed-pnl", {"category": "linear", "limit": "50"})
            closed_rows = ((closed.get("result") or {}).get("list") or [])
            process_closed_pnl_rows(closed_rows, first_cycle=first_cycle)

            first_cycle = False
            _ACCOUNT_WORKER_STATE.update(last_success=utc_now(), last_error=None, running=True)
        except Exception as exc:
            _ACCOUNT_WORKER_STATE.update(last_error=str(exc)[:500], running=True)
            log.exception("Account-watcher fout")
        time.sleep(ACCOUNT_WATCH_INTERVAL_SEC)

def start_account_worker() -> Optional[threading.Thread]:
    if DISABLE_BACKGROUND_WORKERS:
        return None
    if not (BYBIT_API_KEY and BYBIT_API_SECRET):
        _ACCOUNT_WORKER_STATE.update(enabled=False, running=False, last_error="Bybit read-only sleutel ontbreekt")
        return None
    thread = threading.Thread(target=watch_account, daemon=True, name="mytradingbot-account-watcher")
    thread.start()
    return thread

# ------------------------------------------------------------------ journal

def _position_direction(item: Dict[str, Any]) -> str:
    explicit = str(item.get("direction") or "").lower()
    if explicit in {"long", "short"}:
        return explicit
    close_side = str(item.get("side") or item.get("close_side") or "").lower()
    return "long" if close_side == "sell" else "short" if close_side == "buy" else "unknown"


def _trade_pct(item: Dict[str, Any]) -> Optional[float]:
    """Return only a percentage supported by this trade's own snapshot.

    Never backfill a historic trade with today's account equity. Historic
    percentages must remain stable when the live account balance changes.
    """
    stored = finite(item.get("pnl_pct"))
    snapshot = finite(item.get("equity_snapshot"))
    if stored is not None and snapshot is not None and snapshot > 0:
        return stored
    if snapshot is None or snapshot <= 0:
        return None
    pnl = finite(item.get("pnl"))
    return pnl / snapshot * 100 if pnl is not None else None


def compute_journal_stats(rows: Iterable[Dict[str, Any]], *, include_simulated: bool = False) -> Dict[str, Any]:
    """Pure, deterministic journal statistics with explicit data coverage.

    ``closedPnl`` from Bybit is treated as the final net result. Fee/funding
    fields are shown for auditability and are never subtracted a second time.
    Paper and test rows are excluded from owner-live performance unless the
    caller explicitly requests simulated statistics.
    """
    source_rows = [dict(row) for row in rows if isinstance(row, dict)]
    source_counts = {key: 0 for key in SOURCE_LABELS}
    for row in source_rows:
        source_counts[journal_source_class(row)] += 1

    excluded_simulated = 0
    eligible: List[Dict[str, Any]] = []
    for row in source_rows:
        source_class = journal_source_class(row)
        if not include_simulated and source_class in {"PAPER", "TESTDATA"}:
            excluded_simulated += 1
            continue
        eligible.append(row)
    eligible.sort(key=_journal_time_key)

    n = len(eligible)
    empty = {
        "records": 0, "trades": 0, "wins": 0, "losses": 0, "breakeven": 0,
        "winrate": None, "profit_factor": None, "profit_factor_infinite": False,
        "profit_factor_publishable": False, "expectancy_usdt": None,
        "expectancy_pct": None, "total_pnl": 0.0, "total_pnl_pct": None,
        "avg_win": None, "avg_loss": None, "avg_win_pct": None, "avg_loss_pct": None,
        "max_drawdown": None, "max_drawdown_pct": None, "max_loss_streak": 0,
        "fees": 0.0, "funding": 0.0, "slippage": 0.0, "snapshot_coverage": 0,
        "snapshot_count": 0, "percentage_metrics_available": False,
        "percentage_metrics_reason": "Nog geen sluitingsrecords.",
        "source_counts": source_counts, "verified_source_count": source_counts["BYBIT_VERIFIED"],
        "unknown_source_count": source_counts["UNKNOWN"], "excluded_simulated": excluded_simulated,
        "sample_label": "geen data", "sample_sufficient": False, "sample_reliable": False,
        "record_label": "afgeronde sluitingsrecords", "pnl_basis": "NETTO GEREALISEERD",
        "costs_already_included": False, "cost_reconciliation_status": "geen data",
        "per_symbool": {}, "per_richting": {}, "per_setup": {}, "per_timeframe": {},
        "per_risk_profile": {}, "per_process": {},
    }
    if not n:
        return empty

    pnls = [finite(row.get("pnl"), 0.0) or 0.0 for row in eligible]
    pcts = [_trade_pct(row) for row in eligible]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    snapshot_count = sum(1 for row, pct in zip(eligible, pcts) if pct is not None and (finite(row.get("equity_snapshot")) or 0) > 0)
    coverage = snapshot_count / n * 100
    percentage_complete = snapshot_count == n
    available_pcts = [value for value in pcts if value is not None]
    win_pcts = [value for value, pnl in zip(pcts, pnls) if value is not None and pnl > 0]
    loss_pcts = [value for value, pnl in zip(pcts, pnls) if value is not None and pnl < 0]

    # Closed-result USD drawdown from chronological net PnL records.
    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    loss_streak = 0
    max_loss_streak = 0
    for pnl in pnls:
        running += pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)
        if pnl < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0

    # Percentage drawdown uses actual post-close equity snapshots and is only
    # published when every record has a snapshot.
    max_drawdown_pct: Optional[float] = None
    if percentage_complete:
        equity_points = [finite(row.get("equity_snapshot")) for row in eligible]
        if all(value is not None and value > 0 for value in equity_points):
            equity_peak = float(equity_points[0])
            pct_dd = 0.0
            for equity_value in equity_points:
                current = float(equity_value)
                equity_peak = max(equity_peak, current)
                if equity_peak > 0:
                    pct_dd = max(pct_dd, (equity_peak - current) / equity_peak * 100)
            max_drawdown_pct = pct_dd

    def grouped(key_fn) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for row in eligible:
            key = str(key_fn(row) or "onbekend")
            result[key] = round(result.get(key, 0.0) + float(finite(row.get("pnl"), 0.0) or 0.0), 4)
        return result

    r_values = [finite(row.get("r_multiple")) for row in eligible]
    r_values = [value for value in r_values if value is not None]
    mae_values = [finite(row.get("mae_r")) for row in eligible]
    mae_values = [value for value in mae_values if value is not None]
    mfe_values = [finite(row.get("mfe_r")) for row in eligible]
    mfe_values = [value for value in mfe_values if value is not None]
    fees = sum(abs(finite(row.get("fees"), 0.0) or 0.0) for row in eligible)
    funding = sum(finite(row.get("funding"), 0.0) or 0.0 for row in eligible)
    slippage = sum(abs(finite(row.get("slippage"), 0.0) or 0.0) for row in eligible)
    all_bybit = all(journal_source_class(row) == "BYBIT_VERIFIED" for row in eligible)
    any_bybit = any(journal_source_class(row) == "BYBIT_VERIFIED" for row in eligible)
    source_verified = sum(1 for row in eligible if journal_source_class(row) == "BYBIT_VERIFIED")

    sample_label = "betrouwbaarder" if n >= 100 else "in opbouw" if n >= 30 else "te kleine steekproef" if n >= 10 else "onvoldoende trades"
    pct_reason = (
        "Alle sluitingsrecords hebben een eigen historische equity-snapshot."
        if percentage_complete
        else f"Onvoldoende historische equitydata — {snapshot_count} van {n} records."
    )
    profit_factor = gross_win / gross_loss if gross_loss > 0 else None
    return {
        **empty,
        "records": n,
        "trades": n,  # backwards-compatible API alias; UI labels these as close records
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": n - len(wins) - len(losses),
        "winrate": round(len(wins) / n * 100, 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "profit_factor_infinite": bool(gross_win > 0 and gross_loss == 0),
        "profit_factor_publishable": n >= 10,
        "expectancy_usdt": round(sum(pnls) / n, 2),
        "expectancy_pct": round(sum(available_pcts) / len(available_pcts), 4) if percentage_complete and available_pcts else None,
        "partial_expectancy_pct": round(sum(available_pcts) / len(available_pcts), 4) if available_pcts else None,
        "expectancy_r": round(sum(r_values) / len(r_values), 3) if r_values else None,
        "total_pnl": round(sum(pnls), 2),
        "net_pnl": round(sum(pnls), 2),
        "total_pnl_pct": round(sum(available_pcts), 4) if percentage_complete and available_pcts else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else None,
        "avg_win_pct": round(sum(win_pcts) / len(win_pcts), 4) if percentage_complete and win_pcts else None,
        "avg_loss_pct": round(abs(sum(loss_pcts) / len(loss_pcts)), 4) if percentage_complete and loss_pcts else None,
        "partial_avg_win_pct": round(sum(win_pcts) / len(win_pcts), 4) if win_pcts else None,
        "partial_avg_loss_pct": round(abs(sum(loss_pcts) / len(loss_pcts)), 4) if loss_pcts else None,
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 4) if max_drawdown_pct is not None else None,
        "max_loss_streak": max_loss_streak,
        "fees": round(fees, 2),
        "funding": round(funding, 2),
        "slippage": round(slippage, 2),
        "avg_mae_r": round(sum(mae_values) / len(mae_values), 3) if mae_values else None,
        "avg_mfe_r": round(sum(mfe_values) / len(mfe_values), 3) if mfe_values else None,
        "snapshot_coverage": round(coverage, 2),
        "snapshot_count": snapshot_count,
        "percentage_metrics_available": percentage_complete,
        "percentage_metrics_reason": pct_reason,
        "source_counts": source_counts,
        "verified_source_count": source_verified,
        "unknown_source_count": sum(1 for row in eligible if journal_source_class(row) == "UNKNOWN"),
        "excluded_simulated": excluded_simulated,
        "source_coverage": round(source_verified / n * 100, 2),
        "sample_label": sample_label,
        "sample_sufficient": n >= 30,
        "sample_reliable": n >= 100,
        "record_label": "afgeronde sluitingsrecords",
        "pnl_basis": "BYBIT CLOSED PNL (NETTO)" if all_bybit else "GEMENGDE BRONNEN" if any_bybit else "JOURNAL PNL",
        "costs_already_included": all_bybit,
        "cost_reconciliation_status": "Bybit closedPnl bevat trading- en fundingkosten; kosten worden niet dubbel afgetrokken." if all_bybit else "Gemengde of onbekende bron: kostendekking afzonderlijk controleren.",
        "per_symbool": grouped(lambda row: row.get("symbol") or row.get("asset")),
        "per_richting": grouped(_position_direction),
        "per_setup": grouped(lambda row: row.get("setup_type") or "onbekend"),
        "per_timeframe": grouped(lambda row: row.get("origin_timeframe") or "onbekend"),
        "per_risk_profile": grouped(lambda row: row.get("trade_type") or "onbekend"),
        "per_process": grouped(lambda row: "regels_gevolgd" if row.get("rules_followed") is True else "regels_afgeweken" if row.get("rules_followed") is False else "onbekend"),
    }


def journal_stats() -> Dict[str, Any]:
    rows = _load(JOURNAL, [])
    return compute_journal_stats(rows if isinstance(rows, list) else [], include_simulated=False)


def journal_summary() -> str:
    stats = journal_stats()
    if not stats.get("records"):
        return "nog geen afgeronde sluitingsrecords"
    parts = [
        f"{stats['records']} sluitingsrecords ({stats['sample_label']})",
        f"winrate per sluitingsrecord {stats['winrate']}%",
        f"netto gerealiseerd {stats.get('total_pnl')} USDT",
    ]
    if stats.get("total_pnl_pct") is not None:
        parts.append(f"som tradepercentages {stats['total_pnl_pct']}%")
    else:
        parts.append(stats.get("percentage_metrics_reason") or "historische equitydekking onvolledig")
    if stats.get("expectancy_r") is not None:
        parts.append(f"expectancy {stats['expectancy_r']}R")
    return " · ".join(parts)


# ------------------------------------------------------------------ knowledge ingestion

class TranscriptUnavailable(RuntimeError):
    """Permanent source failure: no usable transcript exists for this video."""


def youtube_video_id(value: Any) -> str:
    """Return one canonical YouTube video id from an id or supported URL."""
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in {"live", "shorts", "embed"}:
            video_id = parts[1]
    return video_id if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or "") else ""


def public_feed_state() -> Dict[str, Any]:
    value = _load(PUBLIC_FEED_STATE, {})
    return value if isinstance(value, dict) else {}


def _save_public_feed_state(**fields: Any) -> Dict[str, Any]:
    state = {**public_feed_state(), **fields, "updated_at": utc_now()}
    _atomic_dump(PUBLIC_FEED_STATE, state, indent=2)
    return state


def _runtime_queue() -> List[Dict[str, Any]]:
    value = _load(KNOWLEDGE_QUEUE, []) if KNOWLEDGE_QUEUE.exists() else []
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def enqueue_knowledge_video(
    url_or_id: Any, *, title: Any = "", video_date: Any = "",
    source_label: str = "PLATINUM-MANUAL", ingestion_source: str = "PLATINUM_MANUAL",
    rights_status: str = "operator_private_use_unconfirmed", commercial_use_allowed: bool = False,
) -> Dict[str, Any]:
    """Idempotently append a video to the persistent queue and wake the worker."""
    video_id = youtube_video_id(url_or_id)
    if not video_id:
        raise ValueError("ongeldige YouTube-link of video-id")
    if video_id in load_processed():
        return {"video_id": video_id, "status": "already_processed", "queued": False}
    source_state = load_knowledge_source_state().get(video_id) or {}
    if source_state.get("status") == "excluded_no_transcript":
        return {"video_id": video_id, "status": "quarantined_no_transcript", "queued": False}
    merged = {str(row.get("id")): row for row in load_knowledge_queue() if isinstance(row, dict)}
    if video_id in merged:
        return {"video_id": video_id, "status": "already_queued", "queued": False}
    row = {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": str(title or "").strip()[:300],
        "date": norm_date(video_date),
        "source_label": str(source_label or "EXTERNE-BRON").strip().upper()[:40],
        "ingestion_source": str(ingestion_source or "MANUAL").strip().upper()[:40],
        "rights_status": str(rights_status or "operator_private_use_unconfirmed")[:80],
        "commercial_use_allowed": bool(commercial_use_allowed),
        "queued_at": utc_now(),
    }
    with _LOCK:
        runtime = _runtime_queue()
        if any(str(item.get("id")) == video_id for item in runtime):
            return {"video_id": video_id, "status": "already_queued", "queued": False}
        runtime.append(row)
        _atomic_dump(KNOWLEDGE_QUEUE, runtime, indent=2)
    update_knowledge_source_state(video_id, status="queued", title=row["title"], ingestion_source=row["ingestion_source"])
    _append_ingestion_event({
        "video_id": video_id, "title": row["title"] or f"YouTube-video {video_id}",
        "status": "queued", "source": row["ingestion_source"],
    })
    _KNOWLEDGE_WAKE.set()
    return {"video_id": video_id, "status": "queued", "queued": True, "row": row}


def knowledge_worker_status() -> Dict[str, Any]:
    return {**_KNOWLEDGE_WORKER_STATE, "public_feed": public_feed_state()}


def load_knowledge_queue() -> List[Dict[str, Any]]:
    """Merge the packaged corpus with an optional persistent operator queue.

    A stale /data queue from an earlier release must not silently hide newly
    packaged sources. Runtime rows may enrich metadata, but source IDs remain
    unique and the packaged 103-source corpus stays present.
    """
    packaged = _load(PACKAGED_KNOWLEDGE_QUEUE, [])
    runtime = _load(KNOWLEDGE_QUEUE, []) if KNOWLEDGE_QUEUE.exists() else []
    merged: Dict[str, Dict[str, Any]] = {}
    for collection in (packaged, runtime):
        if not isinstance(collection, list):
            continue
        for row in collection:
            if not isinstance(row, dict):
                continue
            video_id = str(row.get("id") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                continue
            merged[video_id] = {**merged.get(video_id, {}), **row, "id": video_id}
    return list(merged.values())


def load_knowledge_source_state() -> Dict[str, Dict[str, Any]]:
    value = _load(KNOWLEDGE_SOURCE_STATE, {})
    return {str(key): row for key, row in value.items() if isinstance(row, dict)} if isinstance(value, dict) else {}


def update_knowledge_source_state(video_id: str, **fields: Any) -> None:
    with _LOCK:
        state = load_knowledge_source_state()
        state[str(video_id)] = {**state.get(str(video_id), {}), **fields, "updated_at": utc_now()}
        _atomic_dump(KNOWLEDGE_SOURCE_STATE, state, indent=2)


def get_youtube_metadata(video_id: str) -> Dict[str, str]:
    """Best-effort public metadata; ingestion still works when oEmbed is unavailable."""
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=20,
        )
        if response.status_code == 200:
            data = response.json()
            return {"title": str(data.get("title") or "")[:300], "author_name": str(data.get("author_name") or "")[:200]}
    except Exception:
        pass
    return {}


def get_transcript(video_id: str) -> str:
    cached = TRANSCRIPTS / f"{video_id}.txt"
    if cached.exists():
        text = cached.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) >= 50:
            return text
    if not SUPADATA_API_KEY:
        raise RuntimeError("SUPADATA_API_KEY ontbreekt")
    response = requests.get(
        "https://api.supadata.ai/v1/transcript",
        params={"url": f"https://www.youtube.com/watch?v={video_id}", "text": "true"},
        headers={"x-api-key": SUPADATA_API_KEY},
        timeout=180,
    )
    body = response.text[:500]
    if response.status_code != 200:
        low = body.lower()
        if response.status_code in {400, 404, 422} and any(term in low for term in ("transcript", "caption", "subtitle", "not available", "not found", "disabled")):
            raise TranscriptUnavailable(f"Geen bruikbaar transcript: Supadata HTTP {response.status_code}")
        raise RuntimeError(f"Supadata HTTP {response.status_code}: {body[:300]}")
    content = response.json().get("content")
    if isinstance(content, list):
        text = " ".join(str(segment.get("text") or "") for segment in content if isinstance(segment, dict)).strip()
    else:
        text = str(content or "").strip()
    if len(text) < 50:
        raise TranscriptUnavailable(f"Geen bruikbaar transcript ({len(text)} tekens)")
    cached.write_text(text, encoding="utf-8")
    return text


def _knowledge_prompt(text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Extract lessons only; never create a live trade setup from a video."""
    if not ANTHROPIC_API_KEY:
        return {
            "video_type": "kennis",
            "summary": text[:1200],
            "knowledge": [],
            "warnings": ["Anthropic niet geconfigureerd; transcript is opgeslagen maar nog niet inhoudelijk geëxtraheerd."],
        }
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    schema = {
        "video_type": "daily|weekupdate|deepdive|seminar|kennis|onbekend",
        "summary": "Nederlandse samenvatting",
        "knowledge": [
            {
                "title": "korte regel",
                "statement": "exacte les in eigen woorden",
                "category": "context|zone|entry|risk|management|mindset|journal",
                "source_label": "EXTERNE-BRON",
                "confidence": 0,
                "evidence": "korte onderbouwing uit transcript zonder lang citaat",
                "official_status": "official|interpretation|unconfirmed",
                "tags": ["zoekwoorden in het Nederlands"],
                "timeframes": ["1D|4H|15M|3M|algemeen"],
                "applies_when": "wanneer deze les relevant is",
                "avoid_when": "wanneer deze les niet toegepast mag worden",
            }
        ],
        "warnings": ["onzekerheden of conflicten"],
    }
    message = client.messages.create(
        model=os.environ.get("MYTRADINGBOT_INGEST_MODEL", "claude-sonnet-4-6"),
        max_tokens=1800,
        system=(
            "Je extraheert uitsluitend educatieve MyTradingBot-kennis uit een transcript. "
            "Maak NOOIT een actuele trade, entry, stop of target. Geef alleen JSON volgens het schema. "
            "Gebruik korte parafrases; citeer nooit lange transcriptpassages. "
            "Externe lessen zijn adviserend en mogen OPERATORBELEID of PRODUCTVEILIGHEID nooit overschrijven. "
            "Label iedere regel met de bronlabel uit de metadata en markeer interpretaties of onzekerheden eerlijk."
        ),
        messages=[{
            "role": "user",
            "content": f"METADATA:\n{json.dumps(metadata, ensure_ascii=False)}\n\nSCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\nTRANSCRIPT:\n{text[:80000]}",
        }],
    )
    raw = "".join(getattr(block, "text", "") for block in message.content if getattr(block, "type", "") == "text").strip()
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise RuntimeError("Claude gaf geen JSON-object terug")
    value = json.loads(match.group(0))
    return value if isinstance(value, dict) else {}


def _append_ingestion_event(event: Dict[str, Any]) -> None:
    rows = _load(INGESTION_LOG, [])
    rows = rows if isinstance(rows, list) else []
    clean = {**event, "at": event.get("at") or utc_now()}
    rows.append(clean)
    _atomic_dump(INGESTION_LOG, rows[-1000:], indent=2)


def process_video(meta: Dict[str, Any]) -> bool:
    video_id = str(meta.get("id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("ongeldige YouTube video-id")
    if video_id in load_processed():
        return False
    with _LOCK:
        if video_id in _PROCESSING_VIDEO_IDS:
            return False
        _PROCESSING_VIDEO_IDS.add(video_id)
    try:
        metadata = get_youtube_metadata(video_id) if not meta.get("title") else {}
        title = str(meta.get("title") or metadata.get("title") or f"YouTube-video {video_id}")[:300]
        video_date = norm_date(meta.get("video_date") or meta.get("date"))
        source_label = str(meta.get("source_label") or "DOOPIECASH-VIDEO")[:40].upper()
        ingestion_source = str(meta.get("ingestion_source") or "YOUTUBE/SUPADATA")[:40].upper()
        rights_status = str(meta.get("rights_status") or "operator_private_use_unconfirmed")[:80]
        commercial_use_allowed = bool(meta.get("commercial_use_allowed", False))
        started = utc_now()
        _append_ingestion_event({"video_id": video_id, "title": title, "status": "started", "source": ingestion_source, "started_at": started})
        try:
            transcript = get_transcript(video_id)
            if len(transcript) < 50:
                raise TranscriptUnavailable(f"Geen bruikbaar transcript ({len(transcript)} tekens)")
            (TRANSCRIPTS / f"{video_id}.txt").write_text(transcript, encoding="utf-8")
            extracted = _knowledge_prompt(transcript, {
                "video_id": video_id, "title": title, "date": video_date,
                "source_label": source_label, "rights_status": rights_status,
                "commercial_use_allowed": commercial_use_allowed,
            })
            knowledge = []
            for index, row in enumerate(extracted.get("knowledge") or []):
                if not isinstance(row, dict):
                    continue
                knowledge.append({
                    "id": f"{video_id}:{index + 1}",
                    "title": str(row.get("title") or "Les")[:180],
                    "statement": str(row.get("statement") or row.get("summary") or "")[:1800],
                    "summary": str(row.get("statement") or row.get("summary") or "")[:600],
                    "category": str(row.get("category") or "kennis")[:40],
                    "source_label": str(row.get("source_label") or source_label)[:40].upper(),
                    "source_id": video_id,
                    "source_url": f"https://www.youtube.com/watch?v={video_id}",
                    "source_title": title,
                    "source_date": video_date,
                    "confidence": max(0, min(100, int(finite(row.get("confidence"), 0) or 0))),
                    "evidence": str(row.get("evidence") or "")[:1000],
                    "official_status": str(row.get("official_status") or "unconfirmed")[:30],
                    "extractor_version": "8.2.2-kb3-round23",
                    "tags": [str(value)[:80] for value in (row.get("tags") or []) if str(value).strip()][:20],
                    "timeframes": [str(value)[:20] for value in (row.get("timeframes") or []) if str(value).strip()][:8],
                    "applies_when": str(row.get("applies_when") or "")[:800],
                    "avoid_when": str(row.get("avoid_when") or "")[:800],
                    "rights_status": rights_status,
                    "commercial_use_allowed": commercial_use_allowed,
                })
            data = {
                "_id": video_id, "_title": title, "_video_date": video_date,
                "_processed_at": utc_now(), "_source": "YOUTUBE/SUPADATA",
                "_ingestion_source": ingestion_source,
                "_source_url": f"https://www.youtube.com/watch?v={video_id}",
                "_extractor_version": "8.2.2-kb3-round23",
                "_rights_status": rights_status, "_commercial_use_allowed": commercial_use_allowed,
                "video_type": str(extracted.get("video_type") or "onbekend"),
                "summary": str(extracted.get("summary") or "")[:5000],
                "knowledge": knowledge,
                "warnings": [str(item)[:600] for item in (extracted.get("warnings") or [])],
                "setup": None,
            }
            _atomic_dump(STRUCTURED / f"{video_id}.json", data, indent=2)
            mark_processed(video_id)
            update_knowledge_source_state(video_id, status="completed", title=title, knowledge_count=len(knowledge), ingestion_source=ingestion_source)
            if ingestion_source == "PUBLIC_RSS":
                _save_public_feed_state(
                    channel_id=YT_CHANNEL_ID, enabled=True,
                    last_auto_fetched_at=data["_processed_at"],
                    last_auto_video_id=video_id, last_auto_video_title=title,
                    last_auto_video_date=video_date, last_processed_knowledge_count=len(knowledge),
                )
            _append_ingestion_event({
                "video_id": video_id, "title": title, "status": "completed",
                "source": ingestion_source, "knowledge_count": len(knowledge),
                "processed_at": data["_processed_at"],
            })
            return True
        except TranscriptUnavailable as exc:
            update_knowledge_source_state(video_id, status="excluded_no_transcript", title=title, reason=str(exc)[:500], ingestion_source=ingestion_source)
            _append_ingestion_event({"video_id": video_id, "title": title, "status": "skipped", "error": str(exc)[:800], "source": ingestion_source})
            return False
        except Exception as exc:
            log.exception("Video %s verwerken mislukt", video_id)
            update_knowledge_source_state(video_id, status="retryable_error", title=title, reason=str(exc)[:500], ingestion_source=ingestion_source)
            _append_ingestion_event({"video_id": video_id, "title": title, "status": "failed", "error": str(exc)[:800], "source": ingestion_source})
            return False
    finally:
        with _LOCK:
            _PROCESSING_VIDEO_IDS.discard(video_id)

def ingestion_events(limit: int = 200) -> List[Dict[str, Any]]:
    rows = _load(INGESTION_LOG, [])
    return [row for row in rows if isinstance(row, dict)][-max(1, min(limit, 1000)):] if isinstance(rows, list) else []


def check_new_videos() -> int:
    """Discover public-channel videos and persist them to the same idempotent queue."""
    if not ENABLE_PUBLIC_YOUTUBE_RSS or not YT_CHANNEL_ID:
        return 0
    checked_at = utc_now()
    try:
        feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={YT_CHANNEL_ID}")
        entries = list(getattr(feed, "entries", []) or [])
        if getattr(feed, "bozo", False) and not entries:
            raise RuntimeError(str(getattr(feed, "bozo_exception", "YouTube RSS kon niet worden gelezen")))
        discovered = 0
        latest_id = ""
        latest_title = ""
        latest_published = ""
        for entry in entries:
            video_id = str(getattr(entry, "yt_videoid", "") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                continue
            title = str(getattr(entry, "title", "") or "")[:300]
            published = str(getattr(entry, "published", "") or "")[:10]
            result = enqueue_knowledge_video(
                video_id, title=title, video_date=published,
                source_label="PUBLIC-YOUTUBE", ingestion_source="PUBLIC_RSS",
                rights_status="public_source_private_coaching_only", commercial_use_allowed=False,
            )
            if result.get("queued"):
                discovered += 1
            if not latest_id:
                latest_id, latest_title, latest_published = video_id, title, published
        _save_public_feed_state(
            channel_id=YT_CHANNEL_ID, enabled=True, last_checked_at=checked_at,
            last_success_at=utc_now(), last_error=None, discovered_last_run=discovered,
            last_discovered_video_id=latest_id, last_discovered_video_title=latest_title,
            last_discovered_video_date=latest_published,
            last_discovered_at=utc_now() if discovered else public_feed_state().get("last_discovered_at"),
        )
        _KNOWLEDGE_WORKER_STATE["rss_discovered"] = int(_KNOWLEDGE_WORKER_STATE.get("rss_discovered") or 0) + discovered
        return discovered
    except Exception as exc:
        _save_public_feed_state(channel_id=YT_CHANNEL_ID, enabled=True, last_checked_at=checked_at, last_error=str(exc)[:600])
        raise


def run_backlog() -> int:
    queue = load_knowledge_queue()
    done = load_processed()
    source_state = load_knowledge_source_state()
    count = 0
    for row in queue:
        video_id = str(row.get("id") or "")
        if video_id in done or (source_state.get(video_id) or {}).get("status") == "excluded_no_transcript":
            continue
        if process_video({
            "id": video_id, "title": row.get("title"), "video_date": row.get("date"),
            "source_label": row.get("source_label"), "ingestion_source": row.get("ingestion_source"),
            "rights_status": row.get("rights_status"),
            "commercial_use_allowed": row.get("commercial_use_allowed", False),
        }):
            count += 1
        time.sleep(0.5)
    return count


def background_loop() -> None:  # pragma: no cover - operational worker
    log.info("Kennisworker R23 gestart")
    _KNOWLEDGE_WORKER_STATE.update(enabled=True, running=True, last_error=None)
    while True:
        try:
            discovered = check_new_videos()
            processed = run_backlog()
            _KNOWLEDGE_WORKER_STATE.update(
                running=True, last_success=utc_now(), last_error=None,
                backlog_processed=int(_KNOWLEDGE_WORKER_STATE.get("backlog_processed") or 0) + processed,
                rss_discovered=int(_KNOWLEDGE_WORKER_STATE.get("rss_discovered") or 0),
                last_cycle_discovered=discovered, last_cycle_processed=processed,
            )
        except Exception as exc:
            log.exception("Kennisworker-cyclus mislukt")
            _KNOWLEDGE_WORKER_STATE.update(running=True, last_error=str(exc)[:600])
        _KNOWLEDGE_WAKE.wait(max(60, CHECK_EVERY_SEC))
        _KNOWLEDGE_WAKE.clear()


def start_background_worker() -> Optional[threading.Thread]:
    # External content remains opt-in. RSS is automatic only inside the already
    # explicitly enabled private knowledge-ingestion worker.
    if DISABLE_BACKGROUND_WORKERS or not ENABLE_KNOWLEDGE_INGESTION:
        _KNOWLEDGE_WORKER_STATE.update(enabled=False, running=False)
        return None
    thread = threading.Thread(target=background_loop, daemon=True, name="mytradingbot-knowledge-worker")
    thread.start()
    return thread
