import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_TELEGRAM_DAY_START", "0")

import main
from day_start_coach import build_bilingual_day_start
from telegram_day_start import TelegramDayStartScheduler, compact_day_start_message, parse_send_time


def real_overview(*, fresh=True, price=150.0, position=None):
    trends = {"1D": "down", "4H": "range", "15M": "down", "3M": "up"}
    layers = []
    confirmed = {}
    for timeframe in ("1D", "4H", "15M", "3M"):
        layers.append({
            "timeframe": timeframe,
            "present": True,
            "synced": True,
            "confirmed": True,
            "fresh": fresh,
            "review_fresh": fresh,
            "trend": trends[timeframe],
            "age_hours": 0.25 if fresh else 100.0,
        })
        zones = []
        if timeframe == "4H":
            zones = [
                {"id": "support", "role": "support", "bottom": 110, "top": 120},
                {"id": "resistance", "role": "resistance", "bottom": 180, "top": 190},
            ]
        confirmed[timeframe] = {"trend": trends[timeframe], "range_low": 100, "range_high": 200, "zones": zones}
    return {
        "ok": True,
        "latest": {"price_status": {"ok": True, "stale": False, "price": price}, "execution_gate": {"status": "WAIT_3M_TRIGGER"}},
        "stack_health": {"capture_complete": True, "fresh": fresh, "layers": layers},
        "market_map": {"range_low": 100, "range_high": 200, "layers": confirmed},
        "composite_map": {"range_low": 100, "range_high": 200, "layers": confirmed},
        "account": {"positions": [position] if position else []},
        "journal": {
            "trades": [
                {"closed_at": "2026-07-20T10:00:00Z", "pnl": -8, "process_grade": "B", "notes": "midrange"},
                {"closed_at": "2026-07-20T12:00:00Z", "pnl": -5, "process_grade": "C", "notes": "midrange"},
            ],
            "stats": {},
        },
        "lifecycles": {"records": {}},
    }


def day_start_payload(*, fresh=True, position=None):
    result = build_bilingual_day_start(real_overview(fresh=fresh, position=position))
    return {**result, "coach_release": "R23-AUTO-LESSONS", "automation_release": "R24A-TELEGRAM-DAYSTART"}


class TelegramDayStartR24ATests(unittest.TestCase):
    def test_compact_message_uses_real_five_section_payload(self):
        message = compact_day_start_message(day_start_payload(), "nl")
        for marker in ("1. Waar staan we", "2. Scenario's", "3. Het geen-trade-scenario", "4. Jouw procesfocus vandaag", "5. De drie dagstart-toetsvragen"):
            self.assertIn(marker, message)
        self.assertIn("ALS ", message)
        self.assertIn("DAN ", message)
        self.assertIn("Scenario ≠ trade", message)
        self.assertNotRegex(message.lower(), r"https?://|dossier\s*\d|youtube")
        self.assertLessEqual(len(message), 3900)

    def test_open_position_management_precedes_five_sections(self):
        message = compact_day_start_message(day_start_payload(position={"symbol": "BTCUSDT", "side": "Buy", "pnl": 20}), "nl")
        self.assertLess(message.index("Eerst je lopende positie"), message.index("1. Waar staan we"))
        self.assertIn("TP1 verandert niets", message)
        self.assertIn("pas na TP2", message)

    def test_stale_map_sends_only_required_notice(self):
        message = compact_day_start_message(day_start_payload(fresh=False), "nl")
        self.assertEqual(message, "Je kaart is verouderd — lees eerst je charts.")
        self.assertNotIn("Scenario", message)

    def test_scheduler_is_disabled_by_default_and_sends_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            sent = []
            scheduler = TelegramDayStartScheduler(lambda: day_start_payload(), lambda text: sent.append(text) or True, Path(folder), enabled=False)
            self.assertFalse(scheduler.run_due(datetime(2026, 7, 21, 6, 0, tzinfo=timezone.utc)))
            self.assertEqual(sent, [])
            self.assertEqual(scheduler.status()["last_result"], "disabled")

    def test_due_delivery_is_once_per_amsterdam_day_even_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            sent = []
            now = datetime(2026, 7, 21, 6, 0, tzinfo=timezone.utc)  # 08:00 Europe/Amsterdam
            first = TelegramDayStartScheduler(
                lambda: day_start_payload(), lambda text: sent.append(text) or True, Path(folder),
                enabled=True, send_time="08:00", timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertTrue(first.run_due(now))
            self.assertEqual(len(sent), 1)
            second = TelegramDayStartScheduler(
                lambda: day_start_payload(), lambda text: sent.append(text) or True, Path(folder),
                enabled=True, send_time="08:00", timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertFalse(second.run_due(datetime(2026, 7, 21, 6, 5, tzinfo=timezone.utc)))
            self.assertEqual(len(sent), 1)
            self.assertEqual(second.status()["last_sent_local_date"], "2026-07-21")

    def test_failed_send_releases_claim_for_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            scheduler = TelegramDayStartScheduler(
                lambda: day_start_payload(), lambda text: calls.append(text) and False, Path(folder),
                enabled=True, send_time="08:00", timezone_name="Europe/Amsterdam", telegram_configured=True,
            )
            self.assertFalse(scheduler.run_due(datetime(2026, 7, 21, 6, 0, tzinfo=timezone.utc)))
            self.assertIsNone(scheduler.status()["delivery_claim_local_date"])
            self.assertEqual(scheduler.status()["last_result"], "error")

    def test_main_payload_is_shared_by_http_and_scheduler(self):
        overview = real_overview()
        with patch.object(main, "overview_payload", return_value=overview), patch.object(main, "knowledge_feed", return_value=[]):
            payload = main.build_day_start_payload(None)
        self.assertEqual(payload["automation_release"], "R24A-TELEGRAM-DAYSTART")
        self.assertFalse(payload["blocked"])
        self.assertIn("nl", payload["briefings"])
        self.assertIn("en", payload["briefings"])

    def test_health_exposes_gate_without_secrets(self):
        response = main.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["automation_release"], "R24A-TELEGRAM-DAYSTART")
        self.assertIn("telegram_day_start", data)
        self.assertNotIn("token", str(data["telegram_day_start"]).lower())
        self.assertNotIn("chat_id", str(data["telegram_day_start"]).lower())

    def test_no_incoming_telegram_command_surface_exists(self):
        root = Path(__file__).parent
        text = "\n".join((root / name).read_text(encoding="utf-8") for name in ("main.py", "core_services.py", "telegram_day_start.py"))
        self.assertNotIn("getUpdates", text)
        self.assertNotIn("setWebhook", text)
        self.assertNotRegex(text, r"@app\.(?:get|post)\([^\n]*telegram")

    def test_schedule_time_validation(self):
        self.assertEqual(parse_send_time("08:05").hour, 8)
        with self.assertRaises(ValueError):
            parse_send_time("25:00")


if __name__ == "__main__":
    unittest.main()
