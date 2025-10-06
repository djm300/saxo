import unittest
from unittest.mock import patch, MagicMock

# Assuming saxo_sdk is in the parent directory or accessible in the Python path
from saxo_sdk.client import SaxoClient

class TestSaxoClient(unittest.TestCase):
    def setUp(self):
        # Mock the underlying clients
        self.mock_auth_client = MagicMock()
        self.mock_portfolio_client = MagicMock()
        self.mock_order_client = MagicMock()

        # Patch the imports within SaxoClient to use our mocks
        # This is a bit more involved as we need to patch where SaxoClient *uses* them
        # A simpler approach for this test is to patch the __init__ of SaxoClient
        # to inject our mocks directly, or patch the classes it imports.
        # Let's patch the classes it imports.

        self.patcher_auth = patch('saxo_sdk.client.AuthorizationCodeClient', return_value=self.mock_auth_client)
        self.patcher_portfolio = patch('saxo_sdk.client.PortfolioClient', return_value=self.mock_portfolio_client)
        self.patcher_orders = patch('saxo_sdk.client.OrderClient', return_value=self.mock_order_client)

        self.mock_auth = self.patcher_auth.start()
        self.mock_portfolio = self.patcher_portfolio.start()
        self.mock_orders = self.patcher_orders.start()

        # Initialize SaxoClient with dummy arguments
        self.client = SaxoClient(
            client_id="dummy_id",
            client_secret="dummy_secret",
            redirect_uri="dummy_uri",
            auth_endpoint="dummy_auth",
            token_endpoint="dummy_token"
        )

    def tearDown(self):
        self.patcher_auth.stop()
        self.patcher_portfolio.stop()
        self.patcher_orders.stop()

    def test_init(self):
        # Check if the underlying clients were initialized correctly
        self.mock_auth.assert_called_once_with(
            client_id="dummy_id",
            client_secret="dummy_secret",
            redirect_uri="dummy_uri",
            auth_endpoint="dummy_auth",
            token_endpoint="dummy_token",
            token_file='tokens.json' # Default value
        )
        self.mock_portfolio.assert_called_once_with(self.mock_auth_client)
        self.mock_orders.assert_called_once_with(self.mock_auth_client)
        self.assertEqual(self.client.scope, "required_scope") # Default scope

    def test_get_authorization_url(self):
        self.client.get_authorization_url()
        self.mock_auth_client.get_authorization_url.assert_called_once_with(scope=self.client.scope)

    def test_get_token(self):
        code = "test_code"
        self.client.get_token(code)
        self.mock_auth_client.get_token.assert_called_once_with(code)

    def test_refresh_token(self):
        self.client.refresh_token()
        self.mock_auth_client.refresh_token.assert_called_once()

    def test_get_portfolio(self):
        self.client.get_portfolio()
        self.mock_portfolio_client.get_portfolio.assert_called_once()

    def test_get_positions(self):
        self.client.get_positions()
        self.mock_portfolio_client.get_positions.assert_called_once()

    def test_place_order(self):
        order_details = {"instrument": "MSFT", "quantity": 5}
        self.client.place_order(order_details)
        self.mock_order_client.place_order.assert_called_once_with(order_details)

    def test_get_order_status(self):
        order_id = "order_xyz"
        self.client.get_order_status(order_id)
        self.mock_order_client.get_order_status.assert_called_once_with(order_id)

    def test_get_all_orders(self):
        self.client.get_all_orders()
        self.mock_order_client.get_all_orders.assert_called_once()

if __name__ == '__main__':
    unittest.main()
