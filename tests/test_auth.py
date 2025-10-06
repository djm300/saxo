import unittest
from unittest.mock import patch, MagicMock
import json
import os
import time
import requests # Added import for requests
import base64 # Added import for base64
import hashlib # Added import for hashlib

# Assuming saxo_sdk is in the parent directory or accessible in the Python path
# If not, you might need to adjust sys.path or run tests from the project root
from saxo_sdk.auth import AuthorizationCodeClient, OAuth2Client, handle_oauth_errors

class TestOAuth2Client(unittest.TestCase):
    def setUp(self):
        self.auth_endpoint = "https://sim.logonvalidation.net/authorize"
        self.token_endpoint = "https://sim.logonvalidation.net/token"
        self.client_id = "test_client_id"
        self.client_secret = "test_client_secret"
        self.redirect_uri = "http://localhost/callback"
        self.oauth_client = OAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint
        )

    def test_get_auth_url(self):
        # Basic test for generating the authorization URL
        params = {'scope': 'read', 'state': 'xyz'}
        expected_url = f"{self.auth_endpoint}?client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope=read&state=xyz"
        self.assertEqual(self.oauth_client._get_auth_url(**params), expected_url)

    @patch('requests.post')
    def test_exchange_for_token_success(self, mock_post):
        # Test successful exchange of authorization code for tokens
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "xyz"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        code = "auth_code_123"
        code_verifier = "verifier_abc" # This is not used by OAuth2Client directly, but passed to _exchange_for_token
        token_data = self.oauth_client._exchange_for_token(code, code_verifier)

        mock_post.assert_called_once_with(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': code_verifier # Included as per the original code, though OAuth2Client might not use it for PKCE
        })
        self.assertEqual(token_data, {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "xyz"})

    @patch('requests.post')
    def test_exchange_for_token_failure(self, mock_post):
        # Test failure during token exchange
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad request")
        mock_post.return_value = mock_response

        code = "auth_code_123"
        code_verifier = "verifier_abc"
        with self.assertRaises(requests.exceptions.HTTPError):
            self.oauth_client._exchange_for_token(code, code_verifier)

class TestAuthorizationCodeClient(unittest.TestCase):
    def setUp(self):
        self.client_id = "test_client_id"
        self.client_secret = "test_client_secret"
        self.redirect_uri = "http://localhost/callback"
        self.auth_endpoint = "https://sim.logonvalidation.net/authorize"
        self.token_endpoint = "https://sim.logonvalidation.net/token"
        self.token_file = "test_tokens.json"

        # Mock file operations for token persistence tests
        self.mock_open = patch('builtins.open', unittest.mock.mock_open(read_data='{}'))
        self.mock_os_chmod = patch('os.chmod')
        self.mock_os_path_exists = patch('os.path.exists')

        self.mock_open_ctx = self.mock_open.start()
        self.mock_os_chmod_ctx = self.mock_os_chmod.start()
        self.mock_os_path_exists_ctx = self.mock_os_path_exists.start()

        # Configure the mock file handle to return an empty JSON string by default
        self.mock_file_handle = self.mock_open_ctx.return_value.__enter__.return_value
        self.mock_file_handle.read.return_value = '{}'

        # Initialize AuthorizationCodeClient, which might try to load tokens
        # We will mock its internal methods to control behavior
        self.auth_client = AuthorizationCodeClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            token_file=self.token_file
        )
        # Ensure the client's internal token_file attribute is set correctly
        self.auth_client.token_file = self.token_file

    def tearDown(self):
        self.mock_open.stop()
        self.mock_os_chmod.stop()
        self.mock_os_path_exists.stop()

    @patch.object(AuthorizationCodeClient, '_exchange_for_token')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_get_token(self, mock_save_tokens, mock_exchange_for_token):
        # Test the public method to get a token using an authorization code
        mock_token_data = {"access_token": "new_token", "expires_in": 3600}
        mock_exchange_for_token.return_value = mock_token_data

        code = "auth_code_456"
        # The AuthorizationCodeClient's get_token method uses its own code_verifier
        # We need to ensure it's set or mocked if it's not generated in setUp
        # For simplicity, we'll assume it's handled or not critical for this specific test's assertion
        # If _generate_code_verifier was called in __init__ and stored, it would be used.
        # For this test, we focus on the call to _exchange_for_token and _save_tokens.
        
        # Mock the internal code_verifier if it's expected to be used by _exchange_for_token
        # In the original code, _exchange_for_token takes code_verifier as an argument.
        # The AuthorizationCodeClient stores its own code_verifier.
        # Let's mock the internal verifier to ensure it's passed.
        self.auth_client.code_verifier = "test_verifier_for_get_token"
        
        result = self.auth_client.get_token(code)

        mock_exchange_for_token.assert_called_once_with(code, self.auth_client.code_verifier)
        mock_save_tokens.assert_called_once_with(mock_token_data)
        self.assertEqual(result, mock_token_data)

    @patch('requests.post')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_refresh_token_success(self, mock_save_tokens, mock_post):
        # Test successful refresh of an access token using a refresh token
        self.auth_client.tokens = {"refresh_token": "valid_refresh_token"}
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "new_access", "expires_in": 3600, "refresh_token": "new_refresh"}
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = self.auth_client.refresh_token()

        mock_post.assert_called_once_with(self.token_endpoint, data={
            'grant_type': 'refresh_token',
            'refresh_token': 'valid_refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        })
        mock_save_tokens.assert_called_once()
        self.assertEqual(result, {"access_token": "new_access", "expires_in": 3600, "refresh_token": "new_refresh"})

    @patch('requests.post')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_refresh_token_no_refresh_token(self, mock_save_tokens, mock_post):
        # Test that refresh_token does nothing if no refresh token is available
        self.auth_client.tokens = {"access_token": "valid_token"} # No refresh token
        result = self.auth_client.refresh_token()
        mock_post.assert_not_called()
        mock_save_tokens.assert_not_called()
        self.assertIsNone(result)

    @patch('requests.post')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_refresh_token_failure(self, mock_save_tokens, mock_post):
        # Test failure during refresh token request
        self.auth_client.tokens = {"refresh_token": "invalid_refresh_token"}
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid grant"
        mock_post.return_value = mock_response

        result = self.auth_client.refresh_token()

        mock_post.assert_called_once_with(self.token_endpoint, data={
            'grant_type': 'refresh_token',
            'refresh_token': 'invalid_refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        })
        mock_save_tokens.assert_not_called()
        self.assertIsNone(result)

# Test the decorator
class TestDecorator(unittest.TestCase):
    @handle_oauth_errors
    def _test_method_success(self):
        return "Success"

    @handle_oauth_errors
    def _test_method_failure(self):
        raise ValueError("Something went wrong")

    def test_decorator_success(self):
        # Test that the decorator passes through successful calls
        self.assertEqual(self._test_method_success(), "Success")

    def test_decorator_failure(self):
        # Test that the decorator catches exceptions and returns an error dictionary
        result = self._test_method_failure()
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Something went wrong")

if __name__ == '__main__':
    unittest.main()
