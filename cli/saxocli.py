#!/usr/bin/env python3
"""Small, read-only, JSON-first Saxo command line interface."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from shared.client import AuthenticationError, RateLimitError, SaxoAPIError
from shared.domain import (
    first,
    normalize_account,
    normalize_balance,
    normalize_position,
    normalize_quote,
    portfolio_summary,
)
from shared.runtime import AuthenticationSession, create_client, load_runtime_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="saxo")
    parser.add_argument("--env", choices=["sim", "live"])
    parser.add_argument("--params", default="params.json")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("account", "balances", "portfolio", "positions", "orders"):
        p = sub.add_parser(name)
        p.add_argument("--format", choices=["json", "text"], default=None)
        p.add_argument("--json", action="store_true", dest="json_output")
        if name == "orders":
            p.add_argument(
                "--history",
                action="store_true",
                help="Show order activities instead of working orders",
            )
    history = sub.add_parser(
        "order-history", aliases=["orderhistory"], help="Show today’s order activities"
    )
    history.add_argument("--limit", type=int, default=200)
    history.add_argument("--format", choices=["json", "text"], default=None)
    history.add_argument("--json", action="store_true", dest="json_output")
    p = sub.add_parser("position")
    p.add_argument("symbol")
    p.add_argument("--json", action="store_true", dest="json_output")
    p = sub.add_parser("instrument")
    p.add_argument("query")
    p.add_argument("--asset-type")
    p.add_argument("--json", action="store_true", dest="json_output")
    p = sub.add_parser("quote")
    p.add_argument("symbol")
    p.add_argument("--json", action="store_true", dest="json_output")
    order = sub.add_parser("order")
    order_sub = order.add_subparsers(dest="order_action", required=True)
    place = order_sub.add_parser("place", help="Preview or place a market/limit order")
    place.add_argument("symbol")
    place.add_argument("--side", choices=["buy", "sell"], required=True)
    place.add_argument("--quantity", type=float, required=True)
    place.add_argument("--type", choices=["market", "limit"], required=True)
    place.add_argument("--limit", type=float)
    place.add_argument("--account-key")
    place.add_argument("--duration", default="DayOrder")
    place.add_argument("--execute", action="store_true")
    place.add_argument("--json", action="store_true", dest="json_output")
    cancel = order_sub.add_parser("cancel", help="Preview or cancel open orders")
    cancel.add_argument("order_ids", nargs="+")
    cancel.add_argument("--account-key", required=True)
    cancel.add_argument("--execute", action="store_true")
    cancel.add_argument("--json", action="store_true", dest="json_output")
    p = sub.add_parser("options")
    p.add_argument("symbol")
    p.add_argument("--expiry")
    p.add_argument("--type", choices=["call", "put"])
    p.add_argument("--min-strike", type=float)
    p.add_argument("--max-strike", type=float)
    p.add_argument("--json", action="store_true", dest="json_output")
    p = sub.add_parser("option")
    p.add_argument("symbol")
    p.add_argument("--expiry", required=True)
    p.add_argument("--strike", required=True, type=float)
    p.add_argument("--type", required=True, choices=["call", "put"])
    p.add_argument("--json", action="store_true", dest="json_output")
    auth = sub.add_parser("auth")
    auth.add_argument("action", choices=["status", "login", "logout"])
    serve = sub.add_parser("serve", help="Start the local web server")
    serve.add_argument("--host", default=os.getenv("SAXO_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")))
    serve.add_argument(
        "--dev", action="store_true", help="Disable the web secret (local development only)"
    )
    return parser.parse_args(argv)


def _data(value):
    return value.get("Data", []) if isinstance(value, dict) else []


def build_positions_payload(client, environment="sim"):
    accounts = _data(client.get_accounts())
    currencies = {a.get("AccountId"): a.get("Currency") for a in accounts}
    result = []
    for raw in _data(client.get_positions()):
        base = raw.get("PositionBase", raw)
        uic, asset = first(base, "Uic", "UIN"), first(base, "AssetType", default="Stock")
        instrument = {}
        if uic:
            try:
                instrument = client.get_instrument_by_uic(uic, asset_type=asset) or {}
            except Exception:
                pass
        result.append(normalize_position(raw, instrument, currencies.get(base.get("AccountId"))))
    return {
        "environment": environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": result,
    }


def _resolve(client, query, asset_type=None):
    matches = _data(client.search_instruments(query, asset_type))
    if not matches:
        raise LookupError(f"No instrument matching {query} was found.")
    query_key = query.strip().casefold()
    exact = [
        match
        for match in matches
        if any(
            str(match.get(field) or "").strip().casefold() == query_key
            for field in ("Symbol", "Identifier")
        )
    ]
    if exact:
        stock_matches = [
            match for match in exact if str(match.get("AssetType") or "").casefold() == "stock"
        ]
        if len(stock_matches) == 1:
            return stock_matches[0]
        if len(exact) == 1:
            return exact[0]
    stock_description_matches = [
        match
        for match in matches
        if str(match.get("AssetType") or "").casefold() == "stock"
        and query_key in str(match.get("Description") or "").casefold()
    ]
    if len(stock_description_matches) == 1:
        return stock_description_matches[0]
    if len(matches) > 1:
        raise ValueError(f"Instrument query {query!r} is ambiguous.")
    return matches[0]


def run(args, config, client):
    env = "sim" if config.simulation_mode else "live"
    if args.env and args.env != env:
        raise RuntimeError("--env differs from the configured environment")
    if args.command == "account":
        return normalize_account((_data(client.get_accounts()) or [{}])[0], env)
    if args.command == "balances":
        account = (_data(client.get_accounts()) or [{}])[0]
        raw = client.get_balances()
        raw = (raw.get("Data") or [{}])[0] if isinstance(raw, dict) else {}
        return normalize_balance(raw, env, account.get("Currency"))
    if args.command == "positions":
        return build_positions_payload(client, env)
    if args.command == "position":
        payload = build_positions_payload(client, env)
        needle = args.symbol.upper()
        return {
            **payload,
            "positions": [
                p for p in payload["positions"] if str(p.get("symbol") or "").upper() == needle
            ],
        }
    if args.command == "portfolio":
        return portfolio_summary(
            build_positions_payload(client, env)["positions"],
            run(argparse.Namespace(command="balances", env=None), config, client),
        )
    if args.command == "orders" and getattr(args, "history", False):
        return {"environment": env, "order_history": _data(client.get_order_history(today=True))}
    if args.command == "orders":
        return {"environment": env, "orders": _data(client.get_orders())}
    if args.command in {"order-history", "orderhistory"}:
        return {
            "environment": env,
            "order_history": _data(client.get_order_history(args.limit, today=True)),
        }
    if args.command == "instrument":
        matches = _data(client.search_instruments(args.query, args.asset_type))
        return {
            "environment": env,
            "matches": [
                {
                    "symbol": first(x, "Symbol"),
                    "description": first(x, "Description"),
                    "exchange": first(x, "ExchangeDescription", "Exchange"),
                    "currency": first(x, "Currency"),
                    "asset_type": first(x, "AssetType"),
                    "uic": first(x, "Identifier", "Uic"),
                }
                for x in matches
            ],
        }
    if args.command == "quote":
        match = _resolve(client, args.symbol)
        raw = client.get_quote(
            first(match, "Identifier", "Uic"), first(match, "AssetType", default="Stock")
        )
        raw = raw.get("Quote", raw) if isinstance(raw, dict) else raw
        return normalize_quote(
            raw, first(match, "Symbol", default=args.symbol), first(match, "Currency")
        )
    if args.command == "order":
        if args.order_action == "place":
            if args.type == "limit" and args.limit is None:
                raise ValueError("--limit is required for limit orders")
            if args.type == "market" and args.limit is not None:
                raise ValueError("--limit is only valid for limit orders")
            match = _resolve(client, args.symbol, "Stock")
            account = (_data(client.get_accounts()) or [{}])[0]
            account_key = args.account_key or first(account, "AccountKey", "AccountId")
            order_payload = {
                "AccountKey": account_key,
                "Amount": args.quantity,
                "AssetType": first(match, "AssetType", default="Stock"),
                "BuySell": args.side.capitalize(),
                "ManualOrder": True,
                "OrderDuration": {"DurationType": args.duration},
                "OrderType": args.type.capitalize(),
                "Uic": first(match, "Identifier", "Uic"),
            }
            if args.limit is not None:
                order_payload["OrderPrice"] = args.limit
            if not args.execute:
                return {
                    "environment": env,
                    "will_execute": False,
                    "order": order_payload,
                    "request": {**order_payload, "WithAdvice": False},
                }
            if not config.trading_enabled:
                raise PermissionError(
                    "Trading is disabled. Set TRADING_ENABLED=true to execute orders."
                )
            return {
                "environment": env,
                "will_execute": True,
                "response": client.place_order(order_payload),
            }
        if not args.execute:
            return {
                "environment": env,
                "will_execute": False,
                "order_ids": args.order_ids,
                "account_key": args.account_key,
            }
        if not config.trading_enabled:
            raise PermissionError("Trading is disabled. Set TRADING_ENABLED=true to cancel orders.")
        return {
            "environment": env,
            "will_execute": True,
            "response": client.cancel_orders(args.order_ids, args.account_key),
        }
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
    )
    session = None
    try:
        config = load_runtime_config(args.params, environment=args.env)
        if getattr(config, "trading_enabled", False):
            logging.warning("WARNING: TRADING_ENABLED is true. Live order execution is enabled.")
        client = create_client(config)
        if args.command == "auth":
            environment = "sim" if config.simulation_mode else "live"
            if args.action == "status":
                result = {"environment": environment, "authenticated": client._is_authenticated()}
            elif args.action == "login":
                result = {
                    "environment": environment,
                    "authenticated": bool(client.authenticate_interactive()),
                }
            else:
                token_path = os.path.abspath(os.path.expanduser(config.token_file))
                if os.path.exists(token_path):
                    os.remove(token_path)
                result = {"environment": environment, "authenticated": False}
        elif args.command == "serve":
            session = AuthenticationSession(client, config.token_refresh_interval_seconds)
            session.authenticate()
            from web.app import startSaxoServer

            session.start_refresh()
            server_args = {
                "client": client,
                "runtime_config": config,
                "host": args.host,
                "port": args.port,
                "dev": args.dev,
            }
            return startSaxoServer(**server_args) or 0
        else:
            session = AuthenticationSession(client, config.token_refresh_interval_seconds)
            session.authenticate()
            result = run(args, config, client)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except LookupError as exc:
        code, name = 3, "instrument_not_found"
        error_message = str(exc)
    except ValueError as exc:
        code, name = 4, "ambiguous_instrument"
        error_message = str(exc)
    except AuthenticationError as exc:
        code, name = 2, "authentication_required"
        error_message = str(exc)
    except RateLimitError as exc:
        code, name = 7, "rate_limit"
        error_message = str(exc)
    except SaxoAPIError as exc:
        code, name = 8, "saxo_api_error"
        error_message = str(exc)
    except RuntimeError as exc:
        code, name = 2, "authentication_required"
        error_message = str(exc)
    except Exception as exc:
        code, name = 1, "error"
        error_message = str(exc)
    finally:
        if session is not None:
            session.close()
    print(json.dumps({"error": {"code": name, "message": error_message}}), file=sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
