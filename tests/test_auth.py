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
        params = {'scope': 'read', 'state': 'xyz'}
        expected_url = f"{self.auth_endpoint}?client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope=read&state=xyz"
        self.assertEqual(self.oauth_client._get_auth_url(**params), expected_url)

    @patch('requests.post')
    def test_exchange_for_token_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "xyz"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        code = "auth_code_123"
        code_verifier = "verifier_abc"
        token_data = self.oauth_client._exchange_for_token(code, code_verifier)

        mock_post.assert_called_once_with(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': code_verifier
        })
        self.assertEqual(token_data, {"access_token": "abc", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "xyz"})

    @patch('requests.post')
    def test_exchange_for_token_failure(self, mock_post):
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

        # Mock file operations
        # Use a fresh mock for each test to avoid state leakage
        self.mock_open = patch('builtins.open', unittest.mock.mock_open(read_data='{}')) 
        self.mock_os_chmod = patch('os.chmod')
        self.mock_os_path_exists = patch('os.path.exists')

        self.mock_open_ctx = self.mock_open.start()
        self.mock_os_chmod_ctx = self.mock_os_chmod.start()
        self.mock_os_path_exists_ctx = self.mock_os_path_exists.start()

        # Configure the mock file handle to return an empty JSON string by default
        self.mock_file_handle = self.mock_open_ctx.return_value.__enter__.return_value
        self.mock_file_handle.read.return_value = '{}' 

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
        # Clean up any created test files if necessary.
        # Since we are using mock_open, no actual file is created, so os.remove is not needed.
        # If we were creating actual files, this would be important.
        # For now, we'll leave it commented out to avoid FileNotFoundError.
        # if os.path.exists(self.token_file):
        #     os.remove(self.token_file)

    @patch('os.urandom', return_value=b'\x01\x02\x03\x04\x05\x06') # More bytes for better simulation
    @patch('base64.urlsafe_b64encode')
    @patch('hashlib.sha256')
    def test_generate_code_verifier_and_challenge(self, mock_sha256, mock_b64encode, mock_urandom):
        # Mock sha256 digest output
        mock_sha256_instance = MagicMock()
        mock_sha256.return_value = mock_sha256_instance
        mock_sha256_instance.digest.return_value = b'digest_hash_bytes'
        
        # Calculate expected values based on mocks
        verifier_bytes = b'\x01\x02\x03\x04\x05\x06'
        encoded_verifier = base64.urlsafe_b64encode(verifier_bytes).decode('utf-8').rstrip('=')
        
        digest_bytes = b'digest_hash_bytes'
        encoded_challenge = base64.urlsafe_b64encode(digest_bytes).decode('utf-8').rstrip('=')

        # Mock base64.urlsafe_b64encode to return the *bytes* that will be decoded
        mock_b64encode.side_effect = lambda x: encoded_verifier.encode('utf-8') if x == verifier_bytes else encoded_challenge.encode('utf-8')

        verifier = self.auth_client._generate_code_verifier()
        # The verifier is the result of decode().rstrip()
        self.assertEqual(verifier, encoded_verifier)

        challenge = self.auth_client._generate_code_challenge(verifier)
        # The challenge is the result of decode().rstrip()
        self.assertEqual(challenge, encoded_challenge)

        mock_urandom.assert_called_once_with(64)
        mock_sha256.assert_called_once_with(verifier.encode('utf-8'))
        mock_sha256_instance.digest.assert_called_once()
        # Check that base64.urlsafe_b64encode was called twice with the correct arguments
        self.assertEqual(mock_b64encode.call_count, 2)
        mock_b64encode.assert_any_call(verifier_bytes)
        mock_b64encode.assert_any_call(digest_bytes)


    def test_save_and_load_tokens(self):
        token_data = {"access_token": "new_token", "expires_in": 3600, "refresh_token": "new_refresh"}
        
        # Mock open for writing
        write_mock = MagicMock()
        self.mock_open_ctx.return_value.__enter__.return_value = write_mock
        
        self.auth_client._save_tokens(token_data)

        # Check if open was called with the correct file and mode
        self.mock_open_ctx.assert_any_call(self.token_file, 'w')
        # Check if json.dump was called with the correct data
        written_data_str = write_mock.write.call_args[0][0]
        written_data = json.loads(written_data_str)
        self.assertEqual(written_data['access_token'], "new_token")
        self.assertIn('expires_at', written_data)
        self.mock_os_chmod_ctx.assert_called_once_with(self.token_file, 0o600)

        # Simulate loading tokens
        self.mock_os_path_exists_ctx.return_value = True
        # Configure mock_open to return the saved data
        read_mock = MagicMock()
        read_mock.read.return_value = json.dumps(token_data)
        self.mock_open_ctx.return_value.__enter__.return_value = read_mock
        
        loaded_tokens = self.auth_client._load_tokens()

        self.assertEqual(loaded_tokens, token_data)
        self.mock_open_ctx.assert_any_call(self.token_file, 'r')

    def test_is_expired(self):
        # Case 1: No expiry
        self.auth_client.tokens = {}
        self.assertTrue(self.auth_client._is_expired())

        # Case 2: Expired token
        self.auth_client.tokens = {"expires_at": int(time.time()) - 100}
        self.assertTrue(self.auth_client._is_expired())

        # Case 3: Token expiring soon (within skew)
        self.auth_client.tokens = {"expires_at": int(time.time()) + 20}
        self.assertTrue(self.auth_client._is_expired(skew=30))

        # Case 4: Valid token
        self.auth_client.tokens = {"expires_at": int(time.time()) + 100}
        self.assertFalse(self.auth_client._is_expired())

    @patch.object(AuthorizationCodeClient, '_generate_code_verifier')
    @patch.object(AuthorizationCodeClient, '_generate_code_challenge')
    @patch.object(AuthorizationCodeClient, '_get_auth_url')
    def test_get_authorization_url(self, mock_get_auth_url, mock_generate_challenge, mock_generate_verifier):
        mock_verifier = "mock_verifier"
        mock_challenge = "mock_challenge"
        mock_url = "http://mock.auth.url"
        mock_generate_verifier.return_value = mock_verifier
        mock_generate_challenge.return_value = mock_challenge
        mock_get_auth_url.return_value = mock_url

        params = {'scope': 'read', 'state': 'test_state'}
        result_url = self.auth_client.get_authorization_url(**params)

        mock_generate_verifier.assert_called_once()
        mock_generate_challenge.assert_called_once_with(mock_verifier)
        mock_get_auth_url.assert_called_once_with(
            response_type='code',
            code_challenge=mock_challenge,
            code_challenge_method='S256',
            scope='read',
            state='test_state'
        )
        self.assertEqual(result_url, mock_url)

    @patch.object(AuthorizationCodeClient, '_exchange_for_token')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_get_token(self, mock_save_tokens, mock_exchange_for_token):
        mock_token_data = {"access_token": "new_token", "expires_in": 3600}
        mock_exchange_for_token.return_value = mock_token_data

        code = "auth_code_456"
        result = self.auth_client.get_token(code)

        mock_exchange_for_token.assert_called_once_with(code, self.auth_client.code_verifier)
        mock_save_tokens.assert_called_once_with(mock_token_data)
        self.assertEqual(result, mock_token_data)

    @patch.object(AuthorizationCodeClient, 'refresh_token')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='{"refresh_token": "old_refresh_token", "expires_at": %d}') # Mock file loading
    @patch('os.chmod')
    @patch('os.path.exists', return_value=True)
    def test_auto_refresh_on_init_expired(self, mock_path_exists, mock_chmod, mock_open, mock_refresh_token):
        # Mock refresh_token to return a successful result
        mock_refresh_token.return_value = {"access_token": "refreshed_token", "expires_in": 3600, "refresh_token": "new_refresh"}
        
        # Set tokens to be expired (this is handled by the mock_open read_data)
        expired_time = int(time.time()) - 100
        
        # Re-instantiate the client. The patches should be active now.
        self.auth_client = AuthorizationCodeClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            token_file=self.token_file
        )
        self.auth_client.token_file = self.token_file # Ensure attribute is set

        # Now assert that refresh_token was called and the tokens were updated
        mock_refresh_token.assert_called_once()
        self.assertEqual(self.auth_client.tokens.get("access_token"), "refreshed_token")


    @patch.object(AuthorizationCodeClient, 'refresh_token')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='{"access_token": "valid_token", "expires_at": %d}') # Mock file loading
    @patch('os.chmod')
    @patch('os.path.exists', return_value=True)
    def test_auto_refresh_on_init_not_expired(self, mock_path_exists, mock_chmod, mock_open, mock_refresh_token):
        # Set tokens to be valid
        valid_time = int(time.time()) + 100
        
        # Re-initialize to trigger the check in __init__
        # The mock_open read_data will simulate loading valid tokens
        self.auth_client = AuthorizationCodeClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            auth_endpoint=self.auth_endpoint,
            token_endpoint=self.token_endpoint,
            token_file=self.token_file
        )
        self.auth_client.token_file = self.token_file # Ensure attribute is set

        self.assertEqual(self.auth_client.tokens.get("access_token"), "valid_token")
        mock_refresh_token.assert_not_called()


    @patch('requests.post')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_refresh_token_success(self, mock_save_tokens, mock_post):
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
        self.auth_client.tokens = {"access_token": "valid_token"} # No refresh token
        result = self.auth_client.refresh_token()
        mock_post.assert_not_called()
        mock_save_tokens.assert_not_called()
        self.assertIsNone(result)

    @patch('requests.post')
    @patch.object(AuthorizationCodeClient, '_save_tokens')
    def test_refresh_token_failure(self, mock_save_tokens, mock_post):
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
        self.assertEqual(self._test_method_success(), "Success")

    def test_decorator_failure(self):
        result = self._test_method_failure()
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Something went wrong")

if __name__ == '__main__':
    unittest.main()
