import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import g

os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "abcdefghijklmnopqrstuvwxyz1234567890")

import main  # noqa: E402


class PerformanceHotfixTests(unittest.TestCase):
    def test_journal_rows_show_position_direction_not_bybit_close_side(self):
        rows = [
            {"_id": "long-1", "symbol": "BTCUSDT", "side": "Sell", "entry": "64000", "exit": "64500", "pnl": 120, "equity_snapshot": 20000, "time": "2026-07-16T10:00:00+00:00"},
            {"_id": "short-1", "symbol": "BTCUSDT", "side": "Buy", "entry": "65000", "exit": "64800", "pnl": 80, "equity_snapshot": 20000, "time": "2026-07-16T11:00:00+00:00"},
        ]
        deepdives = [{"_id": "long-1", "proces_grade": "A", "les": "Wachtte netjes op de hertest."}]
        normalized = main.normalise_journal_rows(rows, deepdives)
        self.assertEqual(normalized[0]["direction"], "long")
        self.assertEqual(normalized[1]["direction"], "short")
        self.assertEqual(normalized[0]["process_grade"], "A")
        self.assertAlmostEqual(normalized[0]["pnl_pct"], 0.6)

    def test_stats_expose_dashboard_aliases(self):
        stats = main.normalise_journal_stats({"trades": 3, "wins": 2, "losses": 1, "winrate": 66.67, "profit_factor": 2.4, "snapshot_coverage": 67})
        self.assertEqual(stats["trades"], 3)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["snapshot_coverage_pct"], 67)
        self.assertEqual(stats["winrate_display"], "2/3 · 67%")


    def test_incomplete_snapshots_hide_full_percentage_metrics(self):
        rows = [
            {"_id":"a","source":"BYBIT-CLOSED-PNL","pnl":100,"equity_snapshot":10000,"pnl_pct":1.0,"closed_at":"2026-07-01T10:00:00+00:00"},
            {"_id":"b","source":"BYBIT-CLOSED-PNL","pnl":-50,"equity_snapshot":10050,"pnl_pct":-0.4975,"closed_at":"2026-07-02T10:00:00+00:00"},
            {"_id":"c","source":"BYBIT-CLOSED-PNL","pnl":75,"closed_at":"2026-07-03T10:00:00+00:00"},
            {"_id":"d","source":"BYBIT-CLOSED-PNL","pnl":25,"closed_at":"2026-07-04T10:00:00+00:00"},
        ]
        stats = main.services.compute_journal_stats(rows)
        self.assertEqual(stats["snapshot_coverage"], 50.0)
        self.assertIsNone(stats["total_pnl_pct"])
        self.assertIsNone(stats["expectancy_pct"])
        self.assertIsNone(stats["avg_win_pct"])
        self.assertIsNone(stats["avg_loss_pct"])
        self.assertIsNone(stats["max_drawdown_pct"])
        self.assertIn("2 van 4", stats["percentage_metrics_reason"])

    def test_average_percentages_use_only_available_percentage_records(self):
        rows = [
            {"source":"BYBIT-CLOSED-PNL","pnl":100,"equity_snapshot":10000,"pnl_pct":1.0,"closed_at":"2026-07-01T10:00:00+00:00"},
            {"source":"BYBIT-CLOSED-PNL","pnl":50,"closed_at":"2026-07-02T10:00:00+00:00"},
            {"source":"BYBIT-CLOSED-PNL","pnl":25,"closed_at":"2026-07-03T10:00:00+00:00"},
        ]
        stats = main.services.compute_journal_stats(rows)
        self.assertEqual(stats["partial_avg_win_pct"], 1.0)
        self.assertIsNone(stats["avg_win_pct"])

    def test_curve_never_imputes_missing_percentage_as_zero(self):
        rows = [
            {"pnl":100,"pnl_pct":1.0,"closed_at":"2026-07-01T10:00:00+00:00"},
            {"pnl":50,"pnl_pct":None,"closed_at":"2026-07-02T10:00:00+00:00"},
        ]
        curve = main.journal_curve(rows)
        self.assertEqual(curve[0]["pnl_pct"], 1.0)
        self.assertIsNone(curve[1]["pnl_pct"])
        self.assertFalse(curve[1]["percentage_observed"])

    def test_paper_and_test_rows_are_excluded_from_owner_performance(self):
        rows = [
            {"source":"BYBIT-CLOSED-PNL","pnl":100,"closed_at":"2026-07-01T10:00:00+00:00"},
            {"source":"PAPER","pnl":9999,"closed_at":"2026-07-02T10:00:00+00:00"},
            {"source":"TESTDATA","test_data":True,"pnl":9999,"closed_at":"2026-07-03T10:00:00+00:00"},
        ]
        stats = main.services.compute_journal_stats(rows)
        self.assertEqual(stats["records"], 1)
        self.assertEqual(stats["total_pnl"], 100.0)
        self.assertEqual(stats["excluded_simulated"], 2)

    def test_current_price_uses_fresh_tradingview_capture_without_public_network(self):
        now = datetime.now(timezone.utc)
        drafts = {
            "assets": {
                "BTC": {
                    "layers": {
                        "1D": {"at": (now - timedelta(minutes=2)).isoformat(), "chart_context": {"current_price": 63800}},
                        "3M": {"at": now.isoformat(), "chart_context": {"current_price": 63972.7}},
                    }
                }
            }
        }
        with patch.object(main, "market_prices", side_effect=AssertionError("public network should not be called")), patch.object(main, "load_chart_drafts", return_value=drafts):
            state = main.current_price_status("BTC", {"positions": []})
            self.assertEqual(state["price"], 63972.7)
            self.assertEqual(state["source"], "TradingView laatste opname")
            self.assertFalse(state["stale"])

    def test_tester_without_capture_fails_fast_without_public_network(self):
        with main.app.test_request_context("/api/v2/overview"):
            g.principal = {"workspace_id": "tester-fast", "display_name": "Tester", "role": "tester", "mode": "tester", "capabilities": []}
            with patch.object(main, "market_prices", side_effect=AssertionError("tester must not call public ticker")), patch.object(main, "load_chart_drafts", return_value={"assets": {}}):
                state = main.current_price_status("BTC", {"positions": []})
                self.assertFalse(state["ok"])
                self.assertIn("Synchroniseer", state["reason"])

    def test_direction_mismatch_is_marked_not_silently_presented(self):
        rows = [{"_id":"bad-direction","source":"BYBIT-CLOSED-PNL","symbol":"BTCUSDT","direction":"long","entry":64000,"exit":64500,"pnl":-50,"closed_at":"2026-07-02T10:00:00+00:00"}]
        trade = main.normalise_journal_rows(rows)[0]
        self.assertEqual(trade["direction_consistency"], "mismatch")
        self.assertFalse(trade["direction_verified"])
        self.assertIn("handmatig", trade["direction_consistency_reason"])


if __name__ == "__main__":
    unittest.main()
