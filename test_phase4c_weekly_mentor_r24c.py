from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_WEEKLY_MENTOR", "0")

try:
    import main
except ModuleNotFoundError:
    main = None
import weekly_mentor as weekly

NOW = datetime(2026, 7, 26, 16, 0, tzinfo=timezone.utc)  # Sunday 18:00 Amsterdam

REAL_JOURNAL = [
    {
        "id": "close-001", "closed_at": "2026-07-21T10:00:00+00:00", "symbol": "BTCUSDT",
        "pnl": -18.0, "process_grade": "C", "rules_followed": False,
        "notes": "Te vroeg gehandeld in midrange; bevestiging niet afgewacht.",
    },
    {
        "id": "close-002", "closed_at": "2026-07-23T13:00:00+00:00", "symbol": "BTCUSDT",
        "pnl": 24.0, "process_grade": "B", "rules_followed": True,
        "notes": "Midrange vermeden en proces vastgelegd.",
    },
    {
        "id": "close-003", "closed_at": "2026-07-25T15:00:00+00:00", "symbol": "ETHUSDT",
        "pnl": 12.0, "process_grade": "A", "rules_followed": True,
        "notes": "Geduldig gebleven.",
    },
]

REAL_DEEPDIVES = [
    {
        "_id": "close-001", "time": "2026-07-21T10:05:00+00:00", "proces_grade": "C",
        "wat_ging_goed": "Je noteerde eerlijk dat de bevestiging ontbrak.",
        "wat_kan_beter": "Vermijd midrange en wacht tot je procescontrole compleet is.",
        "les": "Beoordeel gedrag vóór uitkomst.",
    },
    {
        "_id": "close-002", "time": "2026-07-23T13:05:00+00:00", "proces_grade": "B",
        "wat_ging_goed": "Je volgde het afgesproken proces en schreef de review af.",
        "wat_kan_beter": "Blijf dezelfde rustige voorbereiding herhalen.",
        "les": "Herhaalbaar gedrag telt zwaarder dan één resultaat.",
    },
]

REAL_KNOWLEDGE = [
    {
        "id": "discipline-repeatable-process",
        "title": "Herhaalbaar gedrag",
        "summary": "Kies één procesgedrag, herhaal het bewust en beoordeel na afloop alleen of je dat gedrag hebt uitgevoerd.",
        "type": "discipline",
        "tags": ["journal", "proces", "discipline", "reflectie"],
        "source_label": "PRODUCTMETHODIEK",
        "official_status": "official",
        "confidence": 100,
        "source_url": "https://example.invalid/should-never-appear",
    }
]


class WeeklyMentorR24CTests(unittest.TestCase):
    def test_real_journal_builds_three_strengths_pattern_and_one_safe_lesson(self):
        report = weekly.build_weekly_mentor_report(REAL_JOURNAL, REAL_DEEPDIVES, REAL_KNOWLEDGE, now=NOW, language="nl")
        self.assertEqual(len(report["strengths"]), 3)
        self.assertEqual(report["trade_count"], 3)
        self.assertIn("midrange", report["pattern"].lower())
        self.assertEqual(report["lesson"]["lesson_id"], "discipline-repeatable-process")
        self.assertEqual(report["lesson"]["role"], "observation_lens_only")
        serialized = json.dumps(report, ensure_ascii=False).lower()
        self.assertNotIn("http", serialized)
        self.assertNotIn("source_url", serialized)
        self.assertIn("nooit een setup", report["safety"].lower())


    def test_external_source_title_is_never_shown_as_the_lesson_title(self):
        knowledge = [{
            "id": "external-process-lesson",
            "title": "Vincent Platinum Livestream Episode 42",
            "source_title": "Vincent Platinum Livestream Episode 42",
            "summary": "Volgens video 42: kies één procesgedrag en controleer dat na afloop. https://example.invalid/source",
            "type": "discipline",
            "tags": ["journal", "proces", "discipline"],
            "confidence": 90,
        }]
        report = weekly.build_weekly_mentor_report(REAL_JOURNAL, REAL_DEEPDIVES, knowledge, now=NOW, language="nl")
        serialized = json.dumps(report["lesson"], ensure_ascii=False).lower()
        self.assertNotIn("vincent", serialized)
        self.assertNotIn("platinum", serialized)
        self.assertNotIn("livestream", serialized)
        self.assertNotIn("http", serialized)
        self.assertEqual(report["lesson"]["title"], "Procesles")

    def test_bilingual_report_and_telegram_format_have_fixed_structure(self):
        payload = weekly.build_bilingual_weekly_mentor_report(REAL_JOURNAL, REAL_DEEPDIVES, REAL_KNOWLEDGE, now=NOW)
        self.assertEqual(set(payload["reports"]), {"nl", "en"})
        nl = weekly.format_weekly_mentor_message(payload, "nl")
        en = weekly.format_weekly_mentor_message(payload, "en")
        for marker in ("3 sterke punten", "1 patroon uit je dagboek", "1 les"):
            self.assertIn(marker, nl)
        for marker in ("3 strengths", "1 journal pattern", "1 lesson"):
            self.assertIn(marker, en)
        self.assertNotRegex((nl + en).lower(), r"https?://|\[(?:bron|source)?\s*\d+\]")
        self.assertLessEqual(len(nl), 3900)

    def test_scheduler_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            sent = []
            scheduler = weekly.WeeklyMentorScheduler(
                lambda: weekly.build_bilingual_weekly_mentor_report([], [], [], now=NOW),
                lambda text: sent.append(text) or True,
                Path(tmp), telegram_configured=True,
            )
            self.assertFalse(scheduler.enabled)
            self.assertFalse(scheduler.run_due(NOW))
            self.assertEqual(sent, [])
            self.assertEqual(scheduler.status()["last_result"], "disabled")

    def test_due_once_per_iso_week_claims_before_network_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sent = []
            def sender(message: str) -> bool:
                state = json.loads((root / "weekly_mentor_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["delivery_claim_week"], "2026-W30")
                sent.append(message)
                return True
            first = weekly.WeeklyMentorScheduler(
                lambda: weekly.build_bilingual_weekly_mentor_report(REAL_JOURNAL, REAL_DEEPDIVES, REAL_KNOWLEDGE, now=NOW),
                sender, root, enabled=True, weekday="sunday", send_time="18:00",
                timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertTrue(first.run_due(NOW))
            self.assertEqual(len(sent), 1)
            second = weekly.WeeklyMentorScheduler(
                lambda: {}, sender, root, enabled=True, weekday="sunday", send_time="18:00",
                timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertFalse(second.run_due(datetime(2026, 7, 26, 16, 10, tzinfo=timezone.utc)))
            self.assertEqual(second.status()["last_sent_week"], "2026-W30")
            self.assertIsNotNone(second.status()["latest_report"])
            self.assertEqual(len(sent), 1)

    def test_amsterdam_winter_time_uses_real_timezone_rules(self):
        winter = datetime(2026, 1, 4, 17, 0, tzinfo=timezone.utc)  # Sunday 18:00 CET
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            scheduler = weekly.WeeklyMentorScheduler(
                lambda: weekly.build_bilingual_weekly_mentor_report([], [], [], now=winter),
                lambda message: sent.append(message) or True, Path(tmp), enabled=True, weekday="sunday", send_time="18:00",
                timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertTrue(scheduler.run_due(winter))
            self.assertEqual(scheduler.status()["last_sent_week"], "2026-W01")
            self.assertEqual(len(sent), 1)

    def test_no_backfill_outside_configured_day_or_grace_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = weekly.WeeklyMentorScheduler(
                lambda: {}, lambda _: True, Path(tmp), enabled=True, weekday="sunday", send_time="18:00",
                timezone_name="Europe/Amsterdam", telegram_configured=True, grace_minutes=30,
            )
            self.assertFalse(scheduler.run_due(datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)))  # Monday
            self.assertFalse(scheduler.run_due(datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)))  # 19:00, outside grace
            self.assertIsNone(scheduler.status()["last_sent_week"])

    def test_failed_send_releases_week_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = weekly.WeeklyMentorScheduler(
                lambda: weekly.build_bilingual_weekly_mentor_report([], [], [], now=NOW),
                lambda _: False, Path(tmp), enabled=True, weekday=6, send_time="18:00",
                timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertFalse(scheduler.run_due(NOW))
            self.assertIsNone(scheduler.status()["delivery_claim_week"])
            self.assertEqual(scheduler.status()["last_result"], "error")

    @unittest.skipIf(main is None, "project dependencies unavailable in this sandbox")
    def test_main_builder_uses_existing_journal_and_knowledge_read_only(self):
        with mock.patch.object(main, "journal_bundle", return_value=(REAL_JOURNAL, REAL_DEEPDIVES, {})), \
             mock.patch.object(main, "knowledge_feed", return_value=REAL_KNOWLEDGE):
            payload = main.build_weekly_mentor_payload()
        self.assertEqual(payload["weekly_mentor_release"], "R24C-WEEKLY-MENTOR")
        self.assertEqual(payload["reports"]["nl"]["trade_count"], 3)

    @unittest.skipIf(main is None, "project dependencies unavailable in this sandbox")
    def test_health_exposes_release_and_safe_status_only(self):
        data = main.app.test_client().get("/health").get_json()
        self.assertEqual(data["weekly_mentor_release"], "R24C-WEEKLY-MENTOR")
        self.assertIn("weekly_mentor", data)
        serialized = json.dumps(data["weekly_mentor"]).lower()
        self.assertNotIn("token", serialized)
        self.assertNotIn("chat_id", serialized)
        self.assertTrue(data["weekly_mentor"]["outgoing_only"])

    def test_module_has_no_market_polling_or_incoming_telegram_surface(self):
        source = Path(weekly.__file__).read_text(encoding="utf-8")
        self.assertNotIn("getUpdates", source)
        self.assertNotIn("setWebhook", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("bybit", source.lower())
        self.assertNotRegex(source, r"@app\.(?:get|post)")

    def test_schedule_validation(self):
        self.assertEqual(weekly.parse_weekday("zondag"), 6)
        self.assertEqual(weekly.parse_weekday("0"), 0)
        self.assertEqual(weekly.parse_send_time("18:05").minute, 5)
        with self.assertRaises(ValueError):
            weekly.parse_weekday("neverday")
        with self.assertRaises(ValueError):
            weekly.parse_send_time("25:00")


if __name__ == "__main__":
    unittest.main()
