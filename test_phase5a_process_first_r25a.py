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

import discipline_progress as discipline
try:
    import main
except ModuleNotFoundError:
    main = None

TOKEN = {"X-MyTradingBot-Token": os.environ["MYTRADINGBOT_API_TOKEN"]}
NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)  # 12:00 Amsterdam


def trade(day: int, *, grade="A", followed=True, pnl=10.0):
    return {
        "id": f"trade-{day}-{grade}",
        "closed_at": f"2026-07-{day:02d}T10:00:00+00:00",
        "updated_time_ms": datetime(2026, 7, day, 10, 0, tzinfo=timezone.utc).timestamp() * 1000,
        "pnl": pnl,
        "process_grade": grade,
        "rules_followed": followed,
        "source_class": "BYBIT_VERIFIED",
        "performance_eligible": True,
    }


class ProcessFirstR25ATests(unittest.TestCase):
    def test_score_uses_process_only_and_ignores_pnl(self):
        rows = [
            trade(12, grade="C", followed=False, pnl=9000),
            trade(13, grade="B", followed=True, pnl=-5000),
            trade(14, grade="A", followed=True, pnl=-2000),
            trade(15, grade="A", followed=True, pnl=1),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            for day in (19, 20, 21, 22):
                discipline.record_day_start(path, now=datetime(2026, 7, day, 6, 0, tzinfo=timezone.utc))
            first = discipline.build_discipline_snapshot(path, rows, [], now=NOW)
            changed = [dict(row, pnl=-row["pnl"] * 100) for row in rows]
            second = discipline.build_discipline_snapshot(path, changed, [], now=NOW)
        self.assertEqual(first["score"], second["score"])
        self.assertEqual(first["rules"]["pct"], 75.0)
        self.assertEqual(first["grades"]["count"], 4)
        self.assertTrue(first["read_only_to_trading_engine"])

    def test_day_start_or_conscious_no_trade_extends_streak(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            discipline.record_day_start(path, now=datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc))
            discipline.record_no_trade(path, [], [], now=datetime(2026, 7, 21, 17, 0, tzinfo=timezone.utc))
            discipline.record_day_start(path, now=NOW)
            snapshot = discipline.build_discipline_snapshot(path, [], [], now=NOW)
        self.assertEqual(snapshot["streak"]["current"], 3)
        self.assertTrue(snapshot["streak"]["today_complete"])
        self.assertTrue(snapshot["streak"]["earned_by_day_start"])
        self.assertEqual(snapshot["streak"]["status"], "earned_today")

    def test_incomplete_today_keeps_yesterday_streak_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            for day in (19, 20, 21):
                discipline.record_day_start(path, now=datetime(2026, 7, day, 6, 0, tzinfo=timezone.utc))
            snapshot = discipline.build_discipline_snapshot(path, [], [], now=NOW)
        self.assertEqual(snapshot["streak"]["current"], 3)
        self.assertFalse(snapshot["streak"]["today_complete"])
        self.assertEqual(snapshot["streak"]["status"], "available_today")

    def test_missed_day_uses_earn_back_not_shame(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            discipline.record_day_start(path, now=datetime(2026, 7, 19, 6, 0, tzinfo=timezone.utc))
            snapshot = discipline.build_discipline_snapshot(path, [], [], now=NOW)
        self.assertEqual(snapshot["streak"]["current"], 0)
        self.assertEqual(snapshot["streak"]["status"], "earn_back")
        self.assertEqual(snapshot["score_band"], "earn_back")

    def test_no_trade_is_blocked_for_open_position_or_trade_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            with self.assertRaisesRegex(ValueError, "positie openstaat"):
                discipline.record_no_trade(path, [], [{"size": 0.1}], now=NOW)
            with self.assertRaisesRegex(ValueError, "handelsactiviteit"):
                discipline.record_no_trade(path, [trade(22)], [], now=NOW)

    def test_later_trade_invalidates_no_trade_mark_but_not_day_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            discipline.record_no_trade(path, [], [], now=NOW)
            invalid = discipline.build_discipline_snapshot(path, [trade(22)], [], now=NOW)
            discipline.record_day_start(path, now=NOW)
            valid = discipline.build_discipline_snapshot(path, [trade(22)], [], now=NOW)
        self.assertFalse(invalid["streak"]["today_complete"])
        self.assertTrue(invalid["today"]["no_trade_invalidated"])
        self.assertTrue(valid["streak"]["today_complete"])
        self.assertTrue(valid["streak"]["earned_by_day_start"])

    def test_process_grade_trend_is_based_on_chronological_real_rows(self):
        rows = [trade(day, grade=grade, followed=True) for day, grade in zip(range(12, 22), ["C","C","B","B","B","A","A","A","A","A"])]
        rows.append({**trade(22), "source_class": "TESTDATA", "test_data": True, "process_grade": "C", "rules_followed": False})
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = discipline.build_discipline_snapshot(Path(tmp) / "discipline.json", rows, [], now=NOW)
        self.assertEqual(snapshot["grades"]["trend"], "improving")
        self.assertEqual(snapshot["grades"]["count"], 10)
        self.assertEqual(snapshot["rules"]["count"], 10)

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken in deze sandbox")
    def test_day_start_api_marks_only_successful_unblocked_briefing(self):
        client = main.app.test_client()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            with mock.patch.object(main, "workspace_file", return_value=path), mock.patch.object(
                main, "build_day_start_payload", return_value={"ok": True, "blocked": False, "briefings": {"nl": {}, "en": {}}}
            ):
                response = client.post("/api/v1/day-start", headers=TOKEN, json={"asset": "BTC"})
            self.assertEqual(response.status_code, 200)
            state = discipline.load_state(path)
            self.assertEqual(len(state["days"]), 1)

            path.unlink()
            with mock.patch.object(main, "workspace_file", return_value=path), mock.patch.object(
                main, "build_day_start_payload", return_value={"ok": True, "blocked": True, "briefings": {"nl": {}, "en": {}}}
            ):
                response = client.post("/api/v1/day-start", headers=TOKEN, json={"asset": "BTC"})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(path.exists())

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken in deze sandbox")
    def test_no_trade_endpoint_is_authenticated_and_returns_snapshot(self):
        client = main.app.test_client()
        self.assertEqual(client.post("/api/v1/discipline/no-trade").status_code, 401)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discipline.json"
            with mock.patch.object(main, "workspace_file", return_value=path), mock.patch.object(
                main, "journal_bundle", return_value=([], [], {})
            ), mock.patch.object(main, "account_payload", return_value={"positions": []}), mock.patch.object(main, "append_activity"):
                response = client.post("/api/v1/discipline/no-trade", headers=TOKEN, json={})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["discipline"]["streak"]["today_complete"])
        self.assertTrue(payload["discipline"]["streak"]["earned_by_no_trade"])

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken in deze sandbox")
    def test_overview_exposes_discipline_without_changing_execution_gate(self):
        journal = [trade(20, grade="A", followed=True)]
        account = {"positions": [], "equity": 10000}
        latest = {"execution_gate": {"status": "NO_TRADE", "orderable": False}, "state_id": "same", "state_generated_at": "2026-07-22T10:00:00Z"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(main, "workspace_file", return_value=Path(tmp) / "discipline.json"), mock.patch.object(
            main, "account_payload", return_value=account
        ), mock.patch.object(main, "decision_payload", return_value=latest), mock.patch.object(
            main, "journal_bundle", return_value=(journal, [], {})
        ), mock.patch.object(main, "load_market_stack", return_value=main.empty_stack()), mock.patch.object(
            main, "load_chart_drafts", return_value=main.empty_stack()
        ), mock.patch.object(main, "public_stack", side_effect=lambda value: value), mock.patch.object(
            main, "public_drafts", side_effect=lambda value: value
        ), mock.patch.object(main, "build_composite_map", return_value={}), mock.patch.object(
            main, "build_stack_health", return_value={}
        ), mock.patch.object(main, "knowledge_feed", return_value=[]), mock.patch.object(main, "knowledge_source_status", return_value={}), mock.patch.object(
            main.services, "ingestion_events", return_value=[]
        ), mock.patch.object(main, "load_methodology_sources", return_value={}), mock.patch.object(main, "load_activity_log", return_value=[]), mock.patch.object(
            main, "load_lifecycles", return_value={}
        ), mock.patch.object(main, "commercialization_status", return_value={}):
            payload = main.overview_payload("BTC")
        self.assertEqual(payload["latest"]["execution_gate"], latest["execution_gate"])
        self.assertEqual(payload["discipline"]["release"], "R25A-PROCESS-FIRST")
        self.assertTrue(payload["discipline"]["read_only_to_trading_engine"])

    def test_no_trading_engine_imports_discipline_module(self):
        root = Path(__file__).parent
        for name in ("timeframe_stack.py", "chart_sync.py", "trade_lifecycle.py", "beta_access.py"):
            self.assertNotIn("discipline_progress", (root / name).read_text(encoding="utf-8"))

    def test_process_first_dom_and_pnl_collapse_are_present(self):
        root = Path(__file__).parent
        html = (root / "mytradingbot-dashboard.html").read_text(encoding="utf-8")
        js = (root / "dashboard.js").read_text(encoding="utf-8")
        css = (root / "dashboard.css").read_text(encoding="utf-8")
        for element_id in ("disciplineScore", "disciplineStreak", "disciplineRules", "disciplineTrend", "noTradeDayButton", "accountPnlDisclosure"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("function renderDiscipline()", js)
        self.assertIn("/api/v1/discipline/no-trade", js)
        self.assertIn(".discipline-card", css)
        self.assertIn(".pnl-disclosure", css)
        self.assertNotIn("discipline_progress", (root / "dashboard.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
