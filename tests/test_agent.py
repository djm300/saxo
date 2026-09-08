import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from shared.agent import (
    AgentPlanError,
    chart_payload,
    execute_plan,
    portfolio_performance,
    sanitize,
    validate_plan,
)

NOW = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)


def thesis():
    return {
        "summary": "Demand compounds unless revenue growth falls below 5%.",
        "supporting_evidence": ["Primary filing"],
        "contrary_evidence": ["Valuation is elevated"],
        "bull_case": "Growth accelerates",
        "base_case": "Growth persists",
        "bear_case": "Margins contract",
        "catalysts": ["Next earnings"],
        "invalidation_conditions": ["Revenue growth below 5%"],
        "review_trigger": "Next results or a profit warning",
    }


def mandate(**overrides):
    value = {
        "allowed_asset_types": ["Stock", "Etf"],
        "max_orders_per_run": 5,
        "max_position_fraction": 0.10,
        "min_cash_fraction": 0.15,
        "max_run_turnover_fraction": 0.20,
        "max_rolling_turnover_fraction": 0.40,
        "max_spread_fraction": 0.01,
        "max_precheck_drift_fraction": 0.02,
        "plan_max_age_minutes": 360,
        "benchmark": {"symbol": "SPY", "asset_type": "Stock"},
    }
    value.update(overrides)
    return value


def plan(orders=None, run_id="run-1", created_at=NOW):
    return {
        "run_id": run_id,
        "environment": "sim",
        "created_at": created_at.isoformat(),
        "orders": orders or [],
    }


def order(side="buy", quantity=1, uic=101, asset_type="Stock"):
    value = {
        "symbol": "ABC:xams",
        "uic": uic,
        "asset_type": asset_type,
        "side": side,
        "quantity": quantity,
    }
    if side == "buy":
        value["thesis"] = thesis()
    return value


def client(position_quantity=0, position_value=0, precheck_notional=500):
    mock = MagicMock()
    mock.auth_client.baseurl = "https://gateway.saxobank.com/sim/openapi"
    mock.get_accounts.return_value = {
        "Data": [{"AccountKey": "secret-account", "AccountId": "hidden", "Currency": "EUR"}]
    }
    mock.get_balances.return_value = {
        "CashBalance": 5000,
        "TotalValue": 10000,
        "AvailableForTrading": 5000,
    }
    positions = []
    if position_quantity:
        positions.append(
            {
                "PositionBase": {
                    "AccountKey": "secret-account",
                    "Uic": 101,
                    "AssetType": "Stock",
                    "Amount": position_quantity,
                },
                "PositionView": {
                    "CurrentPrice": position_value / position_quantity,
                    "MarketValueInBaseCurrency": position_value,
                },
            }
        )
    mock.get_positions.return_value = {"Data": positions}
    mock.get_orders.return_value = {"Data": []}
    mock.get_order_history.return_value = {"Data": []}
    mock.get_instrument_by_uic.return_value = {
        "Identifier": 101,
        "Uic": 101,
        "Symbol": "ABC:xams",
        "AssetType": "Stock",
        "Currency": "EUR",
        "IsTradable": True,
    }
    mock.get_quote.return_value = {
        "Quote": {
            "Bid": 99.5,
            "Ask": 100,
            "LastTraded": 99.75,
            "DelayedByMinutes": 0,
            "MarketState": "Open",
        }
    }
    mock.precheck_order.return_value = {
        "PreCheckResult": "Ok",
        "EstimatedTotalCostInAccountCurrency": precheck_notional,
    }
    mock.place_order.return_value = {"OrderId": "placed-1", "AccountKey": "secret-account"}
    return mock


class TestAgentValidation(unittest.TestCase):
    def test_validates_zero_or_many_research_candidates_without_a_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            result = validate_plan(client(), plan(), mandate(), directory, NOW)
        self.assertEqual(result["orders"], [])
        watchlist = [{"symbol": f"IDEA{i}"} for i in range(250)]
        self.assertEqual(len(sanitize(watchlist)), 250)
        self.assertEqual(
            sanitize(
                {
                    "AuthorizationUrl": "secret",
                    "AccessToken": "secret",
                    "ClientId": "secret",
                    "raw": {"anything": "secret"},
                    "safe": 1,
                }
            ),
            {"safe": 1},
        )

    def test_buy_is_prechecked_and_sanitized(self):
        mock = client()
        with tempfile.TemporaryDirectory() as directory:
            result = validate_plan(mock, plan([order()]), mandate(), directory, NOW)
        self.assertAlmostEqual(result["planned_turnover_fraction"], 0.05)
        payload = result["orders"][0]["payload"]
        self.assertEqual(payload["ExternalReference"], "run-1-1")
        self.assertEqual(payload["OrderType"], "Market")
        public = sanitize(result)
        self.assertNotIn("AccountKey", json.dumps(public))

    def test_position_cash_and_turnover_guards(self):
        cases = [
            (client(position_quantity=10, position_value=900), mandate(), "position weight"),
            (client(precheck_notional=4000), mandate(max_position_fraction=1), "cash reserve"),
            (
                client(precheck_notional=2100),
                mandate(max_position_fraction=1),
                "per-run turnover",
            ),
        ]
        for mock, rules, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(AgentPlanError, expected):
                    validate_plan(mock, plan([order()]), rules, directory, NOW)

    def test_order_count_asset_sell_and_thesis_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AgentPlanError, "maximum number"):
                validate_plan(
                    client(), plan([order() for _ in range(6)]), mandate(), directory, NOW
                )
            with self.assertRaisesRegex(AgentPlanError, "not allowed"):
                validate_plan(
                    client(), plan([order(asset_type="CfdOnStock")]), mandate(), directory, NOW
                )
            leveraged = client()
            leveraged.get_instrument_by_uic.return_value.update(
                {"AssetType": "Etf", "Description": "Daily S&P 500 Bull 3X ETF"}
            )
            with self.assertRaisesRegex(AgentPlanError, "Leveraged or inverse"):
                validate_plan(
                    leveraged,
                    plan([order(asset_type="Etf")]),
                    mandate(),
                    directory,
                    NOW,
                )
            with self.assertRaisesRegex(AgentPlanError, "exceeds the current"):
                validate_plan(
                    client(position_quantity=1, position_value=100),
                    plan([order("sell", 2)]),
                    mandate(),
                    directory,
                    NOW,
                )
            invalid = order()
            invalid["thesis"].pop("contrary_evidence")
            with self.assertRaisesRegex(AgentPlanError, "contrary_evidence"):
                validate_plan(client(), plan([invalid]), mandate(), directory, NOW)

    def test_quote_and_precheck_fail_closed(self):
        for mutation, expected in [
            ({"MarketState": "Closed"}, "not open"),
            ({"DelayedByMinutes": 1}, "delayed"),
            ({"Bid": 90}, "spread"),
        ]:
            mock = client()
            mock.get_quote.return_value["Quote"].update(mutation)
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(AgentPlanError, expected):
                    validate_plan(mock, plan([order()]), mandate(), directory, NOW)
        mock = client()
        mock.precheck_order.return_value = {"PreCheckResult": "Error", "ErrorInfo": "No cash"}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AgentPlanError, "pre-check failed"):
                validate_plan(mock, plan([order()]), mandate(), directory, NOW)
        mock = client()
        mock.get_quote.return_value["Quote"].pop("DelayedByMinutes")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AgentPlanError, "establish whether"):
                validate_plan(mock, plan([order()]), mandate(), directory, NOW)

    def test_stale_duplicate_and_rolling_turnover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AgentPlanError, "stale"):
                validate_plan(
                    client(), plan(created_at=NOW - timedelta(days=1)), mandate(), root, NOW
                )
            receipt = root / "old" / "execution.json"
            receipt.parent.mkdir()
            receipt.write_text(
                json.dumps(
                    {
                        "run_id": "old",
                        "started_at": NOW.isoformat(),
                        "starting_net_equity": 10000,
                        "orders": [{"status": "placed", "notional_account_currency": 3900}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AgentPlanError, "seven-day"):
                validate_plan(client(precheck_notional=200), plan([order()]), mandate(), root, NOW)
            duplicate = root / "same" / "execution.json"
            duplicate.parent.mkdir()
            duplicate.write_text(json.dumps({"run_id": "run-1"}), encoding="utf-8")
            with self.assertRaisesRegex(AgentPlanError, "already"):
                validate_plan(client(), plan(), mandate(), root, NOW)


class TestAgentExecutionAndPerformance(unittest.TestCase):
    def test_sim_only_and_trading_enablement(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AgentPlanError, "outside Saxo SIM"):
                execute_plan(client(), plan(), mandate(), directory, NOW, False, True)
            with self.assertRaises(PermissionError):
                execute_plan(client(), plan(), mandate(), directory, NOW, True, False)
            live_client = client()
            live_client.auth_client.baseurl = "https://gateway.saxobank.com/openapi"
            with self.assertRaisesRegex(AgentPlanError, "not bound to Saxo SIM"):
                execute_plan(live_client, plan(), mandate(), directory, NOW, True, True)

    def test_executes_once_and_stops_on_first_failure(self):
        mock = client(precheck_notional=400)
        mock.place_order.side_effect = [{"OrderId": "1"}, RuntimeError("rejected")]
        with tempfile.TemporaryDirectory() as directory:
            result = execute_plan(
                mock,
                plan([order(uic=101), order(uic=102)]),
                mandate(max_position_fraction=1),
                directory,
                NOW,
                True,
                True,
            )
            self.assertEqual(result["status"], "partial")
            self.assertEqual(mock.place_order.call_count, 2)
            with self.assertRaisesRegex(AgentPlanError, "already"):
                execute_plan(client(), plan(), mandate(), directory, NOW, True, True)

    def test_indeterminate_order_response_is_a_failure(self):
        mock = client()
        mock.place_order.return_value = {}
        with tempfile.TemporaryDirectory() as directory:
            result = execute_plan(
                mock,
                plan([order()]),
                mandate(),
                directory,
                NOW,
                True,
                True,
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("indeterminate", result["orders"][0]["error"])

    def test_chart_and_benchmark_baseline(self):
        mock = client()
        mock.search_instruments.return_value = {
            "Data": [{"Symbol": "SPY:arcx", "Identifier": 999, "AssetType": "Stock"}]
        }
        mock.get_chart.return_value = {"Data": [{"Time": "x", "CloseBid": 100}]}
        self.assertEqual(chart_payload(mock, "SPY")["samples"][0]["CloseBid"], 100)
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.json"
            first = portfolio_performance(mock, mandate(), baseline, NOW)
            second = portfolio_performance(mock, mandate(), baseline, NOW + timedelta(days=1))
            self.assertTrue(baseline.exists())
        self.assertEqual(first["account_return"], 0)
        self.assertEqual(second["benchmark_return"], 0)


if __name__ == "__main__":
    unittest.main()
