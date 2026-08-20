"""Read-only web dashboard for the running Saxo client."""

import hmac
import json
import logging
import os
import secrets
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from math import isfinite
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

from shared.auth import lifetime_seconds_to_datetime, token_file_lock
from shared.client import SaxoClient
from shared.formatter import CustomFormatter
from shared.runtime import create_client, load_runtime_config

app = Flask(__name__)
runtime_config = load_runtime_config()
config = runtime_config
saxoclient = create_client(runtime_config)
web_secret = None
dev_mode = False
logger = logging.getLogger(__name__)
INSTRUMENT_CACHE_TTL_SECONDS = 5 * 24 * 60 * 60
if not logger.handlers:
    logger.setLevel(logging.INFO)
    logger.propagate = False
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    file_handler = logging.FileHandler(os.getenv("SAXO_APP_LOG", "app.log"))
    file_handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
    logger.addHandler(file_handler)


def _log_order_activity(activity, **details):
    """Write a safe, structured order audit line to console and app.log."""
    logger.info(
        "ORDER activity | %s | %s", activity, json.dumps(details, default=str, sort_keys=True)
    )


def configure(client, config=None, secret=None, dev=False):
    global saxoclient, runtime_config, web_secret, dev_mode
    saxoclient = client
    runtime_config = config
    dev_mode = bool(dev)
    web_secret = (
        None if dev_mode else (secret or os.getenv("SAXO_WEB_SECRET") or secrets.token_urlsafe(32))
    )
    if getattr(config, "trading_enabled", False):
        logger.warning("WARNING: TRADING_ENABLED is true. Web order execution is enabled.")
    return web_secret


@app.before_request
def require_trust():
    if dev_mode or web_secret is None:
        return None
    supplied = request.args.get("secret", "")
    if not hmac.compare_digest(supplied, web_secret):
        abort(403, description="A valid web secret is required.")
    return None


def _require_client():
    if saxoclient is None:
        abort(503, description="The Saxo client is not attached.")
    if not saxoclient._is_authenticated():
        abort(401, description="Saxo authentication is unavailable.")
    return saxoclient


def _data(value):
    return value.get("Data", []) if isinstance(value, dict) else []


def _instrument_cache_path(client):
    configured = os.getenv("SAXO_INSTRUMENT_CACHE")
    if configured:
        return Path(os.path.abspath(os.path.expanduser(configured)))
    token_file = getattr(getattr(client, "auth_client", None), "token_file", None)
    if not isinstance(token_file, (str, Path)):
        configured_token_file = getattr(runtime_config, "token_file", None)
        token_file = (
            configured_token_file
            if isinstance(configured_token_file, (str, Path))
            else "tokens.json"
        )
    token_path = Path(os.path.abspath(os.path.expanduser(token_file)))
    return token_path.with_name("instrument-cache.json")


def _instrument_cache_key(client, uic, asset_type):
    baseurl = getattr(getattr(client, "auth_client", None), "baseurl", "")
    return f"{baseurl}|{asset_type or 'Stock'}|{uic}"


def _read_instrument_cache(path):
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _cached_instrument_metadata(client, uic, asset_type):
    path = _instrument_cache_path(client)
    key = _instrument_cache_key(client, uic, asset_type)
    with token_file_lock(path):
        entry = _read_instrument_cache(path).get(key)
    if not isinstance(entry, dict):
        return None
    try:
        fresh = time.time() - float(entry["cached_at"]) < INSTRUMENT_CACHE_TTL_SECONDS
    except (KeyError, TypeError, ValueError):
        return None
    symbol = entry.get("symbol") or entry.get("name")
    company_name = entry.get("company_name")
    # Entries written by older versions only contain ``name``. Refetch those
    # once so the dashboard can also provide a useful company-name tooltip.
    if not fresh or not symbol or not company_name:
        return None
    return {"symbol": symbol, "company_name": company_name}


def _store_instrument_metadata(client, uic, asset_type, metadata):
    symbol = metadata.get("symbol")
    company_name = metadata.get("company_name")
    if not uic or not symbol or symbol == "N/A":
        return
    path = _instrument_cache_path(client)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = _instrument_cache_key(client, uic, asset_type)
    with token_file_lock(path):
        values = _read_instrument_cache(path)
        values[key] = {
            "name": symbol,  # Backwards compatibility with older readers.
            "symbol": symbol,
            "company_name": company_name or symbol,
            "cached_at": time.time(),
        }
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".saxo-instruments-", dir=path.parent, text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                json.dump(values, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _instrument_metadata(client, uic, asset_type, cache):
    if not uic:
        return {"symbol": "N/A", "company_name": "Unknown instrument"}
    key = (uic, asset_type or "")
    if key not in cache:
        cached_metadata = _cached_instrument_metadata(client, uic, asset_type)
        if cached_metadata:
            cache[key] = cached_metadata
            return cached_metadata
        try:
            instrument = client.get_instrument_by_uic(uic, asset_type=asset_type or "Stock")
            symbol = instrument.get("Symbol") or instrument.get("Description") or "N/A"
            company_name = instrument.get("Description") or symbol
            cache[key] = {"symbol": symbol, "company_name": company_name}
            _store_instrument_metadata(client, uic, asset_type, cache[key])
        except Exception:
            cache[key] = {"symbol": "N/A", "company_name": "Unknown instrument"}
    return cache[key]


def _instrument_name(client, uic, asset_type, cache):
    """Compatibility helper for callers that only need a display symbol."""
    key = (uic, asset_type or "")
    if key not in cache:
        cache[key] = _instrument_metadata(client, uic, asset_type, {})["symbol"]
    return cache[key]


def _positions(client, raw=None):
    raw = client.get_positions() if raw is None else raw
    cache = {}
    items = _data(raw)

    def make_position(item):
        base = item.get("PositionBase", item)
        view = item.get("PositionView", {})
        metadata = _instrument_metadata(
            client, base.get("Uic"), base.get("AssetType"), cache
        )
        amount = base.get("Amount")
        purchase_price = next(
            (base.get(key) or view.get(key) for key in ("OpenPrice", "PurchasePrice", "AverageOpenPrice")
             if base.get(key) is not None or view.get(key) is not None),
            None,
        )
        current_price = next(
            (view.get(key) or base.get(key) for key in ("CurrentPrice", "MarketPrice", "Price")
             if view.get(key) is not None or base.get(key) is not None),
            None,
        )
        profit_loss = view.get("ProfitLossOnTrade")
        market_value = next(
            (view.get(key) for key in ("MarketValue", "MarketValueInBaseCurrency", "Exposure")
             if view.get(key) is not None),
            None,
        )
        if market_value is None and current_price is not None and amount is not None:
            market_value = abs(float(amount)) * float(current_price)
        total_percent = next(
            (view.get(key) for key in ("ProfitLossOnTradeInPercent", "ProfitLossPercent", "TotalProfitLossPercent")
             if view.get(key) is not None),
            None,
        )
        if total_percent is None and profit_loss is not None and purchase_price and amount:
            total_percent = float(profit_loss) / (abs(float(purchase_price)) * abs(float(amount))) * 100
        one_day_percent = next(
            (view.get(key) for key in ("InstrumentPriceDayPercentChange", "OneDayProfitLossPercent", "DailyProfitLossPercent", "DayChangePercent", "ChangePercent")
             if view.get(key) is not None),
            None,
        )
        return {
            "account_id": base.get("AccountId"),
            "account_key": base.get("AccountKey") or base.get("AccountId"),
            "uic": base.get("Uic"),
            "name": metadata["symbol"],
            "company_name": metadata["company_name"],
            "asset_type": base.get("AssetType"),
            "amount": amount,
            "one_day_percent": one_day_percent,
            "total_percent": total_percent,
            "purchase_price": purchase_price,
            "current_price": current_price,
            "total_value": market_value,
            "profit_loss": profit_loss,
        }

    # Instrument detail requests are independent; parallelizing them avoids
    # making the page wait for one round trip per open position.
    workers = min(8, max(1, len(items)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="saxo-position") as executor:
        return list(executor.map(make_position, items))


def _order_display_name(row):
    for key in ("Symbol", "Instrument", "InstrumentSymbol", "DisplayName"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    display = row.get("DisplayAndFormat")
    if isinstance(display, dict):
        return display.get("Symbol") or display.get("Description") or display.get("DisplayName")
    if isinstance(display, str) and display:
        return display
    return None


def _order_company_name(row):
    for key in ("Description", "CompanyName", "InstrumentDescription"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    display = row.get("DisplayAndFormat")
    if isinstance(display, dict):
        return display.get("Description") or display.get("DisplayName")
    return None


def _enrich_order_rows(client, rows):
    rows = [dict(row) for row in rows]
    cache = {}
    missing = {}
    for row in rows:
        if _order_display_name(row) and _order_company_name(row):
            continue
        key = (row.get("Uic"), row.get("AssetType") or "Stock")
        if key[0] is not None:
            missing[key] = None

    def resolve(key):
        return key, _instrument_metadata(client, key[0], key[1], cache)

    if missing:
        with ThreadPoolExecutor(max_workers=min(8, len(missing)), thread_name_prefix="saxo-order") as executor:
            for key, name in executor.map(resolve, missing):
                missing[key] = name
    for row in rows:
        metadata = missing.get((row.get("Uic"), row.get("AssetType") or "Stock"), {})
        row["instrument"] = _order_display_name(row) or metadata.get("symbol", "N/A")
        row["company_name"] = (
            _order_company_name(row)
            or metadata.get("company_name")
            or row["instrument"]
        )
    return rows


def _compact_order(row):
    """Keep only fields rendered by the dashboard to reduce JSON transfer."""
    return {
        "instrument": row.get("instrument") or _order_display_name(row) or "N/A",
        "company_name": row.get("company_name") or _order_company_name(row),
        "Status": row.get("Status"),
        "SubStatus": row.get("SubStatus"),
        "BuySell": row.get("BuySell"),
        "Amount": row.get("Amount"),
        "OrderPrice": row.get("OrderPrice", row.get("Price")),
        "ActivityTime": row.get("ActivityTime"),
        "OrderId": row.get("OrderId"),
        "AccountKey": row.get("AccountKey") or row.get("AccountId"),
        "FilledAmount": row.get("FilledAmount", row.get("FillAmount")),
        "AveragePrice": row.get("AveragePrice"),
    }


def _status(client):
    tokens = getattr(getattr(client, "auth_client", None), "tokens", {}) or {}
    now = time.time()

    def expiry(name):
        value = tokens.get(name)
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return {"at": None, "seconds": None}
        return {
            "at": lifetime_seconds_to_datetime(timestamp),
            "seconds": max(0, int(timestamp - now)),
        }

    state = client.current_state()
    return {
        "app_status": "running",
        "client_state": state,
        "saxoclient state": state,
        "authenticated": client._is_authenticated(),
        "refresh_interval_seconds": getattr(runtime_config, "token_refresh_interval_seconds", None),
        "access_token": expiry("access_token_expires_at"),
        "refresh_token": expiry("refresh_token_expires_at"),
        "dev_mode": dev_mode,
    }


def start_background_tasks():
    saxoclient.start_refresh_thread(runtime_config.token_refresh_interval_seconds)


def stop_background_tasks():
    saxoclient.stop_refresh_thread()


@app.route("/")
def home():
    return render_template(
        "positions.html", secret=request.args.get("secret", ""), dev_mode=dev_mode
    )


@app.route("/authenticate", methods=["GET", "POST"])
def authenticate():
    code = request.values.get("authorization_code") or request.args.get("code")
    if code and saxoclient.current_state() in (
        SaxoClient.STATE_WAITING_FOR_AUTHORIZATION_CODE,
        SaxoClient.STATE_NOT_AUTHENTICATED,
        SaxoClient.STATE_ERROR,
    ):
        saxoclient.get_token(code)
        return (
            redirect(url_for("status"))
            if saxoclient._is_authenticated()
            else redirect(url_for("authenticate"))
        )
    if request.method == "POST":
        return redirect(url_for("status"))
    return jsonify(
        {"auth_url": saxoclient.get_authorization_url(), "state": saxoclient.current_state()}
    )


@app.route("/oauth/callback")
def oauth_callback():
    return redirect(url_for("authenticate", **request.args))


@app.route("/status")
def status():
    if saxoclient is None:
        abort(503, description="The Saxo client is not attached.")
    return jsonify(_status(saxoclient))


@app.route("/api/status")
def api_status():
    if saxoclient is None:
        abort(503, description="The Saxo client is not attached.")
    return jsonify(_status(saxoclient))


@app.route("/api/dashboard")
def dashboard():
    client = _require_client()
    try:
        # Positions and orders are independent API calls. Fetch them together
        # so a slow orders endpoint does not delay positions (or vice versa).
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="saxo-dashboard") as executor:
            positions_future = executor.submit(client.get_positions)
            orders_future = executor.submit(client.get_orders)
            history_future = executor.submit(client.get_order_history)
            positions_raw = positions_future.result()
            order_data = orders_future.result()
            history_data = history_future.result()
        orders = _enrich_order_rows(client, _data(order_data))
        history = _enrich_order_rows(client, _data(history_data))
        _log_order_activity("list", count=len(orders), source="dashboard")
        _log_order_activity("history_list", count=len(history), source="dashboard")
        compact_orders = [_compact_order(row) for row in orders]
        compact_history = [_compact_order(row) for row in history]
        order_data = {**order_data, "Data": compact_orders} if isinstance(order_data, dict) else {"Data": compact_orders}
        history_data = {**history_data, "Data": compact_history} if isinstance(history_data, dict) else {"Data": compact_history}
        return jsonify({"positions": _positions(client, positions_raw), "orders": order_data, "order_history": history_data, "status": _status(client)})
    except Exception as exc:
        _log_order_activity("list_failed", source="dashboard", error=str(exc))
        logger.exception("Failed to load dashboard data")
        return jsonify({"error": str(exc)}), 502


@app.route("/api/positions")
def api_positions():
    return jsonify({"Data": _positions(_require_client())})


@app.route("/api/orders")
def api_orders():
    client = _require_client()
    rows = _enrich_order_rows(client, _data(client.get_orders()))
    _log_order_activity("list", count=len(rows), source="compact_orders_endpoint")
    return jsonify({"Data": [_compact_order(row) for row in rows]})


@app.route("/api/order-history")
def api_order_history():
    client = _require_client()
    rows = _enrich_order_rows(client, _data(client.get_order_history()))
    _log_order_activity("history_list", count=len(rows), source="compact_history_endpoint")
    return jsonify({"Data": [_compact_order(row) for row in rows]})


@app.route("/api/positions/sell", methods=["POST"])
def sell_position():
    client = _require_client()
    _log_order_activity("sell_requested", payload=request.get_json(silent=True) or {})
    if not getattr(client, "trading_enabled", False):
        _log_order_activity("sell_rejected", reason="trading_disabled")
        return jsonify(
            {"error": "Trading is disabled. Set TRADING_ENABLED=true to sell positions."}
        ), 403
    payload = request.get_json(silent=True) or {}
    try:
        uic = int(payload["uic"])
        amount = abs(float(payload["amount"]))
    except (KeyError, TypeError, ValueError):
        _log_order_activity("sell_rejected", reason="invalid_payload")
        return jsonify({"error": "uic and a numeric amount are required."}), 400
    if not isfinite(amount) or amount <= 0:
        _log_order_activity("sell_rejected", reason="invalid_amount", amount=amount)
        return jsonify({"error": "The position amount must be greater than zero."}), 400
    asset_type = str(payload.get("asset_type") or "Stock")
    account_key = payload.get("account_key") or payload.get("account_id")
    if not account_key:
        _log_order_activity("sell_rejected", reason="missing_account_key", uic=uic)
        return jsonify({"error": "The position has no account key."}), 400
    order = {
        "AccountKey": account_key,
        "Amount": amount,
        "AssetType": asset_type,
        "BuySell": "Sell",
        "ManualOrder": True,
        "OrderDuration": {"DurationType": "DayOrder"},
        "OrderType": "Market",
        "Uic": uic,
    }
    try:
        response = client.place_order(order)
    except Exception as exc:
        _log_order_activity("sell_failed", uic=uic, amount=amount, error=str(exc))
        logger.exception("Failed to sell position %s", uic)
        return jsonify({"error": str(exc)}), 502
    _log_order_activity(
        "sell_submitted", uic=uic, amount=amount, account_key=account_key, response=response
    )
    return jsonify({"message": "Sell order submitted.", "order": order, "response": response}), 201


@app.route("/api/orders/cancel", methods=["POST"])
def cancel_order():
    client = _require_client()
    payload = request.get_json(silent=True) or {}
    _log_order_activity("cancel_requested", payload=payload)
    if not getattr(client, "trading_enabled", False):
        _log_order_activity("cancel_rejected", reason="trading_disabled")
        return jsonify(
            {"error": "Trading is disabled. Set TRADING_ENABLED=true to cancel orders."}
        ), 403
    order_id = str(payload.get("order_id") or "").strip()
    account_key = str(payload.get("account_key") or "").strip()
    if not order_id or not account_key:
        _log_order_activity("cancel_rejected", reason="invalid_payload")
        return jsonify({"error": "order_id and account_key are required."}), 400
    try:
        response = client.cancel_orders([order_id], account_key)
    except Exception as exc:
        _log_order_activity(
            "cancel_failed", order_id=order_id, account_key=account_key, error=str(exc)
        )
        logger.exception("Failed to cancel order %s", order_id)
        return jsonify({"error": str(exc)}), 502
    _log_order_activity(
        "cancel_submitted", order_id=order_id, account_key=account_key, response=response
    )
    return jsonify({"message": "Cancel request submitted.", "response": response}), 200


@app.route("/positions")
def positions():
    return jsonify(_require_client().get_positions())


@app.route("/orders")
def orders():
    client = _require_client()
    result = client.get_orders()
    enriched = _enrich_order_rows(client, _data(result))
    _log_order_activity("list", count=len(enriched), source="orders_endpoint")
    return jsonify({**result, "Data": enriched} if isinstance(result, dict) else {"Data": enriched})


@app.route("/order-history")
def order_history():
    client = _require_client()
    result = client.get_order_history()
    enriched = _enrich_order_rows(client, _data(result))
    _log_order_activity("history_list", count=len(enriched), source="history_endpoint")
    return jsonify({**result, "Data": enriched} if isinstance(result, dict) else {"Data": enriched})


@app.route("/positionstable")
def positionstable():
    client = _require_client()
    return render_template(
        "positions.html",
        positions=_positions(client),
        secret=request.args.get("secret", ""),
        dev_mode=dev_mode,
    )


def startSaxoServer(client, runtime_config, host=None, port=None, dev=False, secret=None):
    configured_secret = configure(client, runtime_config, secret=secret, dev=dev)
    address = f"http://{host or os.getenv('SAXO_HOST', '127.0.0.1')}:{port or int(os.getenv('PORT', '5000'))}"
    if configured_secret:
        logger.info("Web dashboard: %s?secret=%s", address, configured_secret)
    else:
        logger.info("Web dashboard (development mode): %s", address)
    # The reloader intentionally belongs to --dev only. Flask starts a
    # second process when it is enabled, so production serve must remain
    # single-process and deterministic for the authentication session.
    return app.run(
        host=host or os.getenv("SAXO_HOST", "0.0.0.0"),
        port=port or int(os.getenv("PORT", "5000")),
        debug=dev,
        use_reloader=dev,
    )
