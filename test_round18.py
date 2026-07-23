import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")

import main
from coach_dossiers import sanitise_coach_answer, select_dossiers
from day_start_coach import (
    briefing_has_price_advice,
    build_bilingual_day_start,
    build_day_start_context,
    day_start_dossier_numbers,
)
from knowledge_retrieval import prompt_lessons


def overview(*, price=150.0, low=100.0, high=200.0, fresh=True, position=None, trades=None, lifecycle_stage=None):
    layers = []
    confirmed = {}
    trends = {"1D": "down", "4H": "range", "15M": "down", "3M": "up"}
    for tf in ("1D", "4H", "15M", "3M"):
        layers.append({
            "timeframe": tf,
            "present": True,
            "synced": True,
            "confirmed": True,
            "fresh": fresh,
            "review_fresh": fresh,
            "trend": trends[tf],
            "age_hours": 0.4 if fresh else 100.0,
        })
        zones = []
        if tf == "4H":
            zones = [
                {"id": "support", "role": "support", "bottom": 110, "top": 120},
                {"id": "resistance", "role": "resistance", "bottom": 180, "top": 190},
            ]
        confirmed[tf] = {"trend": trends[tf], "range_low": low, "range_high": high, "zones": zones}
    records = {}
    if lifecycle_stage and position:
        records["active"] = {"symbol": position["symbol"], "stage": lifecycle_stage}
    return {
        "ok": True,
        "state_id": "state-1",
        "latest": {"price_status": {"ok": True, "stale": False, "price": price}, "execution_gate": {"status": "WAIT_3M_TRIGGER"}},
        "stack_health": {"capture_complete": True, "fresh": fresh, "layers": layers},
        "market_map": {"range_low": low, "range_high": high, "layers": confirmed},
        "composite_map": {"range_low": low, "range_high": high, "layers": confirmed},
        "account": {"positions": [position] if position else []},
        "journal": {"trades": trades or [], "stats": {}},
        "lifecycles": {"records": records},
    }


class Round18Tests(unittest.TestCase):
    def test_complete_fresh_map_has_five_sections_and_safe_scenarios(self):
        result = build_bilingual_day_start(overview(), now=datetime(2026, 7, 20, 6, 0, tzinfo=timezone.utc))
        briefing = result["briefings"]["nl"]
        self.assertFalse(briefing["blocked"])
        self.assertEqual([row["key"] for row in briefing["sections"]], [
            "where_we_are", "scenarios", "no_trade", "process_focus", "checklist"
        ])
        scenarios = next(row for row in briefing["sections"] if row["key"] == "scenarios")["items"]
        self.assertLessEqual(len(scenarios), 3)
        self.assertTrue(all(item["if"].startswith("ALS ") and item["then"].startswith("DAN ") for item in scenarios))
        self.assertFalse(briefing_has_price_advice(briefing))
        self.assertNotRegex(str(briefing).lower(), r"https?://|dossier\s*\d|\[\d+\]")

    def test_midrange_makes_no_trade_prominent(self):
        briefing = build_bilingual_day_start(overview(price=150))["briefings"]["nl"]
        no_trade = next(row for row in briefing["sections"] if row["key"] == "no_trade")
        self.assertTrue(no_trade["prominent"])
        self.assertIn("midden", no_trade["body"])
        self.assertIn("proceswinst", no_trade["body"])

    def test_stale_map_refuses_scenarios(self):
        result = build_bilingual_day_start(overview(fresh=False))
        self.assertTrue(result["blocked"])
        self.assertTrue(result["briefings"]["nl"]["blocked"])
        self.assertEqual(result["briefings"]["nl"]["sections"], [])
        self.assertIn("Vernieuw", result["briefings"]["nl"]["title"])

    def test_open_position_management_is_first_and_tp_rule_is_correct(self):
        position = {"symbol": "BTCUSDT", "side": "Buy", "pnl": 20}
        briefing = build_bilingual_day_start(overview(position=position, lifecycle_stage="SCALP_ACTIVE"))["briefings"]["nl"]
        self.assertEqual(briefing["sections"][0]["key"], "position_management")
        text = briefing["sections"][0]["body"]
        self.assertIn("TP1 verandert niets", text)
        self.assertIn("pas na TP2", text)
        self.assertIn("in winst", text)

    def test_losing_streak_is_woven_into_process_focus(self):
        trades = [
            {"closed_at": "2026-07-18T10:00:00Z", "pnl": 5},
            {"closed_at": "2026-07-18T11:00:00Z", "pnl": -2},
            {"closed_at": "2026-07-18T12:00:00Z", "pnl": -3},
        ]
        context = build_day_start_context(overview(trades=trades))
        self.assertEqual(context["current_loss_streak"], 2)
        self.assertIn("12", day_start_dossier_numbers(context))
        focus = next(row for row in build_bilingual_day_start(overview(trades=trades))["briefings"]["nl"]["sections"] if row["key"] == "process_focus")
        self.assertIn("verliesreeks", focus["body"])
        self.assertIn("Geen revenge", focus["body"])

    def test_video_prompt_payload_structurally_excludes_titles_and_urls(self):
        rows = [{
            "id": "video-1:lesson-1", "title": "Secret title", "source_title": "Doopie video",
            "source_url": "https://youtube.example/watch?v=1", "summary": "Wait for confirmation.",
            "type": "confirmatie", "confidence": 80, "official_status": "interpretation",
        }]
        payload = prompt_lessons(rows)
        self.assertEqual(payload[0]["lesson_id"], "video-1:lesson-1")
        self.assertNotIn("title", payload[0])
        self.assertNotIn("source_title", payload[0])
        self.assertNotIn("source_url", payload[0])
        self.assertNotIn("youtube", str(payload).lower())

    def test_fallback_strips_dossier_cross_references(self):
        answer = sanitise_coach_answer("Wacht op C (zie dossier 07). Zie module 12 voor meer. https://example.com")
        self.assertNotRegex(answer.lower(), r"zie dossier|zie module|https?://")
        self.assertNotIn("07", answer)

    def test_english_stop_hunt_queries_select_liquidity_dossier(self):
        selected = select_dossiers("I got stop hunted again below the low", latest={}, limit=3)
        self.assertIn("10", [row["number"] for row in selected])

    def test_day_start_endpoint_is_read_only_and_bilingual(self):
        client = main.app.test_client()
        payload = overview()
        with patch.object(main, "overview_payload", return_value=payload), patch.object(main, "rate_allowed", return_value=True):
            response = client.post("/api/v1/day-start", json={"asset": "BTC"}, headers={"X-MyTradingBot-Token": main.API_TOKEN})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["coach_release"], "R23-AUTO-LESSONS")
        self.assertIn("nl", data["briefings"])
        self.assertIn("en", data["briefings"])
        self.assertFalse(data["blocked"])


if __name__ == "__main__":
    unittest.main()
