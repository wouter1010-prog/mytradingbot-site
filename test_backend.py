import base64
import importlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

TEST_TOKEN = "test-token-with-at-least-thirty-two-characters"
TEST_DIR = tempfile.mkdtemp(prefix="mytradingbot-v6-test-")
os.environ["MYTRADINGBOT_API_TOKEN"] = TEST_TOKEN
os.environ["DATA_DIR"] = TEST_DIR
os.environ["DISABLE_BACKGROUND_WORKERS"] = "1"
os.environ["MYTRADINGBOT_TEST_MODE"] = "1"
os.environ.pop("BYBIT_API_KEY", None)
os.environ.pop("BYBIT_API_SECRET", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

main = importlib.import_module("main")
engine = importlib.import_module("timeframe_stack")
lifecycle = importlib.import_module("trade_lifecycle")
charts = importlib.import_module("chart_sync")

main.services.get_prices = lambda assets=None: {"BTC": 100.2, "ETH": 2000.0}
main.market_prices = lambda force=False, asset=None: {"BTC": 100.2, "ETH": 2000.0}
main.services.get_equity = lambda: 1000.0
main.services.get_open_positions = lambda: []
main.services.journal_stats = lambda: {}
main.services.journal_summary = lambda: ""
main.get_instrument = lambda symbol: {
    "symbol": symbol,
    "qty_step": 0.001,
    "min_qty": 0.001,
    "min_notional": 5.0,
    "tick_size": 0.1,
    "min_leverage": 1.0,
    "max_leverage": 100.0,
    "leverage_step": 0.01,
    "source": "test",
}


def zone(zone_id, role, top, bottom, *, tf, intent="structure", invalidation=None, parent=None, reason="handmatig gecontroleerde TradingView-zone"):
    return {
        "id": zone_id,
        "role": role,
        "top": top,
        "bottom": bottom,
        "timeframe": tf,
        "intent": intent,
        "invalidation": invalidation,
        "parent_zone_id": parent,
        "reason": reason,
        "reviewed": True,
        "confirmations": 2,
        "tests": 1,
        "confidence": 95,
    }


def layer_payload(tf, *, trade_type="day", one_d_trend="down", trigger=True, setup=True):
    base = {
        "asset": "BTC",
        "source_timeframe": tf,
        "chart_timeframe": tf,
        "reviewed": True,
        "confirmed": True,
        "trade_type": trade_type,
        "overall_confidence": 95,
    }
    if tf == "1D":
        base.update(
            trend=one_d_trend,
            range_low=85,
            range_high=120,
            zones=[
                zone("d-s", "support", 92, 89, tf="1D", invalidation=87),
                zone("d-r3", "resistance", 114, 112, tf="1D", invalidation=116),
            ],
        )
    elif tf == "4H":
        base.update(
            trend="range",
            range_low=90,
            range_high=120,
            zones=[
                zone("h-s", "support", 100.5, 99.5, tf="4H", invalidation=98.5),
                zone("h-r2", "resistance", 108.5, 108, tf="4H", invalidation=109.5),
            ],
        )
    elif tf == "15M":
        base.update(
            trend="down",
            approach_direction="down",
            setup={
                "detected": bool(setup),
                "type": "reversal" if setup else "none",
                "direction": "long" if setup else "unknown",
                "confidence": 92,
                "evidence": "Dalende benadering in bevestigde 4H-support; lokale reclaim en compressie.",
                "confirmed": bool(setup),
                "reviewed": bool(setup),
            },
            zones=[
                zone("m15-s", "support", 100.25, 99.75, tf="15M", parent="h-s", invalidation=99.2),
                zone("m15-r1", "resistance", 104.5, 104, tf="15M", invalidation=105.2),
            ],
        )
    elif tf == "3M":
        base.update(
            trend="up",
            approach_direction="down",
            trigger={
                "detected": bool(trigger),
                "type": "local_reversal" if trigger else "none",
                "direction": "long" if trigger else "unknown",
                "local_trend_before": "down",
                "approach_direction": "down",
                "price": 100.0 if trigger else None,
                "confidence": 94,
                "evidence": "Lokale downtrend kantelde: creating move gegained en retest hield.",
                "confirmed": bool(trigger),
                "reviewed": bool(trigger),
                "evidence_flags": {
                    "zone_reaction": True,
                    "structure_break": True,
                    "retest": True,
                    "momentum_resume": True,
                },
                "ticket_requested": bool(trigger),
                "entry_zone_id": "m3-e" if trigger else None,
                "stop_loss": 99.4 if trigger else None,
            },
            zones=[
                zone("m3-e", "support", 100.1, 99.9, tf="3M", intent="entry", invalidation=99.4, parent="m15-s"),
                zone("m3-r0", "resistance", 102.5, 102, tf="3M", intent="target", invalidation=103),
            ],
        )
    return base


def build_stack(*, include=("1D", "4H", "15M", "3M"), trade_type="day", trigger=True, setup=True, one_d_trend="down"):
    stack = engine.empty_stack()
    for tf in include:
        layer = engine.normalize_layer(layer_payload(tf, trade_type=trade_type, trigger=trigger, setup=setup, one_d_trend=one_d_trend), strict=True)
        stack = engine.save_layer_in_stack(stack, layer)
    return stack




def build_breakout_stack():
    """Long breakout/retest through 4H resistance with a 15M role-flip support."""
    now = datetime.now(timezone.utc).isoformat()
    payloads = {
        "1D": {
            "asset": "BTC", "source_timeframe": "1D", "reviewed": True, "confirmed": True,
            "trend": "up", "range_low": 80, "range_high": 130, "trade_type": "day",
            "zones": [
                zone("d-base", "support", 95, 92, tf="1D", invalidation=90),
                zone("d-t3", "resistance", 122, 120, tf="1D", invalidation=124),
            ],
        },
        "4H": {
            "asset": "BTC", "source_timeframe": "4H", "reviewed": True, "confirmed": True,
            "trend": "up", "range_low": 90, "range_high": 110, "trade_type": "day",
            "zones": [
                {**zone("h-break", "resistance", 110.5, 109.5, tf="4H", invalidation=111.2), "thesis_state": "invalidated"},
                zone("h-t2", "resistance", 116.5, 116, tf="4H", invalidation=117.2),
            ],
        },
        "15M": {
            "asset": "BTC", "source_timeframe": "15M", "reviewed": True, "confirmed": True,
            "trend": "up", "approach_direction": "up", "trade_type": "day",
            "setup": {
                "detected": True, "confirmed": True, "reviewed": True, "type": "breakout",
                "direction": "long", "confidence": 94,
                "evidence": "4H resistance is gebroken; 15M bouwt een role-flip support en retest."
            },
            "zones": [
                zone("m15-flip", "support", 110.25, 109.85, tf="15M", invalidation=109.3, parent="h-break"),
                zone("m15-t1", "resistance", 113.5, 113, tf="15M", invalidation=114),
            ],
        },
        "3M": {
            "asset": "BTC", "source_timeframe": "3M", "reviewed": True, "confirmed": True,
            "trend": "up", "approach_direction": "up", "trade_type": "day",
            "trigger": {
                "detected": True, "confirmed": True, "reviewed": True, "type": "breakout_retest",
                "direction": "long", "local_trend_before": "up", "price": 110.1, "confidence": 95,
                "evidence": "3M close boven 4H resistance en retest van de role-flip support houdt.",
                "evidence_flags": {"structure_break": True, "close": True, "retest": True, "momentum_resume": True},
                "ticket_requested": True, "entry_zone_id": "m3-break-entry", "stop_loss": 109.7,
            },
            "zones": [
                zone("m3-break-entry", "support", 110.2, 110.0, tf="3M", intent="entry", invalidation=109.7, parent="m15-flip"),
                zone("m3-t0", "resistance", 112.2, 112, tf="3M", intent="target", invalidation=112.7),
            ],
        },
    }
    stack = engine.empty_stack()
    for tf in engine.PRIMARY_TIMEFRAMES:
        payloads[tf]["at"] = now
        layer = engine.normalize_layer(payloads[tf], strict=True)
        stack = engine.save_layer_in_stack(stack, layer)
    return stack


def capture_payload(tf="4H"):
    image = Image.new("RGB", (1200, 800), "#0a0c10")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 500, 1050, 550), fill="#1f8f66")
    draw.rectangle((80, 180, 1050, 230), fill="#a74235")
    buffer = io.BytesIO(); image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "image": "data:image/png;base64," + encoded,
        "context": {
            "symbol": "BYBIT:BTCUSDT.P", "timeframe": tf,
            "page_title": f"BTCUSDT {tf} TradingView", "url": "https://www.tradingview.com/chart/test/",
            "trigger": "test", "viewport": {"width": 1200, "height": 800},
            "chart_rect": {"x": 40, "y": 40, "width": 1080, "height": 700},
        },
    }


def model_result(tf="4H"):
    return {
        "asset": "BTC", "chart_timeframe": tf, "trend": "range", "approach_direction": "down",
        "setup": {"detected": tf == "15M", "type": "reversal" if tf == "15M" else "none", "direction": "long" if tf == "15M" else "unknown", "confidence": 88, "evidence": "local setup" if tf == "15M" else ""},
        "trigger": {
            "detected": tf == "3M", "type": "local_reversal" if tf == "3M" else "none", "direction": "long" if tf == "3M" else "unknown",
            "local_trend_before": "down", "price": 100 if tf == "3M" else 0, "confidence": 87, "evidence": "kanteling" if tf == "3M" else "",
            "evidence_flags": {"structure_break_confirmed": tf == "3M", "close_confirmed": tf == "3M", "retest_confirmed": tf == "3M", "sweep_confirmed": False, "reclaim_confirmed": False, "momentum_shift": tf == "3M", "pullback_confirmed": False, "continuation_confirmed": False},
        },
        "range_low": 90, "range_high": 120, "range_confidence": 85, "overall_confidence": 90,
        "zones": [
            {"top": 100.5, "bottom": 99.5, "role": "support", "color": "turquoise", "label": "support", "timeframe": tf, "intent": "entry" if tf == "3M" else "structure", "reason": "Getekende support", "invalidation": 99 if tf == "3M" else 0, "invalidation_detected": tf == "3M", "confirmations": 2, "tests": 1, "confidence": 94},
            {"top": 105, "bottom": 104, "role": "resistance", "color": "red", "label": "R1", "timeframe": tf, "intent": "target", "reason": "Getekende resistance", "invalidation": 0, "invalidation_detected": False, "confirmations": 0, "tests": 0, "confidence": 91},
        ],
        "warnings": [],
    }


class EngineTests(unittest.TestCase):
    def test_workflow_is_fixed(self):
        self.assertEqual(engine.VERSION, "8.2.2")
        self.assertEqual(engine.PRIMARY_TIMEFRAMES, ("1D", "4H", "15M", "3M"))

    def test_layers_do_not_overwrite_each_other(self):
        stack = build_stack()
        self.assertEqual(set(stack["assets"]["BTC"]["layers"]), {"1D", "4H", "15M", "3M"})
        self.assertEqual(engine.get_layer(stack, "BTC", "4H")["zones"][0]["id"], "h-s")
        self.assertEqual(engine.get_layer(stack, "BTC", "3M")["zones"][0]["id"], "m3-e")

    def test_missing_3m_is_waiting_not_rejection(self):
        decision = engine.build_decision(build_stack(include=("1D", "4H", "15M")), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_SYNC")
        self.assertFalse(decision["execution_gate"]["orderable"])
        self.assertEqual(decision["missing_timeframes"], ["3M"])
        self.assertIn("3M", decision["execution_gate"]["reason"])


    def test_four_successful_drafts_make_map_complete_without_manual_review(self):
        drafts = engine.empty_stack()
        for index, tf in enumerate(engine.PRIMARY_TIMEFRAMES):
            payload = layer_payload(tf)
            payload.update(
                reviewed=False, confirmed=False,
                revision=f"draft-{tf}-{index}", sync_id=f"draft-{tf}-{index}",
                at=datetime.now(timezone.utc).isoformat(),
            )
            if tf == "15M":
                payload["setup"] = {**payload["setup"], "confirmed": False, "reviewed": False}
            if tf == "3M":
                payload["trigger"] = {**payload["trigger"], "confirmed": False, "reviewed": False}
                payload["zones"][0]["reviewed"] = False
            layer = engine.normalize_layer(payload, strict=False)
            drafts = engine.save_layer_in_stack(drafts, layer)

        decision = engine.build_decision(
            engine.empty_stack(), asset="BTC", current_price=100,
            risk_profiles=main.RISK_PROFILES, draft_stack_value=drafts,
        )
        self.assertEqual(decision["execution_gate"]["status"], "REVIEW_STACK")
        self.assertEqual(decision["execution_gate"]["label"], "CONTROLEER 1D")
        self.assertTrue(decision["capture_complete"])
        self.assertFalse(decision["verified_complete"])
        self.assertEqual(decision["synced_count"], 4)
        self.assertEqual(decision["confirmed_count"], 0)
        self.assertEqual(decision["missing_timeframes"], [])
        self.assertEqual(decision["review_timeframes"], ["1D", "4H", "15M", "3M"])
        self.assertFalse(decision["execution_gate"]["orderable"])

    def test_partial_drafts_report_exact_missing_layers(self):
        drafts = engine.empty_stack()
        for tf in ("1D", "4H"):
            payload = layer_payload(tf)
            payload.update(reviewed=False, confirmed=False, revision=f"draft-{tf}", sync_id=f"draft-{tf}")
            drafts = engine.save_layer_in_stack(drafts, engine.normalize_layer(payload, strict=False))
        decision = engine.build_decision(
            engine.empty_stack(), asset="BTC", current_price=100,
            risk_profiles=main.RISK_PROFILES, draft_stack_value=drafts,
        )
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_SYNC")
        self.assertEqual(decision["missing_timeframes"], ["15M", "3M"])
        self.assertEqual(decision["synced_count"], 2)
        self.assertIn("15M, 3M", decision["execution_gate"]["reason"])

    def test_no_trigger_is_waiting_at_htf_zone(self):
        decision = engine.build_decision(build_stack(trigger=False), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_3M_TURN")
        self.assertIn("niet afgekeurd", decision["execution_gate"]["reason"])

    def test_missing_15m_setup_is_waiting_not_rejection(self):
        decision = engine.build_decision(build_stack(setup=False), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_15M_SETUP")
        self.assertFalse(decision["execution_gate"]["orderable"])
        self.assertIn("niets afgekeurd", decision["execution_gate"]["reason"])

    def test_wrong_local_trend_before_blocks_execution_but_keeps_candidate(self):
        stack = build_stack()
        m3 = engine.get_layer(stack, "BTC", "3M")
        m3["trigger"]["local_trend_before"] = "up"
        decision = engine.build_decision(stack, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "ENTRY_CANDIDATE")
        self.assertFalse(decision["execution_gate"]["orderable"])
        self.assertIn("Lokale trendkanteling klopt", decision["execution_gate"]["failed"])

    def test_breakout_retest_through_htf_resistance_can_be_valid(self):
        stack = build_stack()
        h4 = engine.get_layer(stack, "BTC", "4H")
        h4["zones"] = [
            engine.normalize_zone({"id":"h-break","role":"resistance","top":100.5,"bottom":99.5,"invalidation":101.5,"timeframe":"4H","reason":"Bevestigde 4H breakout-locatie","reviewed":True,"confirmations":2,"tests":1}, timeframe="4H", strict=True),
            engine.normalize_zone({"id":"h-t1","role":"resistance","top":104.5,"bottom":104,"invalidation":105.5,"timeframe":"4H","intent":"target","reason":"Eerste target","reviewed":True,"confirmations":2,"tests":1}, timeframe="4H", strict=True),
            engine.normalize_zone({"id":"h-t2","role":"resistance","top":108.5,"bottom":108,"invalidation":109.5,"timeframe":"4H","intent":"target","reason":"Tweede target","reviewed":True,"confirmations":2,"tests":1}, timeframe="4H", strict=True),
        ]
        m15 = engine.get_layer(stack, "BTC", "15M")
        m15["setup"] = engine.normalize_setup({"detected":True,"confirmed":True,"reviewed":True,"type":"breakout","direction":"long","evidence":"15M accepteert boven resistance en bouwt retest"}, timeframe="15M", strict=True)
        m15["zones"] = [engine.normalize_zone({"id":"m15-break","role":"support","top":100.7,"bottom":100.2,"timeframe":"15M","parent_zone_id":"h-break","invalidation":99.9,"reason":"15M breakout-retestzone","reviewed":True,"confirmations":2,"tests":1}, timeframe="15M", strict=True)]
        m3 = engine.get_layer(stack, "BTC", "3M")
        m3["trigger"] = engine.normalize_trigger({"detected":True,"confirmed":True,"reviewed":True,"type":"breakout_retest","direction":"long","local_trend_before":"down","price":100.6,"evidence":"3M close boven level en retest houdt","evidence_flags":{"structure_break":True,"close":True,"retest":True,"momentum_resume":True},"ticket_requested":True,"entry_zone_id":"m3-break-entry","stop_loss":100.1}, timeframe="3M", strict=True)
        m3["zones"] = [engine.normalize_zone({"id":"m3-break-entry","role":"support","top":100.65,"bottom":100.45,"invalidation":100.1,"timeframe":"3M","intent":"entry","parent_zone_id":"m15-break","reason":"3M retest-entry","reviewed":True,"confirmations":2,"tests":1}, timeframe="3M", strict=True)]
        decision = engine.build_decision(stack, asset="BTC", current_price=100.6, risk_profiles=main.RISK_PROFILES)
        self.assertTrue(decision["execution_gate"]["orderable"], decision["execution_gate"])
        self.assertEqual(decision["setup"]["relation_to_context"], "BREAKOUT")

    def test_explicitly_invalidated_htf_parent_blocks_local_reversal(self):
        stack = build_stack()
        engine.get_layer(stack, "BTC", "4H")["zones"][0]["thesis_state"] = "invalidated"
        decision = engine.build_decision(stack, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "SETUP_INVALIDATED")
        self.assertFalse(decision["execution_gate"]["orderable"])

    def test_bullish_3m_reversal_after_down_approach_at_support_is_valid(self):
        decision = engine.build_decision(build_stack(one_d_trend="down"), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertTrue(decision["execution_gate"]["orderable"], decision["execution_gate"])
        self.assertEqual(decision["execution_gate"]["status"], "ENTRY_READY")
        self.assertEqual(decision["setup"]["relation_to_context"], "COUNTERTREND_HTF_REACTION")
        self.assertEqual(decision["setup"]["origin_timeframe"], "3M")
        self.assertTrue(decision["setup"]["risk_locked"])
        self.assertEqual(decision["setup"]["entry"], 100.0)
        self.assertEqual(decision["setup"]["stop_loss"], 99.4)
        self.assertEqual(decision["setup"]["take_profits"][:3], [102.0, 104.0, 108.0])

    def test_risk_profiles_are_selected_by_planned_horizon(self):
        for trade_type, expected in main.RISK_PROFILES.items():
            with self.subTest(trade_type=trade_type):
                decision = engine.build_decision(build_stack(trade_type=trade_type), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
                self.assertEqual(decision["setup"]["risk_pct"], expected)
                self.assertEqual(decision["setup"]["lifecycle"], "SCALP_ORIGIN")

    def test_parent_child_links_are_generated(self):
        stack = build_stack()
        composite = engine.build_composite_map(stack, "BTC")
        links = composite["parent_links"]
        self.assertTrue(any(row["child_zone_id"] == "m15-s" and row["parent_zone_id"] == "h-s" for row in links["15M"]))
        self.assertTrue(any(row["child_zone_id"] == "m3-e" and row["parent_zone_id"] == "m15-s" for row in links["3M"]))


    def test_15m_without_local_setup_stays_on_watch(self):
        decision = engine.build_decision(build_stack(setup=False), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_15M_SETUP")
        self.assertIn("niets afgekeurd", decision["execution_gate"]["reason"])

    def test_wrong_local_trend_classification_blocks_ready_state_but_not_the_location(self):
        stack = build_stack()
        m3 = dict(engine.get_layer(stack, "BTC", "3M"))
        trigger = dict(m3["trigger"]); trigger["local_trend_before"] = "up"; m3["trigger"] = trigger
        stack = engine.save_layer_in_stack(stack, m3)
        decision = engine.build_decision(stack, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(decision["execution_gate"]["status"], "ENTRY_CANDIDATE")
        self.assertFalse(decision["execution_gate"]["orderable"])
        self.assertIn("Lokale trendkanteling klopt", decision["execution_gate"]["failed"])

    def test_breakout_retest_uses_15m_role_flip_invalidation_not_old_resistance_stop(self):
        decision = engine.build_decision(build_breakout_stack(), asset="BTC", current_price=110.1, risk_profiles=main.RISK_PROFILES)
        self.assertTrue(decision["execution_gate"]["orderable"], decision["execution_gate"])
        self.assertEqual(decision["execution_gate"]["status"], "ENTRY_READY")
        self.assertEqual(decision["setup"]["relation_to_context"], "BREAKOUT")
        self.assertEqual(decision["setup"]["htf_thesis_invalidation"], 109.3)
        self.assertEqual(decision["setup"]["stop_loss"], 109.7)
        self.assertEqual(decision["setup"]["take_profits"][:3], [112.0, 113.0, 116.0])

    def test_stack_health_reports_each_required_layer(self):
        health = engine.build_stack_health(build_stack(), "BTC")
        self.assertTrue(health["complete"])
        self.assertTrue(health["fresh"])
        self.assertEqual(health["confirmed_count"], 4)
        self.assertEqual([row["timeframe"] for row in health["layers"]], ["1D", "4H", "15M", "3M"])


    def test_equivalent_resync_keeps_existing_human_review(self):
        confirmed = build_stack()
        draft_stack = engine.empty_stack()
        draft = dict(engine.get_layer(confirmed, "BTC", "1D"))
        draft.update({"confirmed": False, "reviewed": False, "revision": "new-equivalent-capture", "at": "2099-01-01T00:00:00+00:00"})
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, verified, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["1D"], "VERIFIED")
        self.assertTrue(available["1D"].get("review_carried_forward"))
        self.assertEqual(verified["1D"].get("source_sync_id"), "new-equivalent-capture")

    def test_one_of_four_zones_cannot_disappear_without_review(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "1D"))
        layer["zones"] = [
            zone("d-s1", "support", 96000, 95000, tf="1D"),
            zone("d-s2", "support", 90000, 89000, tf="1D"),
            zone("d-r1", "resistance", 104000, 103000, tf="1D"),
            zone("d-r2", "resistance", 110000, 109000, tf="1D"),
        ]
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        draft_stack = engine.empty_stack()
        draft = dict(layer)
        draft.update({"confirmed": False, "reviewed": False, "revision": "zone-removed", "at": datetime.now(timezone.utc).isoformat()})
        draft["zones"] = list(layer["zones"][:-1])
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, _, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["1D"], "SYNCED")
        self.assertIn("zone", available["1D"]["review_reason"])

    def test_one_of_four_zones_cannot_shift_materially_without_review(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "1D"))
        layer["zones"] = [
            zone("d-s1", "support", 96000, 95000, tf="1D"),
            zone("d-s2", "support", 90000, 89000, tf="1D"),
            zone("d-r1", "resistance", 104000, 103000, tf="1D"),
            zone("d-r2", "resistance", 110000, 109000, tf="1D"),
        ]
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        draft_stack = engine.empty_stack()
        draft = dict(layer)
        draft.update({"confirmed": False, "reviewed": False, "revision": "zone-shifted", "at": datetime.now(timezone.utc).isoformat()})
        draft["zones"] = [dict(item) for item in layer["zones"]]
        draft["zones"][0].update(top=99800, bottom=98800)  # +$3,800 on BTC
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, _, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["1D"], "SYNCED")
        self.assertIn("zone", available["1D"]["review_reason"])

    def test_wide_zone_shift_above_one_percent_requires_review(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "4H"))
        layer["zones"] = [zone("h-wide", "support", 101.5, 98.5, tf="4H")]
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        draft_stack = engine.empty_stack()
        draft = dict(layer)
        draft.update({"confirmed": False, "reviewed": False, "revision": "wide-zone-shift-1.2pct", "at": datetime.now(timezone.utc).isoformat()})
        draft["zones"] = [dict(layer["zones"][0], top=102.7, bottom=99.7)]
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, _, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["4H"], "SYNCED")
        self.assertIn("zone", available["4H"]["review_reason"])

    def test_wide_zone_shift_below_one_percent_keeps_review(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "4H"))
        layer["zones"] = [zone("h-wide", "support", 101.5, 98.5, tf="4H")]
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        draft_stack = engine.empty_stack()
        draft = dict(layer)
        draft.update({"confirmed": False, "reviewed": False, "revision": "wide-zone-shift-0.8pct", "at": datetime.now(timezone.utc).isoformat()})
        draft["zones"] = [dict(layer["zones"][0], top=102.3, bottom=99.3)]
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, _, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["4H"], "VERIFIED")
        self.assertTrue(available["4H"].get("review_carried_forward"))

    def test_review_expiry_uses_human_review_time_not_capture_time(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "3M"))
        old_review = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        layer["at"] = datetime.now(timezone.utc).isoformat()
        layer["confirmed_at"] = old_review
        layer["provenance"] = {**(layer.get("provenance") or {}), "reviewed_at": old_review}
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        draft_stack = engine.empty_stack()
        draft = dict(layer)
        draft.update({"confirmed": False, "reviewed": False, "revision": "fresh-equivalent-capture", "at": datetime.now(timezone.utc).isoformat()})
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        available, _, states = engine.resolve_layers(confirmed, draft_stack, "BTC")
        self.assertEqual(states["3M"], "SYNCED")
        self.assertTrue(available["3M"].get("review_expired"))
        self.assertIn("ouder dan 2 uur", available["3M"]["review_reason"])

    def test_review_expiry_applies_even_without_a_new_capture(self):
        confirmed = build_stack()
        layer = dict(engine.get_layer(confirmed, "BTC", "4H"))
        old_review = (datetime.now(timezone.utc) - timedelta(hours=37)).isoformat()
        layer["at"] = datetime.now(timezone.utc).isoformat()
        layer["confirmed_at"] = old_review
        layer["provenance"] = {**(layer.get("provenance") or {}), "reviewed_at": old_review}
        confirmed = engine.save_layer_in_stack(confirmed, layer)
        available, _, states = engine.resolve_layers(confirmed, engine.empty_stack(), "BTC")
        self.assertEqual(states["4H"], "SYNCED")
        self.assertTrue(available["4H"].get("review_expired"))

    def test_only_materially_changed_htf_layer_needs_review(self):
        confirmed = build_stack()
        draft_stack = engine.empty_stack()
        draft = dict(engine.get_layer(confirmed, "BTC", "1D"))
        draft.update({"confirmed": False, "reviewed": False, "revision": "trend-changed", "at": "2099-01-01T00:00:00+00:00", "trend": "up"})
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        decision = engine.build_decision(confirmed, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES, draft_stack_value=draft_stack)
        self.assertEqual(decision["execution_gate"]["status"], "REVIEW_STACK")
        self.assertEqual(decision["execution_gate"]["label"], "CONTROLEER 1D")
        self.assertEqual(decision["blocking_review_timeframes"], ["1D"])
        self.assertEqual(decision["review_timeframes"], ["1D"])

    def test_15m_refresh_without_setup_does_not_force_form(self):
        confirmed = build_stack(setup=True)
        draft_stack = engine.empty_stack()
        draft = dict(engine.get_layer(confirmed, "BTC", "15M"))
        draft.update({"confirmed": False, "reviewed": False, "revision": "15m-no-setup", "at": "2099-01-01T00:00:00+00:00"})
        draft["setup"] = {"detected": False, "type": "none", "direction": "unknown", "confirmed": False, "reviewed": False}
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        decision = engine.build_decision(confirmed, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES, draft_stack_value=draft_stack)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_15M_SETUP")
        self.assertEqual(decision["blocking_review_timeframes"], [])
        self.assertIn("niet handmatig", decision["execution_gate"]["reason"])

    def test_3m_refresh_without_trigger_does_not_force_form(self):
        confirmed = build_stack(trigger=True)
        draft_stack = engine.empty_stack()
        draft = dict(engine.get_layer(confirmed, "BTC", "3M"))
        draft.update({"confirmed": False, "reviewed": False, "revision": "3m-no-trigger", "at": "2099-01-01T00:00:00+00:00"})
        draft["trigger"] = {"detected": False, "type": "none", "direction": "unknown", "confirmed": False, "reviewed": False, "ticket_requested": False}
        draft_stack = engine.save_layer_in_stack(draft_stack, draft)
        decision = engine.build_decision(confirmed, asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES, draft_stack_value=draft_stack)
        self.assertEqual(decision["execution_gate"]["status"], "WAIT_3M_TRIGGER")
        self.assertEqual(decision["blocking_review_timeframes"], [])
        self.assertIn("niet handmatig", decision["execution_gate"]["reason"])

    def test_chart_review_does_not_require_a_stop_until_ticket_is_requested(self):
        payload = layer_payload("3M")
        payload["trigger"]["ticket_requested"] = False
        payload["trigger"]["entry_zone_id"] = None
        payload["trigger"]["stop_loss"] = None
        payload["zones"][0]["invalidation"] = None
        layer = engine.normalize_layer(payload, strict=True)
        self.assertTrue(layer["confirmed"])
        self.assertFalse(layer["trigger"]["ticket_requested"])
        self.assertTrue(all(zone["invalidation"] is None for zone in layer["zones"]))

    def test_ticket_request_requires_one_selected_zone_and_one_stop(self):
        payload = layer_payload("3M")
        payload["trigger"]["stop_loss"] = None
        with self.assertRaisesRegex(ValueError, "technische stop"):
            engine.normalize_layer(payload, strict=True)

    def test_trigger_needs_user_review(self):
        payload = layer_payload("3M")
        payload["trigger"]["confirmed"] = False
        payload["trigger"]["reviewed"] = False
        with self.assertRaisesRegex(ValueError, "controleerd"):
            engine.normalize_layer(payload, strict=True)


class LifecycleTests(unittest.TestCase):
    def test_promotion_never_increases_initial_risk(self):
        setup = engine.build_decision(build_stack(trade_type="day"), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)["setup"]
        record = lifecycle.create_record(setup)
        self.assertEqual(record["stage"], "SCALP_ACTIVE")
        promoted = lifecycle.promote(record, {"tp2_filled": True, "position_in_profit": True, "risk_reduced": True, "stop_not_widened": True, "structure_15m_intact": True, "htf_thesis_active": True}, confirmed_by_user=True)
        self.assertEqual(promoted["stage"], "DAY_RUNNER")
        self.assertLessEqual(promoted["current_risk_pct"], promoted["initial_risk_pct"])
        swing = lifecycle.promote(promoted, {"runner_remaining": True, "stop_not_widened": True, "structure_4h_intact": True, "trend_1d_intact": True, "room_to_next_htf_zone": True}, confirmed_by_user=True)
        self.assertEqual(swing["stage"], "SWING_RUNNER")
        self.assertEqual(swing["initial_risk_pct"], record["initial_risk_pct"])

    def test_promotion_requires_user_confirmation_and_evidence(self):
        record = lifecycle.create_record(engine.build_decision(build_stack(), asset="BTC", current_price=100, risk_profiles=main.RISK_PROFILES)["setup"])
        with self.assertRaisesRegex(ValueError, "expliciet"):
            lifecycle.promote(record, {}, confirmed_by_user=False)
        with self.assertRaisesRegex(ValueError, "mist"):
            lifecycle.promote(record, {}, confirmed_by_user=True)


class BackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.app.config.update(TESTING=True)
        cls.client = main.app.test_client()
        cls.headers = {"X-MyTradingBot-Token": TEST_TOKEN}

    def setUp(self):
        main.RATE_STATE.clear()
        main.PRICE_CACHE.update(at=0, prices={"BTC": 100.0})
        for path in Path(TEST_DIR).glob("*"):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                import shutil; shutil.rmtree(path)

    def post_layer(self, tf, **kwargs):
        return self.client.post("/api/v1/market-map", headers=self.headers, json=layer_payload(tf, **kwargs))

    def test_health_public_private_api_protected(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["workflow"], ["1D", "4H", "15M", "3M"])
        self.assertEqual(self.client.get("/api/v1/config").status_code, 401)
        config = self.client.get("/api/v1/config", headers=self.headers)
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.get_json()["risk_profiles"], {"scalp": 0.5, "day": 1.0, "swing": 2.0})
        legacy_header = self.client.get("/api/v1/config", headers={"X-DoopieCash-Token": TEST_TOKEN})
        self.assertEqual(legacy_header.status_code, 200)
        self.assertFalse(config.get_json()["final_order_click"])
        self.assertNotEqual(config.headers.get("Access-Control-Allow-Origin"), "*")

    def test_api_saves_each_timeframe_independently(self):
        for tf in engine.PRIMARY_TIMEFRAMES:
            response = self.post_layer(tf)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        stack = self.client.get("/api/v1/market-stack", headers=self.headers).get_json()["stack"]
        self.assertEqual(set(stack["assets"]["BTC"]["layers"]), set(engine.PRIMARY_TIMEFRAMES))
        latest = self.client.get("/api/v1/latest", headers=self.headers).get_json()
        self.assertTrue(latest["execution_gate"]["orderable"])
        self.assertEqual(latest["setup"]["origin_timeframe"], "3M")

    def test_chart_sync_draft_is_unconfirmed_and_timeframe_specific(self):
        with patch.object(main, "analyze_with_claude", return_value=model_result("4H")):
            main.services.ANTHROPIC_API_KEY = "test-key"
            response = self.client.post("/api/v1/chart/analyze", headers=self.headers, json=capture_payload("4H"))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        draft = response.get_json()["draft"]
        self.assertEqual(draft["source_timeframe"], "4H")
        self.assertFalse(draft["confirmed"])
        self.assertEqual(self.client.get("/api/v1/chart/draft/BTC/3M", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/chart/draft/BTC/4H", headers=self.headers).status_code, 200)
        self.assertEqual(response.get_json()["stack_health"]["synced_count"], 1)
        self.assertEqual(response.get_json()["latest"]["missing_timeframes"], ["1D", "15M", "3M"])


    def test_syncing_all_four_charts_immediately_completes_capture_stack(self):
        main.services.ANTHROPIC_API_KEY = "test-key"
        for tf in engine.PRIMARY_TIMEFRAMES:
            with patch.object(main, "analyze_with_claude", return_value=model_result(tf)):
                response = self.client.post("/api/v1/chart/analyze", headers=self.headers, json=capture_payload(tf))
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertEqual(payload["draft"]["source_timeframe"], tf)

        latest = self.client.get("/api/v1/latest", headers=self.headers).get_json()
        self.assertEqual(latest["execution_gate"]["status"], "REVIEW_STACK")
        self.assertEqual(latest["execution_gate"]["label"], "CONTROLEER 1D")
        self.assertTrue(latest["capture_complete"])
        self.assertEqual(latest["synced_count"], 4)
        self.assertEqual(latest["missing_timeframes"], [])

        health = self.client.get("/health").get_json()
        self.assertEqual(health["version"], "8.2.2")
        self.assertEqual(health["schema_version"], 86)
        self.assertTrue(health["capture_complete"])
        self.assertEqual(health["synced_timeframes"], 4)

    def test_stale_revision_is_rejected_per_timeframe(self):
        draft = engine.normalize_layer(layer_payload("4H"), strict=False)
        draft.update(revision="new-revision", sync_id="new-revision", source="tradingview-vision", confirmed=False, reviewed=False)
        main.save_chart_draft(draft)
        payload = layer_payload("4H")
        payload["source_sync_id"] = "old-revision"
        response = self.client.post("/api/v1/chart/confirm", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 409)

    def test_lifecycle_api_only_starts_from_entry_ready_3m_setup(self):
        for tf in engine.PRIMARY_TIMEFRAMES:
            self.post_layer(tf)
        response = self.client.post("/api/v1/lifecycle", headers=self.headers, json={"action": "create", "asset": "BTC"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        record = response.get_json()["record"]
        self.assertEqual(record["stage"], "SCALP_ACTIVE")
        self.assertTrue(record["risk_locked"])

    def test_dashboard_assets_and_csp(self):
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"1D", page.data)
        self.assertIn(b"3M", page.data)
        self.assertIn("frame-ancestors 'none'", page.headers.get("Content-Security-Policy", ""))
        self.assertEqual(self.client.get("/assets/dashboard.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/dashboard.css").status_code, 200)

    def test_profit_factor_is_honest_when_no_loss_trade_exists(self):
        rows = [
            {"symbol":"BTCUSDT","side":"Buy","pnl":120.0},
            {"symbol":"BTCUSDT","side":"Sell","pnl":80.0},
        ]
        stats = main.normalise_journal_stats({"trades": 2, "wins": 2, "losses": 0, "profit_factor": None, "profit_factor_infinite": True})
        self.assertIsNone(stats["profit_factor"])
        self.assertTrue(stats["profit_factor_infinite"])
        self.assertIn("onvoldoende", stats["profit_factor_display"].lower())
        self.assertNotIn("999", stats["profit_factor_display"])


class VisionNormalisationTests(unittest.TestCase):
    def test_3m_vision_proposes_but_never_confirms_trigger(self):
        context = capture_payload("3M")["context"]
        draft = charts.normalize_vision_result(model_result("3M"), context=context, image_hash="abc", crop_meta={}, previous={})
        self.assertEqual(draft["source_timeframe"], "3M")
        self.assertTrue(draft["trigger"]["detected"])
        self.assertFalse(draft["trigger"]["confirmed"])
        self.assertFalse(draft["trigger"]["reviewed"])
        self.assertFalse(any(zone["intent"] == "entry" for zone in draft["zones"]))

    def test_non_3m_never_returns_execution_trigger(self):
        context = capture_payload("15M")["context"]
        raw = model_result("15M")
        raw["trigger"]["detected"] = True
        raw["trigger"]["type"] = "local_reversal"
        raw["trigger"]["direction"] = "long"
        draft = charts.normalize_vision_result(raw, context=context, image_hash="abc", crop_meta={}, previous={})
        self.assertFalse(draft["trigger"]["detected"])
        self.assertEqual(draft["trigger"]["type"], "none")



class V7RegressionTests(unittest.TestCase):
    def test_side_check_blocks_marketable_long_limit(self):
        result = engine.build_decision(build_stack(), asset="BTC", current_price=99.8, risk_profiles=main.RISK_PROFILES)
        self.assertFalse(result["execution_gate"]["orderable"])
        self.assertFalse(next(row for row in result["execution_gate"]["checks"] if row["key"] == "price_side")["ok"])

    def test_side_check_allows_long_entry_below_market(self):
        result = engine.build_decision(build_stack(), asset="BTC", current_price=100.2, risk_profiles=main.RISK_PROFILES)
        self.assertTrue(result["execution_gate"]["orderable"], result["execution_gate"])

    def test_break_even_requires_tp2_and_profit(self):
        setup = engine.build_decision(build_stack(), asset="BTC", current_price=100.2, risk_profiles=main.RISK_PROFILES)["setup"]
        record = lifecycle.create_record(setup)
        early = lifecycle.evaluate(record, {"tp1_filled": True, "risk_reduced": True, "stop_not_widened": True, "structure_15m_intact": True, "htf_thesis_active": True})
        self.assertFalse(early["eligible"])
        self.assertIn("tp2_filled", early["missing"])
        good = lifecycle.evaluate(record, {"tp2_filled": True, "position_in_profit": True, "risk_reduced": True, "stop_not_widened": True, "structure_15m_intact": True, "htf_thesis_active": True})
        self.assertTrue(good["eligible"])

    def test_management_policy_has_provenance(self):
        result = engine.build_decision(build_stack(), asset="BTC", current_price=100.2, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(result["setup"]["management_policy"]["break_even_source"], "OPERATORBELEID")
        self.assertEqual(result["setup"]["risk_policy_source"], "OPERATORBELEID")

    def test_warning_normalisation_never_silently_looks_official(self):
        value = charts._normalise_warning("Unmapped English model note")
        self.assertIn("Ruwe visionwaarneming", value)



class V701AuditFixTests(unittest.TestCase):
    def test_rr_below_three_is_hard_no_trade_and_c_grade(self):
        stack = build_stack()
        layers = stack["assets"]["BTC"]["layers"]
        # Keep every resistance target above entry but inside 3R.
        for layer in layers.values():
            for item in layer.get("zones", []):
                if item.get("role") == "resistance":
                    item["bottom"] = 101.0
                    item["top"] = 101.2
        result = engine.build_decision(stack, asset="BTC", current_price=100.2, risk_profiles=main.RISK_PROFILES)
        self.assertFalse(result["execution_gate"]["orderable"])
        self.assertEqual(result["execution_gate"]["status"], "NO_TRADE")
        self.assertEqual(result["setup"]["grade"], "C")
        self.assertFalse(result["setup"]["rr_ok"])
        self.assertIn("3.00R", result["execution_gate"]["reason"])

    def test_target_distribution_is_three_equal_parts_without_fourth_runner(self):
        result = engine.build_decision(build_stack(), asset="BTC", current_price=100.2, risk_profiles=main.RISK_PROFILES)
        self.assertEqual(result["setup"]["target_distribution"], [33.33, 33.33, 33.34])
        self.assertEqual(len(result["setup"]["target_distribution"]), 3)
        self.assertAlmostEqual(sum(result["setup"]["target_distribution"]), 100.0, places=2)

    def test_closed_pnl_writer_is_idempotent_and_independent_from_telegram(self):
        services = main.services
        with tempfile.TemporaryDirectory(prefix="journal-writer-") as folder:
            journal = Path(folder) / "journal.json"
            reset = Path(folder) / "journal_reset.json"
            with patch.object(services, "JOURNAL", journal), patch.object(services, "JOURNAL_RESET", reset), patch.object(services, "get_equity", lambda force=False: 20000.0):
                row = {
                    "orderId": "closed-1", "symbol": "BTCUSDT", "side": "Sell",
                    "avgEntryPrice": "64000", "avgExitPrice": "64500", "qty": "0.1",
                    "closedPnl": "50", "openFee": "1", "closeFee": "1.2",
                    "createdTime": "1780000000000", "updatedTime": "1780000001000",
                }
                self.assertTrue(services.log_closed_trade(row))
                self.assertFalse(services.log_closed_trade(row))
                saved = services._load(journal, [])
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["direction"], "long")
                self.assertEqual(saved[0]["source"], "BYBIT-CLOSED-PNL")
                self.assertAlmostEqual(saved[0]["pnl_pct"], 0.25, places=5)
                self.assertAlmostEqual(saved[0]["fees"], 2.2, places=5)

    def test_tp_notifications_keep_stop_after_tp1_and_allow_be_only_after_tp2_in_profit(self):
        services = main.services
        messages = []
        with tempfile.TemporaryDirectory(prefix="tp-progress-") as folder:
            progress = Path(folder) / "tp.json"
            with patch.object(services, "TP_PROGRESS", progress), patch.object(services, "telegram", lambda text: messages.append(text) or True), patch.object(services, "get_open_positions", lambda force=False: [{"symbol": "BTCUSDT", "pnl": 12.0}]):
                first = {"execId": "e1", "orderId": "tp1-order", "orderLinkId": "trade-tp1", "stopOrderType": "TakeProfit", "symbol": "BTCUSDT", "side": "Sell", "execQty": "0.03", "execPrice": "65000", "positionIdx": 0}
                second = {"execId": "e2", "orderId": "tp2-order", "orderLinkId": "trade-tp2", "stopOrderType": "TakeProfit", "symbol": "BTCUSDT", "side": "Sell", "execQty": "0.03", "execPrice": "65500", "positionIdx": 0}
                event1 = services.notify_execution(first)
                event2 = services.notify_execution(second)
                self.assertEqual(event1["tp_number"], 1)
                self.assertEqual(event2["tp_number"], 2)
                self.assertIn("nog NIET toegestaan", messages[0])
                self.assertIn("handmatig toegestaan", messages[1])
                self.assertTrue(all("automatisch aangepast" in text or "NIET toegestaan" in text for text in messages))

    def test_overview_and_health_expose_account_watcher_status(self):
        health = main.app.test_client().get("/health").get_json()
        self.assertIn("account_watcher", health)
        overview = main.overview_payload("BTC")
        self.assertIn("services", overview)
        self.assertIn("account_watcher", overview["services"])

    def test_startup_backlog_is_seen_without_telegram_spam(self):
        services = main.services
        seen = set()
        rows = [{"execId": "old-1", "symbol": "BTCUSDT", "side": "Buy", "execQty": "0.01", "execPrice": "64000"}]
        with patch.object(services, "notify_execution") as notifier:
            new_rows = services.process_execution_rows(rows, seen, first_cycle=True)
            self.assertEqual(len(new_rows), 1)
            self.assertIn("old-1", seen)
            notifier.assert_not_called()

    def test_position_snapshot_uses_authoritative_position_fields(self):
        positions = [{
            "symbol": "BTCUSDT", "side": "Buy", "size": 0.125, "entry": 64000.0,
            "stop_loss": 63200.0, "take_profit": 66000.0, "leverage": 3.0,
        }]
        services = main.services
        with patch.object(services, "get_open_positions", lambda force=False: positions):
            text = services._position_snapshot_message()
        self.assertIn("LONG 0.125 BTCUSDT @ 64000.0", text)
        self.assertIn("SL 63200.0", text)
        self.assertIn("TP 66000.0", text)
        self.assertIn("3.0x", text)

    def test_partial_fills_are_aggregated_into_one_telegram_event(self):
        services = main.services
        rows = [
            {"execId": "fill-1", "orderId": "order-1", "symbol": "BTCUSDT", "side": "Buy", "execQty": "0.04", "execPrice": "64000"},
            {"execId": "fill-2", "orderId": "order-1", "symbol": "BTCUSDT", "side": "Buy", "execQty": "0.06", "execPrice": "64100"},
        ]
        messages = []
        with tempfile.TemporaryDirectory(prefix="aggregate-fills-") as folder, \
             patch.object(services, "DATA_DIR", Path(folder)), \
             patch.object(services, "MANUAL_ALERTS", Path(folder) / "alerts.json"), \
             patch.object(services, "telegram", lambda text: messages.append(text) or True), \
             patch.object(services, "get_open_positions", lambda force=False: [{"symbol": "BTCUSDT", "side": "Buy", "entry": 64060, "stop_loss": 63800, "take_profit": 65000, "leverage": 3}]):
            seen = set()
            new_rows = services.process_execution_rows(rows, seen, first_cycle=False)
        self.assertEqual(len(new_rows), 2)
        fill_messages = [text for text in messages if "Order gevuld" in text]
        self.assertEqual(len(fill_messages), 1)
        self.assertIn("0.1", fill_messages[0])
        self.assertIn("64060.0", fill_messages[0])
        self.assertIn("2 deelvullingen", fill_messages[0])
        self.assertEqual(sum("Huidige open positie" in text for text in messages), 1)

    def test_manual_position_mirror_is_sent_once_and_never_blocks(self):
        services = main.services
        row = {"execId": "manual-fill-1", "orderId": "manual-order-1", "symbol": "BTCUSDT", "side": "Buy", "execQty": "0.1", "execPrice": "64000"}
        messages = []
        position = {"symbol": "BTCUSDT", "side": "Buy", "entry": 64000, "stop_loss": 63800, "take_profit": 64300, "leverage": 7}
        with tempfile.TemporaryDirectory(prefix="manual-mirror-") as folder, \
             patch.object(services, "MANUAL_ALERTS", Path(folder) / "alerts.json"), \
             patch.object(services, "DATA_DIR", Path(folder)), \
             patch.object(services, "telegram", lambda text: messages.append(text) or True), \
             patch.object(services, "get_open_positions", lambda force=False: [position]):
            self.assertTrue(services._manual_position_alert(row))
            self.assertFalse(services._manual_position_alert(row))
        self.assertEqual(len(messages), 1)
        self.assertIn("Handmatig geopende positie", messages[0])
        self.assertIn("lager dan 3R", messages[0])
        self.assertIn("blokkeert niets", messages[0])

    def test_generic_exit_execution_is_suppressed_in_favour_of_closed_pnl(self):
        services = main.services
        messages = []
        row = {"execId": "exit-1", "orderId": "exit-order", "symbol": "BTCUSDT", "side": "Sell", "execQty": "0.1", "execPrice": "64500", "closedSize": "0.1"}
        with patch.object(services, "telegram", lambda text: messages.append(text) or True):
            event = services.notify_execution(row)
        self.assertEqual(event["kind"], "exit")
        self.assertTrue(event["telegram_suppressed"])
        self.assertEqual(messages, [])

    def test_deepdive_grade_is_persisted_on_the_matching_journal_row(self):
        services = main.services
        with tempfile.TemporaryDirectory(prefix="deepdive-link-") as folder:
            journal = Path(folder) / "journal.json"
            dives = Path(folder) / "deepdives.json"
            services._atomic_dump(journal, [{"_id": "trade-1", "symbol": "BTCUSDT", "pnl": -5}], indent=2)
            row = {"orderId": "trade-1", "symbol": "BTCUSDT", "side": "Sell", "closedPnl": "-5"}
            analysis = {"proces_grade": "C", "oordeel": "Proces afgekeurd", "les": "Wacht op bevestiging"}
            with patch.object(services, "JOURNAL", journal), patch.object(services, "DEEPDIVES", dives):
                self.assertTrue(services.save_deepdive(row, analysis))
                saved = services._load(journal, [])
        self.assertEqual(saved[0]["proces_grade"], "C")
        self.assertEqual(saved[0]["deepdive_id"], "trade-1")
        self.assertEqual(saved[0]["lesson"], "Wacht op bevestiging")

    def test_closed_trade_origin_distinguishes_manual_from_verified_ticket(self):
        services = main.services
        row = {"orderId": "closed-manual", "symbol": "BTCUSDT", "side": "Sell", "avgEntryPrice": "64000", "updatedTime": "1780000001000"}
        with tempfile.TemporaryDirectory(prefix="trade-origin-") as folder, patch.object(services, "DATA_DIR", Path(folder)):
            manual = services.trade_origin(row)
            services._atomic_dump(Path(folder) / "activity_v8.json", [{
                "type": "submitted", "ticket_verified": True, "symbol": "BTCUSDT", "direction": "long",
                "entry": 64000, "at": datetime.fromtimestamp(1780000000, tz=timezone.utc).isoformat(),
            }], indent=2)
            prepared = services.trade_origin(row)
        self.assertEqual(manual["class"], "MANUAL_OPEN")
        self.assertEqual(prepared["class"], "MYTRADINGBOT_TICKET")

    def test_methodology_registry_contains_provenance_for_rr_targets_and_journal(self):
        registry = main.load_methodology_sources()
        rules = {row.get("id"): row for row in registry.get("rules", [])}
        for rule_id in ("rr-minimum-3", "three-equal-targets", "journal-authoritative-source"):
            self.assertIn(rule_id, rules)
            self.assertTrue(rules[rule_id].get("source_label"))
        methodology = Path(main.METHODOLOGY_FILE).read_text(encoding="utf-8")
        self.assertNotIn("Miking Average", methodology)
        self.assertNotIn("30% / 30% / 30% + 10%", methodology)
        self.assertNotIn("$500–$1.000", methodology)


if __name__ == "__main__":
    unittest.main()
