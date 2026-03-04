import unittest
from unittest.mock import MagicMock, patch

import requests

from shared.auth import AuthorizationCodeClient, OAuth2Client, handle_oauth_errors


class TestOAuth2Client(unittest.TestCase):
    def setUp(self):
        self.auth_endpoint = "https://sim.logonvalidation.net/authorize"
        self.token_endpoint = "https://sim.logonvalidation.net/token"
        self.client_id = "test_client_id"
        self.redirect_uri = "http://localhost/callback"
        self.baseurl = "https://gateway.saxobank.com/sim/openapi"
        self.oauth_client = OAuth2Client(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            baseurl=self.baseurl,
        )

    def test_get_auth_url(self):
        params = {"scope": "read", "state": "xyz"}
        expected_url = (
            f"{self.auth_endpoint}?client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope=read&state=xyz"
        )
        self.assertEqual(self.oauth_client._get_auth_url(**params), expected_url)

    @patch("shared.auth.requests.post")
    def test_exchange_for_token_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        code = "auth_code_123"
        code_verifier = "verifier_abc"
        token_data = self.oauth_client._exchange_for_token(code, code_verifier)

        mock_post.assert_called_once_with(
            self.token_endpoint,
            data={
                "client_id": self.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        self.assertEqual(token_data["access_token"], "abc")

    @patch("shared.auth.requests.post")
    def test_exchange_for_token_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad request")
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            self.oauth_client._exchange_for_token("auth_code_123", "verifier_abc")


class TestAuthorizationCodeClient(unittest.TestCase):
    def setUp(self):
        self.client_id = "test_client_id"
        self.redirect_uri = "http://localhost/callback"
        self.auth_endpoint = "https://sim.logonvalidation.net/authorize"
        self.token_endpoint = "https://sim.logonvalidation.net/token"
        self.token_file = "test_tokens.json"

        self.mock_open = patch("builtins.open", unittest.mock.mock_open(read_data="{}"))
        self.mock_os_chmod = patch("os.chmod")
        self.mock_os_path_exists = patch("os.path.exists", return_value=False)

        self.mock_open.start()
        self.mock_os_chmod.start()
        self.mock_os_path_exists.start()

        self.auth_client = AuthorizationCodeClient(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            baseurl="https://gateway.saxobank.com/sim/openapi",
            token_file=self.token_file,
        )

    def tearDown(self):
        self.mock_open.stop()
        self.mock_os_chmod.stop()
        self.mock_os_path_exists.stop()

    @patch.object(AuthorizationCodeClient, "_exchange_for_token")
    @patch.object(AuthorizationCodeClient, "_save_tokens")
    def test_get_token(self, mock_save_tokens, mock_exchange_for_token):
        self.auth_client.code_verifier = "test_verifier"
        mock_token_data = {"access_token": "new_token", "expires_in": 3600}
        mock_exchange_for_token.return_value = mock_token_data

        result = self.auth_client.get_token("auth_code_456")

        mock_exchange_for_token.assert_called_once_with("auth_code_456", "test_verifier")
        mock_save_tokens.assert_called_once()
        self.assertEqual(result["access_token"], "new_token")

    @patch("shared.auth.requests.post")
    @patch.object(AuthorizationCodeClient, "_save_tokens")
    @patch.object(AuthorizationCodeClient, "_is_refresh_token_expired", return_value=False)
    def test_refresh_token_success(self, _mock_expired, mock_save_tokens, mock_post):
        self.auth_client.tokens = {"refresh_token": "valid_refresh_token", "code_verifier": "cv"}
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "new_access", "expires_in": 3600}
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = self.auth_client.refresh_token()

        mock_post.assert_called_once_with(
            self.token_endpoint,
            data={"grant_type": "refresh_token", "refresh_token": "valid_refresh_token", "code_verifier": "cv"},
        )
        mock_save_tokens.assert_called_once()
        self.assertEqual(result["access_token"], "new_access")

    @patch("shared.auth.requests.post")
    @patch.object(AuthorizationCodeClient, "_save_tokens")
    def test_refresh_token_no_refresh_token(self, mock_save_tokens, mock_post):
        self.auth_client.tokens = {"access_token": "valid_token"}
        result = self.auth_client.refresh_token()
        mock_post.assert_not_called()
        mock_save_tokens.assert_not_called()
        self.assertIsNone(result)


class TestDecorator(unittest.TestCase):
    @handle_oauth_errors
    def _test_method_success(self):
        return "Success"

    @handle_oauth_errors
    def _test_method_failure(self):
        raise ValueError("Something went wrong")

    def test_decorator_success(self):
        self.assertEqual(self._test_method_success(), "Success")

    def test_decorator_failure(self):
        result = self._test_method_failure()
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Something went wrong")


if __name__ == "__main__":
    unittest.main()
