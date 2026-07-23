from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_R_BREACH_TELEGRAM", "0")

import account_guards as guards
try:
    import core_services as services
    import main
except ModuleNotFoundError:
    services = None
    main = None

TOKEN = {"X-MyTradingBot-Token": os.environ["MYTRADINGBOT_API_TOKEN"]}
NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)  # noon Amsterdam


def trade(pnl: float, *, at="2026-07-22T09:00:00+00:00", trade_id="t1"):
    return {"id": trade_id, "pnl": pnl, "closed_at": at, "source_class": "BYBIT_VERIFIED", "performance_eligible": True}


class AccountGuardsR25BTests(unittest.TestCase):
    def test_commitment_is_one_way_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            first = guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=2, max_loss_limit_pct=2, now=NOW)
            self.assertTrue(first["active"])
            with self.assertRaisesRegex(ValueError, "alleen strenger"):
                guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=2.5, max_loss_limit_pct=3, now=NOW)
            tighter = guards.activate_commitment(path, equity=12000, requested_loss_limit_pct=1, max_loss_limit_pct=2, now=NOW)
            self.assertEqual(tighter["daily_loss_limit_pct"], 1)
            self.assertEqual(tighter["baseline_equity"], 10000)

    def test_later_win_never_restores_consumed_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=2, max_loss_limit_pct=2, now=NOW)
            loss = guards.build_account_guard_snapshot(path, [trade(-120)], [], 9880, now=NOW)
            recovered = guards.build_account_guard_snapshot(path, [trade(-120), trade(120, at="2026-07-22T09:30:00+00:00", trade_id="t2")], [], 10000, now=NOW)
            self.assertEqual(loss["buffer_remaining_usdt"], 80)
            self.assertEqual(recovered["buffer_remaining_usdt"], 80)
            self.assertTrue(recovered["one_way"])

    def test_day_stop_and_max_one_position_are_hard_cockpit_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=1, max_loss_limit_pct=2, now=NOW)
            stopped = guards.build_account_guard_snapshot(path, [trade(-101)], [], 9899, now=NOW)
            self.assertTrue(stopped["day_stop"])
            self.assertEqual(stopped["gate_status"], "COMMITMENT_DAY_STOP")
            position = guards.build_account_guard_snapshot(path, [], [{"size": 0.1, "pnl": 0}], 10000, now=NOW)
            self.assertTrue(position["position_block"])
            self.assertTrue(position["ticket_blocked"])

    def test_stop_out_cooldown_is_monotonic_and_only_hard_when_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            guards.record_stop_out(path, event_id="sl-1", symbol="BTCUSDT", occurred_at=NOW, cooldown_minutes=30)
            advisory = guards.build_account_guard_snapshot(path, [], [], 10000, now=NOW + timedelta(minutes=5))
            self.assertTrue(advisory["cooldown_active"])
            self.assertFalse(advisory["ticket_blocked"])
            guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=2, max_loss_limit_pct=2, now=NOW)
            hard = guards.build_account_guard_snapshot(path, [], [], 10000, now=NOW + timedelta(minutes=5))
            self.assertTrue(hard["ticket_blocked"])
            self.assertEqual(hard["gate_status"], "REVENGE_COOLDOWN")
            duplicate = guards.record_stop_out(path, event_id="sl-1", symbol="BTCUSDT", occurred_at=NOW + timedelta(minutes=20), cooldown_minutes=60)
            self.assertFalse(duplicate["new_event"])
            guards.record_stop_out(path, event_id="sl-2", symbol="BTCUSDT", occurred_at=NOW + timedelta(minutes=10), cooldown_minutes=10)
            state = guards.load_state(path)
            self.assertEqual(state["days"]["2026-07-22"]["cooldown_until"], (NOW + timedelta(minutes=30)).isoformat())

    def test_next_amsterdam_day_starts_uncommitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            guards.activate_commitment(path, equity=10000, requested_loss_limit_pct=1, max_loss_limit_pct=2, now=NOW)
            tomorrow = guards.build_account_guard_snapshot(path, [], [], 10000, now=NOW + timedelta(days=1))
            self.assertFalse(tomorrow["active"])
            self.assertFalse(tomorrow["ticket_blocked"])

    def test_r_breach_claim_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guards.json"
            self.assertTrue(guards.claim_r_breach(path, trade_id="close-1", r_multiple=-1.2, occurred_at=NOW))
            self.assertFalse(guards.claim_r_breach(path, trade_id="close-1", r_multiple=-1.2, occurred_at=NOW))
            self.assertFalse(guards.claim_r_breach(path, trade_id="close-2", r_multiple=-0.99, occurred_at=NOW))

    @unittest.skipIf(services is None, "projectdependencies ontbreken")
    def test_real_close_persists_planned_r_and_alarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "journal.json"
            reset = Path(tmp) / "reset.json"
            row = {"orderId":"close-r", "symbol":"BTCUSDT", "side":"Sell", "closedPnl":"-125", "avgEntryPrice":"64000", "avgExitPrice":"63500", "qty":"0.1", "updatedTime":"1784707200000"}
            with mock.patch.object(services, "JOURNAL", journal), mock.patch.object(services, "JOURNAL_RESET", reset), mock.patch.object(
                services, "get_equity", return_value=10000
            ), mock.patch.object(services, "_recent_ticket_activity", return_value={"risk_usd":100, "ticket_verified":True}):
                self.assertTrue(services.log_closed_trade(row))
            saved = json.loads(journal.read_text(encoding="utf-8"))[0]
            self.assertEqual(saved["planned_risk_usd"], 100)
            self.assertEqual(saved["r_multiple"], -1.25)
            self.assertTrue(saved["r_breach_alarm"])

    @unittest.skipIf(services is None, "projectdependencies ontbreken")
    def test_stop_execution_reuses_existing_watcher_event(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(services, "ACCOUNT_GUARD_STATE", Path(tmp) / "guards.json"), mock.patch.object(
            services, "telegram", return_value=True
        ), mock.patch.object(services, "_execution_kind", return_value="sl"), mock.patch.object(services, "_clear_tp_progress"):
            event = services.notify_execution({"execId":"sl-event", "symbol":"BTCUSDT", "side":"Sell", "execQty":"0.1", "execPrice":"63000"})
            self.assertEqual(event["kind"], "sl")
            self.assertTrue(event["revenge_cooldown_until"])

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken")
    def test_commitment_api_has_no_off_or_loosen_route(self):
        client = main.app.test_client()
        self.assertEqual(client.post("/api/v1/commitment/activate", json={}).status_code, 401)
        account = {"equity":10000, "equity_fresh":True, "positions":[]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(main, "workspace_file", return_value=Path(tmp) / "guards.json"), mock.patch.object(
            main, "account_payload", return_value=account
        ), mock.patch.object(main, "journal_bundle", return_value=([], [], {})), mock.patch.object(main, "append_activity"):
            first = client.post("/api/v1/commitment/activate", headers=TOKEN, json={"daily_loss_limit_pct":2})
            self.assertEqual(first.status_code, 200)
            off = client.post("/api/v1/commitment/activate", headers=TOKEN, json={"active":False})
            self.assertEqual(off.status_code, 409)
            wider = client.post("/api/v1/commitment/activate", headers=TOKEN, json={"daily_loss_limit_pct":3})
            self.assertEqual(wider.status_code, 409)

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken")
    def test_guard_can_only_turn_entry_ready_into_blocked(self):
        latest = {"execution_gate":{"status":"ENTRY_READY", "orderable":True, "reason":"ready"}, "state_id":"base"}
        guard = {"ticket_blocked":True, "gate_status":"COMMITMENT_DAY_STOP", "reason":"stop", "buffer_remaining_usdt":0, "cooldown_until":None}
        main.apply_account_guard(latest, guard)
        self.assertFalse(latest["execution_gate"]["orderable"])
        self.assertEqual(latest["execution_gate"]["underlying_status"], "ENTRY_READY")
        unblocked = {"execution_gate":{"status":"NO_TRADE", "orderable":False}, "state_id":"x"}
        main.apply_account_guard(unblocked, {"ticket_blocked":False, "gate_status":"COMMITMENT_OFF"})
        self.assertEqual(unblocked["execution_gate"]["status"], "NO_TRADE")

    def test_trading_engine_files_do_not_import_account_guards(self):
        root = Path(__file__).parent
        for name in ("timeframe_stack.py", "chart_sync.py", "trade_lifecycle.py", "beta_access.py"):
            self.assertNotIn("account_guards", (root / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
