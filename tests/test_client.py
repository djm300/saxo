import unittest
from unittest.mock import MagicMock, patch

import httpx

from shared.client import AuthenticationError, SaxoAPIError, SaxoClient


class TestSaxoClient(unittest.TestCase):
    def setUp(self):
        self.mock_auth_client = MagicMock()
        self.mock_auth_client._is_access_token_expired.return_value = False
        self.mock_auth_client.tokens = {"access_token": "abc"}

        self.patcher_auth = patch(
            "shared.client.AuthorizationCodeClient", return_value=self.mock_auth_client
        )
        self.mock_auth_cls = self.patcher_auth.start()

        self.client = SaxoClient(
            client_id="dummy_id",
            redirect_uri="dummy_uri",
            auth_endpoint="dummy_auth",
            token_endpoint="dummy_token",
        )

    def tearDown(self):
        self.patcher_auth.stop()

    def test_init(self):
        self.mock_auth_cls.assert_called_once_with(
            client_id="dummy_id",
            redirect_uri="dummy_uri",
            auth_endpoint="dummy_auth",
            token_endpoint="dummy_token",
            token_file="tokens.json",
            baseurl="https://gateway.saxobank.com/sim/openapi",
        )
        self.assertEqual(self.client.scope, "required_scope")

    def test_get_authorization_url(self):
        self.client.get_authorization_url()
        self.mock_auth_client.get_authorization_url.assert_called_once_with(scope=self.client.scope)

    def test_get_token(self):
        code = "test_code"
        self.client.get_token(code)
        self.mock_auth_client.get_token.assert_called_once_with(code)

    def test_refresh_token(self):
        self.mock_auth_client.refresh_token.return_value = {"access_token": "new"}
        self.client.refresh_token()
        self.mock_auth_client.refresh_token.assert_called_once()

    def test_ensure_access_token_skips_valid_token(self):
        self.client.ensure_access_token()
        self.mock_auth_client.refresh_token.assert_not_called()

    def test_ensure_access_token_refreshes_expired_token(self):
        self.mock_auth_client._is_access_token_expired.return_value = True
        self.mock_auth_client.refresh_token.return_value = {"access_token": "new"}
        self.mock_auth_client.tokens = {"access_token": "new"}

        self.client.ensure_access_token()

        self.mock_auth_client.refresh_token.assert_called_once_with()

    def test_ensure_access_token_raises_when_refresh_is_unusable(self):
        self.mock_auth_client._is_access_token_expired.return_value = True
        self.mock_auth_client.refresh_token.return_value = None
        self.mock_auth_client.tokens = {}

        with self.assertRaises(AuthenticationError):
            self.client.ensure_access_token()

    @patch.object(SaxoClient, "_make_api_request")
    def test_get_positions(self, mock_api):
        self.client.get_positions()
        mock_api.assert_called_once_with("GET", "/port/v1/positions/me")

    @patch.object(SaxoClient, "_make_api_request")
    def test_get_order_history(self, mock_api):
        self.client.get_order_history()
        args, kwargs = mock_api.call_args
        self.assertEqual(args, ("GET", "/cs/v1/audit/orderactivities"))
        self.assertEqual(kwargs["params"]["EntryType"], "All")
        self.assertEqual(kwargs["params"]["$top"], 200)
        self.assertEqual(kwargs["params"]["FieldGroups"], "DisplayAndFormat")
        self.assertIsInstance(kwargs["params"]["FromDateTime"], str)
        self.assertIsInstance(kwargs["params"]["ToDateTime"], str)

    def test_api_request_rejects_write_methods(self):
        with self.assertRaises(PermissionError):
            self.client._make_api_request("POST", "/trade/v2/orders", data={"Amount": 1})

    def test_order_writes_are_disabled_by_default(self):
        with self.assertRaises(PermissionError):
            self.client.place_order({"Amount": 1})
        with self.assertRaises(PermissionError):
            self.client.cancel_orders(["123"], "account")

    def test_place_and_cancel_orders_when_enabled(self):
        self.client.trading_enabled = True
        with patch.object(self.client, "_make_api_request", return_value={"OrderId": "123"}) as api:
            self.assertEqual(self.client.place_order({"Amount": 1}), {"OrderId": "123"})
            api.assert_called_once_with(
                "POST",
                "/trade/v2/orders",
                data={"Amount": 1, "WithAdvice": False},
            )
        with patch.object(self.client, "_make_api_request", return_value={"Orders": []}) as api:
            self.assertEqual(self.client.cancel_orders(["123", "456"], "account"), {"Orders": []})
            api.assert_called_once_with(
                "DELETE", "/trade/v2/orders/123,456", params={"AccountKey": "account"}
            )

    def test_http_errors_are_not_reported_as_authentication(self):
        self.mock_auth_client.tokens = {"access_token": "x"}
        response = MagicMock(status_code=404)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "missing", request=httpx.Request("GET", "https://example.test/missing"), response=httpx.Response(404)
        )
        with patch("shared.client._http2_client.request", return_value=response):
            with self.assertRaises(SaxoAPIError):
                self.client._make_api_request("GET", "/missing")

    def test_state_and_authentication_transitions(self):
        self.client.transition("unknown")
        self.client.transition(self.client.STATE_ERROR)
        self.mock_auth_client.get_authorization_url.return_value = "url"
        self.assertEqual(
            self.client.current_state(), self.client.STATE_WAITING_FOR_AUTHORIZATION_CODE
        )
        self.mock_auth_client.get_token.return_value = {"access_token": "x"}
        self.mock_auth_client.tokens = {"access_token": "x"}
        self.assertEqual(self.client.get_token("code")["access_token"], "x")
        self.mock_auth_client.get_token.side_effect = RuntimeError("bad")
        self.assertIsNone(self.client.get_token("bad"))

    def test_refresh_and_api_request(self):
        self.mock_auth_client.refresh_token.return_value = {"access_token": "new"}
        self.mock_auth_client.tokens = {"access_token": "new"}
        self.assertEqual(self.client.refresh_token()["access_token"], "new")
        self.mock_auth_client.refresh_token.return_value = None
        self.assertIsNone(self.client.refresh_token())
        self.mock_auth_client._is_access_token_expired.return_value = False
        response = MagicMock()
        response.json.return_value = {"ok": True}
        with patch("shared.client._http2_client.request", return_value=response) as request:
            self.assertEqual(
                self.client._make_api_request("get", "/x", data={"a": 1}, params={"p": 2}),
                {"ok": True},
            )
            request.assert_called_once()
        self.mock_auth_client.tokens = {}
        self.mock_auth_client.refresh_token.return_value = None
        with self.assertRaises(ConnectionError):
            self.client._make_api_request("GET", "/x")

    def test_api_methods_and_request_error(self):
        with patch.object(self.client, "_make_api_request", return_value={}) as api:
            self.client.get_accounts()
            self.client.get_balances()
            self.client.get_orders()
            self.client.get_instrument_by_uic(1, "Stock")
            self.client.search_instruments("abc", "Stock")
            self.client.get_quote(1, account_key="a")
            self.assertEqual(api.call_count, 6)
        self.mock_auth_client.tokens = {"access_token": "x"}
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.RequestError(
            "down", request=httpx.Request("GET", "https://example.test/x")
        )
        with patch("shared.client._http2_client.request", return_value=response):
            with self.assertRaises(ConnectionError):
                self.client._make_api_request("GET", "/x")

    def test_interactive_and_refresh_thread_paths(self):
        self.mock_auth_client.get_authorization_url.return_value = "url"
        self.mock_auth_client.get_token.return_value = {"access_token": "x"}
        self.mock_auth_client.tokens = {"access_token": "x"}
        with patch("builtins.input", return_value=" code "):
            self.assertTrue(self.client.authenticate_interactive())
        self.mock_auth_client.tokens = {}
        self.mock_auth_client.get_token.return_value = None
        with patch("builtins.input", return_value="bad"):
            self.assertFalse(self.client.authenticate_interactive())
        self.mock_auth_client.refresh_token.side_effect = RuntimeError("bad")
        with self.assertRaises(RuntimeError):
            self.client.refresh_token()
        thread = MagicMock()
        thread.is_alive.return_value = True
        self.client._refresh_thread = thread
        self.client._stop_event = MagicMock()
        self.client.start_refresh_thread()
        self.client.stop_refresh_thread()
        thread.is_alive.return_value = False
        self.client.stop_refresh_thread()

    def test_refresh_loop_success_failure_and_valid_token(self):
        class StopEvent:
            def __init__(self):
                self.calls = 0

            def is_set(self):
                return self.calls > 0

            def wait(self, _interval):
                self.calls += 1

        self.client._stop_event = StopEvent()
        self.mock_auth_client._is_access_token_expired.return_value = True
        self.mock_auth_client.refresh_token.return_value = {"access_token": "x"}
        self.client._refresh_loop(0)
        self.client._stop_event = StopEvent()
        self.mock_auth_client.refresh_token.return_value = None
        self.client._refresh_loop(0)
        self.client._stop_event = StopEvent()
        self.mock_auth_client._is_access_token_expired.return_value = False
        self.mock_auth_client.tokens = {"access_token_expires_at": 9999999999}
        self.client._refresh_loop(0)


if __name__ == "__main__":
    unittest.main()
