"""Validate complete position-by-position review coverage for an investment-bot run."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

DECISIONS = {"add", "hold", "trim", "exit"}
THESIS_STATUSES = {"strengthened", "intact", "weakened", "broken", "uncovered"}


def _read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _identity(value: dict) -> tuple[str, str]:
    uic = value.get("uic")
    asset_type = value.get("asset_type")
    if uic is None or not isinstance(asset_type, str) or not asset_type.strip():
        raise ValueError("Every position must have uic and asset_type identity fields.")
    return str(uic), asset_type.casefold()


def _meaningful_strings(value, field: str, identity: tuple[str, str]) -> None:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{field} must contain evidence for position {identity}.")


def validate_holdings_review(snapshot: dict, review: dict, plan: dict) -> dict:
    snapshot_positions = snapshot.get("positions")
    review_positions = review.get("positions")
    if not isinstance(snapshot_positions, list) or not isinstance(review_positions, list):
        raise ValueError("Snapshot and review positions must be arrays.")
    if review.get("run_id") != plan.get("run_id"):
        raise ValueError("Holdings review run_id must match plan run_id.")
    if review.get("snapshot_timestamp") != snapshot.get("timestamp"):
        raise ValueError("Holdings review snapshot_timestamp must match the snapshot.")
    conclusion = review.get("portfolio_conclusion")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise ValueError("Holdings review requires a portfolio_conclusion.")

    snapshot_by_id = {}
    for position in snapshot_positions:
        identity = _identity(position)
        if identity in snapshot_by_id:
            raise ValueError(f"Snapshot contains duplicate position identity {identity}.")
        snapshot_by_id[identity] = position

    review_by_id = {}
    for assessment in review_positions:
        identity = _identity(assessment)
        if identity in review_by_id:
            raise ValueError(f"Holdings review contains duplicate identity {identity}.")
        decision = str(assessment.get("decision", "")).casefold()
        thesis_status = str(assessment.get("thesis_status", "")).casefold()
        if decision not in DECISIONS:
            raise ValueError(f"Invalid decision for position {identity}: {decision!r}.")
        if thesis_status not in THESIS_STATUSES:
            raise ValueError(f"Invalid thesis_status for position {identity}: {thesis_status!r}.")
        for field in ("symbol", "rationale", "review_trigger"):
            if not isinstance(assessment.get(field), str) or not assessment[field].strip():
                raise ValueError(f"{field} is required for position {identity}.")
        _meaningful_strings(assessment.get("supporting_evidence"), "supporting_evidence", identity)
        _meaningful_strings(assessment.get("contrary_evidence"), "contrary_evidence", identity)
        review_by_id[identity] = assessment

    missing = sorted(set(snapshot_by_id) - set(review_by_id))
    extra = sorted(set(review_by_id) - set(snapshot_by_id))
    if missing or extra:
        raise ValueError(f"Holdings review coverage mismatch; missing={missing}, extra={extra}.")

    for identity, position in snapshot_by_id.items():
        expected = position.get("quantity")
        actual = review_by_id[identity].get("quantity")
        if not isinstance(expected, (int, float)) or not isinstance(actual, (int, float)):
            raise ValueError(f"Quantity must be numeric for position {identity}.")
        if not math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"Holdings review quantity does not match snapshot for {identity}.")

    orders = plan.get("orders")
    if not isinstance(orders, list):
        raise ValueError("Plan orders must be an array.")
    for order in orders:
        identity = _identity(order)
        if identity not in snapshot_by_id:
            continue
        side = str(order.get("side", "")).casefold()
        decision = str(review_by_id[identity]["decision"]).casefold()
        if side == "buy" and decision != "add":
            raise ValueError(f"Existing-position buy requires add decision for {identity}.")
        if side == "sell" and decision not in {"trim", "exit"}:
            raise ValueError(f"Existing-position sell requires trim or exit decision for {identity}.")
        if side == "sell" and decision == "exit":
            quantity = order.get("quantity")
            held = snapshot_by_id[identity].get("quantity")
            if not isinstance(quantity, (int, float)) or not math.isclose(
                float(quantity), float(held), rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError(f"Exit order must sell the full snapshot quantity for {identity}.")

    return {"valid": True, "run_id": plan.get("run_id"), "positions_reviewed": len(review_by_id)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_holdings_review(
            _read_object(args.snapshot), _read_object(args.review), _read_object(args.plan)
        )
    except ValueError as exc:
        parser.exit(1, f"holdings review invalid: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
