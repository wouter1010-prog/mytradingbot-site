from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import post_trade_coach_loop as loopmod
import core_services as services


REAL_CLOSE = {
    "orderId": "close-r24b-001",
    "symbol": "BTCUSDT",
    "side": "Sell",
    "avgEntryPrice": "64200.0",
    "avgExitPrice": "64420.0",
    "closedPnl": "21.84",
    "updatedTime": "1784642400000",
}
REAL_DEEPDIVE = {
    "uitkomst": "Winst, maar het proces was te vroeg.",
    "proces_grade": "B",
    "oordeel": "De richting klopte, maar de bevestiging was nog niet af.",
    "wat_ging_goed": "De trade lag aan de juiste kant van de 4H-zone.",
    "wat_kan_beter": "Wacht op de 3M-close en hertest voordat je handelt.",
    "les": "Een goede richting is nog geen goede entry; bevestiging blijft nodig.",
    "source_label": "POST-TRADE-COACH",
}


def write_knowledge(root: Path) -> tuple[Path, Path]:
    structured = root / "structured"
    structured.mkdir(parents=True, exist_ok=True)
    methodology = root / "methodology_sources.json"
    methodology.write_text(json.dumps({"rules": [{
        "id": "rule-confirmation",
        "title": "Wacht op bevestiging",
        "category": "entry",
        "statement": "Een richting wordt pas een uitvoerbaar idee nadat de 3M-close en hertest de lokale kanteling bevestigen.",
        "source_label": "PRODUCTMETHODIEK",
        "official_status": "official",
        "confidence": 100,
        "tags": ["3m", "close", "hertest", "bevestiging"],
    }]}, ensure_ascii=False), encoding="utf-8")
    (structured / "new-video.json").write_text(json.dumps({
        "video_type": "kennis",
        "_title": "Geduld bij lokale kantelingen",
        "knowledge": [{
            "id": "video:new:confirmation",
            "title": "Laat de hertest het werk doen",
            "statement": "Een microcompressie na de eerste 3M-close is alleen een observatielens; wacht op de hertest voordat je het proces beoordeelt.",
            "category": "entry",
            "source_label": "EXTERNE-BRON",
            "official_status": "interpretation",
            "confidence": 88,
            "tags": ["microcompressie", "3m", "hertest"],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    return structured, methodology


class PostTradeCoachLoopTests(unittest.TestCase):
    def test_env_gate_is_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            loop = loopmod.PostTradeCoachLoop(Path(tmp))
            self.assertFalse(loop.enabled)
            self.assertFalse(loop.queue(REAL_CLOSE, REAL_DEEPDIVE))
            self.assertEqual(loop.flush(lambda _: True), 0)

    def test_real_deepdive_selects_one_existing_lesson(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured, methodology = write_knowledge(root)
            lesson = loopmod.select_lesson(
                REAL_CLOSE, REAL_DEEPDIVE,
                structured_dir=structured,
                methodology_file=methodology,
            )
            self.assertIsNotNone(lesson)
            self.assertEqual(lesson["role"], "observation_lens_only")
            self.assertIn("bevestig", lesson["summary"].lower())
            self.assertNotIn("http", json.dumps(lesson).lower())

    def test_queue_retry_and_restart_deduplicate_one_closed_trade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured, methodology = write_knowledge(root)
            loop = loopmod.PostTradeCoachLoop(root, enabled=True, structured_dir=structured, methodology_file=methodology)
            enriched = loop.enrich_analysis(REAL_CLOSE, REAL_DEEPDIVE)
            self.assertIn("coach_loop_lesson", enriched)
            self.assertTrue(loop.queue(REAL_CLOSE, enriched))
            self.assertFalse(loop.queue(REAL_CLOSE, enriched))

            attempts = []
            self.assertEqual(loop.flush(lambda message: attempts.append(message) or False), 0)
            self.assertEqual(loop.status()["pending"], 1)
            self.assertEqual(len(attempts), 1)

            sent = []
            self.assertEqual(loop.flush(lambda message: sent.append(message) or True), 1)
            self.assertEqual(loop.status()["pending"], 0)
            self.assertEqual(loop.status()["sent"], 1)
            self.assertEqual(loop.flush(lambda message: sent.append(message) or True), 0)
            self.assertEqual(len(sent), 1)

            restarted = loopmod.PostTradeCoachLoop(root, enabled=True, structured_dir=structured, methodology_file=methodology)
            self.assertEqual(restarted.status()["sent"], 1)
            self.assertFalse(restarted.queue(REAL_CLOSE, enriched))
            self.assertEqual(restarted.flush(lambda _: True), 0)

    def test_message_contains_deepdive_and_safe_knowledge_lens(self):
        payload = {
            "symbol": "BTCUSDT", "direction": "long", "pnl": 21.84,
            "analysis": REAL_DEEPDIVE,
            "lesson": {
                "title": "Laat de hertest het werk doen",
                "summary": "Gebruik microcompressie alleen om beter te kijken; het is geen reden om te handelen.",
            },
        }
        message = loopmod.format_message(payload)
        self.assertIn("Gesloten leerlus", message)
        self.assertIn("Deepdive", message)
        self.assertIn("Kennislens", message)
        self.assertIn("microcompressie", message)
        self.assertIn("geen handelssignaal", message)
        self.assertNotIn("http", message.lower())
        self.assertNotRegex(message, r"\[(?:bron|source)?\s*\d+\]")

    def test_existing_close_event_queues_and_flushes_without_new_polling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured, methodology = write_knowledge(root)
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_COACH_LOOP": "1"}, clear=False):
                loopmod.configure_post_trade_coach_loop(root, structured_dir=structured, methodology_file=methodology)
            sent = []
            saved = []
            with mock.patch.object(services, "log_closed_trade", return_value=True), \
                 mock.patch.object(services, "_clear_tp_progress"), \
                 mock.patch.object(services, "get_equity", return_value=20000.0), \
                 mock.patch.object(services, "telegram", side_effect=lambda message: sent.append(message) or True), \
                 mock.patch.object(services, "analyze_closed_trade", return_value=dict(REAL_DEEPDIVE)), \
                 mock.patch.object(services, "save_deepdive", side_effect=lambda row, analysis: saved.append(analysis) or True):
                count = services.process_closed_pnl_rows([REAL_CLOSE], first_cycle=False)
            self.assertEqual(count, 1)
            self.assertEqual(len(saved), 1)
            self.assertIn("coach_loop_lesson", saved[0])
            self.assertEqual(sum("Gesloten leerlus" in message for message in sent), 1)
            self.assertEqual(sum("🔎 Deepdive" in message for message in sent), 0, "oude losse deepdive mag bij actieve coachlus niet dubbel verzenden")

    def test_first_cycle_never_backfills_old_trades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured, methodology = write_knowledge(root)
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_COACH_LOOP": "1"}, clear=False):
                loop = loopmod.configure_post_trade_coach_loop(root, structured_dir=structured, methodology_file=methodology)
            sent = []
            with mock.patch.object(services, "log_closed_trade", return_value=True), \
                 mock.patch.object(services, "_clear_tp_progress"), \
                 mock.patch.object(services, "telegram", side_effect=lambda message: sent.append(message) or True), \
                 mock.patch.object(services, "analyze_closed_trade") as analyse:
                self.assertEqual(services.process_closed_pnl_rows([REAL_CLOSE], first_cycle=True), 1)
            analyse.assert_not_called()
            self.assertEqual(sent, [])
            self.assertEqual(loop.status()["pending"], 0)


    def test_real_close_writes_journal_deepdive_and_one_coach_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structured, methodology = write_knowledge(root)
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_COACH_LOOP": "1"}, clear=False):
                loopmod.configure_post_trade_coach_loop(root, structured_dir=structured, methodology_file=methodology)
            sent = []
            paths = {
                "DATA_DIR": root,
                "JOURNAL": root / "journal.json",
                "JOURNAL_RESET": root / "journal_reset.json",
                "DEEPDIVES": root / "deepdives.json",
                "TP_PROGRESS": root / "tp_progress.json",
            }
            patches = [mock.patch.object(services, key, value) for key, value in paths.items()]
            for patcher in patches:
                patcher.start()
            try:
                with mock.patch.object(services, "get_equity", return_value=20000.0), \
                     mock.patch.object(services, "telegram", side_effect=lambda message: sent.append(message) or True), \
                     mock.patch.object(services, "analyze_closed_trade", return_value=dict(REAL_DEEPDIVE)):
                    self.assertEqual(services.process_closed_pnl_rows([REAL_CLOSE], first_cycle=False), 1)
            finally:
                for patcher in reversed(patches):
                    patcher.stop()
            journal = json.loads((root / "journal.json").read_text(encoding="utf-8"))
            dives = json.loads((root / "deepdives.json").read_text(encoding="utf-8"))
            self.assertEqual(len(journal), 1)
            self.assertEqual(len(dives), 1)
            self.assertEqual(journal[0]["deepdive_id"], "close-r24b-001")
            self.assertEqual(dives[0]["coach_loop_lesson"]["role"], "observation_lens_only")
            self.assertEqual(sum("Gesloten leerlus" in message for message in sent), 1)

    def test_health_exposes_r24b_without_secrets(self):
        import main
        data = main.app.test_client().get("/health").get_json()
        self.assertEqual(data["automation_release"], "R24A-TELEGRAM-DAYSTART")
        self.assertEqual(data["coach_loop_release"], "R24B-POST-TRADE-COACH-LOOP")
        status = data["post_trade_coach_loop"]
        self.assertTrue(status["outgoing_only"])
        self.assertNotIn("token", json.dumps(status).lower())
        self.assertNotIn("chat_id", json.dumps(status).lower())

    def test_module_has_no_incoming_telegram_or_new_polling_worker(self):
        source = Path(loopmod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("getUpdates", source)
        self.assertNotIn("webhook", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("Thread(", source)
        self.assertNotIn("time.sleep", source)


if __name__ == "__main__":
    unittest.main()
