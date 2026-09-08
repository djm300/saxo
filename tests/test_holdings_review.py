import unittest

from scripts.validate_holdings_review import validate_holdings_review


def position(symbol="ABC:xams", uic=1, quantity=10):
    return {"symbol": symbol, "uic": uic, "asset_type": "Stock", "quantity": quantity}


def assessment(symbol="ABC:xams", uic=1, quantity=10, decision="hold"):
    return {
        "symbol": symbol,
        "uic": uic,
        "asset_type": "Stock",
        "quantity": quantity,
        "decision": decision,
        "thesis_status": "intact",
        "rationale": "Current evidence supports this disposition.",
        "supporting_evidence": ["Current position and price evidence reviewed."],
        "contrary_evidence": ["A named downside risk remains."],
        "review_trigger": "Next results release",
    }


class TestHoldingsReview(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"timestamp": "2026-08-20T10:00:00Z", "positions": [position()]}
        self.review = {
            "run_id": "run-1",
            "snapshot_timestamp": self.snapshot["timestamp"],
            "portfolio_conclusion": "Hold after comparing the position with cash and alternatives.",
            "positions": [assessment()],
        }
        self.plan = {"run_id": "run-1", "orders": []}

    def test_accepts_complete_review(self):
        result = validate_holdings_review(self.snapshot, self.review, self.plan)
        self.assertEqual(result["positions_reviewed"], 1)

    def test_rejects_missing_or_extra_positions(self):
        self.review["positions"] = []
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

        self.review["positions"] = [assessment(), assessment("XYZ:xnas", 2)]
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

    def test_rejects_quantity_mismatch_and_thin_evidence(self):
        self.review["positions"][0]["quantity"] = 9
        with self.assertRaisesRegex(ValueError, "quantity does not match"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

        self.review["positions"][0]["quantity"] = 10
        self.review["positions"][0]["contrary_evidence"] = []
        with self.assertRaisesRegex(ValueError, "contrary_evidence"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

    def test_reconciles_existing_position_orders(self):
        self.plan["orders"] = [
            {"uic": 1, "asset_type": "Stock", "side": "buy", "quantity": 1}
        ]
        with self.assertRaisesRegex(ValueError, "requires add"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

        self.review["positions"][0]["decision"] = "add"
        validate_holdings_review(self.snapshot, self.review, self.plan)

        self.plan["orders"][0].update(side="sell", quantity=5)
        self.review["positions"][0]["decision"] = "exit"
        with self.assertRaisesRegex(ValueError, "full snapshot quantity"):
            validate_holdings_review(self.snapshot, self.review, self.plan)

        self.review["positions"][0]["decision"] = "trim"
        validate_holdings_review(self.snapshot, self.review, self.plan)


if __name__ == "__main__":
    unittest.main()
