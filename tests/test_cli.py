import argparse
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cli.saxocli import parse_args, run


class TestOrderCommands(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.search_instruments.return_value = {
            "Data": [{"Symbol": "ASRNL:xams", "AssetType": "Stock", "Identifier": 4289285}]
        }
        self.client.get_accounts.return_value = {"Data": [{"AccountKey": "account"}]}
        self.config = SimpleNamespace(simulation_mode=True, trading_enabled=False)

    def test_market_preview_does_not_write(self):
        args = argparse.Namespace(
            command="order",
            order_action="place",
            symbol="ASR",
            side="buy",
            quantity=1,
            type="market",
            limit=None,
            account_key=None,
            duration="DayOrder",
            execute=False,
            env=None,
        )
        result = run(args, self.config, self.client)
        self.assertFalse(result["will_execute"])
        self.assertEqual(result["order"]["OrderType"], "Market")
        self.client.place_order.assert_not_called()

    def test_limit_preview_contains_price(self):
        args = argparse.Namespace(
            command="order",
            order_action="place",
            symbol="ASR",
            side="sell",
            quantity=2,
            type="limit",
            limit=80,
            account_key=None,
            duration="DayOrder",
            execute=False,
            env=None,
        )
        result = run(args, self.config, self.client)
        self.assertEqual(result["order"]["OrderPrice"], 80)
        self.assertFalse(result["will_execute"])

    def test_execute_requires_trading_enabled(self):
        args = argparse.Namespace(
            command="order",
            order_action="cancel",
            order_ids=["123"],
            account_key="account",
            execute=True,
            env=None,
        )
        with self.assertRaises(PermissionError):
            run(args, self.config, self.client)

    def test_execute_cancel_calls_client(self):
        self.config.trading_enabled = True
        self.client.cancel_orders.return_value = {"Orders": []}
        args = argparse.Namespace(
            command="order",
            order_action="cancel",
            order_ids=["123", "456"],
            account_key="account",
            execute=True,
            env=None,
        )
        result = run(args, self.config, self.client)
        self.assertTrue(result["will_execute"])
        self.client.cancel_orders.assert_called_once_with(["123", "456"], "account")


class TestServeLifecycle(unittest.TestCase):
    def test_serve_parser_defaults_to_local_port(self):
        args = parse_args(["serve"])
        self.assertEqual(args.command, "serve")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 5000)

    def test_orders_history_flag_is_available(self):
        args = parse_args(["orders", "--history"])
        self.assertTrue(args.history)

    @patch("cli.saxocli.AuthenticationSession")
    @patch("cli.saxocli.create_client")
    @patch("cli.saxocli.load_runtime_config")
    def test_serve_authenticates_and_owns_session(self, load_config, create_client, session_cls):
        config = SimpleNamespace(simulation_mode=True, token_refresh_interval_seconds=19)
        client = MagicMock()
        session = session_cls.return_value
        load_config.return_value = config
        create_client.return_value = client

        web_app = types.ModuleType("web.app")
        web_app.startSaxoServer = MagicMock(return_value=None)
        web_package = types.ModuleType("web")
        web_package.app = web_app
        with patch.dict(sys.modules, {"web": web_package, "web.app": web_app}):
            from cli.saxocli import main

            self.assertEqual(main(["serve", "--port", "5011"]), 0)

        session_cls.assert_called_once_with(client, 19)
        session.authenticate.assert_called_once_with()
        session.start_refresh.assert_called_once_with()
        session.close.assert_called_once_with()
        web_app.startSaxoServer.assert_called_once_with(
            client=client,
            runtime_config=config,
            host="127.0.0.1",
            port=5011,
            dev=False,
        )


if __name__ == "__main__":
    unittest.main()
