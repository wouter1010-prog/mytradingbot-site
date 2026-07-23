from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("MYTRADINGBOT_API_TOKEN", "test-token-with-at-least-thirty-two-characters")
os.environ.setdefault("MYTRADINGBOT_TEST_MODE", "1")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM", "0")

import journal_pattern_gates as gates
try:
    import main
except ModuleNotFoundError:
    main = None

TOKEN = {"X-MyTradingBot-Token": os.environ["MYTRADINGBOT_API_TOKEN"]}
NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


def closed_trade(index: int, *, pnl: float = -80.0, relation: str = "COUNTERTREND_HTF_REACTION", grade: str = "B"):
    return {
        "id": f"bybit-close-{index}",
        "_id": f"bybit-close-{index}",
        "source": "BYBIT-CLOSED-PNL",
        "source_class": "BYBIT_VERIFIED",
        "performance_eligible": True,
        "test_data": False,
        "record_kind": "BYBIT_CLOSE_RECORD",
        "symbol": "BTCUSDT",
        "direction": "long",
        "pnl": pnl,
        "closed_at": f"2026-07-{10+index:02d}T09:30:00+00:00",
        "trade_type": "day",
        "setup_type": "reversal",
        "trigger_type": "local_reversal",
        "relation_to_context": relation,
        "setup_grade": "A",
        "process_grade": grade,
    }


def matching_latest(*, orderable=True, status="ENTRY_READY"):
    return {
        "state_id": "engine-state",
        "setup": {
            "direction": "long",
            "trade_type": "day",
            "trigger_type": "local_reversal",
            "relation_to_context": "COUNTERTREND_HTF_REACTION",
            "grade": "A",
            "setup_15m": {"type": "reversal"},
        },
        "execution_gate": {"status": status, "label": "READY", "orderable": orderable, "reason": "engine reason"},
    }


class JournalPatternGatesR25CTests(unittest.TestCase):
    def test_detection_creates_only_text_suggestion_never_rule(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            result = gates.refresh_suggestions(path, rows, [], now=NOW, min_repetitions=4, min_loss_rate=.65)
            state = gates.load_state(path)
        self.assertEqual(len(result["created"]), 1, "identiek bewijs mag niet als vijf duplicaatsuggesties verschijnen")
        suggestion = result["created"][0]
        self.assertEqual(suggestion["status"], "open")
        self.assertEqual(suggestion["proposed_rule"]["effect"], "orderable_true_to_false_only")
        self.assertEqual(state["rules"], {})
        self.assertFalse(any(row["event"] == "rule_activated" for row in state["audit"]))

    def test_real_deepdive_grade_drives_pattern_when_journal_ticket_was_a(self):
        rows = [closed_trade(i, grade="B") for i in range(1, 5)]
        for row in rows:
            row.pop("process_grade", None)
        deepdives = [
            {
                "_id": row["_id"],
                "proces_grade": "B",
                "oordeel": "De tegen-trendreactie was onvoldoende bevestigd.",
                "wat_kan_beter": "Wacht op de lokale kanteling.",
                "les": "Behandel dit als observatie, niet als zelfstandig signaal.",
            }
            for row in rows
        ]
        patterns = gates.detect_patterns(rows, deepdives, min_repetitions=4, min_loss_rate=.65)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["grade"], "B")
        self.assertEqual(patterns[0]["evidence_trade_ids"], [f"bybit-close-{i}" for i in range(1, 5)])

    def test_process_grade_overrides_orderable_setup_grade_a(self):
        rows = [closed_trade(i, grade="B") for i in range(1, 5)]
        self.assertTrue(all(row["setup_grade"] == "A" for row in rows))
        patterns = gates.detect_patterns(rows, [], min_repetitions=4, min_loss_rate=.65)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["grade"], "B")
        self.assertEqual(patterns[0]["dimension"], "relation_to_context")

    def test_insufficient_sample_and_weak_loss_rate_create_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            too_small = gates.refresh_suggestions(path, [closed_trade(i) for i in range(1, 4)], [], now=NOW, min_repetitions=4)
            self.assertEqual(too_small["created"], [])
            mixed = [closed_trade(i, pnl=-50 if i <= 4 else 50) for i in range(1, 9)]
            too_weak = gates.refresh_suggestions(path, mixed, [], now=NOW, min_repetitions=4, min_loss_rate=.65)
            self.assertEqual(too_weak["created"], [])

    def test_owner_activation_is_explicit_and_rule_only_blocks(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            before = matching_latest()
            gates.apply_active_rules(before, [])
            self.assertTrue(before["execution_gate"]["orderable"])
            rule = gates.activate_suggestion(path, suggestion["id"], actor="Wouter", now=NOW)
            after = matching_latest()
            gates.apply_active_rules(after, [rule])
        self.assertFalse(after["execution_gate"]["orderable"])
        self.assertEqual(after["execution_gate"]["status"], "JOURNAL_PATTERN_BLOCK")
        self.assertEqual(after["execution_gate"]["underlying_status"], "ENTRY_READY")
        self.assertEqual(rule["effect"], "orderable_true_to_false_only")
        self.assertEqual(rule["evidence_grade"], "B")
        self.assertNotIn("setup_grade", rule["criteria"], "bewijsgrade mag een orderbaar A-ticket niet buiten de regel laten vallen")

    def test_rule_never_opens_or_rewrites_an_existing_block(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            rule = gates.activate_suggestion(path, suggestion["id"], now=NOW)
            latest = matching_latest(orderable=False, status="NO_TRADE")
            gates.apply_active_rules(latest, [rule])
        self.assertFalse(latest["execution_gate"]["orderable"])
        self.assertEqual(latest["execution_gate"]["status"], "NO_TRADE")
        self.assertEqual(len(latest["execution_gate"]["additional_blockers"]), 1)

    def test_deactivation_requires_confirmation_reason_and_is_audited(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            rule = gates.activate_suggestion(path, suggestion["id"], actor="Wouter", now=NOW)
            with self.assertRaisesRegex(ValueError, "Bevestiging"):
                gates.deactivate_rule(path, rule["id"], actor="Wouter", reason="Bewuste wijziging", confirmed=False, now=NOW)
            with self.assertRaisesRegex(ValueError, "minimaal 10"):
                gates.deactivate_rule(path, rule["id"], actor="Wouter", reason="kort", confirmed=True, now=NOW)
            deactivated = gates.deactivate_rule(path, rule["id"], actor="Wouter", reason="Ik wil dit patroon opnieuw handmatig evalueren", confirmed=True, now=NOW)
            state = gates.load_state(path)
        self.assertFalse(deactivated["active"])
        audit = [row for row in state["audit"] if row["event"] == "rule_deactivated"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["actor"], "Wouter")
        self.assertIn("handmatig evalueren", audit[0]["reason"])

    def test_suggestions_expire_but_active_rules_do_not(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            first = gates.refresh_suggestions(path, rows, [], now=NOW, ttl_days=1)["created"][0]
            gates.refresh_suggestions(path, rows, [], now=NOW + timedelta(days=2), ttl_days=1)
            expired = gates.load_state(path)["suggestions"][first["id"]]
            self.assertEqual(expired["status"], "expired")

            # New evidence can produce a new suggestion; once activated, time never expires the rule.
            rows.append(closed_trade(5))
            second = gates.refresh_suggestions(path, rows, [], now=NOW + timedelta(days=2), ttl_days=1)["created"][0]
            rule = gates.activate_suggestion(path, second["id"], now=NOW + timedelta(days=2))
            gates.refresh_suggestions(path, rows, [], now=NOW + timedelta(days=50), ttl_days=1)
            persisted = gates.load_state(path)["rules"][rule["id"]]
        self.assertTrue(persisted["active"])
        self.assertIsNone(persisted["deactivated_at"])

    def test_telegram_is_off_by_default_and_has_no_backlog_retry(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        sent = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            created = gates.refresh_suggestions(path, rows, [], now=NOW)["created"]
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM": "0"}):
                self.assertEqual(gates.notify_created_suggestions(path, created, lambda message: sent.append(message) or True), 0)
            with mock.patch.dict(os.environ, {"MYTRADINGBOT_ENABLE_PATTERN_SUGGESTION_TELEGRAM": "1"}):
                self.assertEqual(gates.notify_created_suggestions(path, created, lambda message: False), 0)
                self.assertEqual(gates.notify_created_suggestions(path, created, lambda message: sent.append(message) or True), 0)
        self.assertEqual(sent, [])

    def test_unrelated_ticket_does_not_match_active_rule(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            rule = gates.activate_suggestion(path, suggestion["id"], now=NOW)
            latest = matching_latest()
            latest["setup"]["relation_to_context"] = "WITH_TREND"
            gates.apply_active_rules(latest, [rule])
        self.assertTrue(latest["execution_gate"]["orderable"])
        self.assertEqual(latest["journal_pattern_gate"]["matched_count"], 0)

    @unittest.skipIf(main is None, "Flask-projectdependencies ontbreken")
    def test_owner_endpoints_reject_automatic_or_silent_changes(self):
        client = main.app.test_client()
        self.assertEqual(client.post("/api/v1/pattern-gates/activate", json={"suggestion_id": "x"}).status_code, 401)
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            with mock.patch.object(main, "workspace_file", return_value=path), mock.patch.object(main, "journal_bundle", return_value=(rows, [], {})), mock.patch.object(main, "append_activity"):
                activated = client.post("/api/v1/pattern-gates/activate", headers=TOKEN, json={"suggestion_id": suggestion["id"]})
                self.assertEqual(activated.status_code, 200)
                rule_id = activated.get_json()["rule"]["id"]
                silent = client.post("/api/v1/pattern-gates/deactivate", headers=TOKEN, json={"rule_id": rule_id, "reason": "Ik wil dit bewust evalueren"})
                self.assertEqual(silent.status_code, 409)
                confirmed = client.post("/api/v1/pattern-gates/deactivate", headers=TOKEN, json={"rule_id": rule_id, "reason": "Ik wil dit bewust opnieuw evalueren", "confirm": "DEACTIVEER REGEL"})
                self.assertEqual(confirmed.status_code, 200)
        self.assertFalse(confirmed.get_json()["rule"]["active"])

    def test_tampered_permissive_suggestion_is_rejected_without_rule(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            state = gates.load_state(path)
            state["suggestions"][suggestion["id"]]["proposed_rule"]["effect"] = "orderable_false_to_true"
            gates.save_state(path, state)
            with self.assertRaisesRegex(ValueError, "Onveilige"):
                gates.activate_suggestion(path, suggestion["id"], actor="attacker", now=NOW)
            after = gates.load_state(path)
        self.assertEqual(after["rules"], {})
        self.assertEqual(after["suggestions"][suggestion["id"]]["status"], "open")

    def test_deactivated_rule_cannot_be_silently_changed_twice(self):
        rows = [closed_trade(i) for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pattern.json"
            suggestion = gates.refresh_suggestions(path, rows, [], now=NOW)["created"][0]
            rule = gates.activate_suggestion(path, suggestion["id"], actor="Wouter", now=NOW)
            first = gates.deactivate_rule(
                path, rule["id"], actor="Wouter",
                reason="Bewuste evaluatie na nieuwe dagboekdata", confirmed=True, now=NOW,
            )
            with self.assertRaisesRegex(ValueError, "al uitgeschakeld"):
                gates.deactivate_rule(
                    path, rule["id"], actor="system",
                    reason="Stille automatische wijziging", confirmed=True, now=NOW + timedelta(minutes=1),
                )
            state = gates.load_state(path)
        self.assertFalse(first["active"])
        self.assertEqual(len([row for row in state["audit"] if row["event"] == "rule_deactivated"]), 1)
        self.assertEqual(state["rules"][rule["id"]]["deactivated_by"], "Wouter")

    def test_no_auto_activation_route_or_permissive_effect_exists(self):
        root = Path(__file__).parent
        main_source = (root / "main.py").read_text(encoding="utf-8")
        module_source = (root / "journal_pattern_gates.py").read_text(encoding="utf-8")
        self.assertNotIn("def auto_activate", module_source)
        self.assertNotIn("orderable_false_to_true", module_source)
        self.assertNotIn("pattern-gates/override", main_source)
        self.assertNotIn("pattern-gates/relax", main_source)
        self.assertIn('effect": "orderable_true_to_false_only"', module_source)


if __name__ == "__main__":
    unittest.main()
