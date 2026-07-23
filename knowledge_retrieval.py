"""Dependency-free retrieval for the MyTradingBot coach knowledge bank.

The module ranks short, structured lessons. It never reads or returns full
transcripts and it never turns educational content into an orderable setup.
Operator policy and product-safety rules always outrank external video lessons.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

AUTHORITATIVE_LABELS = {"OPERATORBELEID", "PRODUCTVEILIGHEID"}
EXTERNAL_LABELS = {"DOOPIECASH-VIDEO", "PUBLIC-YOUTUBE", "PLATINUM-MANUAL", "EXTERNE-BRON", "LEGACY-IMPORT"}

_STOPWORDS = {
    # Dutch
    "aan", "als", "bij", "dan", "dat", "de", "deze", "die", "dit", "door", "een",
    "en", "er", "geen", "heb", "het", "hoe", "ik", "in", "is", "je", "kan", "maar",
    "met", "mijn", "naar", "niet", "of", "om", "op", "te", "uit", "van", "voor", "wat",
    "waar", "wanneer", "waarom", "wel", "wordt", "zijn", "zo",
    # English
    "a", "about", "and", "are", "as", "at", "be", "by", "can", "do", "for", "from",
    "how", "i", "in", "is", "it", "my", "not", "of", "on", "or", "should", "that",
    "the", "this", "to", "what", "when", "where", "why", "with", "you", "your",
}

_QUERY_EXPANSIONS = {
    "risk": {"risico", "risk", "sizing", "positie", "position", "leverage", "hefboom"},
    "management": {"tp", "target", "doel", "stop", "break-even", "beheer", "management"},
    "entry": {"entry", "instap", "trigger", "kanteling", "reversal", "breakout", "sweep"},
    "zone": {"zone", "support", "steun", "resistance", "weerstand", "level", "niveau"},
    "context": {"1d", "4h", "context", "trend", "range", "structuur", "structure"},
    "setup": {"15m", "setup", "opbouw", "benadering", "approach"},
    "execution": {"3m", "uitvoering", "execution", "ticket", "confirmatie", "confirmation"},
    "mindset": {"mindset", "discipline", "geduld", "wachten", "emotie", "psychologie"},
    "journal": {"journal", "journaal", "dagboek", "deepdive", "review", "evaluatie"},
}

_POLICY_TERMS = {
    "risico", "risk", "leverage", "hefboom", "stop", "rr", "r:r", "target", "doel",
    "order", "ticket", "buy", "sell", "confirm", "bevestig", "positie", "position",
}


def _text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9:%+._-]+", " ", text).strip()


def _tokens(value: Any) -> List[str]:
    return [token for token in _normalise(value).split() if len(token) > 1 and token not in _STOPWORDS]


def _expanded_query(question: str) -> Counter[str]:
    tokens = Counter(_tokens(question))
    token_set = set(tokens)
    for family in _QUERY_EXPANSIONS.values():
        if token_set & family:
            for token in family:
                tokens[token] += 1
    return tokens


def _source_priority(row: Dict[str, Any]) -> int:
    label = _text(row.get("source_label"), 60).upper()
    status = _text(row.get("official_status"), 40).lower()
    provenance = _text(row.get("provenance"), 80).lower()
    if label in AUTHORITATIVE_LABELS:
        return 100
    if provenance == "static-methodology":
        return 90
    if status == "official":
        return 35
    if status == "interpretation":
        return 15
    if status in {"unconfirmed", "unknown", ""}:
        return 0
    return 5


def _lesson_haystack(row: Dict[str, Any]) -> Dict[str, List[str]]:
    return {
        "title": _tokens(row.get("title")),
        "summary": _tokens(row.get("summary") or row.get("statement")),
        "type": _tokens(row.get("type") or row.get("category")),
        "evidence": _tokens(row.get("evidence")),
        "tags": _tokens(" ".join(row.get("tags") or []) if isinstance(row.get("tags"), list) else row.get("tags")),
        "timeframes": _tokens(" ".join(row.get("timeframes") or []) if isinstance(row.get("timeframes"), list) else row.get("timeframes")),
    }


def rank_knowledge(
    question: str,
    rows: Iterable[Dict[str, Any]],
    latest: Optional[Dict[str, Any]] = None,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Return the most relevant short lessons with explicit provenance.

    The returned dictionaries are safe for prompt context and UI display. Full
    transcripts are never included. At most two lessons per source are returned
    so a single long video cannot dominate the answer.
    """
    query = _expanded_query(question)
    if latest:
        gate = ((latest.get("execution_gate") or {}).get("status") or "")
        setup = latest.get("setup") or {}
        context_hint = " ".join(
            str(value or "")
            for value in (gate, setup.get("direction"), setup.get("profile"), setup.get("parent_timeframe"))
        )
        for token in _tokens(context_hint):
            query[token] += 1
    query_terms = set(query)
    policy_sensitive = bool(query_terms & _POLICY_TERMS)
    ranked: List[Dict[str, Any]] = []

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"), 240)
        summary = _text(raw.get("summary") or raw.get("statement"), 1400)
        if not title and not summary:
            continue
        fields = _lesson_haystack(raw)
        score = 0.0
        reasons: List[str] = []
        weights = {"title": 7.0, "type": 5.0, "tags": 4.0, "timeframes": 4.0, "summary": 2.5, "evidence": 1.0}
        for field, tokens in fields.items():
            counts = Counter(tokens)
            overlap = sum(min(counts[token], query[token]) for token in query_terms)
            if overlap:
                score += overlap * weights[field]
                reasons.append(f"{field}:{overlap}")

        normal_question = _normalise(question)
        for phrase in (title, raw.get("type"), raw.get("category")):
            normal_phrase = _normalise(phrase)
            if normal_phrase and len(normal_phrase) >= 4 and normal_phrase in normal_question:
                score += 8.0
                reasons.append("exacte-term")

        priority = _source_priority(raw)
        if priority >= 90:
            score += 5.0
            if policy_sensitive:
                score += 30.0
                reasons.append("beleid-eerst")
        elif policy_sensitive and _text(raw.get("source_label"), 60).upper() in EXTERNAL_LABELS:
            score -= 2.0

        confidence = max(0, min(100, int(raw.get("confidence") or 0)))
        score += confidence / 50.0
        if score <= 0 and query_terms:
            continue
        ranked.append({
            "id": _text(raw.get("id"), 160),
            "title": title or "Les",
            "summary": summary,
            "type": _text(raw.get("type") or raw.get("category") or "kennis", 60),
            "source_label": _text(raw.get("source_label") or "ONBEVESTIGD", 60).upper(),
            "source_title": _text(raw.get("source_title") or title, 260),
            "source_url": _text(raw.get("source_url"), 700),
            "source_date": _text(raw.get("date") or raw.get("source_date"), 30),
            "official_status": _text(raw.get("official_status") or "unconfirmed", 40),
            "confidence": confidence,
            "evidence": _text(raw.get("evidence"), 700),
            "tags": [_text(value, 80).lower() for value in (raw.get("tags") or []) if _text(value, 80)][:12],
            "provenance": _text(raw.get("provenance"), 80),
            "policy_priority": priority,
            "score": round(score, 3),
            "rank_reason": ", ".join(reasons[:5]),
        })

    ranked.sort(key=lambda row: (row["score"], row["policy_priority"], row["confidence"]), reverse=True)
    selected: List[Dict[str, Any]] = []
    per_source: defaultdict[str, int] = defaultdict(int)
    seen_summaries: set[str] = set()
    for row in ranked:
        source_key = row.get("source_url") or row.get("source_title") or row.get("id")
        if per_source[source_key] >= 2:
            continue
        fingerprint = " ".join(_tokens(row.get("summary"))[:18])
        if fingerprint and fingerprint in seen_summaries:
            continue
        selected.append(row)
        per_source[source_key] += 1
        if fingerprint:
            seen_summaries.add(fingerprint)
        if len(selected) >= max(1, min(limit, 12)):
            break
    return selected


def source_cards(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return compact numbered source metadata for an API response."""
    cards = []
    for index, row in enumerate(rows, 1):
        cards.append({
            "index": index,
            "title": _text(row.get("source_title") or row.get("title"), 260),
            "url": _text(row.get("source_url"), 700),
            "label": _text(row.get("source_label"), 60),
            "status": _text(row.get("official_status"), 40),
            "confidence": int(row.get("confidence") or 0),
        })
    return cards



def _strip_source_references(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"\[(?:bron|source)?\s*\d+\]", "", text, flags=re.I)
    text = re.sub(r"\(?\b(?:zie|see)\s+(?:het\s+)?(?:dossier|module|seminar|video|transcript)\s*[0-9A-Za-z._-]*\)?", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" -\n")

def deterministic_knowledge_answer(question: str, latest: Dict[str, Any], rows: List[Dict[str, Any]], language: str = "nl") -> str:
    """Small source-free fallback when no LLM key is configured."""
    if not rows:
        return "Geen passende kennisregel gevonden. Gebruik de mechanische cockpitregels en forceer geen trade."
    english = str(language).lower().startswith("en")
    lines = ["Keep it mechanical." if english else "Hou het mechanisch."]
    for row in rows[:3]:
        summary = _text(row.get("summary"), 500)
        if summary:
            lines.append(summary)
    gate = ((latest.get("execution_gate") or {}).get("reason") or "").strip()
    if gate:
        lines.append(("Current cockpit rule: " if english else "Huidige cockpitregel: ") + gate)
    lines.append("The cockpit safety rules remain decisive." if english else "De veiligheidsregels van de cockpit blijven beslissend.")
    return _strip_source_references("\n\n".join(lines))


def prompt_lessons(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return lesson content for the LLM without titles, URLs or source names."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({
            "lesson_id": _text(row.get("id"), 160),
            "summary": _text(row.get("summary"), 1400),
            "type": _text(row.get("type"), 60),
            "confidence": max(0, min(100, int(row.get("confidence") or 0))),
            "official_status": _text(row.get("official_status"), 40),
            "tags": [_text(value, 80).lower() for value in (row.get("tags") or []) if _text(value, 80)][:12],
        })
    return out
