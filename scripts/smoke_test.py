#!/usr/bin/env python3
"""Interactive, simulation-only smoke test for the Saxo CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


COMMANDS = [
    ("help", ["--help"]),
    ("auth status", ["auth", "status"]),
    ("account", ["account", "--json"]),
    ("balances", ["balances", "--json"]),
    ("portfolio", ["portfolio", "--json"]),
    ("positions", ["positions", "--json"]),
    ("position ASR", ["position", "ASR", "--json"]),
    ("orders", ["orders", "--json"]),
    ("instrument ASR", ["instrument", "ASR", "--json"]),
    ("quote ASR", ["quote", "ASR", "--json"]),
    (
        "order place market preview",
        ["order", "place", "ASR", "--side", "buy", "--quantity", "1", "--type", "market", "--json"],
    ),
    (
        "order place limit preview",
        [
            "order",
            "place",
            "ASR",
            "--side",
            "buy",
            "--quantity",
            "1",
            "--type",
            "limit",
            "--limit",
            "60",
            "--json",
        ],
    ),
    (
        "order cancel preview",
        ["order", "cancel", "SMOKE-ORDER-ID", "--account-key", "SMOKE-ACCOUNT", "--json"],
    ),
]

RESPONSE_SHAPES = {
    "auth status": {"environment": str, "authenticated": bool},
    "account": {"environment": str, "account_key": (str, type(None))},
    "balances": {
        "environment": str,
        "currency": (str, type(None)),
        "cash": (int, float),
        "net_equity": (int, float),
    },
    "portfolio": {"environment": str, "net_value": (int, float), "asset_classes": dict},
    "positions": {"environment": str, "positions": list},
    "position ASR": {"environment": str, "positions": list},
    "orders": {"environment": str, "orders": list},
    "instrument ASR": {"environment": str, "matches": list},
    "quote ASR": {
        "symbol": str,
        "bid": (int, float, type(None)),
        "ask": (int, float, type(None)),
        "mid": (int, float, type(None)),
        "is_delayed": (bool, type(None)),
    },
    "order place market preview": {"environment": str, "will_execute": bool, "order": dict},
    "order place limit preview": {"environment": str, "will_execute": bool, "order": dict},
    "order cancel preview": {
        "environment": str,
        "will_execute": bool,
        "order_ids": list,
        "account_key": str,
    },
}


def cli_command() -> list[str]:
    return [sys.executable, "-m", "cli"]


def validate_response_shape(name: str, payload: dict) -> str | None:
    expected = RESPONSE_SHAPES.get(name, {})
    missing = [field for field in expected if field not in payload]
    if missing:
        return f"missing response fields: {', '.join(missing)}"
    wrong_types = [
        f"{field}={type(payload[field]).__name__}"
        for field, allowed_types in expected.items()
        if not isinstance(payload[field], allowed_types)
    ]
    if wrong_types:
        return f"unexpected response field types: {', '.join(wrong_types)}"
    return None


def run_one(
    base_command: list[str], name: str, arguments: list[str], environment: dict[str, str]
) -> Result:
    command = base_command + ["--env", "sim"] + arguments
    try:
        completed = subprocess.run(
            command,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=environment,
            stdin=None,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return Result(name, "FAIL", "command timed out after 30 seconds")
    output = completed.stdout.strip()
    if name == "help":
        if completed.returncode == 0 and "usage:" in output:
            return Result(name, "PASS")
        return Result(name, "FAIL", f"unexpected help output: {output[:160]}")
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        return Result(name, "FAIL", f"non-JSON output: {output[:160]}")

    if (
        payload.get("error", {}).get("code") == "authentication_required"
        or completed.returncode == 2
    ):
        return Result(name, "FAIL", "authentication required; smoke test must be authenticated")
    if completed.returncode != 0:
        return Result(name, "FAIL", json.dumps(payload)[:240])
    shape_error = validate_response_shape(name, payload)
    if shape_error:
        return Result(name, "FAIL", shape_error)
    if name != "help" and payload.get("environment") not in (None, "sim"):
        return Result(name, "FAIL", "response did not identify simulation environment")
    return Result(name, "PASS")


def run_json_command(
    base_command: list[str], arguments: list[str], environment: dict[str, str]
) -> tuple[int, dict]:
    completed = subprocess.run(
        base_command + ["--env", "sim"] + arguments,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=environment,
        stdin=None,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        payload = {"error": {"message": completed.stdout.strip()[:240]}}
    return completed.returncode, payload


def require_authentication(base_command: list[str], environment: dict[str, str]) -> Result | None:
    """Ensure the smoke test has a valid simulation token before testing data commands."""
    status_code, status = run_json_command(base_command, ["auth", "status"], environment)
    if status_code != 0:
        return Result("authentication", "FAIL", json.dumps(status)[:240])
    if status.get("authenticated") is True:
        return None

    print("Authentication is required for the smoke test.", flush=True)
    print("Starting the normal interactive CLI login flow...", flush=True)
    completed = subprocess.run(
        base_command + ["--env", "sim", "auth", "login"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=environment,
        stdin=None,
        capture_output=False,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        return Result("authentication", "FAIL", "interactive authentication failed")

    status_code, status = run_json_command(base_command, ["auth", "status"], environment)
    if status_code != 0 or status.get("authenticated") is not True:
        return Result("authentication", "FAIL", "interactive login did not produce a valid token")
    return None


def run_simulation_order_cycle(base_command: list[str], environment: dict[str, str]) -> Result:
    account_code, account = run_json_command(base_command, ["account", "--json"], environment)
    account_key = account.get("account_key")
    if account_code != 0 or not account_key:
        return Result("real simulation order cycle", "FAIL", "could not resolve simulation account")

    quote_code, quote = run_json_command(base_command, ["quote", "ASR", "--json"], environment)
    bid = quote.get("bid")
    if quote_code != 0 or not isinstance(bid, (int, float)):
        return Result("real simulation order cycle", "FAIL", "could not resolve ASR bid")
    # Reuse the broker-provided bid so the price is guaranteed to match the
    # instrument's current tick-size increments.
    test_limit = float(bid)

    place_code, placed = run_json_command(
        base_command,
        [
            "order",
            "place",
            "ASR",
            "--side",
            "buy",
            "--quantity",
            "1",
            "--type",
            "limit",
            "--limit",
            str(test_limit),
            "--execute",
            "--json",
        ],
        environment,
    )
    if place_code != 0:
        return Result("real simulation order cycle", "FAIL", json.dumps(placed)[:240])
    response = placed.get("response", placed)
    order_id = response.get("OrderId") if isinstance(response, dict) else None
    if not order_id and isinstance(response, dict):
        order_id = next(
            (
                item.get("OrderId")
                for item in response.get("Orders", [])
                if isinstance(item, dict) and item.get("OrderId")
            ),
            None,
        )
    if not order_id:
        return Result("real simulation order cycle", "FAIL", "place response contained no OrderId")

    cancel_code, cancelled = run_json_command(
        base_command,
        [
            "order",
            "cancel",
            str(order_id),
            "--account-key",
            account_key,
            "--execute",
            "--json",
        ],
        environment,
    )
    if cancel_code != 0:
        return Result("real simulation order cycle", "FAIL", json.dumps(cancelled)[:240])
    return Result("real simulation order cycle", "PASS", f"placed and cancelled order {order_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Saxo CLI smoke tests against simulation only")
    parser.add_argument(
        "--execute-orders",
        action="store_true",
        help="Place and cancel one real limit order in simulation (never live)",
    )
    args = parser.parse_args(argv)

    environment = os.environ.copy()
    environment["SIMULATION_MODE"] = "True"
    environment["TRADING_ENABLED"] = "True" if args.execute_orders else "False"
    base_command = cli_command()
    results = []
    auth_failure = require_authentication(base_command, environment)
    if auth_failure:
        print(f"{auth_failure.status:>4}  {auth_failure.name} - {auth_failure.detail}", flush=True)
        return 1

    for name, arguments in COMMANDS:
        print(f"RUN   {name}", flush=True)
        result = run_one(base_command, name, arguments, environment)
        results.append(result)
        suffix = f" - {result.detail}" if result.detail else ""
        print(f"{result.status:>4}  {result.name}{suffix}", flush=True)

    if args.execute_orders:
        print("RUN   real simulation order cycle", flush=True)
        result = run_simulation_order_cycle(base_command, environment)
        results.append(result)
        suffix = f" - {result.detail}" if result.detail else ""
        print(f"{result.status:>4}  {result.name}{suffix}", flush=True)

    failures = [result for result in results if result.status == "FAIL"]
    successes = [result for result in results if result.status == "PASS"]
    print(
        f"\nSummary: {len(results)} checked | {len(successes)} successes | {len(failures)} failures"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
