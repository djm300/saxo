"""Deterministic portfolio-agent state, validation, and SIM execution."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .domain import first, normalize_balance, normalize_position, normalize_quote, number


class AgentPlanError(ValueError):
    """An agent plan is malformed or violates the configured mandate."""


PRIVATE_KEYS = {
    "accountkey",
    "accountid",
    "clientkey",
    "clientid",
    "userid",
    "handledby",
    "accesstoken",
    "refreshtoken",
    "authorizationurl",
    "raw",
}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REQUIRED_THESIS_FIELDS = {
    "summary",
    "supporting_evidence",
    "contrary_evidence",
    "bull_case",
    "base_case",
    "bear_case",
    "catalysts",
    "invalidation_conditions",
    "review_trigger",
}


def _data(value):
    return value.get("Data", []) if isinstance(value, dict) else []


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_time(value, field="timestamp"):
    if not isinstance(value, str) or not value.strip():
        raise AgentPlanError(f"{field} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentPlanError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise AgentPlanError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    os.replace(temporary, target)


def sanitize(value):
    """Remove identifiers and credentials before returning or persisting agent artifacts."""
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: sanitize(item)
        for key, item in value.items()
        if re.sub(r"[^a-z0-9]", "", key.casefold()) not in PRIVATE_KEYS and not key.startswith("_")
    }


def load_mandate(path="agent/mandate.json"):
    mandate = read_json(path)
    if not isinstance(mandate, dict):
        raise AgentPlanError(f"Mandate not found or invalid: {path}")
    return mandate


def build_agent_snapshot(client, environment="sim", instrument_cache_path=None):
    accounts = _data(client.get_accounts())
    if not accounts:
        raise AgentPlanError("Saxo returned no account for the portfolio agent.")
    account = accounts[0]
    raw_balance = client.get_balances()
    if isinstance(raw_balance, dict) and "Data" in raw_balance:
        raw_balance = (raw_balance.get("Data") or [{}])[0]
    balance = normalize_balance(raw_balance or {}, environment, account.get("Currency"))
    instrument_cache = read_json(instrument_cache_path, {}) if instrument_cache_path else {}
    instrument_cache = instrument_cache if isinstance(instrument_cache, dict) else {}
    cache_changed = False
    positions = []
    for raw in _data(client.get_positions()):
        base = raw.get("PositionBase", raw)
        uic = first(base, "Uic", "UIN")
        asset_type = first(base, "AssetType", default="Stock")
        cache_key = f"{uic}:{asset_type}"
        details = instrument_cache.get(cache_key, {})
        if uic is not None and not details:
            try:
                details = client.get_instrument_by_uic(uic, asset_type) or {}
                if instrument_cache_path:
                    instrument_cache[cache_key] = {
                        key: details.get(key)
                        for key in (
                            "Identifier",
                            "Uic",
                            "Symbol",
                            "Description",
                            "AssetType",
                            "Currency",
                        )
                        if details.get(key) is not None
                    }
                    cache_changed = True
            except Exception:
                details = {}
        position = normalize_position(raw, details, account.get("Currency"))
        position["account_key"] = first(base, "AccountKey", default=account.get("AccountKey"))
        positions.append(position)
    if instrument_cache_path and cache_changed:
        write_json(instrument_cache_path, sanitize(instrument_cache))
    return {
        "environment": environment,
        "timestamp": _utcnow().isoformat(),
        "account_key": first(account, "AccountKey", "AccountId"),
        "currency": account.get("Currency"),
        "balance": balance,
        "positions": positions,
        "working_orders": _data(client.get_orders()),
        "recent_order_history": _data(client.get_order_history(limit=200, today=False)),
    }


def _order_summary(order):
    display = order.get("DisplayAndFormat") or {}
    return {
        "activity_time": first(order, "ActivityTime", "OrderTime", "LastUpdated"),
        "order_id": first(order, "OrderId"),
        "external_reference": first(order, "ExternalReference"),
        "status": first(order, "Status"),
        "sub_status": first(order, "SubStatus"),
        "symbol": first(display, "Symbol", default=first(order, "Symbol")),
        "description": first(display, "Description"),
        "uic": first(order, "Uic"),
        "asset_type": first(order, "AssetType"),
        "side": first(order, "BuySell"),
        "quantity": first(order, "Amount"),
        "filled_quantity": first(order, "FilledAmount", "FillAmount"),
        "average_price": first(order, "AveragePrice", "ExecutionPrice"),
    }


def public_snapshot(client):
    snapshot = build_agent_snapshot(client, "sim", "agent/state/instruments.json")
    snapshot["working_orders"] = [_order_summary(order) for order in snapshot["working_orders"]]
    snapshot["recent_order_history"] = [
        _order_summary(order) for order in snapshot["recent_order_history"]
    ]
    return sanitize(snapshot)


def resolve_instrument(client, query, asset_type=None):
    matches = _data(client.search_instruments(query, asset_type))
    if not matches:
        raise AgentPlanError(f"No Saxo instrument matching {query!r} was found.")
    key = str(query).strip().casefold()
    exact = [
        item
        for item in matches
        if str(first(item, "Symbol", default="")).split(":", 1)[0].casefold() == key
        or str(first(item, "Identifier", "Uic", default="")).casefold() == key
    ]
    candidates = exact or matches
    if len(candidates) > 1:
        s_and_p = [
            item
            for item in candidates
            if "s&p 500" in str(first(item, "Description", default="")).casefold()
        ]
        if len(s_and_p) == 1:
            candidates = s_and_p
    if len(candidates) != 1:
        raise AgentPlanError(f"Saxo instrument query {query!r} is ambiguous.")
    return candidates[0]


def normalized_quote(client, uic, asset_type, symbol=None, currency=None, account_key=None):
    raw = client.get_quote(uic, asset_type, account_key)
    quote_data = raw.get("Quote", raw) if isinstance(raw, dict) else {}
    combined = dict(quote_data or {})
    if isinstance(raw, dict):
        details = raw.get("PriceInfoDetails") or {}
        for key in ("MarketState", "Timestamp", "LastUpdated", "DelayedByMinutes"):
            if combined.get(key) is None:
                combined[key] = first(raw, key, default=details.get(key))
    return normalize_quote(combined, symbol, currency), raw


def chart_payload(client, query, horizon=1440, count=120):
    if horizon not in {
        1,
        2,
        3,
        5,
        10,
        15,
        30,
        60,
        120,
        180,
        240,
        300,
        360,
        480,
        1440,
        10080,
        43200,
        129600,
        518400,
    }:
        raise AgentPlanError("Unsupported Saxo chart horizon.")
    if count < 1 or count > 1200:
        raise AgentPlanError("Chart count must be between 1 and 1200.")
    match = resolve_instrument(client, query)
    uic = first(match, "Identifier", "Uic")
    asset_type = first(match, "AssetType", default="Stock")
    raw = client.get_chart(uic, asset_type, horizon, count)
    return {
        "environment": "sim",
        "instrument": {
            "symbol": first(match, "Symbol"),
            "description": first(match, "Description"),
            "uic": uic,
            "asset_type": asset_type,
        },
        "chart_info": raw.get("ChartInfo", {}) if isinstance(raw, dict) else {},
        "display": raw.get("DisplayAndFormat", {}) if isinstance(raw, dict) else {},
        "samples": _data(raw),
    }


def _execution_files(runs_dir):
    root = Path(runs_dir)
    return root.glob("*/execution.json") if root.exists() else []


def _find_execution(run_id, runs_dir):
    for path in _execution_files(runs_dir):
        value = read_json(path, {}) or {}
        if value.get("run_id") == run_id:
            return path
    return None


def _rolling_turnover(runs_dir, now):
    cutoff = now - timedelta(days=7)
    rows = []
    for path in _execution_files(runs_dir):
        value = read_json(path, {}) or {}
        try:
            timestamp = _parse_time(
                value.get("started_at") or value.get("timestamp"), "execution timestamp"
            )
        except AgentPlanError:
            continue
        if timestamp < cutoff:
            continue
        notional = sum(
            abs(number(order.get("notional_account_currency")))
            for order in value.get("orders", [])
            if order.get("status") == "placed"
        )
        rows.append((timestamp, notional, number(value.get("starting_net_equity"))))
    rows.sort(key=lambda row: row[0])
    total = sum(row[1] for row in rows)
    starting_equity = next((row[2] for row in rows if row[2] > 0), 0)
    return total, starting_equity


def _validate_thesis(order):
    thesis = order.get("thesis")
    if not isinstance(thesis, dict):
        raise AgentPlanError("Every buy order must include a structured thesis.")
    missing = sorted(field for field in REQUIRED_THESIS_FIELDS if field not in thesis)
    if missing:
        raise AgentPlanError(f"Trade thesis is missing: {', '.join(missing)}")
    for field in (
        "supporting_evidence",
        "contrary_evidence",
        "catalysts",
        "invalidation_conditions",
    ):
        if not isinstance(thesis.get(field), list) or not thesis[field]:
            raise AgentPlanError(f"Trade thesis field {field!r} must be a non-empty list.")


def _reject_leveraged_etf(details, asset_type):
    if asset_type != "Etf":
        return
    leverage = number(first(details, "Leverage", "LeverageFactor", default=1), 1)
    description = " ".join(
        str(first(details, field, default="")) for field in ("Symbol", "Description", "Name")
    ).casefold()
    leveraged_name = re.search(
        r"\b(leveraged|inverse|ultra|[2-9]x)\b|\bdaily\b.*\b(bull|bear|short)\b",
        description,
    )
    if leverage > 1 or leveraged_name:
        raise AgentPlanError("Leveraged or inverse ETFs are not executable.")


def _quote_checks(quote, max_spread):
    market_state = str(quote.get("market_state") or "").casefold()
    if market_state != "open":
        raise AgentPlanError(f"Market is not open (state={quote.get('market_state')!r}).")
    if quote.get("is_delayed") is None and quote.get("delayed_by_minutes") is None:
        raise AgentPlanError("Saxo did not establish whether the quote is delayed.")
    if quote.get("is_delayed") is True or number(quote.get("delayed_by_minutes")) > 0:
        raise AgentPlanError("The Saxo quote is delayed.")
    bid, ask = number(quote.get("bid")), number(quote.get("ask"))
    if bid <= 0 or ask <= 0 or ask < bid:
        raise AgentPlanError("A valid positive bid and ask are required.")
    midpoint = (bid + ask) / 2
    spread = (ask - bid) / midpoint
    if spread > max_spread:
        raise AgentPlanError(f"Quoted spread {spread:.2%} exceeds {max_spread:.2%}.")
    return spread


def _precheck_notional(precheck):
    result = str(precheck.get("PreCheckResult") or "").casefold()
    if result != "ok" or precheck.get("ErrorInfo"):
        raise AgentPlanError(f"Saxo pre-check failed: {precheck.get('ErrorInfo') or result}")
    notional = abs(
        number(
            first(
                precheck,
                "EstimatedTotalCostInAccountCurrency",
                "EstimatedCashRequired",
                default=0,
            )
        )
    )
    if notional <= 0:
        raise AgentPlanError("Saxo pre-check did not return an account-currency order value.")
    return notional


def _validate_plan_header(plan, mandate, now):
    if not isinstance(plan, dict):
        raise AgentPlanError("Plan JSON must be an object.")
    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise AgentPlanError("run_id must be 1-64 safe filename characters.")
    if plan.get("environment") != "sim":
        raise AgentPlanError("Portfolio-agent plans must explicitly target sim.")
    created = _parse_time(plan.get("created_at"), "created_at")
    max_age = timedelta(minutes=number(mandate.get("plan_max_age_minutes"), 360))
    if created > now + timedelta(minutes=5) or now - created > max_age:
        raise AgentPlanError("Plan is stale or dated in the future.")
    orders = plan.get("orders")
    if not isinstance(orders, list):
        raise AgentPlanError("orders must be a JSON array.")
    if len(orders) > int(mandate["max_orders_per_run"]):
        raise AgentPlanError("Plan exceeds the maximum number of orders per run.")
    return run_id, orders


def _prepare_orders(client, orders, snapshot, mandate, historical_notional, weekly_equity):
    net_equity = number(snapshot["balance"].get("net_equity"))
    cash = number(snapshot["balance"].get("cash"))
    available = number(snapshot["balance"].get("available_for_trading"))
    if net_equity <= 0:
        raise AgentPlanError("A positive Saxo net equity value is required.")
    position_values = {}
    position_quantities = {}
    for position in snapshot["positions"]:
        try:
            key = (int(position.get("uic")), str(position.get("asset_type")))
        except (TypeError, ValueError):
            continue
        position_values[key] = position_values.get(key, 0) + abs(
            number(position.get("market_value"))
        )
        position_quantities[key] = position_quantities.get(key, 0) + number(
            position.get("quantity")
        )
    prepared = []
    run_notional = 0.0
    allowed_assets = set(mandate["allowed_asset_types"])
    sorted_orders = sorted(
        enumerate(orders), key=lambda item: 0 if str(item[1].get("side")).lower() == "sell" else 1
    )
    for original_index, order in sorted_orders:
        if not isinstance(order, dict):
            raise AgentPlanError("Each order must be a JSON object.")
        side = str(order.get("side") or "").lower()
        if side not in {"buy", "sell"}:
            raise AgentPlanError("Order side must be buy or sell.")
        quantity = number(order.get("quantity"))
        if not math.isfinite(quantity) or quantity <= 0:
            raise AgentPlanError("Order quantity must be positive and finite.")
        try:
            uic = int(order.get("uic"))
        except (TypeError, ValueError) as exc:
            raise AgentPlanError("Every order requires an integer Saxo uic.") from exc
        asset_type = str(order.get("asset_type") or "")
        if asset_type not in allowed_assets:
            raise AgentPlanError(f"Asset type {asset_type!r} is not allowed.")
        if side == "buy":
            _validate_thesis(order)
        key = (uic, asset_type)
        held_quantity = position_quantities.get(key, 0)
        if side == "sell" and quantity > held_quantity + 1e-9:
            raise AgentPlanError("A sell order exceeds the current long holding.")
        details = client.get_instrument_by_uic(uic, asset_type) or {}
        if first(details, "AssetType", default=asset_type) != asset_type:
            raise AgentPlanError("The plan asset type does not match Saxo instrument details.")
        if details.get("IsTradable") is False:
            raise AgentPlanError("Saxo marks the instrument as non-tradable.")
        _reject_leveraged_etf(details, asset_type)
        symbol = order.get("symbol") or first(details, "Symbol", "Identifier")
        quote, _raw_quote = normalized_quote(
            client,
            uic,
            asset_type,
            symbol,
            first(details, "Currency"),
            snapshot["account_key"],
        )
        spread = _quote_checks(quote, number(mandate["max_spread_fraction"]))
        payload = {
            "AccountKey": snapshot["account_key"],
            "Amount": quantity,
            "AssetType": asset_type,
            "BuySell": side.capitalize(),
            "ExternalReference": f"{order.get('_run_id', 'agent')}-{original_index + 1}"[:50],
            "ManualOrder": False,
            "OrderDuration": {"DurationType": "DayOrder"},
            "OrderType": "Market",
            "Uic": uic,
        }
        precheck = client.precheck_order(payload)
        notional = _precheck_notional(precheck)
        current_value = position_values.get(key, 0)
        post_value = current_value + notional if side == "buy" else max(0, current_value - notional)
        if (
            side == "buy"
            and post_value / net_equity > number(mandate["max_position_fraction"]) + 1e-9
        ):
            raise AgentPlanError("Buy would exceed the maximum post-trade position weight.")
        cash = cash - notional if side == "buy" else cash + notional
        available = available - notional if side == "buy" else available + notional
        if side == "buy":
            if available < -1e-9:
                raise AgentPlanError("Order sequence exceeds cash available for trading.")
            if cash / net_equity < number(mandate["min_cash_fraction"]) - 1e-9:
                raise AgentPlanError("Order sequence would breach the minimum cash reserve.")
        run_notional += notional
        if run_notional / net_equity > number(mandate["max_run_turnover_fraction"]) + 1e-9:
            raise AgentPlanError("Plan exceeds the per-run turnover ceiling.")
        weekly_denominator = weekly_equity or net_equity
        if (historical_notional + run_notional) / weekly_denominator > number(
            mandate["max_rolling_turnover_fraction"]
        ) + 1e-9:
            raise AgentPlanError("Plan exceeds the rolling seven-day turnover ceiling.")
        position_values[key] = post_value
        position_quantities[key] = (
            held_quantity + quantity if side == "buy" else held_quantity - quantity
        )
        prepared.append(
            {
                "sequence": original_index + 1,
                "symbol": symbol,
                "uic": uic,
                "asset_type": asset_type,
                "side": side,
                "quantity": quantity,
                "spread_fraction": spread,
                "notional_account_currency": notional,
                "precheck_result": precheck.get("PreCheckResult"),
                "payload": payload,
                "thesis": order.get("thesis"),
            }
        )
    return prepared, run_notional, net_equity


def validate_plan(client, plan, mandate, runs_dir="agent/runs", now=None, check_duplicate=True):
    now = now or _utcnow()
    run_id, orders = _validate_plan_header(plan, mandate, now)
    if check_duplicate and _find_execution(run_id, runs_dir):
        raise AgentPlanError(f"Run {run_id!r} already has an execution receipt.")
    tagged_orders = [dict(order, _run_id=run_id) for order in orders]
    snapshot = build_agent_snapshot(client, "sim")
    historical, weekly_equity = _rolling_turnover(runs_dir, now)
    prepared, run_notional, net_equity = _prepare_orders(
        client, tagged_orders, snapshot, mandate, historical, weekly_equity
    )
    result = {
        "run_id": run_id,
        "environment": "sim",
        "validated_at": now.isoformat(),
        "starting_net_equity": net_equity,
        "starting_cash": number(snapshot["balance"].get("cash")),
        "historical_seven_day_notional": historical,
        "planned_turnover_notional": run_notional,
        "planned_turnover_fraction": run_notional / net_equity if net_equity else 0,
        "orders": prepared,
        "_snapshot": snapshot,
    }
    return result


def public_validation(client, plan, mandate, runs_dir="agent/runs", now=None):
    return sanitize(validate_plan(client, plan, mandate, runs_dir, now))


def execute_plan(
    client,
    plan,
    mandate,
    runs_dir="agent/runs",
    now=None,
    simulation_mode=True,
    trading_enabled=False,
):
    if not simulation_mode:
        raise AgentPlanError("The portfolio agent refuses to execute outside Saxo SIM.")
    baseurl = str(getattr(getattr(client, "auth_client", None), "baseurl", "")).casefold()
    if "/sim/" not in baseurl:
        raise AgentPlanError("The portfolio agent refuses a client that is not bound to Saxo SIM.")
    if not trading_enabled:
        raise PermissionError("Set TRADING_ENABLED=true to execute a validated SIM plan.")
    now = now or _utcnow()
    validation = validate_plan(client, plan, mandate, runs_dir, now)
    run_id = validation["run_id"]
    receipt_path = Path(runs_dir) / run_id / "execution.json"
    receipt = {
        "run_id": run_id,
        "environment": "sim",
        "started_at": now.isoformat(),
        "starting_net_equity": validation["starting_net_equity"],
        "status": "running",
        "orders": [],
    }
    write_json(receipt_path, sanitize(receipt))
    for prepared in validation["orders"]:
        row = {
            key: prepared[key]
            for key in (
                "sequence",
                "symbol",
                "uic",
                "asset_type",
                "side",
                "quantity",
                "notional_account_currency",
            )
        }
        try:
            fresh = build_agent_snapshot(client, "sim")
            fresh_quote, _raw = normalized_quote(
                client,
                prepared["uic"],
                prepared["asset_type"],
                prepared["symbol"],
                account_key=fresh["account_key"],
            )
            _quote_checks(fresh_quote, number(mandate["max_spread_fraction"]))
            payload = dict(prepared["payload"], AccountKey=fresh["account_key"])
            fresh_precheck = client.precheck_order(payload)
            fresh_notional = _precheck_notional(fresh_precheck)
            drift = (
                abs(fresh_notional - prepared["notional_account_currency"])
                / prepared["notional_account_currency"]
            )
            if drift > number(mandate.get("max_precheck_drift_fraction"), 0.02):
                raise AgentPlanError("Fresh pre-check cost moved beyond the allowed drift.")
            fresh_equity = number(fresh["balance"].get("net_equity"))
            fresh_cash = number(fresh["balance"].get("cash"))
            if fresh_equity <= 0:
                raise AgentPlanError("Fresh Saxo state has no positive net equity.")
            matching = [
                position
                for position in fresh["positions"]
                if number(position.get("uic"), -1) == prepared["uic"]
                and position.get("asset_type") == prepared["asset_type"]
            ]
            held_quantity = sum(number(position.get("quantity")) for position in matching)
            held_value = sum(abs(number(position.get("market_value"))) for position in matching)
            if prepared["side"] == "sell" and prepared["quantity"] > held_quantity + 1e-9:
                raise AgentPlanError("Fresh holding is insufficient for the planned reduction.")
            if prepared["side"] == "buy":
                if (held_value + fresh_notional) / fresh_equity > number(
                    mandate["max_position_fraction"]
                ) + 1e-9:
                    raise AgentPlanError("Fresh state would exceed maximum position weight.")
                if (fresh_cash - fresh_notional) / fresh_equity < number(
                    mandate["min_cash_fraction"]
                ) - 1e-9:
                    raise AgentPlanError("Fresh state would breach the minimum cash reserve.")
            placed_notional = sum(
                number(item.get("notional_account_currency"))
                for item in receipt["orders"]
                if item.get("status") == "placed"
            )
            if (placed_notional + fresh_notional) / validation["starting_net_equity"] > number(
                mandate["max_run_turnover_fraction"]
            ) + 1e-9:
                raise AgentPlanError("Fresh execution would exceed per-run turnover.")
            weekly_equity = validation["starting_net_equity"]
            if (
                validation["historical_seven_day_notional"] + placed_notional + fresh_notional
            ) / weekly_equity > number(mandate["max_rolling_turnover_fraction"]) + 1e-9:
                raise AgentPlanError("Fresh execution would exceed seven-day turnover.")
            response = client.place_order(payload)
            order_ids = []
            if isinstance(response, dict):
                if response.get("OrderId"):
                    order_ids.append(response["OrderId"])
                order_ids.extend(
                    item.get("OrderId")
                    for item in response.get("Orders", [])
                    if isinstance(item, dict) and item.get("OrderId")
                )
            if not order_ids:
                raise AgentPlanError("Saxo returned an indeterminate order response.")
            row.update(
                {
                    "status": "placed",
                    "notional_account_currency": fresh_notional,
                    "order_ids": order_ids,
                    "response": sanitize(response),
                }
            )
        except Exception as exc:
            row.update({"status": "failed", "error": str(exc)})
            receipt["orders"].append(row)
            receipt["status"] = (
                "partial"
                if any(item.get("status") == "placed" for item in receipt["orders"])
                else "failed"
            )
            receipt["completed_at"] = _utcnow().isoformat()
            write_json(receipt_path, sanitize(receipt))
            break
        receipt["orders"].append(row)
        write_json(receipt_path, sanitize(receipt))
    else:
        receipt["status"] = "completed"
        receipt["completed_at"] = _utcnow().isoformat()
        write_json(receipt_path, sanitize(receipt))
    return sanitize(receipt)


def portfolio_performance(
    client,
    mandate,
    baseline_path="agent/state/baseline.json",
    now=None,
):
    now = now or _utcnow()
    accounts = _data(client.get_accounts())
    if not accounts:
        raise AgentPlanError("Saxo returned no account for performance measurement.")
    account = accounts[0]
    raw_balance = client.get_balances()
    if isinstance(raw_balance, dict) and "Data" in raw_balance:
        raw_balance = (raw_balance.get("Data") or [{}])[0]
    balance = normalize_balance(raw_balance or {}, "sim", account.get("Currency"))
    benchmark_config = mandate.get("benchmark", {})
    query = benchmark_config.get("symbol", "SPY")
    if benchmark_config.get("uic") is not None:
        match = client.get_instrument_by_uic(
            int(benchmark_config["uic"]), benchmark_config.get("asset_type", "Etf")
        )
        if not isinstance(match, dict) or not match:
            raise AgentPlanError("Configured benchmark instrument could not be resolved by Saxo.")
    else:
        match = resolve_instrument(client, query, benchmark_config.get("asset_type"))
    uic = first(match, "Identifier", "Uic")
    asset_type = first(match, "AssetType", default="Stock")
    quote, _raw = normalized_quote(client, uic, asset_type, first(match, "Symbol"))
    benchmark_price = number(first(quote, "last", "mid", "bid", "ask"))
    net_equity = number(balance.get("net_equity"))
    if benchmark_price <= 0 or net_equity <= 0:
        raise AgentPlanError("Positive portfolio and benchmark values are required.")
    baseline = read_json(baseline_path)
    if baseline is None:
        baseline = {
            "environment": "sim",
            "started_at": now.isoformat(),
            "portfolio_net_equity": net_equity,
            "currency": account.get("Currency"),
            "benchmark": {
                "symbol": first(match, "Symbol", default=query),
                "uic": uic,
                "asset_type": asset_type,
                "price": benchmark_price,
            },
        }
        write_json(baseline_path, sanitize(baseline))
    account_return = net_equity / number(baseline["portfolio_net_equity"]) - 1
    benchmark_return = benchmark_price / number(baseline["benchmark"]["price"]) - 1
    return {
        "environment": "sim",
        "timestamp": now.isoformat(),
        "baseline": baseline,
        "current_portfolio_net_equity": net_equity,
        "current_benchmark_price": benchmark_price,
        "account_return": account_return,
        "benchmark_return": benchmark_return,
        "excess_return": account_return - benchmark_return,
    }
