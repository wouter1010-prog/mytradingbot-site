"""Outgoing-only weekly mentor report for MyTradingBot R24c.

The module reads already persisted journal/process data, selects one existing
knowledge lesson as an observation lens, and sends at most one report per local
ISO calendar week. It never reads markets, changes gates, creates setups, or
places orders.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections import Counter
from datetime import datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from knowledge_retrieval import rank_knowledge
from coach_dossiers import sanitise_coach_answer

log = logging.getLogger("mytradingbot-weekly-mentor")

DEFAULT_DAY = "sunday"
DEFAULT_SEND_TIME = "18:00"
DEFAULT_TIMEZONE = "Europe/Amsterdam"
MAX_MESSAGE_LENGTH = 3900
_LOCK = threading.RLock()

_WEEKDAYS = {
    "monday": 0, "mon": 0, "maandag": 0, "ma": 0,
    "tuesday": 1, "tue": 1, "dinsdag": 1, "di": 1,
    "wednesday": 2, "wed": 2, "woensdag": 2, "wo": 2,
    "thursday": 3, "thu": 3, "donderdag": 3, "do": 3,
    "friday": 4, "fri": 4, "vrijdag": 4, "vr": 4,
    "saturday": 5, "sat": 5, "zaterdag": 5, "za": 5,
    "sunday": 6, "sun": 6, "zondag": 6, "zo": 6,
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _clean(value: Any, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"\[(?:bron|source)?\s*\d+\]", "", text, flags=re.I)
    text = re.sub(r"\b(?:zie|see)\s+(?:dossier|module|seminar|video|transcript)\s*[\w.-]*", "", text, flags=re.I)
    return text[:limit].strip(" -")


def _atomic_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def parse_send_time(value: str) -> clock_time:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        raise ValueError("wekelijkse mentortijd moet HH:MM zijn")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("ongeldige wekelijkse mentortijd")
    return clock_time(hour=hour, minute=minute)


def parse_weekday(value: Any) -> int:
    text = str(value if value is not None else DEFAULT_DAY).strip().lower()
    if text.isdigit() and 0 <= int(text) <= 6:
        return int(text)
    if text not in _WEEKDAYS:
        raise ValueError("wekelijkse mentordag moet maandag-zondag of 0-6 zijn")
    return _WEEKDAYS[text]


def _timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    raw = row.get("closed_at") or row.get("time") or row.get("at") or row.get("updated_at")
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _recent_rows(rows: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    cutoff = now.astimezone(timezone.utc) - timedelta(days=7)
    recent: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        stamp = _timestamp(raw)
        if stamp is not None and stamp >= cutoff:
            recent.append(dict(raw))
    recent.sort(key=lambda row: _timestamp(row) or datetime.min.replace(tzinfo=timezone.utc))
    return recent


def _matching_deepdives(rows: Iterable[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    return _recent_rows(rows, now)


def _grade(row: Dict[str, Any]) -> str:
    return _clean(row.get("process_grade") or row.get("proces_grade"), 4).upper()


def _pnl(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("pnl") if row.get("pnl") is not None else row.get("closedPnl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _loss_streak(rows: List[Dict[str, Any]]) -> int:
    best = current = 0
    for row in rows:
        if _pnl(row) < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _issue_key(text: str) -> Optional[str]:
    normal = _clean(text, 1500).lower()
    families = {
        "midrange": ("midrange", "midden van de range", "middengebied"),
        "confirmation": ("bevestiging", "confirmatie", "hertest", "close afwachten", "te vroeg"),
        "discipline": ("revenge", "fomo", "ongeduld", "forceren", "discipline"),
        "risk": ("risico", "risk", "positie te groot", "hefboom", "leverage"),
        "journal": ("dagboek", "journal", "niet beoordeeld", "procesgrade"),
    }
    for key, needles in families.items():
        if any(needle in normal for needle in needles):
            return key
    return None


def _strengths(rows: List[Dict[str, Any]], dives: List[Dict[str, Any]], language: str) -> List[str]:
    english = language.startswith("en")
    total = len(rows)
    graded = sum(_grade(row) in {"A", "B", "C"} for row in rows)
    strong_grades = sum(_grade(row) in {"A", "B"} for row in rows)
    rules_true = sum(row.get("rules_followed") is True for row in rows)
    candidates: List[str] = []
    if total:
        candidates.append(
            f"You logged {total} closed trade{'s' if total != 1 else ''}; that gives you honest material to learn from."
            if english else
            f"Je legde {total} gesloten trade{'s' if total != 1 else ''} vast; dat geeft eerlijk materiaal om van te leren."
        )
    if graded:
        candidates.append(
            f"{strong_grades} of {graded} reviewed trades received an A or B process grade."
            if english else
            f"{strong_grades} van {graded} beoordeelde trades kregen procesgrade A of B."
        )
    if rules_true:
        candidates.append(
            f"For {rules_true} trade{'s' if rules_true != 1 else ''}, the journal explicitly records that the rules were followed."
            if english else
            f"Bij {rules_true} trade{'s' if rules_true != 1 else ''} staat expliciet vast dat de regels zijn gevolgd."
        )
    good = next((_clean(row.get("wat_ging_goed"), 300) for row in reversed(dives) if _clean(row.get("wat_ging_goed"), 300)), "")
    if good:
        candidates.append(("A recent deep dive confirms: " if english else "Een recente deepdive bevestigt: ") + good)
    fallbacks = ([
        "There are not enough closed trades yet to support another strength honestly.",
        "There are not enough process grades yet to support another strength honestly.",
        "Keep recording before drawing a stronger conclusion about your behaviour.",
    ] if english else [
        "Er zijn nog te weinig gesloten trades om eerlijk nog een sterk punt te onderbouwen.",
        "Er zijn nog te weinig procesgrades om eerlijk nog een sterk punt te onderbouwen.",
        "Blijf vastleggen vóór je een sterkere conclusie over je gedrag trekt.",
    ])
    for fallback in fallbacks:
        if len(candidates) >= 3:
            break
        candidates.append(fallback)
    return candidates[:3]


def _pattern(rows: List[Dict[str, Any]], dives: List[Dict[str, Any]], language: str) -> str:
    english = language.startswith("en")
    issues = Counter(filter(None, (_issue_key(" ".join(filter(None, [
        _clean(row.get("wat_kan_beter"), 500), _clean(row.get("les"), 500), _clean(row.get("notes"), 500)
    ]))) for row in [*rows, *dives])))
    labels = {
        "midrange": ("mid-range trades keep returning", "midrange-trades keren terug"),
        "confirmation": ("entries are repeatedly taken before confirmation is complete", "instappen gebeuren herhaaldelijk vóór de bevestiging af is"),
        "discipline": ("impatience or forcing returns in the process notes", "ongeduld of forceren keert terug in de procesnotities"),
        "risk": ("risk execution needs repeated attention", "de uitvoering van het risicoplan vraagt herhaaldelijk aandacht"),
        "journal": ("process reviews are still missing or incomplete", "procesbeoordelingen ontbreken nog of zijn onvolledig"),
    }
    if issues:
        key, count = issues.most_common(1)[0]
        phrase = labels[key][0 if english else 1]
        return (f"The clearest pattern across {count} note{'s' if count != 1 else ''}: {phrase}."
                if english else f"Het duidelijkste patroon in {count} notitie{'s' if count != 1 else ''}: {phrase}.")
    streak = _loss_streak(rows)
    if streak >= 2:
        return (f"The journal shows a losing streak of {streak}. Treat that as a process signal to slow down, not as a reason to win it back."
                if english else f"Het dagboek toont een verliesreeks van {streak}. Zie dat als processignaal om te vertragen, niet als reden om iets terug te winnen.")
    c_count = sum(_grade(row) == "C" for row in rows)
    if c_count:
        return (f"{c_count} trade{'s' if c_count != 1 else ''} received a C process grade. That is the clearest area to review."
                if english else f"{c_count} trade{'s' if c_count != 1 else ''} kregen procesgrade C. Dat is het duidelijkste aandachtspunt.")
    return ("No hard repeating pattern is visible yet; the sample is too small to make a confident claim."
            if english else "Er is nog geen hard terugkerend patroon zichtbaar; de steekproef is te klein voor een stellige conclusie.")


def _safe_lesson(pattern: str, dives: List[Dict[str, Any]], knowledge_rows: Iterable[Dict[str, Any]], language: str) -> Dict[str, Any]:
    english = language.startswith("en")
    query = " ".join([pattern, *[_clean(row.get("wat_kan_beter") or row.get("les"), 400) for row in dives[-6:]], "journal process discipline reflection psychology"])
    ranked = rank_knowledge(query, knowledge_rows, limit=8)
    process_terms = {"mindset", "discipline", "psychologie", "journal", "journaal", "dagboek", "proces", "review", "evaluatie", "no-trade", "notrade"}
    blocked = re.compile(r"\b(?:buy|sell|koop|verkoop|entry|instap|target|take[ -]?profit|order|ticket|stop[- ]?loss|sl\b)\b", re.I)
    price_like = re.compile(r"\b\d{3,}(?:[.,]\d+)?\b")
    for row in ranked:
        haystack = " ".join([str(row.get("type") or ""), " ".join(row.get("tags") or []), str(row.get("title") or "")]).lower()
        summary = _clean(row.get("summary"), 700)
        if not summary or not (process_terms & set(re.findall(r"[a-zà-ÿ-]+", haystack))):
            continue
        if blocked.search(summary) or price_like.search(summary):
            continue
        source_title = _clean(row.get("source_title"), 180)
        candidate_title = _clean(row.get("title"), 180)
        source_like = bool(re.search(r"\b(?:youtube|youtu|doopie|vincent|platinum|livestream|episode|transcript)\b", candidate_title, re.I))
        if not candidate_title or source_like or (source_title and candidate_title.casefold() == source_title.casefold()):
            candidate_title = "Process lesson" if english else "Procesles"
        return {
            "lesson_id": _clean(row.get("id"), 160),
            "title": sanitise_coach_answer(candidate_title)[:180],
            "summary": sanitise_coach_answer(summary)[:700],
            "role": "observation_lens_only",
        }
    return {
        "lesson_id": "weekly-process-focus",
        "title": "One process focus" if english else "Eén procesfocus",
        "summary": (
            "Choose one process behaviour for the coming week and review it after every closed trade. Improve the repetition, not the prediction."
            if english else
            "Kies voor de komende week één procesgedrag en beoordeel dat na iedere gesloten trade. Verbeter de herhaling, niet de voorspelling."
        ),
        "role": "observation_lens_only",
    }


def build_weekly_mentor_report(
    journal_rows: Iterable[Dict[str, Any]],
    deepdives: Iterable[Dict[str, Any]],
    knowledge_rows: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    language: str = "nl",
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    language = "en" if str(language).lower().startswith("en") else "nl"
    rows = _recent_rows(journal_rows, now)
    dives = _matching_deepdives(deepdives, now)
    pattern = _pattern(rows, dives, language)
    lesson = _safe_lesson(pattern, dives, list(knowledge_rows), language)
    start = (now.astimezone(timezone.utc) - timedelta(days=7)).date().isoformat()
    end = now.astimezone(timezone.utc).date().isoformat()
    return {
        "language": language,
        "title": "Weekly mentor report" if language == "en" else "Wekelijks mentor-rapport",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "period_start": start,
        "period_end": end,
        "trade_count": len(rows),
        "strengths": _strengths(rows, dives, language),
        "pattern": pattern,
        "lesson": lesson,
        "safety": (
            "Reflection only. This report is never a setup, entry, stop, target or order."
            if language == "en" else
            "Alleen reflectie. Dit rapport is nooit een setup, instap, stop, doel of order."
        ),
    }


def build_bilingual_weekly_mentor_report(
    journal_rows: Iterable[Dict[str, Any]],
    deepdives: Iterable[Dict[str, Any]],
    knowledge_rows: Iterable[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    journal_rows, deepdives, knowledge_rows = list(journal_rows), list(deepdives), list(knowledge_rows)
    now = now or datetime.now(timezone.utc)
    return {
        "reports": {
            "nl": build_weekly_mentor_report(journal_rows, deepdives, knowledge_rows, now=now, language="nl"),
            "en": build_weekly_mentor_report(journal_rows, deepdives, knowledge_rows, now=now, language="en"),
        },
        "generated_at": now.astimezone(timezone.utc).isoformat(),
    }


def format_weekly_mentor_message(payload: Dict[str, Any], language: str = "nl") -> str:
    language = "en" if str(language).lower().startswith("en") else "nl"
    report = ((payload.get("reports") or {}).get(language) or payload)
    strengths = list(report.get("strengths") or [])[:3]
    while len(strengths) < 3:
        strengths.append("Not enough data yet." if language == "en" else "Nog onvoldoende data.")
    lines = ["🧭 " + _clean(report.get("title"), 120), ""]
    lines.append("3 strengths" if language == "en" else "3 sterke punten")
    lines.extend(f"• {_clean(item, 700)}" for item in strengths)
    lines.extend(["", "1 journal pattern" if language == "en" else "1 patroon uit je dagboek", _clean(report.get("pattern"), 900)])
    lesson = report.get("lesson") or {}
    lines.extend(["", "1 lesson" if language == "en" else "1 les", _clean(lesson.get("title"), 180), _clean(lesson.get("summary"), 900)])
    lines.extend(["", _clean(report.get("safety"), 300)])
    return "\n".join(line for line in lines if line is not None).strip()[:MAX_MESSAGE_LENGTH]


class WeeklyMentorScheduler:
    """Persistent one-report-per-local-ISO-week outgoing scheduler."""

    def __init__(
        self,
        report_builder: Callable[[], Dict[str, Any]],
        sender: Callable[[str], bool],
        data_dir: Path,
        *,
        enabled: Optional[bool] = None,
        weekday: Any = None,
        send_time: Optional[str] = None,
        timezone_name: Optional[str] = None,
        language: Optional[str] = None,
        poll_seconds: Optional[int] = None,
        grace_minutes: Optional[int] = None,
        telegram_configured: bool = False,
    ) -> None:
        self.report_builder = report_builder
        self.sender = sender
        self.data_dir = Path(data_dir)
        self.enabled = _env_bool("MYTRADINGBOT_ENABLE_WEEKLY_MENTOR", False) if enabled is None else bool(enabled)
        self.weekday = parse_weekday(weekday if weekday is not None else os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_DAY", DEFAULT_DAY))
        self.send_time_text = send_time or os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_TIME", DEFAULT_SEND_TIME)
        self.send_time = parse_send_time(self.send_time_text)
        self.timezone_name = timezone_name or os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_TIMEZONE", DEFAULT_TIMEZONE)
        self.timezone = ZoneInfo(self.timezone_name)
        self.language = "en" if str(language or os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_LANGUAGE", "nl")).lower().startswith("en") else "nl"
        self.poll_seconds = max(15, int(poll_seconds or os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_POLL_SEC", "60")))
        self.grace_minutes = max(1, int(grace_minutes or os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_GRACE_MINUTES", "180")))
        self.telegram_configured = bool(telegram_configured)
        self.stop_event = threading.Event()
        self.state_path = self.data_dir / "weekly_mentor_state.json"
        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "configured": self.telegram_configured,
            "weekday": self.weekday,
            "time": self.send_time_text,
            "timezone": self.timezone_name,
            "language": self.language,
            "last_attempt": None,
            "last_sent": None,
            "last_sent_week": None,
            "delivery_claim_week": None,
            "last_result": None,
            "last_error": None,
            "latest_report": None,
            "outgoing_only": True,
        }
        self._load_state()

    def _load_state(self) -> None:
        saved = _load(self.state_path, {})
        if isinstance(saved, dict):
            for key in ("last_attempt", "last_sent", "last_sent_week", "delivery_claim_week", "last_result", "last_error", "latest_report"):
                if key in saved:
                    self.state[key] = saved[key]

    def _save_state(self) -> None:
        _atomic_dump(self.state_path, self.state)

    @staticmethod
    def _week_key(local: datetime) -> str:
        iso = local.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def status(self) -> Dict[str, Any]:
        with _LOCK:
            return dict(self.state)

    def _due(self, now: datetime) -> bool:
        local = now.astimezone(self.timezone)
        if local.weekday() != self.weekday:
            return False
        week = self._week_key(local)
        if self.state.get("last_sent_week") == week or self.state.get("delivery_claim_week") == week:
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

        local = now.astimezone(self.timezone)
        week = self._week_key(local)
        self.state["last_attempt"] = now.astimezone(timezone.utc).isoformat()
        # Ponytail: claim the local ISO week before the network call. A crash may
        # miss one report, but it can never duplicate a weekly mentor message.
        self.state["delivery_claim_week"] = week
        self._save_state()
        try:
            payload = self.report_builder()
            message = format_weekly_mentor_message(payload, self.language)
            if not message:
                raise RuntimeError("leeg weekrapport")
            if not bool(self.sender(message)):
                raise RuntimeError("Telegram verzending mislukt")
            self.state.update(
                last_sent=now.astimezone(timezone.utc).isoformat(),
                last_sent_week=week,
                delivery_claim_week=None,
                last_result="report_sent",
                last_error=None,
                latest_report=payload,
            )
            self._save_state()
            return True
        except Exception as exc:  # pragma: no cover - operational resilience
            self.state.update(delivery_claim_week=None, last_result="error", last_error=str(exc)[:500])
            self._save_state()
            log.exception("Wekelijks mentor-rapport mislukt")
            return False

    def loop(self) -> None:  # pragma: no cover - operational worker
        self.state.update(running=True, last_error=None)
        log.info("Wekelijks mentor-rapport gestart voor weekday=%s %s %s", self.weekday, self.timezone_name, self.send_time_text)
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
        thread = threading.Thread(target=self.loop, daemon=True, name="mytradingbot-weekly-mentor")
        thread.start()
        return thread


_SCHEDULER: Optional[WeeklyMentorScheduler] = None


def start_weekly_mentor_scheduler(
    report_builder: Callable[[], Dict[str, Any]],
    sender: Callable[[str], bool],
    data_dir: Path,
    *,
    telegram_configured: bool,
) -> Optional[threading.Thread]:
    global _SCHEDULER
    _SCHEDULER = WeeklyMentorScheduler(report_builder, sender, data_dir, telegram_configured=telegram_configured)
    return _SCHEDULER.start()


def weekly_mentor_status() -> Dict[str, Any]:
    if _SCHEDULER is None:
        return {
            "enabled": False,
            "running": False,
            "configured": False,
            "weekday": parse_weekday(os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_DAY", DEFAULT_DAY)),
            "time": os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_TIME", DEFAULT_SEND_TIME),
            "timezone": os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_TIMEZONE", DEFAULT_TIMEZONE),
            "language": os.environ.get("MYTRADINGBOT_WEEKLY_MENTOR_LANGUAGE", "nl"),
            "latest_report": None,
            "outgoing_only": True,
        }
    return _SCHEDULER.status()
