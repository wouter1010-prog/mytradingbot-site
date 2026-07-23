"""Env-gated outgoing Telegram scheduler for the read-only day-start briefing.

This module never reads Telegram updates, accepts commands, or mutates trading state.
It receives a read-only payload builder and an outgoing sender callback from main.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger("mytradingbot-telegram-day-start")

DEFAULT_TIMEZONE = "Europe/Amsterdam"
DEFAULT_SEND_TIME = "08:00"
MAX_MESSAGE_LENGTH = 3900


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def parse_send_time(value: str) -> clock_time:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        raise ValueError("MYTRADINGBOT_TELEGRAM_DAY_START_TIME must use HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("MYTRADINGBOT_TELEGRAM_DAY_START_TIME is outside 00:00-23:59")
    return clock_time(hour=hour, minute=minute)


def resolve_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(value or DEFAULT_TIMEZONE))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {value}") from exc


def _clean(value: Any, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"\b(?:zie|see)\s+(?:dossier|module|source|bron)\s*\d+\b", "", text, flags=re.I)
    return text[:limit].strip()


def _section_map(briefing: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(row.get("key") or ""): row
        for row in (briefing.get("sections") or [])
        if isinstance(row, dict) and row.get("key")
    }


def compact_day_start_message(payload: Dict[str, Any], language: str = "nl") -> str:
    """Render the existing day-start payload into a compact outgoing-only message."""
    language = "en" if str(language).lower().startswith("en") else "nl"
    briefing = ((payload.get("briefings") or {}).get(language) or {})
    if payload.get("blocked") or briefing.get("blocked"):
        return (
            "Your market map is stale — refresh your charts first."
            if language == "en"
            else "Je kaart is verouderd — lees eerst je charts."
        )

    sections = _section_map(briefing)
    lines = ["🌅 MyTradingBot · " + ("Morning briefing" if language == "en" else "Ochtendbriefing")]

    management = sections.get("position_management")
    if management:
        lines.extend(["", "📌 " + _clean(management.get("title")), _clean(management.get("body"))])

    where = sections.get("where_we_are") or {}
    lines.extend(["", "1. " + _clean(where.get("title") or ("Where we are" if language == "en" else "Waar staan we"))])
    lines.extend("• " + _clean(value) for value in (where.get("lines") or [])[:2] if _clean(value))

    scenarios = sections.get("scenarios") or {}
    lines.extend(["", "2. " + _clean(scenarios.get("title") or ("Scenarios" if language == "en" else "Scenario's"))])
    for item in (scenarios.get("items") or [])[:3]:
        if not isinstance(item, dict):
            continue
        combined = " · ".join(filter(None, [_clean(item.get("if")), _clean(item.get("then")), _clean(item.get("invalidated"))]))
        if combined:
            lines.append("• " + combined)

    no_trade = sections.get("no_trade") or {}
    lines.extend(["", "3. " + _clean(no_trade.get("title") or ("No-trade scenario" if language == "en" else "Geen-trade-scenario")), _clean(no_trade.get("body"))])

    focus = sections.get("process_focus") or {}
    lines.extend(["", "4. " + _clean(focus.get("title") or ("Process focus" if language == "en" else "Procesfocus")), _clean(focus.get("body"))])

    checklist = sections.get("checklist") or {}
    lines.extend(["", "5. " + _clean(checklist.get("title") or ("Three questions" if language == "en" else "Drie toetsvragen"))])
    lines.extend("☐ " + _clean(value) for value in (checklist.get("items") or [])[:3] if _clean(value))

    lines.extend(["", "Scenario ≠ trade. " + ("The final decision remains yours." if language == "en" else "De eindbeslissing blijft van jou.")])
    message = "\n".join(line for line in lines if line is not None).strip()
    return message[:MAX_MESSAGE_LENGTH]


class TelegramDayStartScheduler:
    """Single-process scheduler with persistent once-per-local-day delivery."""

    def __init__(
        self,
        payload_builder: Callable[[], Dict[str, Any]],
        sender: Callable[[str], bool],
        data_dir: Path,
        *,
        enabled: Optional[bool] = None,
        send_time: Optional[str] = None,
        timezone_name: Optional[str] = None,
        language: Optional[str] = None,
        poll_seconds: Optional[int] = None,
        grace_minutes: Optional[int] = None,
        telegram_configured: bool = True,
    ) -> None:
        self.payload_builder = payload_builder
        self.sender = sender
        self.enabled = _env_bool("MYTRADINGBOT_ENABLE_TELEGRAM_DAY_START", False) if enabled is None else bool(enabled)
        self.send_time_text = str(send_time or os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_TIME", DEFAULT_SEND_TIME))
        self.send_time = parse_send_time(self.send_time_text)
        self.timezone_name = str(timezone_name or os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_TIMEZONE", DEFAULT_TIMEZONE))
        self.timezone = resolve_timezone(self.timezone_name)
        selected_language = str(language or os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_LANGUAGE", "nl")).lower()
        self.language = "en" if selected_language.startswith("en") else "nl"
        self.poll_seconds = _safe_int(poll_seconds if poll_seconds is not None else os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_POLL_SEC", 30), 30, 10, 3600)
        self.grace_minutes = _safe_int(grace_minutes if grace_minutes is not None else os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_GRACE_MINUTES", 120), 120, 1, 720)
        self.telegram_configured = bool(telegram_configured)
        self.state_path = Path(data_dir) / "telegram_day_start_state.json"
        self.stop_event = threading.Event()
        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "configured": self.telegram_configured,
            "time": self.send_time_text,
            "timezone": self.timezone_name,
            "language": self.language,
            "last_attempt": None,
            "last_sent": None,
            "last_sent_local_date": None,
            "delivery_claim_local_date": None,
            "last_result": None,
            "last_error": None,
        }
        self._load_state()

    def _load_state(self) -> None:
        try:
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            saved = {}
        if isinstance(saved, dict):
            for key in ("last_attempt", "last_sent", "last_sent_local_date", "delivery_claim_local_date", "last_result", "last_error"):
                if key in saved:
                    self.state[key] = saved[key]

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=self.state_path.name + ".", suffix=".tmp", dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.state_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def status(self) -> Dict[str, Any]:
        return dict(self.state)

    def _due(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        local_date = local.date().isoformat()
        if self.state.get("last_sent_local_date") == local_date or self.state.get("delivery_claim_local_date") == local_date:
            return False
        target = local.replace(hour=self.send_time.hour, minute=self.send_time.minute, second=0, microsecond=0)
        elapsed_minutes = (local - target).total_seconds() / 60
        return 0 <= elapsed_minutes <= self.grace_minutes

    def run_due(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        self.state.update(enabled=self.enabled, configured=self.telegram_configured)
        if not self.enabled:
            self.state.update(last_result="disabled", last_error=None)
            return False
        if not self.telegram_configured:
            self.state.update(last_result="not_configured", last_error="Telegram token/chat-id ontbreekt")
            return False
        if not self._due(now):
            return False

        local_date = now.astimezone(self.timezone).date().isoformat()
        self.state["last_attempt"] = now.astimezone(timezone.utc).isoformat()
        # Ponytail: claim the local date before the network call. If the process
        # dies mid-send, we prefer one missed briefing over a duplicate message.
        self.state["delivery_claim_local_date"] = local_date
        self._save_state()
        try:
            payload = self.payload_builder()
            message = compact_day_start_message(payload, self.language)
            if not message:
                raise RuntimeError("lege ochtendbriefing")
            sent = bool(self.sender(message))
            if not sent:
                raise RuntimeError("Telegram verzending mislukt")
            self.state.update(
                last_sent=now.astimezone(timezone.utc).isoformat(),
                last_sent_local_date=local_date,
                delivery_claim_local_date=None,
                last_result="stale_notice" if payload.get("blocked") else "briefing_sent",
                last_error=None,
            )
            self._save_state()
            return True
        except Exception as exc:  # pragma: no cover - operational resilience
            self.state.update(delivery_claim_local_date=None, last_result="error", last_error=str(exc)[:500])
            self._save_state()
            log.exception("Telegram-ochtendbriefing mislukt")
            return False

    def loop(self) -> None:  # pragma: no cover - operational worker
        self.state.update(running=True, last_error=None)
        log.info("Telegram-ochtendbriefing gestart voor %s %s", self.timezone_name, self.send_time_text)
        try:
            while not self.stop_event.is_set():
                self.run_due()
                self.stop_event.wait(self.poll_seconds)
        finally:
            self.state["running"] = False

    def start(self) -> Optional[threading.Thread]:
        if not self.enabled or not self.telegram_configured or _env_bool("DISABLE_BACKGROUND_WORKERS", False):
            self.state.update(running=False)
            return None
        thread = threading.Thread(target=self.loop, daemon=True, name="mytradingbot-telegram-day-start")
        thread.start()
        return thread


_SCHEDULER: Optional[TelegramDayStartScheduler] = None


def start_telegram_day_start_scheduler(
    payload_builder: Callable[[], Dict[str, Any]],
    sender: Callable[[str], bool],
    data_dir: Path,
    *,
    telegram_configured: bool,
) -> Optional[threading.Thread]:
    global _SCHEDULER
    _SCHEDULER = TelegramDayStartScheduler(
        payload_builder,
        sender,
        data_dir,
        telegram_configured=telegram_configured,
    )
    return _SCHEDULER.start()


def telegram_day_start_status() -> Dict[str, Any]:
    if _SCHEDULER is None:
        return {
            "enabled": False,
            "running": False,
            "configured": False,
            "time": os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_TIME", DEFAULT_SEND_TIME),
            "timezone": os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_TIMEZONE", DEFAULT_TIMEZONE),
            "language": os.environ.get("MYTRADINGBOT_TELEGRAM_DAY_START_LANGUAGE", "nl"),
        }
    return _SCHEDULER.status()
