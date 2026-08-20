import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

web_module = importlib.import_module("web.app")
flask_app = web_module.app


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = flask_app.test_client()

    def test_home_status_and_callback(self):
        with patch.object(web_module.saxoclient, "current_state", return_value="authenticated"):
            self.assertEqual(self.client.get("/").status_code, 200)
            status = self.client.get("/status").get_json()
            self.assertEqual(status["app_status"], "running")
            callback = self.client.get("/oauth/callback?code=abc")
            self.assertEqual(callback.status_code, 302)

    def test_authenticate_paths(self):
        client = web_module.saxoclient
        with (
            patch.object(web_module, "config", SimpleNamespace(REDIRECT_URI="http://redirect")),
            patch.object(client, "current_state", return_value=client.STATE_NOT_AUTHENTICATED),
            patch.object(client, "get_authorization_url", return_value="http://auth"),
        ):
            response = self.client.get("/authenticate")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"http://auth", response.data)
        with patch.object(client, "current_state", return_value=client.STATE_WAITING_FOR_TOKEN):
            self.assertEqual(self.client.post("/authenticate").status_code, 302)
        with (
            patch.object(client, "current_state", return_value=client.STATE_NOT_AUTHENTICATED),
            patch.object(client, "get_token"),
            patch.object(client, "_is_authenticated", return_value=True),
        ):
            self.assertEqual(self.client.get("/authenticate?code=abc").status_code, 302)

    def test_positions_and_table(self):
        client = web_module.saxoclient
        with patch.object(client, "_is_authenticated", return_value=False):
            self.assertEqual(self.client.get("/positions").status_code, 401)
            self.assertEqual(self.client.get("/positionstable").status_code, 401)
        raw = {
            "Data": [
                {
                    "PositionBase": {"AccountId": "A", "Uic": 1, "AssetType": "Stock", "Amount": 2},
                    "PositionView": {"ProfitLossOnTrade": 3},
                }
            ]
        }
        with (
            patch.object(client, "_is_authenticated", return_value=True),
            patch.object(client, "get_positions", return_value=raw),
            patch.object(client, "get_instrument_by_uic", return_value={"Symbol": "ABC"}),
        ):
            self.assertEqual(self.client.get("/positions").get_json(), raw)
            response = self.client.get("/positionstable")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"ABC", response.data)

    def test_instrument_cache_and_background(self):
        cache = {}
        mock_client = MagicMock()
        mock_client.auth_client.token_file = "tokens.json"
        mock_client.auth_client.baseurl = "https://example.test/sim"
        mock_client.get_instrument_by_uic.return_value = {"Description": "Desc"}
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "instruments.json"
            with patch.object(web_module, "_instrument_cache_path", return_value=cache_path):
                self.assertEqual(web_module._instrument_name(mock_client, 1, "Stock", cache), "Desc")
                self.assertEqual(web_module._instrument_name(mock_client, 1, "Stock", cache), "Desc")
                # A fresh request-local cache should still hit the shared disk cache.
                self.assertEqual(web_module._instrument_name(mock_client, 1, "Stock", {}), "Desc")
                self.assertEqual(mock_client.get_instrument_by_uic.call_count, 1)
                self.assertEqual(web_module._instrument_name(mock_client, None, "Stock", cache), "N/A")
                mock_client.get_instrument_by_uic.side_effect = RuntimeError("bad")
                self.assertEqual(web_module._instrument_name(mock_client, 2, "Stock", cache), "N/A")
        with (
            patch.object(web_module.saxoclient, "start_refresh_thread"),
            patch.object(web_module.saxoclient, "stop_refresh_thread"),
        ):
            web_module.start_background_tasks()
            web_module.stop_background_tasks()

    def test_instrument_cache_expiry_refreshes_value(self):
        mock_client = MagicMock()
        mock_client.auth_client.baseurl = "https://example.test/sim"
        mock_client.get_instrument_by_uic.return_value = {"Symbol": "FRESH"}
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "instruments.json"
            key = web_module._instrument_cache_key(mock_client, 7, "Stock")
            cache_path.write_text(
                json.dumps({key: {"name": "STALE", "cached_at": 100}}), encoding="utf-8"
            )
            expired_at = 100 + web_module.INSTRUMENT_CACHE_TTL_SECONDS + 1
            with (
                patch.object(web_module, "_instrument_cache_path", return_value=cache_path),
                patch.object(web_module.time, "time", return_value=expired_at),
            ):
                self.assertEqual(web_module._instrument_name(mock_client, 7, "Stock", {}), "FRESH")
            self.assertEqual(mock_client.get_instrument_by_uic.call_count, 1)
            self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8"))[key]["name"], "FRESH")

    def test_instrument_cache_separates_environments_and_does_not_cache_failures(self):
        sim_client = MagicMock()
        sim_client.auth_client.baseurl = "https://example.test/sim"
        sim_client.get_instrument_by_uic.return_value = {"Symbol": "SIM"}
        live_client = MagicMock()
        live_client.auth_client.baseurl = "https://example.test/live"
        live_client.get_instrument_by_uic.return_value = {"Symbol": "LIVE"}
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "instruments.json"
            with patch.object(web_module, "_instrument_cache_path", return_value=cache_path):
                self.assertEqual(web_module._instrument_name(sim_client, 9, "Stock", {}), "SIM")
                self.assertEqual(web_module._instrument_name(live_client, 9, "Stock", {}), "LIVE")
                sim_client.get_instrument_by_uic.side_effect = [RuntimeError("temporary"), {"Symbol": "OK"}]
                self.assertEqual(web_module._instrument_name(sim_client, 10, "Stock", {}), "N/A")
                self.assertEqual(web_module._instrument_name(sim_client, 10, "Stock", {}), "OK")
        self.assertEqual(sim_client.get_instrument_by_uic.call_count, 3)
        self.assertEqual(live_client.get_instrument_by_uic.call_count, 1)

    def test_instrument_cache_path_defaults_to_token_directory_and_supports_override(self):
        mock_client = MagicMock()
        mock_client.auth_client.token_file = str(Path("credentials") / "tokens-sim.json")
        expected = Path(os.path.abspath("credentials")) / "instrument-cache.json"
        self.assertEqual(web_module._instrument_cache_path(mock_client), expected)
        with patch.dict(os.environ, {"SAXO_INSTRUMENT_CACHE": "custom/cache.json"}):
            self.assertEqual(
                web_module._instrument_cache_path(mock_client),
                Path(os.path.abspath("custom/cache.json")),
            )

    def test_sell_position_requires_trading_and_submits_market_order(self):
        client = web_module.saxoclient
        with (
            patch.object(client, "_is_authenticated", return_value=True),
            patch.object(client, "trading_enabled", False, create=True),
        ):
            response = self.client.post(
                "/api/positions/sell", json={"uic": 1, "amount": 2, "account_key": "A"}
            )
            self.assertEqual(response.status_code, 403)

        with (
            patch.object(client, "_is_authenticated", return_value=True),
            patch.object(client, "trading_enabled", True, create=True),
            patch.object(client, "place_order", return_value={"Orders": [{"OrderId": "1"}]}),
        ):
            response = self.client.post(
                "/api/positions/sell",
                json={"uic": 1, "amount": 2, "asset_type": "Stock", "account_key": "A"},
            )
            self.assertEqual(response.status_code, 201)
            client.place_order.assert_called_once_with(
                {
                    "AccountKey": "A",
                    "Amount": 2.0,
                    "AssetType": "Stock",
                    "BuySell": "Sell",
                    "ManualOrder": True,
                    "OrderDuration": {"DurationType": "DayOrder"},
                    "OrderType": "Market",
                    "Uic": 1,
                }
            )

    def test_server_reloader_only_runs_in_dev_mode(self):
        client = MagicMock()
        with patch.object(web_module.app, "run") as run:
            web_module.startSaxoServer(
                client, SimpleNamespace(), host="127.0.0.1", port=5000, dev=True, secret="secret"
            )
            self.assertTrue(run.call_args.kwargs["debug"])
            self.assertTrue(run.call_args.kwargs["use_reloader"])
        with patch.object(web_module.app, "run") as run:
            web_module.startSaxoServer(
                client, SimpleNamespace(), host="127.0.0.1", port=5000, dev=False, secret="secret"
            )
            self.assertFalse(run.call_args.kwargs["debug"])
            self.assertFalse(run.call_args.kwargs["use_reloader"])

    def test_dashboard_script_has_valid_empty_query_in_dev_mode(self):
        web_module.configure(
            web_module.saxoclient, SimpleNamespace(token_refresh_interval_seconds=30), dev=True
        )
        response = self.client.get("/")
        self.assertIn(b'const query="";', response.data)
        self.assertNotIn(b"&#34;", response.data)


if __name__ == "__main__":
    unittest.main()
