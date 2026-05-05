#!/usr/bin/env python3
import argparse
import json
import logging

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

    positions_parser = subparsers.add_parser("positions", help="Show current positions")
    positions_parser.add_argument(
        "--format",
        default="prettytable",
        choices=["prettytable", "text", "json"],
        help="Output format",
    )

    return parser.parse_args()


def build_positions_payload(client):
    accounts = client.get_accounts().get("Data", [])
    account_by_id = {account.get("AccountId"): account for account in accounts if account.get("AccountId")}

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
        "positions": payload_positions,
    }


def render_text(payload):
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


def main():
    args = parse_args()
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    config = load_runtime_config(params_path=args.params, logger=logging.getLogger("saxocli"))
    client = create_client(config)
    ensure_authenticated(client)

    if args.command == "positions":
        payload = build_positions_payload(client)
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        elif args.format == "text":
            render_text(payload)
        else:
            render_prettytable(payload)
        return


if __name__ == "__main__":
    main()
