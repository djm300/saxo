import unittest
from unittest.mock import MagicMock

from cli.saxocli import enrich_order_instruments


class TestSaxoCliOrders(unittest.TestCase):
    def test_enrich_order_instruments_prefers_uic_lookup_over_generic_description(self):
        client = MagicMock()
        client.get_instrument_by_uic.return_value = {"Symbol": "ASML"}

        rows = [
            {
                "OrderId": 1,
                "Uic": 999999,
                "AssetType": "Stock",
                "Description": "Euronext Amsterdam",
            }
        ]

        enrich_order_instruments(client, rows)

        self.assertEqual(rows[0]["Instrument"], "ASML")
        client.get_instrument_by_uic.assert_called_once_with(999999, asset_type="Stock")


if __name__ == "__main__":
    unittest.main()
