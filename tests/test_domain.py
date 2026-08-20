import unittest

from shared.domain import (
    first,
    normalize_account,
    normalize_balance,
    normalize_position,
    normalize_quote,
    number,
    portfolio_summary,
    roll_analysis,
)


class TestDomain(unittest.TestCase):
    def test_small_helpers_and_normalizers(self):
        self.assertEqual(first({"a": None, "b": 2}, "a", "b"), 2)
        self.assertEqual(first(None, "a", default="fallback"), "fallback")
        self.assertEqual(number("bad", 7), 7)
        self.assertEqual(number(None), 0)
        self.assertEqual(
            normalize_account({"AccountId": "A", "AccountCurrency": "EUR"}, "sim")["currency"],
            "EUR",
        )
        balance = normalize_balance({"AccountCurrency": "EUR", "Cash": 10, "NetEquity": 20}, "sim")
        self.assertEqual(balance["cash"], 10)
        self.assertEqual(balance["net_equity"], 20)

    def test_position_and_quote_variants(self):
        position = normalize_position(
            {
                "PositionBase": {"UIN": 42, "Quantity": -2, "AssetType": "Stock"},
                "PositionView": {"MarketPrice": 5, "Currency": "USD", "ProfitLossOnTrade": -3},
            },
            {"Identifier": "ABC", "Name": "Acme"},
            "EUR",
        )
        self.assertEqual(position["symbol"], "ABC")
        self.assertEqual(position["market_value"], -10)
        self.assertEqual(position["side"], "short")
        quote = normalize_quote({"BidAsk": {"Bid": 9}, "Ask": 11, "DelayedByMinutes": 5}, "ABC")
        self.assertEqual(quote["bid"], 9)
        self.assertEqual(quote["mid"], 10)
        self.assertTrue(quote["is_delayed"])
        self.assertEqual(normalize_quote({"IsDelayed": False}, "X")["is_delayed"], False)

    def test_portfolio_summary_and_roll_analysis(self):
        positions = [
            {"symbol": "A", "asset_type": "Stock", "market_value": 100},
            {"symbol": "B", "asset_type": "Option", "market_value": -20},
            {"symbol": "C", "asset_type": "Bond", "market_value": 10},
        ]
        summary = portfolio_summary(positions, {"environment": "sim", "net_equity": 0, "cash": 5})
        self.assertEqual(summary["net_value"], 90)
        self.assertEqual(summary["asset_classes"]["stocks"], 100)
        self.assertEqual(summary["asset_classes"]["options_market_value"], -20)
        self.assertEqual(len(summary["largest_positions"]), 3)
        roll = roll_analysis(
            {"bid": 1, "ask": 2, "strike": 100}, {"bid": 3, "ask": 4, "strike": 110}, 2
        )
        self.assertEqual(roll["conservative_net_credit"], 200)
        self.assertEqual(roll["strike_increase"], 10)


if __name__ == "__main__":
    unittest.main()
