import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shared.runtime import create_client, ensure_authenticated, load_runtime_config, parse_bool


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


if __name__ == "__main__":
    unittest.main()
