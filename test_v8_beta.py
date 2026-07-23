import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# test_backend establishes the isolated environment before importing main.
import test_backend as tb

main = tb.main
beta_access = main.beta_access
engine = tb.engine


class PrivateBetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.app.config.update(TESTING=True)
        cls.client = main.app.test_client()
        cls.owner_headers = {"X-MyTradingBot-Token": tb.TEST_TOKEN}

    def setUp(self):
        main.RATE_STATE.clear()
        main.PRICE_CACHE.update(at=0, prices={"BTC": 100.0})
        root = Path(tb.TEST_DIR)
        for path in root.glob("*"):
            if path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)
        beta_access.DATA_DIR = root
        beta_access.REGISTRY_FILE = root / "beta_access_v8.json"
        beta_access.MASTER_SECRET = tb.TEST_TOKEN.encode("utf-8")

    def create_and_redeem(self, name="Tester Een"):
        invite_response = self.client.post(
            "/api/v2/beta/invites",
            headers=self.owner_headers,
            json={"label": name, "expires_days": 14, "max_uses": 1},
        )
        self.assertEqual(invite_response.status_code, 200, invite_response.get_data(as_text=True))
        code = invite_response.get_json()["invite"]["code"]
        redeem_response = self.client.post(
            "/api/v2/beta/redeem",
            json={"code": code, "display_name": name, "consent": True},
        )
        self.assertEqual(redeem_response.status_code, 200, redeem_response.get_data(as_text=True))
        payload = redeem_response.get_json()
        return payload["token"], payload["principal"]

    def test_invite_is_single_use_and_raw_secrets_are_not_stored(self):
        create = self.client.post(
            "/api/v2/beta/invites", headers=self.owner_headers,
            json={"label": "Broer", "max_uses": 1},
        )
        code = create.get_json()["invite"]["code"]
        first = self.client.post(
            "/api/v2/beta/redeem",
            json={"code": code, "display_name": "Broer", "consent": True},
        )
        self.assertEqual(first.status_code, 200)
        token = first.get_json()["token"]
        second = self.client.post(
            "/api/v2/beta/redeem",
            json={"code": code, "display_name": "Iemand Anders", "consent": True},
        )
        self.assertEqual(second.status_code, 400)
        raw_registry = beta_access.REGISTRY_FILE.read_text(encoding="utf-8")
        self.assertNotIn(code, raw_registry)
        self.assertNotIn(token, raw_registry)


    def test_invite_uses_exact_requested_expiry_and_can_be_revoked_before_use(self):
        created = self.client.post(
            "/api/v2/beta/invites", headers=self.owner_headers,
            json={"label": "Vijf minuten", "expires_minutes": 5, "max_uses": 1},
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        invite = created.get_json()["invite"]
        start = datetime.fromisoformat(invite["created_at"])
        end = datetime.fromisoformat(invite["expires_at"])
        self.assertAlmostEqual((end - start).total_seconds(), 300.0, delta=1.0)
        self.assertEqual(invite["expires_unit"], "minutes")
        self.assertEqual(invite["expires_value"], 5)

        revoked = self.client.post(
            "/api/v2/beta/invites/revoke", headers=self.owner_headers,
            json={"invite_id": invite["id"]},
        )
        self.assertEqual(revoked.status_code, 200, revoked.get_data(as_text=True))
        denied = self.client.post(
            "/api/v2/beta/redeem",
            json={"code": invite["code"], "display_name": "Te laat", "consent": True},
        )
        self.assertEqual(denied.status_code, 400)
        self.assertIn("ingetrokken", denied.get_json()["error"].lower())

    def test_invite_hours_are_not_silently_replaced_by_fourteen_days(self):
        created = self.client.post(
            "/api/v2/beta/invites", headers=self.owner_headers,
            json={"label": "Een uur", "expires_hours": 1},
        )
        invite = created.get_json()["invite"]
        start = datetime.fromisoformat(invite["created_at"])
        end = datetime.fromisoformat(invite["expires_at"])
        self.assertAlmostEqual((end - start).total_seconds(), 3600.0, delta=1.0)
        self.assertEqual(invite["expires_unit"], "hours")

    def test_tester_is_paper_only_and_cannot_use_owner_admin(self):
        token, principal = self.create_and_redeem("Beta Vriend")
        headers = {"X-MyTradingBot-Token": token}
        me = self.client.get("/api/v2/beta/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        body = me.get_json()
        self.assertEqual(body["principal"]["role"], "tester")
        self.assertEqual(body["profile"]["mode"], "tester")
        overview = self.client.get("/api/v1/overview", headers=headers)
        self.assertEqual(overview.status_code, 200)
        payload = overview.get_json()
        self.assertEqual(payload["account"]["mode"], "paper")
        self.assertFalse(payload["latest"]["execution_gate"]["orderable"])
        self.assertEqual(payload["latest"]["execution_gate"]["status"], "PAPER_MODE")
        denied = self.client.get("/api/v2/beta/testers", headers=headers)
        self.assertEqual(denied.status_code, 403)

    def test_each_tester_has_an_isolated_workspace(self):
        token_a, principal_a = self.create_and_redeem("Tester A")
        token_b, principal_b = self.create_and_redeem("Tester B")
        self.assertNotEqual(principal_a["workspace_id"], principal_b["workspace_id"])
        headers_a = {"X-MyTradingBot-Token": token_a}
        headers_b = {"X-MyTradingBot-Token": token_b}
        saved = self.client.post(
            "/api/v1/market-map", headers=headers_a, json=tb.layer_payload("1D")
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        stack_a = self.client.get("/api/v1/market-stack", headers=headers_a).get_json()["stack"]
        stack_b = self.client.get("/api/v1/market-stack", headers=headers_b).get_json()["stack"]
        self.assertIn("BTC", stack_a.get("assets", {}))
        self.assertNotIn("BTC", stack_b.get("assets", {}))

    def test_revoke_immediately_invalidates_tester_token(self):
        token, principal = self.create_and_redeem("Tester Revoke")
        revoke = self.client.post(
            "/api/v2/beta/testers/revoke", headers=self.owner_headers,
            json={"session_id": principal["id"]},
        )
        self.assertEqual(revoke.status_code, 200)
        response = self.client.get("/api/v2/beta/me", headers={"X-MyTradingBot-Token": token})
        self.assertEqual(response.status_code, 401)

    def test_wrong_broker_instrument_is_hard_blocked_before_vision(self):
        payload = tb.capture_payload("3M")
        payload["context"]["symbol"] = "PEPPERSTONE:BTCUSD"
        response = self.client.post(
            "/api/v1/chart/analyze", headers=self.owner_headers, json=payload
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("INSTRUMENT KOMT NIET OVEREEN", response.get_json()["error"])

    def test_tester_can_export_and_delete_own_data(self):
        token, principal = self.create_and_redeem("Tester Export")
        headers = {"X-MyTradingBot-Token": token}
        entry = self.client.post(
            "/api/v2/journal/test-entry", headers=headers,
            json={"direction": "long", "entry": 64000, "exit": 64200, "pnl": 25},
        )
        self.assertEqual(entry.status_code, 200)
        export = self.client.get("/api/v2/beta/export", headers=headers)
        self.assertEqual(export.status_code, 200)
        self.assertIn("journal.json", export.get_json()["export"]["files"])
        deleted = self.client.post(
            "/api/v2/beta/delete-my-data", headers=headers,
            json={"confirm": "verwijder mijn beta-data"},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((Path(tb.TEST_DIR) / "workspaces" / principal["workspace_id"]).exists())
        self.assertEqual(self.client.get("/api/v2/beta/me", headers=headers).status_code, 401)


if __name__ == "__main__":
    unittest.main()
