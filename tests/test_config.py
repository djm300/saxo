import unittest
import os
import json
from unittest.mock import patch, mock_open
from saxo_trading_app.config import Config, _load_config_value, _load_params_json

class TestConfig(unittest.TestCase):

    def setUp(self):
        # Ensure no params.json exists before each test
        if os.path.exists("params.json"):
            os.remove("params.json")
        # Clear environment variables that might interfere
        os.environ.pop("REDIRECT_URI", None)
        os.environ.pop("SIMULATION_MODE", None)
        os.environ.pop("SAXO_AUTH_ENDPOINT", None)
        os.environ.pop("SAXO_TOKEN_ENDPOINT", None)
        os.environ.pop("SAXO_CLIENT_ID", None)
        os.environ.pop("TEST_KEY", None) # Added to clear TEST_KEY environment variable

    def tearDown(self):
        # Clean up after each test
        if os.path.exists("params.json"):
            os.remove("params.json")
        os.environ.pop("REDIRECT_URI", None)
        os.environ.pop("SIMULATION_MODE", None)
        os.environ.pop("SAXO_AUTH_ENDPOINT", None)
        os.environ.pop("SAXO_TOKEN_ENDPOINT", None)
        os.environ.pop("SAXO_CLIENT_ID", None)
        os.environ.pop("TEST_KEY", None) # Added to clear TEST_KEY environment variable

    def _create_params_json(self, content):
        with open("params.json", "w") as f:
            json.dump(content, f)

    # Test _load_config_value
    def test_load_config_value_from_env(self):
        os.environ["TEST_KEY"] = "env_value"
        self.assertEqual(_load_config_value("TEST_KEY", default="default"), "env_value")

    def test_load_config_value_from_json(self):
        self._create_params_json({"TEST_KEY": "json_value"})
        params_config = _load_params_json()
        self.assertEqual(_load_config_value("TEST_KEY", default="default", json_config=params_config), "json_value")

    def test_load_config_value_from_default(self):
        self.assertEqual(_load_config_value("NON_EXISTENT_KEY", default="default_value"), "default_value")

    def test_load_config_value_env_overrides_json(self):
        os.environ["TEST_KEY"] = "env_value"
        self._create_params_json({"TEST_KEY": "json_value"})
        params_config = _load_params_json()
        self.assertEqual(_load_config_value("TEST_KEY", default="default", json_config=params_config), "env_value")

    # Test _load_params_json
    def test_load_params_json_exists(self):
        json_content = {"key": "value"}
        self._create_params_json(json_content)
        self.assertEqual(_load_params_json(), json_content)

    def test_load_params_json_not_found(self):
        self.assertEqual(_load_params_json(), {})

    @patch("builtins.open", new_callable=mock_open, read_data="invalid json")
    def test_load_params_json_invalid(self, mock_file):
        self.assertEqual(_load_params_json(), {})

    # Test Config class
    def test_config_default_simulation_mode(self):
        config_instance = Config()
        self.assertTrue(config_instance.SIMULATION_MODE)
        self.assertEqual(config_instance.AUTH_ENDPOINT, "https://sim.logonvalidation.net/authorize")
        self.assertEqual(config_instance.TOKEN_FILE, "saxo_tokens_sim.json")

    def test_config_live_mode_from_env(self):
        os.environ["SIMULATION_MODE"] = "False"
        config_instance = Config()
        self.assertFalse(config_instance.SIMULATION_MODE)
        self.assertEqual(config_instance.AUTH_ENDPOINT, "https://live.logonvalidation.net/authorize")
        self.assertEqual(config_instance.TOKEN_FILE, "saxo_tokens_live.json")

    def test_config_live_mode_from_json(self):
        self._create_params_json({"SIMULATION_MODE": "False"})
        config_instance = Config()
        self.assertFalse(config_instance.SIMULATION_MODE)
        self.assertEqual(config_instance.AUTH_ENDPOINT, "https://live.logonvalidation.net/authorize")
        self.assertEqual(config_instance.TOKEN_FILE, "saxo_tokens_live.json")

    def test_config_redirect_uri_from_env(self):
        os.environ["REDIRECT_URI"] = "http://env.redirect"
        config_instance = Config()
        self.assertEqual(config_instance.REDIRECT_URI, "http://env.redirect")

    def test_config_redirect_uri_from_json(self):
        self._create_params_json({"REDIRECT_URI": "http://json.redirect"})
        config_instance = Config()
        self.assertEqual(config_instance.REDIRECT_URI, "http://json.redirect")

    def test_config_redirect_uri_default(self):
        config_instance = Config()
        self.assertEqual(config_instance.REDIRECT_URI, "https://djm300.github.io/saxo/oauth-redirect.html")

    def test_config_redirect_uri_tuple_handling(self):
        # Simulate a scenario where load_config_value might return a tuple
        # This is a bit tricky to mock directly for _load_config_value without affecting other tests.
        # Instead, we'll directly set the attribute to a tuple and check if it's handled.
        # This tests the logic within Config.__init__
        class MockConfigValueLoader:
            def __init__(self, value):
                self.value = value
            def __call__(self, key, default=None, json_config=None):
                if key == "REDIRECT_URI":
                    return self.value
                return default

        with patch("saxo_trading_app.config._load_config_value", new=MockConfigValueLoader(("http://tuple.redirect",))):
            config_instance = Config()
            self.assertEqual(config_instance.REDIRECT_URI, "http://tuple.redirect")

    def test_config_client_id_simulation(self):
        config_instance = Config()
        self.assertEqual(config_instance.CLIENT_ID, "89da08eeb25c428a9099f768cdb1696e")

    def test_config_client_id_live(self):
        os.environ["SIMULATION_MODE"] = "False"
        config_instance = Config()
        self.assertEqual(config_instance.CLIENT_ID, "28d17c462242447f94c4b0767c41a552")

    def test_config_order_details(self):
        config_instance = Config()
        self.assertIn('AccountKey', config_instance.ORDER_DETAILS)
        self.assertEqual(config_instance.ORDER_DETAILS['Amount'], 1)

if __name__ == '__main__':
    unittest.main()
