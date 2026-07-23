from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "r23-test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_KNOWLEDGE_INGESTION", "0")

import core_services
import main
from day_start_coach import build_bilingual_day_start
from knowledge_retrieval import prompt_lessons, rank_knowledge
from test_round18 import overview


class TemporaryKnowledgeStore:
    def __init__(self, root: Path):
        self.root = root
        self.packaged = root / "packaged.json"
        self.runtime = root / "runtime.json"
        self.processed = root / "processed.json"
        self.state = root / "source_state.json"
        self.log = root / "ingestion.json"
        self.feed = root / "public_feed.json"
        self.transcripts = root / "transcripts"
        self.structured = root / "structured"
        self.method = root / "methodology.json"
        self.packaged.write_text("[]", encoding="utf-8")
        self.runtime.write_text("[]", encoding="utf-8")
        self.processed.write_text("[]", encoding="utf-8")
        self.method.write_text('{"rules": []}', encoding="utf-8")
        self.transcripts.mkdir()
        self.structured.mkdir()
        self.stack = ExitStack()

    def __enter__(self):
        for name, value in {
            "PACKAGED_KNOWLEDGE_QUEUE": self.packaged,
            "KNOWLEDGE_QUEUE": self.runtime,
            "PROCESSED": self.processed,
            "KNOWLEDGE_SOURCE_STATE": self.state,
            "INGESTION_LOG": self.log,
            "PUBLIC_FEED_STATE": self.feed,
            "TRANSCRIPTS": self.transcripts,
            "STRUCTURED": self.structured,
        }.items():
            self.stack.enter_context(patch.object(core_services, name, value))
        self.stack.enter_context(patch.object(main, "METHOD_SOURCES_FILE", self.method))
        core_services._PROCESSING_VIDEO_IDS.clear()
        core_services._KNOWLEDGE_WAKE.clear()
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


class Phase3IngestionTests(unittest.TestCase):
    def test_public_rss_discovers_and_queues_once(self):
        with tempfile.TemporaryDirectory() as folder, TemporaryKnowledgeStore(Path(folder)) as store:
            entry = SimpleNamespace(yt_videoid="R23public01", title="Public lesson", published="2026-07-20T08:00:00Z")
            feed = SimpleNamespace(entries=[entry], bozo=False)
            with patch.object(core_services, "YT_CHANNEL_ID", "UC1234567890"), patch.object(core_services, "ENABLE_PUBLIC_YOUTUBE_RSS", True), patch.object(core_services.feedparser, "parse", return_value=feed):
                self.assertEqual(1, core_services.check_new_videos())
                self.assertEqual(0, core_services.check_new_videos())
            queue = json.loads(store.runtime.read_text(encoding="utf-8"))
            self.assertEqual(1, len(queue))
            self.assertEqual("R23public01", queue[0]["id"])
            self.assertEqual("PUBLIC_RSS", queue[0]["ingestion_source"])
            state = json.loads(store.feed.read_text(encoding="utf-8"))
            self.assertEqual("R23public01", state["last_discovered_video_id"])
            self.assertNotIn("last_auto_fetched_at", state)
            self.assertTrue(state["last_checked_at"])

    def test_manual_queue_is_idempotent_and_owner_only(self):
        token = "r23-owner-token-with-at-least-thirty-two-chars"
        with tempfile.TemporaryDirectory() as folder, TemporaryKnowledgeStore(Path(folder)):
            client = main.app.test_client()
            with patch.object(main, "API_TOKEN", token), patch.object(main, "rate_allowed", return_value=True):
                first = client.post("/api/v1/knowledge/queue", json={"url": "https://youtube.com/live/R23platnum1?feature=share"}, headers={"X-MyTradingBot-Token": token})
                second = client.post("/api/v1/knowledge/queue", json={"url": "https://youtu.be/R23platnum1"}, headers={"X-MyTradingBot-Token": token})
                self.assertEqual(202, first.status_code)
                self.assertEqual("queued", first.get_json()["result"]["status"])
                self.assertTrue(core_services._KNOWLEDGE_WAKE.is_set(), "een handmatige link moet de worker direct wakker maken")
                self.assertEqual(200, second.status_code)
                self.assertEqual("already_queued", second.get_json()["result"]["status"])
                with patch.object(main, "is_owner", return_value=False):
                    denied = client.post("/api/v1/knowledge/queue", json={"url": "https://youtu.be/Another0001"}, headers={"X-MyTradingBot-Token": token})
                self.assertEqual(403, denied.status_code)

    def test_no_transcript_is_quarantined_and_not_retried(self):
        with tempfile.TemporaryDirectory() as folder, TemporaryKnowledgeStore(Path(folder)) as store:
            store.runtime.write_text(json.dumps([{"id": "R23noCapt01", "title": "No captions"}]), encoding="utf-8")
            with patch.object(core_services, "get_transcript", side_effect=core_services.TranscriptUnavailable("captions disabled")) as transcript:
                self.assertEqual(0, core_services.run_backlog())
                self.assertEqual(1, transcript.call_count)
            source_state = json.loads(store.state.read_text(encoding="utf-8"))
            self.assertEqual("excluded_no_transcript", source_state["R23noCapt01"]["status"])
            with patch.object(core_services, "get_transcript") as transcript:
                self.assertEqual(0, core_services.run_backlog())
                transcript.assert_not_called()

    def test_realistic_new_lesson_flows_into_coach_and_day_start(self):
        video_id = "R23lesson01"
        transcript = (
            "Na een liquidity sweep ontstaat soms microcompressie. Wacht dan op een candle close en een retest. "
            "Zonder bevestiging is de beweging alleen een waarneming en geen uitvoerbare trade. "
            "De marktkaart en vaste risicopoorten blijven altijd leidend."
        )
        extraction = {
            "video_type": "kennis",
            "summary": "Microcompressie na een sweep vraagt om geduld.",
            "knowledge": [{
                "title": "Microcompressie na sweep",
                "statement": "Bij microcompressie na een liquidity sweep wacht je op candle-close en retest; zonder bevestiging blijft het observatie.",
                "category": "entry",
                "source_label": "PUBLIC-YOUTUBE",
                "confidence": 91,
                "evidence": "De spreker koppelt sweep, compressie, close en retest in die volgorde.",
                "official_status": "interpretation",
                "tags": ["microcompressie", "sweep", "confirmatie", "retest"],
                "timeframes": ["15M", "3M"],
                "applies_when": "na een sweep bij een bevestigde zone",
                "avoid_when": "zonder candle-close of retest",
            }],
            "warnings": [],
        }
        with tempfile.TemporaryDirectory() as folder, TemporaryKnowledgeStore(Path(folder)) as store:
            with patch.object(core_services, "get_transcript", return_value=transcript), patch.object(core_services, "_knowledge_prompt", return_value=extraction):
                self.assertTrue(core_services.process_video({
                    "id": video_id, "title": "Nieuwe openbare les", "video_date": "2026-07-20",
                    "source_label": "PUBLIC-YOUTUBE", "ingestion_source": "PUBLIC_RSS",
                }))
            structured = json.loads((store.structured / f"{video_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(transcript, (store.transcripts / f"{video_id}.txt").read_text(encoding="utf-8"))
            self.assertEqual("PUBLIC_RSS", structured["_ingestion_source"])
            self.assertEqual(1, len(structured["knowledge"]))

            token = "r23-coach-token-with-at-least-thirty-two-chars"
            main.RATE_STATE.clear()
            with patch.object(main, "API_TOKEN", token), patch.object(main, "decision_payload", return_value={"execution_gate": {"reason": "Wacht op bevestiging"}}), patch.object(main.services, "ANTHROPIC_API_KEY", ""):
                response = main.app.test_client().post(
                    "/api/v1/coach",
                    json={"question": "Wat betekent microcompressie na een liquidity sweep?", "language": "nl"},
                    headers={"X-MyTradingBot-Token": token},
                )
            self.assertEqual(200, response.status_code)
            answer = response.get_json()["answer"].lower()
            self.assertIn("microcompressie", answer)
            self.assertNotIn("youtube", answer)
            self.assertNotIn("bron", answer)

            ranked = rank_knowledge(
                "dagstart range confirmatie discipline sweep momentum no trade microcompressie",
                main.knowledge_feed(500), limit=12,
            )
            video_lessons = [row for row in ranked if row.get("provenance") == "video-extraction"][:3]
            briefing = build_bilingual_day_start(overview(), supplemental_lessons=prompt_lessons(video_lessons or ranked[:3]))
            self.assertIn(f"{video_id}:1", briefing["context"]["knowledge_lesson_ids"])
            focus = next(row for row in briefing["briefings"]["nl"]["sections"] if row["key"] == "process_focus")
            self.assertIn("Kennisfocus", focus["body"])
            self.assertIn("microcompressie", focus["body"].lower())
            self.assertNotIn("YouTube", focus["body"])

    def test_video_id_parser_accepts_supported_forms(self):
        expected = "abcdefghijk"
        for value in [
            expected,
            f"https://youtu.be/{expected}",
            f"https://www.youtube.com/watch?v={expected}",
            f"https://youtube.com/live/{expected}?feature=share",
            f"https://www.youtube.com/shorts/{expected}",
        ]:
            self.assertEqual(expected, core_services.youtube_video_id(value))
        self.assertEqual("", core_services.youtube_video_id("https://example.com/not-youtube"))


if __name__ == "__main__":
    unittest.main()
