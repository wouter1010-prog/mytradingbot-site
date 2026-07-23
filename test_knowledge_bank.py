from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from coach_dossiers import coach_instruction, deterministic_dossier_answer, dossier_context, select_dossiers
from knowledge_retrieval import deterministic_knowledge_answer, rank_knowledge, source_cards
import core_services


class KnowledgeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "knowledge_sources.json").read_text(encoding="utf-8"))
        self.queue = json.loads((ROOT / "queue.json").read_text(encoding="utf-8"))

    def test_all_103_sources_are_dynamically_checked(self):
        sources = self.catalog["sources"]
        self.assertEqual(103, len(sources))
        self.assertEqual(32, sum(row["format"] == "live" for row in sources))
        self.assertEqual(0, sum(row["selection_status"].startswith("excluded") for row in sources))
        self.assertEqual(103, len(self.queue))
        self.assertIsNone(self.catalog["counts"]["target_verified_transcripts"])
        self.assertTrue(self.catalog["counts"]["dynamic_quarantine"])
        self.assertTrue(all(row["coach_eligible"] for row in sources))

    def test_video_ids_are_unique(self):
        ids = [row["video_id"] for row in self.catalog["sources"]]
        queue_ids = [row["id"] for row in self.queue]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, queue_ids)
        self.assertTrue(all(len(video_id) == 11 for video_id in ids))

    def test_external_content_is_not_commercially_cleared(self):
        self.assertTrue(all(row["commercial_use_allowed"] is False for row in self.catalog["sources"]))
        self.assertTrue(self.catalog["policy"]["transcript_availability_decided_by_ingestion"])
        self.assertFalse(self.catalog["policy"]["coach_visible_source_citations_default"])


class CuratedDossierTests(unittest.TestCase):
    def test_complete_curated_bank_is_packaged(self):
        folder = ROOT / "coach_knowledge"
        files = sorted(folder.glob("*.md"))
        self.assertEqual(18, len(files))
        self.assertTrue((folder / "00-COACH-INSTRUCTIE.md").exists())
        self.assertTrue((folder / "99-SITUATIE-INDEX.md").exists())
        self.assertIn("Trade-ABC", coach_instruction())

    def test_stoploss_question_selects_primary_stop_dossier(self):
        selected = select_dossiers("Ik word steeds door een wick uitgestopt; waar hoort mijn stoploss?", limit=3)
        numbers = [row["number"] for row in selected]
        self.assertGreaterEqual(len(numbers), 2)
        self.assertLessEqual(len(numbers), 3)
        self.assertIn("06", numbers)
        self.assertIn("10", numbers)

    def test_english_question_uses_same_primary_bank(self):
        selected = select_dossiers("Where should my stop loss go after a liquidity sweep?", limit=3)
        numbers = [row["number"] for row in selected]
        self.assertIn("06", numbers)
        self.assertIn("10", numbers)

    def test_context_contains_only_selected_full_dossiers(self):
        context = dossier_context("Ik wil revenge traden na drie verliezen")
        self.assertGreaterEqual(len(context["selected"]), 2)
        self.assertLessEqual(len(context["selected"]), 3)
        self.assertIn("discipline", context["text"].lower())


class RetrievalTests(unittest.TestCase):
    def test_operator_policy_outranks_external_risk_claim(self):
        rows = [
            {
                "id": "external", "title": "Meer risico nemen",
                "summary": "Gebruik vijf procent risico voor een sterke setup.", "type": "risk",
                "source_label": "DOOPIECASH-VIDEO", "source_title": "Video",
                "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
                "official_status": "interpretation", "confidence": 90,
            },
            {
                "id": "policy", "title": "Risicoprofielen",
                "summary": "Scalp 0,5%, day 1,0%, swing 2,0%.", "type": "risk",
                "source_label": "OPERATORBELEID", "source_title": "MyTradingBot beleid",
                "official_status": "official", "confidence": 100, "provenance": "static-methodology",
            },
        ]
        ranked = rank_knowledge("Hoeveel risico moet ik nemen?", rows, limit=2)
        self.assertEqual("policy", ranked[0]["id"])
        self.assertGreater(ranked[0]["policy_priority"], ranked[1]["policy_priority"])

    def test_retrieval_is_relevant_and_source_bounded(self):
        rows = []
        for index in range(4):
            rows.append({
                "id": f"same:{index}", "title": "3M kanteling",
                "summary": f"Les {index} over een 3M kanteling bij steun.", "type": "entry",
                "source_label": "DOOPIECASH-VIDEO", "source_title": "Zelfde video",
                "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "confidence": 80,
            })
        rows.append({
            "id": "other", "title": "4H steun",
            "summary": "Gebruik de 4H-zone als locatie, niet als directe entry.", "type": "zone",
            "source_label": "DOOPIECASH-VIDEO", "source_title": "Andere video",
            "source_url": "https://www.youtube.com/watch?v=lmnopqrstuv", "confidence": 80,
        })
        ranked = rank_knowledge("Wat betekent de 3M kanteling bij 4H steun?", rows, limit=5)
        counts = {}
        for row in ranked:
            counts[row["source_url"]] = counts.get(row["source_url"], 0) + 1
        self.assertLessEqual(max(counts.values()), 2)
        self.assertTrue(any(row["id"] == "other" for row in ranked))

    def test_api_context_never_contains_full_transcript_field(self):
        rows = [{
            "id": "lesson", "title": "Wachten", "summary": "Wachten is correct buiten een geldige zone.",
            "type": "mindset", "source_label": "DOOPIECASH-VIDEO", "source_title": "Video",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "confidence": 75,
            "transcript": "GEHELE TRANSCRIPT MAG NIET MEE",
        }]
        ranked = rank_knowledge("Moet ik wachten?", rows)
        self.assertNotIn("transcript", ranked[0])
        self.assertNotIn("GEHELE TRANSCRIPT", json.dumps(ranked, ensure_ascii=False))

    def test_fallback_answers_have_no_visible_source_markers(self):
        rows = [{
            "id": "lesson", "title": "Wachten", "summary": "Wachten is correct buiten een geldige zone.",
            "type": "mindset", "source_label": "DOOPIECASH-VIDEO", "source_title": "Video",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk", "confidence": 75,
        }]
        ranked = rank_knowledge("Moet ik wachten?", rows)
        answer = deterministic_knowledge_answer(
            "Moet ik wachten?", {"execution_gate": {"reason": "Geen geldige setup"}}, ranked
        )
        self.assertNotIn("[1]", answer)
        self.assertNotIn("bron", answer.lower())
        self.assertIn("veiligheidsregels", answer)
        self.assertEqual(1, len(source_cards(ranked)))  # internal audit metadata remains available

    def test_curated_fallback_is_source_free(self):
        context = dossier_context("Ik wil na een verlies meteen opnieuw instappen")
        answer = deterministic_dossier_answer(
            "Ik wil na een verlies meteen opnieuw instappen",
            {"execution_gate": {"reason": "Geen geldige setup"}},
            context["text"], [], language="nl",
        )
        self.assertNotIn("dossier", answer.lower())
        self.assertNotIn("video", answer.lower())
        self.assertNotRegex(answer, r"\[\d+\]")


class IngestionStaticTests(unittest.TestCase):
    def test_permanent_no_transcript_is_quarantined_in_code(self):
        source = (ROOT / "core_services.py").read_text(encoding="utf-8")
        self.assertIn("class TranscriptUnavailable", source)
        self.assertIn('status="excluded_no_transcript"', source)
        self.assertIn("load_knowledge_source_state", source)

    def test_persistent_queue_cannot_hide_packaged_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            packaged = Path(folder) / "packaged.json"
            runtime = Path(folder) / "runtime.json"
            packaged.write_text(json.dumps([
                {"id": "abcdefghijk", "title": "packaged"},
                {"id": "lmnopqrstuv", "title": "second"},
            ]), encoding="utf-8")
            runtime.write_text(json.dumps([
                {"id": "abcdefghijk", "title": "runtime override"},
            ]), encoding="utf-8")
            old_packaged, old_runtime = core_services.PACKAGED_KNOWLEDGE_QUEUE, core_services.KNOWLEDGE_QUEUE
            try:
                core_services.PACKAGED_KNOWLEDGE_QUEUE = packaged
                core_services.KNOWLEDGE_QUEUE = runtime
                rows = core_services.load_knowledge_queue()
            finally:
                core_services.PACKAGED_KNOWLEDGE_QUEUE = old_packaged
                core_services.KNOWLEDGE_QUEUE = old_runtime
            self.assertEqual({"abcdefghijk", "lmnopqrstuv"}, {row["id"] for row in rows})
            self.assertEqual("runtime override", next(row["title"] for row in rows if row["id"] == "abcdefghijk"))

    def test_coach_uses_primary_dossiers_then_supplemental_videos(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("dossier_context(question, latest=latest, limit=3)", source)
        self.assertIn("rank_knowledge(question, knowledge_feed(500)", source)
        self.assertIn("PRIMAIRE GESELECTEERDE DOSSIERS", source)
        self.assertIn("AANVULLENDE KORTE VIDEOLESSEN", source)
        self.assertIn('source="grounded_curated_knowledge"', source)
        self.assertIn("COACH_SHOW_SOURCES", source)
        self.assertIn('MYTRADINGBOT_COACH_SHOW_SOURCES", "0"', source)
        self.assertNotIn("Gebruik bronverwijzingen als [1]", source)

    def test_trade_engine_files_are_not_part_of_dossier_selection(self):
        source = (ROOT / "coach_dossiers.py").read_text(encoding="utf-8")
        for forbidden in ("send_order", "place_order", "timeframe_stack", "trade_lifecycle"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
