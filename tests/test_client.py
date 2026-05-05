import unittest
from unittest.mock import MagicMock, patch

from shared.client import SaxoClient


class TestSaxoClient(unittest.TestCase):
    def setUp(self):
        self.mock_auth_client = MagicMock()
        self.mock_auth_client._is_access_token_expired.return_value = False
        self.mock_auth_client.tokens = {"access_token": "abc"}

        self.patcher_auth = patch("shared.client.AuthorizationCodeClient", return_value=self.mock_auth_client)
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

    @patch.object(SaxoClient, "_make_api_request")
    def test_get_positions(self, mock_api):
        self.client.get_positions()
        mock_api.assert_called_once_with("GET", "/port/v1/positions/me")

    def test_api_request_rejects_write_methods(self):
        with self.assertRaises(PermissionError):
            self.client._make_api_request("POST", "/trade/v2/orders", data={"Amount": 1})


if __name__ == "__main__":
    unittest.main()
