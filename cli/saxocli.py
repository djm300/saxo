#!/usr/bin/env python3
import argparse
import curses
import json
import logging
import math
import sys
import time
from datetime import datetime
from collections import deque
from urllib.parse import quote

import requests

from shared.runtime import create_client, ensure_authenticated, load_runtime_config

try:
    from prettytable import PrettyTable
except ImportError:
    PrettyTable = None


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        if default is None:
            return None
        return float(default)


def _pct_or_none(numerator, denominator):
    denom = abs(_safe_float(denominator, 0.0))
    if denom == 0:
        return None
    return (_safe_float(numerator, 0.0) / denom) * 100.0


def _fmt_pct(value):
    return "N/A" if value is None else f"{value:.2f}%"


def _lookup_instrument_name(client, uic, asset_type, cache):
    if not uic or not asset_type or asset_type == "N/A":
        return ""
    cache_key = (uic, asset_type)
    if cache_key in cache:
        return cache[cache_key]
    try:
        instrument = client.get_instrument_by_uic(uic, asset_type=asset_type)
        symbol = instrument.get("Symbol") or instrument.get("Description") or ""
    except Exception:
        symbol = ""
    cache[cache_key] = symbol
    return symbol


def parse_args():
    parser = argparse.ArgumentParser(prog="saxo", description="Saxo CLI utility")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable informational logs",
    )
    parser.add_argument(
        "--params",
        default="params.json",
        help="Path to params.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    portfolio_parser = subparsers.add_parser("portfolio", help="Show portfolio balances and positions")
    portfolio_parser.add_argument(
        "--format",
        default="prettytable",
        choices=["prettytable", "text", "json"],
        help="Output format",
    )

    orders_parser = subparsers.add_parser("orders", help="Get and/or cancel orders")
    orders_parser.add_argument(
        "--format",
        default="prettytable",
        choices=["prettytable", "text", "json"],
        help="Output format",
    )
    orders_parser.add_argument(
        "--order-id",
        help="Get one order by OrderId",
    )
    orders_parser.add_argument(
        "--cancel",
        metavar="ORDER_ID",
        help="Cancel an order by OrderId",
    )

    follow_parser = subparsers.add_parser("follow", help="Follow one instrument in a TUI with price/volume graphs")
    follow_parser.add_argument(
        "instrument",
        help="Instrument to follow: UIC (numeric) or symbol/keyword (e.g. ASML)",
    )
    follow_parser.add_argument(
        "--asset-type",
        default="Stock",
        help="Asset type for lookup/pricing (default: Stock)",
    )
    follow_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    follow_parser.add_argument(
        "--points",
        type=int,
        default=120,
        help="Maximum stored points in graph history (default: 120)",
    )
    return parser.parse_args()


def build_portfolio_payload(client):
    accounts = client.get_accounts().get("Data", [])
    account_by_id = {account.get("AccountId"): account for account in accounts if account.get("AccountId")}

    balance = client.get_portfolio()
    positions = client.get_positions().get("Data", [])

    payload_positions = []
    instrument_name_cache = {}
    for position in positions:
        position_base = position.get("PositionBase", {})
        position_view = position.get("PositionView", {})

        uic = position_base.get("Uic")
        asset_type = position_base.get("AssetType", "N/A")
        account_id = position_base.get("AccountId")

        symbol = _lookup_instrument_name(client, uic, asset_type, instrument_name_cache)

        payload_positions.append(
            {
                "account_id": account_id,
                "account_currency": account_by_id.get(account_id, {}).get("Currency", "N/A"),
                "uic": uic,
                "name": symbol or "N/A",
                "asset_type": asset_type,
                "amount": position_base.get("Amount", 0),
                "current_price": position_view.get("CurrentPrice", 0),
                "profit_loss_on_trade": position_view.get("ProfitLossOnTrade", 0),
                "daily_gain_abs": position_view.get("ProfitLossOnTradeIntradayInBaseCurrency", 0),
                "all_time_gain_abs": position_view.get("ProfitLossOnTradeInBaseCurrency", 0),
                "daily_gain_rel": _pct_or_none(
                    position_view.get("ProfitLossOnTradeIntradayInBaseCurrency", 0),
                    position_view.get("MarketValueOpenInBaseCurrency", 0),
                ),
                "all_time_gain_rel": _pct_or_none(
                    position_view.get("ProfitLossOnTradeInBaseCurrency", 0),
                    position_view.get("MarketValueOpenInBaseCurrency", 0),
                ),
            }
        )

    payload_positions.sort(key=lambda row: (str(row.get("asset_type") or ""), str(row.get("name") or "")))

    return {
        "cash_balance": balance.get("CashBalance", {}),
        "positions": payload_positions,
    }


def render_text(payload):
    print("Cash balance:")
    print(json.dumps(payload["cash_balance"], indent=2))
    print("")
    print("Positions:")
    header = (
        f"{'Account':<12} {'UIC':<10} {'Type':<10} {'Name':<20} {'Amount':>12} {'Price':>12} "
        f"{'DailyAbs':>12} {'Daily%':>10} {'AllTimeAbs':>12} {'AllTime%':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in payload["positions"]:
        print(
            f"{str(row['account_id']):<12} "
            f"{str(row['uic']):<10} "
            f"{str(row['asset_type']):<10} "
            f"{str(row['name']):<20} "
            f"{str(row['amount']):>12} "
            f"{str(row['current_price']):>12} "
            f"{str(row['daily_gain_abs']):>12} "
            f"{_fmt_pct(row['daily_gain_rel']):>10} "
            f"{str(row['all_time_gain_abs']):>12} "
            f"{_fmt_pct(row['all_time_gain_rel']):>10}"
        )


def render_prettytable(payload):
    if PrettyTable is None:
        raise RuntimeError("prettytable is not installed. Install it or use --format text/json.")

    print("Cash balance:")
    print(json.dumps(payload["cash_balance"], indent=2))
    print("")

    table = PrettyTable()
    table.field_names = [
        "Account",
        "UIC",
        "Type",
        "Name",
        "Amount",
        "Price",
        "Daily Abs",
        "Daily %",
        "All-time Abs",
        "All-time %",
        "Currency",
    ]
    for row in payload["positions"]:
        table.add_row(
            [
                row["account_id"],
                row["uic"],
                row["asset_type"],
                row["name"],
                row["amount"],
                row["current_price"],
                row["daily_gain_abs"],
                _fmt_pct(row["daily_gain_rel"]),
                row["all_time_gain_abs"],
                _fmt_pct(row["all_time_gain_rel"]),
                row["account_currency"],
            ]
        )
    print(table)


def ensure_fresh_access_token(client):
    if client.auth_client._is_access_token_expired():
        client.refresh_token()


def api_request(client, method, endpoint, params=None, data=None):
    ensure_fresh_access_token(client)
    access_token = client.auth_client.tokens.get("access_token")
    if not access_token:
        raise RuntimeError("No access token available.")

    url = f"{client.auth_client.baseurl}{endpoint}"
    response = requests.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params=params,
        json=data,
        timeout=30,
    )

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    return response.status_code, payload


def get_account_context(client):
    accounts = client.get_accounts().get("Data", [])
    if not accounts:
        raise RuntimeError("No accounts returned by /port/v1/accounts/me.")

    first = accounts[0]
    return {
        "account_key": first.get("AccountKey"),
        "client_key": first.get("ClientKey"),
    }


def get_orders_payload(client, order_id=None):
    account_context = get_account_context(client)
    if order_id:
        client_key = quote(account_context["client_key"], safe="")
        endpoint = f"/port/v1/orders/{client_key}/{order_id}"
    else:
        endpoint = "/port/v1/orders/me"

    status_code, payload = api_request(client, "GET", endpoint)
    if status_code >= 400:
        raise RuntimeError(f"Failed to get orders (HTTP {status_code}): {json.dumps(payload)}")
    return payload


def normalize_orders(payload):
    def find_first_value(data, keys, max_depth=6, _depth=0):
        if _depth > max_depth:
            return None

        if isinstance(data, dict):
            for key in keys:
                if key in data and data.get(key) is not None:
                    return data.get(key)
            for value in data.values():
                found = find_first_value(value, keys, max_depth=max_depth, _depth=_depth + 1)
                if found is not None:
                    return found
            return None

        if isinstance(data, list):
            for item in data:
                found = find_first_value(item, keys, max_depth=max_depth, _depth=_depth + 1)
                if found is not None:
                    return found
            return None

        return None

    def normalize_order_row(row):
        normalized = dict(row)
        field_variants = {
            "OrderId": ["OrderId"],
            "Status": ["Status"],
            "BuySell": ["BuySell"],
            "AssetType": ["AssetType"],
            "Uic": ["Uic", "UIC"],
            "Amount": ["Amount", "OrderAmount"],
            "AmountFilled": ["AmountFilled", "FilledAmount"],
            "OrderType": ["OrderType", "Type"],
            "Symbol": ["Symbol", "DisplaySymbol", "InstrumentSymbol"],
            "Description": ["Description", "InstrumentDescription", "InstrumentName"],
        }

        for target_field, keys in field_variants.items():
            if normalized.get(target_field) is None:
                normalized[target_field] = find_first_value(row, keys)

        return normalized

    if isinstance(payload, dict):
        if isinstance(payload.get("Data"), list):
            return [normalize_order_row(row) for row in payload.get("Data", [])]
        if "OrderId" in payload:
            return [normalize_order_row(payload)]
    if isinstance(payload, list):
        return [normalize_order_row(row) for row in payload]
    return []


def enrich_order_instruments(client, rows):
    instrument_name_cache = {}
    for row in rows:
        uic = row.get("Uic")
        asset_type = row.get("AssetType")
        symbol = row.get("Symbol") or row.get("DisplaySymbol") or row.get("InstrumentSymbol") or ""
        if not symbol:
            symbol = _lookup_instrument_name(client, uic, asset_type, instrument_name_cache)

        if not symbol:
            symbol = row.get("InstrumentDescription") or row.get("InstrumentName") or row.get("Description") or ""

        row["Instrument"] = symbol or "N/A"


def render_orders_json(payload):
    print(json.dumps(payload, indent=2))


def render_orders_text(payload, client):
    rows = normalize_orders(payload)
    if not rows:
        print("No orders found.")
        return

    enrich_order_instruments(client, rows)

    header = (
        f"{'OrderId':<14} {'Status':<12} {'BuySell':<8} {'AssetType':<10} "
        f"{'UIC':<10} {'Instrument':<24} {'Amount':>10} {'Filled':>10} {'Type':<10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{str(row.get('OrderId', 'N/A')):<14} "
            f"{str(row.get('Status', 'N/A')):<12} "
            f"{str(row.get('BuySell', 'N/A')):<8} "
            f"{str(row.get('AssetType', 'N/A')):<10} "
            f"{str(row.get('Uic', 'N/A')):<10} "
            f"{str(row.get('Instrument', 'N/A')):<24} "
            f"{str(row.get('Amount', 'N/A')):>10} "
            f"{str(row.get('AmountFilled', 'N/A')):>10} "
            f"{str(row.get('OrderType', 'N/A')):<10}"
        )


def render_orders_prettytable(payload, client):
    if PrettyTable is None:
        raise RuntimeError("prettytable is not installed. Install it or use --format text/json.")

    rows = normalize_orders(payload)
    if not rows:
        print("No orders found.")
        return

    enrich_order_instruments(client, rows)

    table = PrettyTable()
    table.field_names = ["OrderId", "Status", "BuySell", "AssetType", "UIC", "Instrument", "Amount", "Filled", "Type"]
    for row in rows:
        table.add_row(
            [
                row.get("OrderId", "N/A"),
                row.get("Status", "N/A"),
                row.get("BuySell", "N/A"),
                row.get("AssetType", "N/A"),
                row.get("Uic", "N/A"),
                row.get("Instrument", "N/A"),
                row.get("Amount", "N/A"),
                row.get("AmountFilled", "N/A"),
                row.get("OrderType", "N/A"),
            ]
        )
    print(table)


def render_orders(client, payload, output_format):
    if output_format == "json":
        render_orders_json(payload)
    elif output_format == "text":
        render_orders_text(payload, client)
    else:
        render_orders_prettytable(payload, client)


def cancel_order(client, order_id):
    account_context = get_account_context(client)
    account_key = account_context["account_key"]
    client_key = quote(account_context["client_key"], safe="")

    candidates = [
        {
            "label": "trade-v2-by-order-id-query-accountkey",
            "endpoint": f"/trade/v2/orders/{order_id}",
            "params": {"AccountKey": account_key},
            "data": None,
        },
        {
            "label": "trade-v2-by-order-id-body-accountkey",
            "endpoint": f"/trade/v2/orders/{order_id}",
            "params": None,
            "data": {"AccountKey": account_key},
        },
        {
            "label": "trade-v2-by-clientkey-order-id",
            "endpoint": f"/trade/v2/orders/{client_key}/{order_id}",
            "params": None,
            "data": None,
        },
    ]

    attempts = []
    for candidate in candidates:
        status_code, payload = api_request(
            client,
            "DELETE",
            candidate["endpoint"],
            params=candidate["params"],
            data=candidate["data"],
        )
        attempts.append(
            {
                "candidate": candidate["label"],
                "endpoint": candidate["endpoint"],
                "status_code": status_code,
                "response": payload,
            }
        )
        if 200 <= status_code < 300:
            return {
                "ok": True,
                "order_id": order_id,
                "used_candidate": candidate["label"],
                "status_code": status_code,
                "response": payload,
                "attempts": attempts,
            }

    return {
        "ok": False,
        "order_id": order_id,
        "message": "Could not cancel order with known endpoint variants.",
        "attempts": attempts,
    }


def _find_first_value(data, keys, max_depth=8, _depth=0):
    if _depth > max_depth:
        return None

    if isinstance(data, dict):
        for key in keys:
            if key in data and data.get(key) is not None:
                return data.get(key)
        for value in data.values():
            found = _find_first_value(value, keys, max_depth=max_depth, _depth=_depth + 1)
            if found is not None:
                return found
        return None

    if isinstance(data, list):
        for item in data:
            found = _find_first_value(item, keys, max_depth=max_depth, _depth=_depth + 1)
            if found is not None:
                return found
        return None

    return None


def _safe_addstr(stdscr, y, x, text, attr=0):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def _extract_price(payload):
    data = payload.get("Data") if isinstance(payload, dict) and isinstance(payload.get("Data"), dict) else payload
    if isinstance(data, dict):
        quote_data = data.get("Quote", {})
        if isinstance(quote_data, dict):
            if quote_data.get("LastTraded") is not None:
                return _safe_float(quote_data.get("LastTraded"), default=None)
            if quote_data.get("Mid") is not None:
                return _safe_float(quote_data.get("Mid"), default=None)
            bid = _safe_float(quote_data.get("Bid"), default=math.nan)
            ask = _safe_float(quote_data.get("Ask"), default=math.nan)
            if not math.isnan(bid) and not math.isnan(ask):
                return (bid + ask) / 2.0

        price_info = data.get("PriceInfo", {})
        if isinstance(price_info, dict):
            if price_info.get("LastTraded") is not None:
                return _safe_float(price_info.get("LastTraded"), default=None)
            if price_info.get("Mid") is not None:
                return _safe_float(price_info.get("Mid"), default=None)

    raw = _find_first_value(data, ["LastTraded", "LastPrice", "Mid", "Price"])
    return _safe_float(raw, default=None)


def _extract_volume(payload):
    data = payload.get("Data") if isinstance(payload, dict) and isinstance(payload.get("Data"), dict) else payload
    raw = _find_first_value(
        data,
        ["LastTradedVolume", "Volume", "TotalVolume", "Volume24Hour", "TradeVolume"],
    )
    return _safe_float(raw, default=None)


def _get_info_price_payload(client, uic, asset_type):
    account_key = None
    try:
        account_key = get_account_context(client).get("account_key")
    except Exception:
        account_key = None

    endpoint_candidates = [
        "/trade/v1/infoprices",
        "/trade/v1/prices",
    ]
    param_candidates = [
        {"Uic": uic, "AssetType": asset_type},
    ]
    if account_key:
        param_candidates.append({"Uic": uic, "AssetType": asset_type, "AccountKey": account_key})
    param_candidates.append({"Uic": uic, "AssetType": asset_type, "FieldGroups": "Quote,PriceInfo"})
    if account_key:
        param_candidates.append(
            {
                "Uic": uic,
                "AssetType": asset_type,
                "AccountKey": account_key,
                "FieldGroups": "Quote,PriceInfo",
            }
        )

    last_error = None
    for endpoint in endpoint_candidates:
        for params in param_candidates:
            status_code, payload = api_request(client, "GET", endpoint, params=params)
            if status_code < 400:
                return payload
            last_error = RuntimeError(f"{endpoint} (HTTP {status_code}): {json.dumps(payload)}")
    raise last_error or RuntimeError("Could not fetch market price data.")


def _resolve_instrument(client, instrument, asset_type):
    query = str(instrument).strip()
    query_upper = query.upper()
    if str(instrument).isdigit():
        uic = int(str(instrument))
        details = {}
        try:
            details = client.get_instrument_by_uic(uic, asset_type=asset_type)
        except Exception:
            details = {}
        return {
            "uic": uic,
            "asset_type": asset_type,
            "symbol": details.get("Symbol") or str(uic),
            "description": details.get("Description") or "",
        }

    status_code, payload = api_request(
        client,
        "GET",
        "/ref/v1/instruments",
        params={"Keywords": instrument, "AssetTypes": asset_type},
    )
    if status_code >= 400:
        raise RuntimeError(f"Instrument lookup failed (HTTP {status_code}): {json.dumps(payload)}")

    rows = payload.get("Data", []) if isinstance(payload, dict) else []
    if not rows:
        raise RuntimeError(f"No instrument found for query: {instrument} ({asset_type})")

    query = query_upper

    def score(row):
        symbol = str(row.get("Symbol") or "").upper()
        desc = str(row.get("Description") or "").upper()
        if symbol == query:
            return 0
        if symbol.startswith(query):
            return 1
        if query in symbol:
            return 2
        if query in desc:
            return 3
        return 4

    best = sorted(rows, key=score)[0]
    return {
        "uic": best.get("Identifier") or best.get("Uic") or best.get("UIC"),
        "asset_type": best.get("AssetType") or asset_type,
        "symbol": best.get("Symbol") or instrument,
        "description": best.get("Description") or "",
    }


def _draw_chart(stdscr, y, x, width, height, title, values, value_format):
    if width < 10 or height < 5:
        return

    inner_width = width - 2
    inner_height = height - 2
    clipped_values = list(values)[-inner_width:]

    _safe_addstr(stdscr, y, x, "+" + "-" * (width - 2) + "+")
    for row in range(1, height - 1):
        _safe_addstr(stdscr, y + row, x, "|")
        _safe_addstr(stdscr, y + row, x + width - 1, "|")
    _safe_addstr(stdscr, y + height - 1, x, "+" + "-" * (width - 2) + "+")

    if clipped_values:
        vmin = min(clipped_values)
        vmax = max(clipped_values)
        if abs(vmax - vmin) < 1e-12:
            vmax = vmin + 1.0
        for idx, value in enumerate(clipped_values):
            norm = (value - vmin) / (vmax - vmin)
            filled = int(round(norm * (inner_height - 1)))
            for dy in range(filled + 1):
                py = y + 1 + (inner_height - 1 - dy)
                px = x + 1 + idx
                _safe_addstr(stdscr, py, px, "█")
        stats = f"min={value_format(vmin)} max={value_format(max(clipped_values))}"
        _safe_addstr(stdscr, y, x + 2, f"[{title}] {stats}"[: max(0, width - 4)])
    else:
        _safe_addstr(stdscr, y, x + 2, f"[{title}] waiting for data"[: max(0, width - 4)])


def _run_follow_tui(stdscr, client, instrument_info, interval, points):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    price_history = deque(maxlen=max(10, int(points)))
    volume_history = deque(maxlen=max(10, int(points)))
    last_price = None
    last_volume = None
    last_error = ""
    last_update_str = "never"

    next_poll_at = 0.0
    while True:
        now = time.monotonic()
        if now >= next_poll_at:
            try:
                payload = _get_info_price_payload(client, instrument_info["uic"], instrument_info["asset_type"])
                price = _extract_price(payload)
                volume = _extract_volume(payload)

                if price is not None:
                    last_price = price
                    price_history.append(price)
                if volume is not None:
                    last_volume = volume
                    volume_history.append(volume)

                last_update_str = datetime.now().strftime("%H:%M:%S")
                last_error = ""
            except Exception as exc:
                last_error = str(exc)

            next_poll_at = now + max(0.2, float(interval))

        stdscr.erase()
        height, width = stdscr.getmaxyx()

        title = (
            f"{instrument_info.get('symbol', 'N/A')} | UIC {instrument_info.get('uic')} | "
            f"{instrument_info.get('asset_type', 'N/A')} | poll {interval:.1f}s | q=quit"
        )
        _safe_addstr(stdscr, 0, 0, title[: max(0, width - 1)], curses.A_BOLD)
        _safe_addstr(
            stdscr,
            1,
            0,
            f"Last price: {f'{last_price:.6f}' if last_price is not None else 'N/A'}   "
            f"Last volume: {f'{last_volume:,.0f}' if last_volume is not None else 'N/A'}   "
            f"Updated: {last_update_str}"[: max(0, width - 1)],
        )

        if instrument_info.get("description"):
            _safe_addstr(stdscr, 2, 0, str(instrument_info["description"])[: max(0, width - 1)])

        top = 4
        available = height - top - 2
        chart_height = max(5, available // 2)
        lower_chart_height = max(5, available - chart_height)

        _draw_chart(
            stdscr,
            y=top,
            x=0,
            width=width,
            height=chart_height,
            title="Price",
            values=price_history,
            value_format=lambda v: f"{v:.4f}",
        )
        _draw_chart(
            stdscr,
            y=top + chart_height,
            x=0,
            width=width,
            height=lower_chart_height,
            title="Volume",
            values=volume_history,
            value_format=lambda v: f"{v:,.0f}",
        )

        if last_error:
            _safe_addstr(stdscr, height - 1, 0, f"Error: {last_error}"[: max(0, width - 1)], curses.A_BOLD)

        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        time.sleep(0.02)


def main():
    args = parse_args()
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    config = load_runtime_config(params_path=args.params, logger=logging.getLogger("saxocli"))
    client = create_client(config)
    ensure_authenticated(client)

    if args.command == "portfolio":
        payload = build_portfolio_payload(client)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        elif args.format == "text":
            render_text(payload)
        else:
            render_prettytable(payload)
        return

    if args.command == "orders":
        if args.cancel:
            result = cancel_order(client, args.cancel)
            if args.format == "json":
                print(json.dumps(result, indent=2))
            elif args.format == "text":
                status = "success" if result.get("ok") else "failed"
                print(f"Cancel {status} for order {args.cancel}")
                print(json.dumps(result, indent=2))
            else:
                if PrettyTable is None:
                    raise RuntimeError("prettytable is not installed. Install it or use --format text/json.")
                table = PrettyTable()
                table.field_names = ["OrderId", "OK", "Candidate", "HTTP"]
                table.add_row([
                    result.get("order_id"),
                    result.get("ok"),
                    result.get("used_candidate", "N/A"),
                    result.get("status_code", "N/A"),
                ])
                print(table)
            if not result.get("ok"):
                raise SystemExit(1)
            return

        orders_payload = get_orders_payload(client, order_id=args.order_id)
        render_orders(client, orders_payload, args.format)
        return

    if args.command == "follow":
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("The follow command requires an interactive TTY terminal.")
        if args.interval <= 0:
            raise RuntimeError("--interval must be > 0")
        if args.points < 10:
            raise RuntimeError("--points must be >= 10")

        instrument_info = _resolve_instrument(client, args.instrument, args.asset_type)
        if not instrument_info.get("uic"):
            raise RuntimeError("Could not resolve instrument UIC. Try passing a numeric UIC directly.")

        curses.wrapper(
            _run_follow_tui,
            client,
            instrument_info,
            args.interval,
            args.points,
        )
        return


if __name__ == "__main__":
    main()
