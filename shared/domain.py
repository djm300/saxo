"""Normalized, agent-facing Saxo data models and local portfolio analytics."""

from datetime import datetime, timezone


def first(data, *keys, default=None):
    for key in keys:
        if isinstance(data, dict) and data.get(key) is not None:
            return data[key]
    return default


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_account(raw, environment):
    return {
        "environment": environment,
        "account_key": first(raw, "AccountKey", "AccountId"),
        "account_id": first(raw, "AccountId"),
        "currency": first(raw, "Currency", "AccountCurrency"),
        "account_type": first(raw, "AccountType", "AccountTypeName"),
        "client_key": first(raw, "ClientKey"),
    }


def normalize_balance(raw, environment, currency=None):
    return {
        "environment": environment,
        "currency": currency or first(raw, "Currency", "AccountCurrency", "BaseCurrency"),
        "cash": first(raw, "CashBalance", "Cash", "CashBalanceInBaseCurrency", default=0),
        "net_equity": first(
            raw, "TotalValue", "NetEquityForMargin", "NetEquity", "TotalNetValue", default=0
        ),
        "available_for_trading": first(
            raw, "AvailableForTrading", "AvailableCash", "CashAvailableForTrading", default=0
        ),
        "margin_used": first(raw, "MarginUsed", "MarginUtilization", default=0),
    }


def normalize_position(raw, instrument=None, account_currency=None):
    base = raw.get("PositionBase", raw)
    view = raw.get("PositionView", {})
    instrument = instrument or {}
    quantity = first(base, "Amount", "Quantity", default=0)
    price = first(view, "CurrentPrice", "MarketPrice", "Price", default=0)
    market_value = first(
        view, "MarketValue", "MarketValueInBaseCurrency", default=number(quantity) * number(price)
    )
    return {
        "symbol": first(instrument, "Symbol", "Identifier", "Description")
        or first(base, "Symbol", "Identifier"),
        "description": first(instrument, "Description", "Name"),
        "asset_type": first(base, "AssetType", default=first(instrument, "AssetType")),
        "uin": first(base, "Uic", "UIN"),
        "uic": first(base, "Uic", "UIN"),
        "quantity": quantity,
        "currency": first(view, "Currency") or account_currency,
        "market_price": price,
        "market_value": market_value,
        "cost_price": first(view, "AverageOpenPrice", "OpenPrice", "EntryPrice", default=0),
        "unrealized_pnl": first(
            view, "ProfitLossOnTrade", "ProfitLossOnTradeInBaseCurrency", default=0
        ),
        "account_id": first(base, "AccountId"),
        "side": "short" if number(quantity) < 0 else "long",
        "raw": {"Uic": first(base, "Uic", "UIN"), "AssetType": first(base, "AssetType")},
    }


def normalize_quote(raw, symbol=None, currency=None):
    bid = first(raw, "Bid", "BidAsk", default=None)
    ask = first(raw, "Ask", default=None)
    if isinstance(bid, dict):
        bid = first(bid, "Bid", "Price")
    mid = first(
        raw,
        "Mid",
        "MidPrice",
        default=(number(bid) + number(ask)) / 2 if bid is not None and ask is not None else None,
    )
    delayed_minutes = first(raw, "DelayedByMinutes", default=None)
    is_delayed = first(raw, "IsDelayed", "Delayed", default=None)
    if is_delayed is None and delayed_minutes is not None:
        is_delayed = number(delayed_minutes) > 0
    return {
        "symbol": symbol,
        "timestamp": first(raw, "Timestamp", "LastUpdated"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "last": first(raw, "LastTraded", "Last", "Price"),
        "currency": currency or first(raw, "Currency"),
        "is_delayed": is_delayed,
        "delayed_by_minutes": delayed_minutes,
        "market_state": first(raw, "MarketState", "MarketStatus"),
        "raw": raw,
    }


def portfolio_summary(positions, balance):
    total = number(balance.get("net_equity")) or sum(
        number(p.get("market_value")) for p in positions
    )
    classes = {}
    for p in positions:
        kind = str(p.get("asset_type") or "other").lower()
        key = (
            "options_market_value"
            if "option" in kind
            else ("stocks" if "stock" in kind or "equity" in kind else "other")
        )
        classes[key] = classes.get(key, 0) + number(p.get("market_value"))
    if balance.get("cash") is not None:
        classes["cash"] = number(balance.get("cash"))
    largest = sorted(
        (
            dict(p, weight=(number(p.get("market_value")) / total if total else 0))
            for p in positions
        ),
        key=lambda p: abs(number(p.get("market_value"))),
        reverse=True,
    )[:10]
    return {
        "environment": balance.get("environment"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "net_value": total,
        "cash": balance.get("cash"),
        "asset_classes": classes,
        "largest_positions": [
            {
                "symbol": p.get("symbol"),
                "market_value": p.get("market_value"),
                "weight": p["weight"],
            }
            for p in largest
        ],
    }


def roll_analysis(existing, new, contracts, multiplier=100):
    old_bid, old_ask = number(existing.get("bid")), number(existing.get("ask"))
    new_bid, new_ask = number(new.get("bid")), number(new.get("ask"))
    # A short-call roll buys the old call at ask and sells the new call at bid.
    # Positive values therefore mean a net credit to the account.
    conservative = (new_bid - old_ask) * contracts * multiplier
    midpoint = ((new_bid + new_ask) / 2 - (old_bid + old_ask) / 2) * contracts * multiplier
    strike_increase = number(new.get("strike")) - number(existing.get("strike"))
    return {
        "existing_option": existing,
        "new_option": new,
        "contracts": contracts,
        "conservative_net_credit": conservative,
        "midpoint_net_credit": midpoint,
        "strike_increase": strike_increase,
        "additional_uncapped_share_gain_until_new_strike": strike_increase * contracts * multiplier,
        "new_effective_sale_price_before_dividends": number(new.get("strike")) + new_bid,
    }
