from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

# core_services imports feedparser at module load. The R25C integration under
# test does not use RSS, so a narrow import stub keeps this regression runnable
# without changing production code or pretending to test the RSS client.
if "feedparser" not in sys.modules:
    sys.modules["feedparser"] = types.SimpleNamespace(parse=lambda *_a, **_k: types.SimpleNamespace(entries=[], bozo=False))

os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM", "0")

import core_services as services
import journal_pattern_gates as gates


def close_row(index: int) -> dict:
    return {
        "orderId": f"order-{index}",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "closedPnl": "-80.0",
        "avgEntryPrice": "64000",
        "avgExitPrice": "63600",
        "qty": "0.01",
        "closedSize": "0.01",
        "fillCount": "1",
        "updatedTime": str(1784712600000 + index * 60000),
    }


class Phase5CCoreIntegrationTests(unittest.TestCase):
    def _configure_paths(self, root: Path) -> None:
        services.DATA_DIR = root
        services.JOURNAL = root / "journal.json"
        services.JOURNAL_RESET = root / "journal_reset.json"
        services.DEEPDIVES = root / "deepdives.json"
        services.JOURNAL_PATTERN_GATE_STATE = root / "journal_pattern_gates_r25c.json"
        services.ACCOUNT_GUARD_STATE = root / "account_guards_r25b.json"
        services.TP_PROGRESS = root / "tp_progress_v7.json"
        services.JOURNAL.write_text("[]", encoding="utf-8")
        services.DEEPDIVES.write_text("[]", encoding="utf-8")

    @staticmethod
    def _risk_context(_row: dict) -> dict:
        return {
            "planned_risk_usd": 100.0,
            "r_multiple": -0.8,
            "r_breach_alarm": False,
            "activity": {
                "risk_pct": 1.0,
                "stop_loss": 63200.0,
                "trade_type": "day",
                "timeframe": "3M",
                "setup_type": "reversal",
                "trigger_type": "local_reversal",
                "relation_to_context": "COUNTERTREND_HTF_REACTION",
                "setup_grade": "A",
            },
        }

    @staticmethod
    def _analysis(_row: dict) -> dict:
        return {
            "uitkomst": "verlies",
            "proces_grade": "B",
            "oordeel": "De tegen-trendreactie werd te vroeg uitgevoerd.",
            "wat_ging_goed": "De vooraf bepaalde risicogrootte bleef staan.",
            "wat_kan_beter": "Wacht op de lokale kanteling.",
            "les": "Gebruik tegen-trend alleen als observatielens tot de lokale kanteling bevestigd is.",
            "source_label": "POST-TRADE-COACH",
        }

    def test_existing_close_event_creates_suggestion_but_never_rule(self):
        sent: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._configure_paths(root)
            with mock.patch.object(services, "get_equity", return_value=10000.0), \
                 mock.patch.object(services, "_planned_risk_context", side_effect=self._risk_context), \
                 mock.patch.object(services, "analyze_closed_trade", side_effect=self._analysis), \
                 mock.patch.object(services, "queue_post_trade_coach_loop", return_value=False), \
                 mock.patch.object(services, "flush_post_trade_coach_loop"), \
                 mock.patch.object(services, "telegram", side_effect=lambda message: sent.append(message) or True):
                inserted = services.process_closed_pnl_rows([close_row(i) for i in range(1, 5)], first_cycle=False)
            state = gates.load_state(services.JOURNAL_PATTERN_GATE_STATE)
            journal = json.loads(services.JOURNAL.read_text(encoding="utf-8"))
            deepdives = json.loads(services.DEEPDIVES.read_text(encoding="utf-8"))
        self.assertEqual(inserted, 4)
        self.assertEqual(len(journal), 4)
        self.assertTrue(all(row["setup_grade"] == "A" for row in journal))
        self.assertTrue(all(row["proces_grade"] == "B" for row in journal))
        self.assertEqual(len(deepdives), 4)
        self.assertEqual(len([row for row in state["suggestions"].values() if row.get("status") == "open"]), 1)
        self.assertEqual(state["rules"], {}, "het bestaande close-event mag nooit zelf een poortregel activeren")

    def test_first_watcher_cycle_creates_no_suggestion_or_telegram_backlog(self):
        sent: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._configure_paths(root)
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM": "1"}), \
                 mock.patch.object(services, "get_equity", return_value=10000.0), \
                 mock.patch.object(services, "_planned_risk_context", side_effect=self._risk_context), \
                 mock.patch.object(services, "analyze_closed_trade", side_effect=self._analysis), \
                 mock.patch.object(services, "telegram", side_effect=lambda message: sent.append(message) or True):
                inserted = services.process_closed_pnl_rows([close_row(i) for i in range(1, 5)], first_cycle=True)
            state = gates.load_state(services.JOURNAL_PATTERN_GATE_STATE)
        self.assertEqual(inserted, 4)
        self.assertEqual(state["suggestions"], {})
        self.assertEqual(state["rules"], {})
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
