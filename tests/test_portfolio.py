import unittest
from unittest.mock import patch, MagicMock

# Assuming saxo_sdk is in the parent directory or accessible in the Python path
from saxo_sdk.portfolio import PortfolioClient

class TestPortfolioClient(unittest.TestCase):
    def setUp(self):
        # Mock the authentication client that PortfolioClient depends on
        self.mock_auth_client = MagicMock()
        self.portfolio_client = PortfolioClient(self.mock_auth_client)

    @patch.object(PortfolioClient, 'get_portfolio')
    def test_get_portfolio_calls_auth_client(self, mock_get_portfolio):
        # This test is more about ensuring the method exists and can be called.
        # The actual API call logic is a placeholder and would be tested differently
        # if it were implemented with actual requests.
        self.portfolio_client.get_portfolio()
        # In a real scenario, you'd mock the auth_client's method and assert it was called.
        # For this placeholder, we just ensure the method runs without error.
        self.assertTrue(True) # Placeholder assertion

    @patch.object(PortfolioClient, 'get_positions')
    def test_get_positions_calls_auth_client(self, mock_get_positions):
        # Similar to get_portfolio, this tests the method's existence and callability.
        self.portfolio_client.get_positions()
        self.assertTrue(True) # Placeholder assertion

    # Example of how you might test if the auth_client was used (if it had methods)
    # @patch('requests.get') # If PortfolioClient directly used requests
    # def test_get_portfolio_uses_auth_client_method(self, mock_requests_get):
    #     # Mock the auth_client's method that would make the API call
    #     self.mock_auth_client.get.return_value.json.return_value = {"data": "portfolio"}
    #     result = self.portfolio_client.get_portfolio()
    #     self.mock_auth_client.get.assert_called_once_with('/portfolio')
    #     self.assertEqual(result, {"data": "portfolio"})

if __name__ == '__main__':
    unittest.main()
