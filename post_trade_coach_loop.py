"""Outgoing-only post-trade coach loop for MyTradingBot R24b.

This module never reads markets, creates setups, changes gates, or places orders.
It only turns an already-saved closed-trade deepdive into one reflective Telegram
message and persists the linked knowledge lesson for the cockpit.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from knowledge_retrieval import rank_knowledge

log = logging.getLogger("mytradingbot-post-trade-coach-loop")

_LOCK = threading.RLock()
MAX_MESSAGE_LENGTH = 3900


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"\[(?:bron|source)?\s*\d+\]", "", text, flags=re.I)
    return text[:limit].strip()


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


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


def _knowledge_rows(structured_dir: Path, methodology_file: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    static = _load(methodology_file, {})
    for rule in static.get("rules", []) if isinstance(static, dict) else []:
        if not isinstance(rule, dict):
            continue
        rows.append({
            "id": _clean(rule.get("id"), 160),
            "title": _clean(rule.get("title") or "Procesles", 240),
            "summary": _clean(rule.get("statement"), 1400),
            "type": _clean(rule.get("category") or "methodiek", 60),
            "source_label": _clean(rule.get("source_label") or "METHODIEK", 60).upper(),
            "official_status": _clean(rule.get("official_status") or "official", 40),
            "confidence": int(rule.get("confidence") or 100),
            "tags": [str(value)[:80] for value in (rule.get("tags") or []) if str(value).strip()][:12],
            "provenance": "static-methodology",
        })
    if structured_dir.exists():
        for path in sorted(structured_dir.glob("*.json")):
            item = _load(path, {})
            if not isinstance(item, dict):
                continue
            for index, lesson in enumerate(item.get("knowledge") or []):
                if not isinstance(lesson, dict):
                    continue
                rows.append({
                    "id": _clean(lesson.get("id") or f"{path.stem}:{index}", 160),
                    "title": _clean(lesson.get("title") or "Kennisles", 240),
                    "summary": _clean(lesson.get("summary") or lesson.get("statement"), 1400),
                    "type": _clean(lesson.get("category") or item.get("video_type") or "kennis", 60),
                    "source_label": _clean(lesson.get("source_label") or "EXTERNE-BRON", 60).upper(),
                    "official_status": _clean(lesson.get("official_status") or "unconfirmed", 40),
                    "confidence": max(0, min(100, int(lesson.get("confidence") or 0))),
                    "evidence": _clean(lesson.get("evidence"), 700),
                    "tags": [str(value)[:80] for value in (lesson.get("tags") or []) if str(value).strip()][:12],
                    "timeframes": [str(value)[:20] for value in (lesson.get("timeframes") or []) if str(value).strip()][:8],
                    "provenance": "structured-video-lesson",
                })
    return rows


def select_lesson(
    row: Dict[str, Any],
    analysis: Dict[str, Any],
    *,
    structured_dir: Path,
    methodology_file: Path,
) -> Optional[Dict[str, Any]]:
    """Select exactly one existing lesson as a future observation lens."""
    query = " ".join(filter(None, [
        _clean(analysis.get("oordeel"), 500),
        _clean(analysis.get("wat_kan_beter"), 500),
        _clean(analysis.get("les"), 500),
        _clean(analysis.get("proces_grade"), 20),
        _clean(row.get("symbol"), 40),
        _clean(row.get("direction"), 20),
        "journal deepdive proces review discipline",
    ]))
    ranked = rank_knowledge(query, _knowledge_rows(structured_dir, methodology_file), limit=1)
    if not ranked:
        return None
    lesson = ranked[0]
    summary = _clean(lesson.get("summary"), 800)
    if not summary:
        return None
    return {
        "id": _clean(lesson.get("id"), 160),
        "title": _clean(lesson.get("title") or "Procesles", 180),
        "summary": summary,
        "type": _clean(lesson.get("type") or "kennis", 60),
        "confidence": max(0, min(100, int(lesson.get("confidence") or 0))),
        "role": "observation_lens_only",
    }


def format_message(payload: Dict[str, Any]) -> str:
    analysis = payload.get("analysis") or {}
    lesson = payload.get("lesson") or {}
    symbol = _clean(payload.get("symbol"), 32) or "Trade"
    direction = _clean(payload.get("direction"), 12).upper()
    pnl = payload.get("pnl")
    try:
        pnl_text = f"{float(pnl):+.2f} USDT"
    except (TypeError, ValueError):
        pnl_text = "resultaat geregistreerd"
    lines = [f"🔁 Gesloten leerlus · {direction} {symbol} · {pnl_text}"]
    grade = _clean(analysis.get("proces_grade"), 4).upper() or "?"
    judgement = _clean(analysis.get("oordeel") or analysis.get("uitkomst"), 700)
    good = _clean(analysis.get("wat_ging_goed"), 700)
    better = _clean(analysis.get("wat_kan_beter"), 700)
    process_lesson = _clean(analysis.get("les"), 700)
    lines.extend(["", f"Deepdive · proces {grade}"])
    if judgement:
        lines.append(judgement)
    if good:
        lines.append(f"Goed: {good}")
    if better:
        lines.append(f"Beter: {better}")
    if process_lesson:
        lines.append(f"Procesles: {process_lesson}")
    lines.extend(["", f"Kennislens · {_clean(lesson.get('title'), 180) or 'Procesles'}"])
    lines.append(_clean(lesson.get("summary"), 800))
    lines.extend(["", "Gebruik dit alleen als observatielens bij een volgende kaart. Het is geen handelssignaal en verandert geen cockpitregel."])
    return "\n".join(line for line in lines if line is not None).strip()[:MAX_MESSAGE_LENGTH]


class PostTradeCoachLoop:
    """Persistent outgoing queue fed only by newly saved close events."""

    def __init__(
        self,
        data_dir: Path,
        *,
        enabled: Optional[bool] = None,
        structured_dir: Optional[Path] = None,
        methodology_file: Optional[Path] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.enabled = _env_bool("MYTRADINGBOT_ENABLE_COACH_LOOP", False) if enabled is None else bool(enabled)
        self.structured_dir = Path(structured_dir or (self.data_dir / "structured"))
        self.methodology_file = Path(methodology_file or Path(__file__).with_name("methodology_sources.json"))
        self.state_path = self.data_dir / "post_trade_coach_loop_state.json"
        self._state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        value = _load(self.state_path, {})
        base = {"pending": {}, "sent": {}, "claims": {}, "last_sent": None, "last_error": None}
        if isinstance(value, dict):
            for key in base:
                if key in value:
                    base[key] = value[key]
        for key in ("pending", "sent", "claims"):
            if not isinstance(base.get(key), dict):
                base[key] = {}
        return base

    def _save(self) -> None:
        _atomic_dump(self.state_path, self._state)

    def status(self) -> Dict[str, Any]:
        with _LOCK:
            return {
                "enabled": self.enabled,
                "pending": len(self._state.get("pending") or {}),
                "sent": len(self._state.get("sent") or {}),
                "last_sent": self._state.get("last_sent"),
                "last_error": self._state.get("last_error"),
                "outgoing_only": True,
            }

    def enrich_analysis(self, row: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled or not isinstance(analysis, dict):
            return dict(analysis or {})
        lesson = select_lesson(
            row,
            analysis,
            structured_dir=self.structured_dir,
            methodology_file=self.methodology_file,
        )
        enriched = dict(analysis)
        if lesson:
            enriched["coach_loop_lesson"] = lesson
        return enriched

    def queue(self, row: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
        if not self.enabled or not isinstance(analysis, dict):
            return False
        trade_id = _clean(row.get("orderId") or row.get("execId") or row.get("updatedTime"), 160)
        lesson = analysis.get("coach_loop_lesson")
        if not trade_id or not isinstance(lesson, dict) or not _clean(lesson.get("summary"), 800):
            return False
        with _LOCK:
            if trade_id in self._state["sent"] or trade_id in self._state["pending"]:
                return False
            payload = {
                "trade_id": trade_id,
                "symbol": _clean(row.get("symbol"), 32),
                "direction": _clean(row.get("direction"), 12) or ("long" if str(row.get("side") or "").lower() == "sell" else "short"),
                "pnl": row.get("closedPnl"),
                "analysis": {
                    key: _clean(analysis.get(key), 1200)
                    for key in ("uitkomst", "proces_grade", "oordeel", "wat_ging_goed", "wat_kan_beter", "les")
                },
                "lesson": lesson,
                "queued_at": utc_now(),
            }
            self._state["pending"][trade_id] = payload
            self._state["last_error"] = None
            self._save()
            return True

    def flush(self, sender: Callable[[str], bool]) -> int:
        if not self.enabled:
            return 0
        sent_count = 0
        with _LOCK:
            trade_ids = list(self._state["pending"])
        for trade_id in trade_ids:
            with _LOCK:
                if trade_id in self._state["sent"] or trade_id in self._state["claims"]:
                    continue
                payload = self._state["pending"].get(trade_id)
                if not isinstance(payload, dict):
                    self._state["pending"].pop(trade_id, None)
                    self._save()
                    continue
                # Ponytail: claim before the network call. A process death may
                # miss one reflection, but can never duplicate one closed trade.
                self._state["claims"][trade_id] = utc_now()
                self._save()
            try:
                message = format_message(payload)
                if not message or not bool(sender(message)):
                    raise RuntimeError("Telegram verzending mislukt")
                with _LOCK:
                    self._state["sent"][trade_id] = utc_now()
                    self._state["pending"].pop(trade_id, None)
                    self._state["claims"].pop(trade_id, None)
                    self._state["last_sent"] = self._state["sent"][trade_id]
                    self._state["last_error"] = None
                    self._state["sent"] = dict(list(self._state["sent"].items())[-5000:])
                    self._save()
                sent_count += 1
            except Exception as exc:  # operational retry on the next existing watcher cycle
                with _LOCK:
                    self._state["claims"].pop(trade_id, None)
                    self._state["last_error"] = str(exc)[:500]
                    self._save()
                log.warning("Gesloten coachlus niet verzonden voor %s: %s", trade_id, exc)
        return sent_count


_LOOP: Optional[PostTradeCoachLoop] = None


def configure_post_trade_coach_loop(
    data_dir: Path,
    *,
    structured_dir: Optional[Path] = None,
    methodology_file: Optional[Path] = None,
) -> PostTradeCoachLoop:
    global _LOOP
    _LOOP = PostTradeCoachLoop(
        data_dir,
        structured_dir=structured_dir,
        methodology_file=methodology_file,
    )
    return _LOOP


def enrich_post_trade_analysis(row: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    return _LOOP.enrich_analysis(row, analysis) if _LOOP is not None else dict(analysis or {})


def queue_post_trade_coach_loop(row: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    return bool(_LOOP and _LOOP.queue(row, analysis))


def flush_post_trade_coach_loop(sender: Callable[[str], bool]) -> int:
    return _LOOP.flush(sender) if _LOOP is not None else 0


def post_trade_coach_loop_status() -> Dict[str, Any]:
    if _LOOP is None:
        return {"enabled": False, "pending": 0, "sent": 0, "last_sent": None, "last_error": None, "outgoing_only": True}
    return _LOOP.status()
