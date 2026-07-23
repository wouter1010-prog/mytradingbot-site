"""Primary coach knowledge selection for MyTradingBot.

The curated dossier bank is the coach's primary educational layer. Operator
policy and product-safety rules remain authoritative. Video lessons are loaded
separately as supplemental context and never replace these dossiers.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).with_name("coach_knowledge")
INSTRUCTION_FILE = ROOT / "00-COACH-INSTRUCTIE.md"
INDEX_FILE = ROOT / "99-SITUATIE-INDEX.md"
DOSSIER_FILES = {
    match.group(1): path
    for path in sorted(ROOT.glob("[0-1][0-9]-*.md"))
    if (match := re.match(r"^(0[1-9]|1[0-5])-", path.name))
}

_STOPWORDS = {
    "aan", "als", "bij", "dan", "dat", "de", "deze", "die", "dit", "door", "een", "en",
    "er", "geen", "heb", "het", "hoe", "ik", "in", "is", "je", "kan", "maar", "met", "mijn",
    "naar", "niet", "of", "om", "op", "te", "uit", "van", "voor", "wat", "waar", "wanneer",
    "waarom", "wel", "wordt", "zijn", "zo", "a", "about", "and", "are", "as", "at", "be", "by",
    "can", "do", "for", "from", "how", "i", "in", "is", "it", "my", "not", "of", "on", "or",
    "should", "that", "the", "this", "to", "what", "when", "where", "why", "with", "you", "your",
}

_ENGLISH_HINTS = {
    "stop loss": "stoploss invalidatie level 2 uitgestopt",
    "stop hunt": "liquiditeit stophunt sweep uitgestopt",
    "stop hunted": "liquiditeit stophunt sweep uitgestopt",
    "hunt": "liquiditeit stophunt sweep",
    "hunted": "liquiditeit stophunt sweep uitgestopt",
    "stopped out": "uitgestopt stoploss",
    "take profit": "take profit winst nemen tp",
    "break even": "break-even stop profit",
    "entry": "entry instappen instap",
    "risk": "risico sizing positiegrootte",
    "position size": "positiegrootte sizing",
    "leverage": "leverage hefboom",
    "revenge": "revenge discipline emotie",
    "fear": "angst psychologie",
    "journal": "dagboek journal data edge",
    "trend": "trend structuur",
    "range": "range midrange",
    "support": "support steun zone level",
    "resistance": "resistance weerstand zone level",
    "confirmation": "confirmatie close momentum abc",
    "timeframe": "timeframe htf ltf top-down",
    "scalp": "scalp",
    "swing": "swing",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9%+._-]+", " ", text).strip()


def _tokens(value: Any) -> List[str]:
    return [token for token in _normalise(value).split() if len(token) > 1 and token not in _STOPWORDS]


def _expand_english(text: str) -> str:
    normal = _normalise(text)
    additions = [terms for phrase, terms in _ENGLISH_HINTS.items() if phrase in normal]
    return f"{text} {' '.join(additions)}" if additions else text


@lru_cache(maxsize=1)
def coach_instruction() -> str:
    return _read(INSTRUCTION_FILE).strip()


@lru_cache(maxsize=1)
def _selection_rows() -> List[Dict[str, Any]]:
    """Parse situation rows and quick keyword hints from the supplied index."""
    rows: List[Dict[str, Any]] = []
    for raw_line in _read(INDEX_FILE).splitlines():
        line = raw_line.strip()
        if line.startswith("|") and "---" not in line:
            cells = [cell.strip().strip('"') for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0].lower() != "situatie":
                dossiers = re.findall(r"\b(?:0[1-9]|1[0-5])\b", cells[1])
                if dossiers:
                    rows.append({"terms": _tokens(cells[0]), "dossiers": dossiers, "weight": 6})
            continue
        if line.startswith("-") and "→" in line:
            left, right = line[1:].split("→", 1)
            dossiers = re.findall(r"\b(?:0[1-9]|1[0-5])\b", right)
            if dossiers:
                rows.append({"terms": _tokens(left), "dossiers": dossiers, "weight": 4})
    return rows


def _latest_hint(latest: Optional[Dict[str, Any]]) -> str:
    if not isinstance(latest, dict):
        return ""
    gate = latest.get("execution_gate") or {}
    setup = latest.get("setup") or {}
    values = [
        gate.get("status"), gate.get("reason"), " ".join(gate.get("failed") or []),
        setup.get("direction"), setup.get("profile"), setup.get("parent_timeframe"),
    ]
    return " ".join(str(value or "") for value in values)


def select_dossiers(question: str, latest: Optional[Dict[str, Any]] = None, limit: int = 3) -> List[Dict[str, str]]:
    """Select two or three full dossiers using the supplied situation index.

    This deliberately uses a small deterministic matcher: fewer moving parts,
    reproducible audit output, and no embedding dependency for a static corpus.
    """
    cap = max(2, min(int(limit or 3), 3))
    haystack = _expand_english(f"{question} {_latest_hint(latest)}")
    query = Counter(_tokens(haystack))
    scores: Counter[str] = Counter()

    for row in _selection_rows():
        terms = row["terms"]
        overlap = sum(min(query[token], terms.count(token)) for token in set(terms))
        if not overlap:
            continue
        for position, dossier in enumerate(row["dossiers"]):
            scores[dossier] += overlap * row["weight"] + max(0, 3 - position)

    # Secondary recall: match question terms against dossier title and content.
    for dossier, path in DOSSIER_FILES.items():
        content_tokens = Counter(_tokens(f"{path.stem} {_read(path)[:12000]}"))
        overlap = sum(min(query[token], content_tokens[token]) for token in query)
        if overlap:
            scores[dossier] += min(overlap, 12)

    if not scores:
        lower = _normalise(question)
        defaults = ["07", "06", "13"] if any(term in lower for term in ("trade", "positie", "position", "journal", "dagboek")) else ["12", "14"]
        for index, dossier in enumerate(defaults):
            scores[dossier] = 10 - index

    selected: List[Dict[str, str]] = []
    for dossier, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
        path = DOSSIER_FILES.get(dossier)
        if not path:
            continue
        selected.append({
            "number": dossier,
            "key": path.name,
            "title": path.stem[3:].replace("-", " ").strip().title(),
            "content": _read(path).strip(),
            "score": str(score),
        })
        if len(selected) >= cap:
            break

    # The README requires 2-3 dossiers per turn. Fill deterministically when a
    # narrow query only matches one dossier.
    for fallback in ("12", "14", "13", "15"):
        if len(selected) >= 2:
            break
        if any(row["number"] == fallback for row in selected):
            continue
        path = DOSSIER_FILES.get(fallback)
        if path:
            selected.append({
                "number": fallback,
                "key": path.name,
                "title": path.stem[3:].replace("-", " ").strip().title(),
                "content": _read(path).strip(),
                "score": "fallback",
            })
    return selected[:cap]


def dossier_context(question: str, latest: Optional[Dict[str, Any]] = None, limit: int = 3) -> Dict[str, Any]:
    selected = select_dossiers(question, latest=latest, limit=limit)
    return {
        "selected": [{key: row[key] for key in ("number", "key", "title", "score")} for row in selected],
        "text": "\n\n".join(row["content"] for row in selected),
    }



def sanitise_coach_answer(value: Any) -> str:
    """Remove implementation/source references from mentor-facing copy.

    Provenance remains available internally, but the coach must never sound like
    it is reading a filing cabinet or expose URLs/citation markers.
    """
    text = str(value or "").strip()
    text = re.sub(r"https?://\S+", "", text, flags=re.I)
    text = re.sub(r"\[(?:bron|source)?\s*\d+\]", "", text, flags=re.I)
    text = re.sub(r"\(?\b(?:zie|see|vgl\.?|compare)\s+(?:het\s+)?(?:dossier|module|seminar|video|transcript)\s*[0-9A-Za-z._-]*\)?", "", text, flags=re.I)
    text = re.sub(r"\b(?:dossier|module|seminar|transcript)\s*(?:nr\.?\s*)?\d{1,3}\b", "de kennis", text, flags=re.I)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" -\n")

def deterministic_dossier_answer(
    question: str,
    latest: Dict[str, Any],
    dossier_text: str,
    video_rows: List[Dict[str, Any]],
    language: str = "nl",
) -> str:
    """Small source-free fallback for deployments without an LLM key."""
    english = str(language).lower().startswith("en")
    query = Counter(_tokens(_expand_english(question)))
    candidates: List[tuple[int, str]] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", dossier_text):
        sentence = re.sub(r"^[#>*\-\d.\s]+", "", raw).strip()
        if len(sentence) < 35 or sentence.startswith("|"):
            continue
        overlap = sum(min(query[token], Counter(_tokens(sentence))[token]) for token in query)
        if overlap:
            candidates.append((overlap, sentence[:420]))
    candidates.sort(key=lambda row: (-row[0], len(row[1])))

    lines: List[str] = []
    for _, sentence in candidates[:2]:
        if sentence not in lines:
            lines.append(sentence)
    for row in video_rows[:2]:
        summary = str(row.get("summary") or "").strip()
        if summary and summary not in lines:
            lines.append(summary[:420])
        if len(lines) >= 3:
            break

    gate = latest.get("execution_gate") or {}
    reason = str(gate.get("reason") or "").strip()
    if english:
        intro = "Keep it mechanical."
        action = "Next action: write down A, B and C before the next entry."
        safety = "The cockpit rules remain decisive; do not force a trade."
    else:
        intro = "Hou het mechanisch."
        action = "Volgende actie: schrijf vóór je volgende entry A, B en C uit."
        safety = "De cockpitregels blijven beslissend; forceer geen trade."
    answer = [intro]
    answer.extend(lines or [safety])
    if reason:
        answer.append(("Current cockpit rule: " if english else "Huidige cockpitregel: ") + reason)
    answer.append(action)
    return sanitise_coach_answer("\n\n".join(answer))
