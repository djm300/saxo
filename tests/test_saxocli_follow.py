import unittest
from unittest.mock import MagicMock, patch

from cli.saxocli import _extract_price, _extract_volume, _get_info_price_payload, _resolve_instrument


class TestSaxoCliFollow(unittest.TestCase):
    def test_extract_price_prefers_quote_last_traded(self):
        payload = {
            "Data": {
                "Quote": {
                    "LastTraded": 123.45,
                    "Mid": 123.40,
                    "Bid": 123.3,
                    "Ask": 123.5,
                }
            }
        }
        self.assertEqual(_extract_price(payload), 123.45)

    def test_extract_price_falls_back_to_bid_ask_midpoint(self):
        payload = {
            "Data": {
                "Quote": {
                    "Bid": 99.0,
                    "Ask": 101.0,
                }
            }
        }
        self.assertEqual(_extract_price(payload), 100.0)

    def test_extract_price_recursive_fallback(self):
        payload = {
            "Data": {
                "Nested": {
                    "Price": 88.8,
                }
            }
        }
        self.assertEqual(_extract_price(payload), 88.8)

    def test_extract_volume_finds_common_fields(self):
        payload = {
            "Data": {
                "Quote": {
                    "LastTradedVolume": 45000,
                }
            }
        }
        self.assertEqual(_extract_volume(payload), 45000.0)

    def test_extract_volume_returns_none_when_missing(self):
        payload = {"Data": {"Quote": {"Bid": 10.0, "Ask": 11.0}}}
        self.assertIsNone(_extract_volume(payload))

    @patch("cli.saxocli.api_request")
    def test_resolve_instrument_uses_instrument_search(self, mock_api_request):
        client = MagicMock()
        mock_api_request.return_value = (
            200,
            {
                "Data": [
                    {
                        "Identifier": 1636,
                        "AssetType": "Stock",
                        "Symbol": "ASML",
                        "Description": "ASML Holding",
                    }
                ]
            },
        )

        resolved = _resolve_instrument(client, "ASML", "Stock")

        self.assertEqual(resolved["uic"], 1636)
        self.assertEqual(resolved["symbol"], "ASML")
        self.assertEqual(resolved["asset_type"], "Stock")
        self.assertTrue(mock_api_request.called)

    @patch("cli.saxocli.api_request")
    @patch("cli.saxocli.get_account_context")
    def test_get_info_price_payload_retries_with_account_key(self, mock_get_account_context, mock_api_request):
        client = MagicMock()
        mock_get_account_context.return_value = {"account_key": "ABC123"}
        mock_api_request.side_effect = [
            (400, {"Message": "AccountKey required"}),
            (200, {"Data": {"Quote": {"LastTraded": 1.23}}}),
        ]

        payload = _get_info_price_payload(client, 1636, "Stock")

        self.assertEqual(payload["Data"]["Quote"]["LastTraded"], 1.23)
        second_call_params = mock_api_request.call_args_list[1].kwargs["params"]
        self.assertEqual(second_call_params.get("AccountKey"), "ABC123")


if __name__ == "__main__":
    unittest.main()
