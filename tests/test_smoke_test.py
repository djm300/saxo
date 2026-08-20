import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.smoke_test import require_authentication, run_one, validate_response_shape


class TestSmokeResponseValidation(unittest.TestCase):
    def test_valid_quote_shape(self):
        self.assertIsNone(
            validate_response_shape(
                "quote ASR",
                {"symbol": "ASRNL:xams", "bid": 1, "ask": 2, "mid": 1.5, "is_delayed": True},
            )
        )

    def test_missing_field_is_detected(self):
        error = validate_response_shape("balances", {"environment": "sim", "cash": 1})
        self.assertIn("missing response fields", error)

    def test_authentication_required_is_a_failure(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout=json.dumps({"error": {"code": "authentication_required"}}),
            stderr="",
        )
        with patch("scripts.smoke_test.subprocess.run", return_value=completed):
            result = run_one(["saxo"], "positions", ["positions", "--json"], {})

        self.assertEqual(result.status, "FAIL")
        self.assertIn("authentication required", result.detail)

    def test_smoke_starts_interactive_login_when_status_is_unauthenticated(self):
        status_before = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"authenticated": False}), stderr=""
        )
        login = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        status_after = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"authenticated": True}), stderr=""
        )
        with patch(
            "scripts.smoke_test.subprocess.run",
            side_effect=[status_before, login, status_after],
        ) as run:
            result = require_authentication(["saxo"], {})

        self.assertIsNone(result)
        self.assertIsNone(run.call_args_list[1].kwargs["stdin"])


if __name__ == "__main__":
    unittest.main()
