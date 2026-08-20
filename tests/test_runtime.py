import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shared.runtime import (
    AuthenticationSession,
    create_client,
    ensure_authenticated,
    load_runtime_config,
    parse_bool,
)


class TestRuntimeHelpers(unittest.TestCase):
    def test_parse_bool(self):
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool("yes"))
        self.assertTrue(parse_bool("1"))
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool("no"))

    def test_load_runtime_config_uses_params_file_and_env(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as params_file:
            json.dump(
                {
                    "REDIRECT_URI": "http://json.example/callback",
                    "SIMULATION_MODE": False,
                    "TOKEN_FILE": "tokens-from-json.json",
                    "TOKEN_REFRESH_INTERVAL_SECONDS": 17,
                },
                params_file,
            )
            params_path = params_file.name

        try:
            with patch.dict(
                os.environ,
                {
                    "REDIRECT_URI": "http://env.example/callback",
                    "TOKEN_FILE": "tokens-from-env.json",
                    "TOKEN_REFRESH_INTERVAL_SECONDS": "19",
                },
                clear=False,
            ):
                config = load_runtime_config(params_path=params_path)
        finally:
            os.unlink(params_path)

        self.assertEqual(config.redirect_uri, "http://env.example/callback")
        self.assertFalse(config.simulation_mode)
        self.assertEqual(config.token_file, "tokens-from-env.json")
        self.assertEqual(config.auth_endpoint, "https://live.logonvalidation.net/authorize")
        self.assertEqual(config.base_url, "https://gateway.saxobank.com/openapi")
        self.assertEqual(config.token_refresh_interval_seconds, 19)

    def test_authentication_session_one_shot_closes_with_final_refresh_check(self):
        client = MagicMock()
        client._is_authenticated.return_value = True
        session = AuthenticationSession(client, refresh_interval_seconds=17)

        self.assertIs(session.authenticate(), client)
        session.close()

        client.ensure_access_token.assert_called_once_with()
        client.start_refresh_thread.assert_not_called()
        client.stop_refresh_thread.assert_not_called()

    def test_authentication_session_serve_worker_lifecycle(self):
        client = MagicMock()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True

        with patch("shared.runtime.threading.Thread", return_value=fake_thread) as thread_cls:
            session = AuthenticationSession(client, refresh_interval_seconds=23)
            session.start_refresh()
            session.close()

        thread_cls.assert_called_once()
        self.assertEqual(thread_cls.call_args.kwargs["name"], "saxo-token-refresh")
        fake_thread.start.assert_called_once_with()
        fake_thread.join.assert_called_once_with()
        client.ensure_access_token.assert_called_once_with()

    @patch("shared.runtime.SaxoClient")
    def test_create_client_passes_config_through(self, mock_client_cls):
        config = MagicMock(
            client_id="client-id",
            redirect_uri="redirect-uri",
            auth_endpoint="auth-endpoint",
            token_endpoint="token-endpoint",
            token_file="tokens.json",
            base_url="base-url",
        )

        create_client(config)

        mock_client_cls.assert_called_once_with(
            client_id="client-id",
            redirect_uri="redirect-uri",
            auth_endpoint="auth-endpoint",
            token_endpoint="token-endpoint",
            token_file="tokens.json",
            baseurl="base-url",
        )

    def test_ensure_authenticated_skips_when_client_ready(self):
        client = MagicMock()
        client._is_authenticated.return_value = True

        ensure_authenticated(client)

        client.refresh_token.assert_not_called()
        client.authenticate_interactive.assert_not_called()
        client.get_authorization_url.assert_not_called()

    def test_ensure_authenticated_uses_refresh_token(self):
        client = MagicMock()
        client._is_authenticated.side_effect = [False, True]
        client.auth_client.tokens = {"refresh_token": "refresh"}
        client.refresh_token.return_value = {"access_token": "new"}

        ensure_authenticated(client)

        client.refresh_token.assert_called_once()
        client.authenticate_interactive.assert_not_called()
        client.get_authorization_url.assert_not_called()

    def test_ensure_authenticated_raises_without_tty(self):
        client = MagicMock()
        client._is_authenticated.return_value = False
        client.auth_client.tokens = {}
        client.get_authorization_url.return_value = "http://auth.example"

        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(RuntimeError) as exc:
                ensure_authenticated(client)

        self.assertIn("http://auth.example", str(exc.exception))

    def test_runtime_defaults_and_interactive_fallbacks(self):
        from shared.runtime import default_token_file, load_config_value

        logger = MagicMock()
        self.assertEqual(load_config_value("MISSING", default="x", logger=logger), "x")
        self.assertEqual(load_config_value("X", json_config={"X": 3}), 3)
        with patch("shared.runtime.sys.platform", "darwin"):
            self.assertIn("tokens-live.json", default_token_file("live"))
        with (
            patch("shared.runtime.sys.platform", "linux"),
            patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/config"}),
        ):
            self.assertTrue(
                default_token_file("sim")
                .replace("\\", "/")
                .endswith("/tmp/config/saxo/tokens-sim.json")
            )
        with tempfile.NamedTemporaryFile("w", delete=False) as params_file:
            params_file.write("{")
            path = params_file.name
        try:
            self.assertTrue(
                load_runtime_config(path, environment="live").token_endpoint.startswith(
                    "https://live"
                )
            )
        finally:
            os.unlink(path)
        client = MagicMock()
        client._is_authenticated.return_value = False
        client.auth_client.tokens = {"refresh_token": "x"}
        client.refresh_token.return_value = None
        client.authenticate_interactive.return_value = True
        with patch("sys.stdin.isatty", return_value=True):
            ensure_authenticated(client)
        client.authenticate_interactive.return_value = False
        with patch("sys.stdin.isatty", return_value=True):
            with self.assertRaises(RuntimeError):
                ensure_authenticated(client)

    def test_trading_is_disabled_by_default_and_configurable(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as params_file:
            json.dump({"TRADING_ENABLED": True}, params_file)
            params_path = params_file.name
        try:
            config = load_runtime_config(params_path)
        finally:
            os.unlink(params_path)
        self.assertTrue(config.trading_enabled)


if __name__ == "__main__":
    unittest.main()
