#!/usr/bin/env python3
"""Append one sanitized, human-readable conclusion to investbot.log."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SENSITIVE_PATTERN = re.compile(
    r"access[ _-]?token|refresh[ _-]?token|authorization[ _-]?url|"
    r"account[ _-]?key|client[ _-]?key|https?://\S*(?:authorize|oauth)",
    re.IGNORECASE,
)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    return value if isinstance(value, dict) else {}


def _one_line(value: str, field: str) -> str:
    text = " ".join(str(value).split()).replace("|", "/").strip()
    if not text:
        raise ValueError(f"{field} cannot be empty.")
    if SENSITIVE_PATTERN.search(text):
        raise ValueError(f"{field} contains sensitive-looking content.")
    return text


def _timestamp(run_id: str, execution: dict, run_status: dict, snapshot: dict) -> str:
    value = (
        execution.get("completed_at")
        or execution.get("started_at")
        or run_status.get("timestamp")
        or snapshot.get("timestamp")
    )
    if not value:
        match = re.match(r"^(\d{8}T\d{6})", run_id)
        value = f"{match.group(1)}Z" if match else datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Run timestamp is not valid ISO-8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def append_run_log(
    run_dir: str | Path,
    conclusion: str,
    next_trigger: str,
    log_path: str | Path = "investbot.log",
) -> dict:
    run_path = Path(run_dir)
    run_id = run_path.name
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("The run directory name is not a valid run_id.")

    execution = _read_json(run_path / "execution.json")
    run_status = _read_json(run_path / "run-status.json")
    snapshot = _read_json(run_path / "snapshot-summary.json")
    plan = _read_json(run_path / "plan.json")
    status = _one_line(
        execution.get("status") or run_status.get("status") or "aborted_before_summary",
        "status",
    )
    orders = execution.get("orders")
    if not isinstance(orders, list):
        orders = plan.get("orders") if isinstance(plan.get("orders"), list) else []

    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8-sig") if target.exists() else ""
    marker = f"run_id={run_id}"
    if f"| {marker} |" in existing:
        raise ValueError(f"investbot.log already contains {marker}.")

    line = (
        f"{_timestamp(run_id, execution, run_status, snapshot)} | {marker} | "
        f"status={status} | orders={len(orders)} | "
        f"conclusion={_one_line(conclusion, 'conclusion')} | "
        f"next={_one_line(next_trigger, 'next trigger')}\n"
    )
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
    return {"run_id": run_id, "log": str(target), "appended": True}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--conclusion", required=True)
    parser.add_argument("--next-trigger", required=True)
    parser.add_argument("--log", default="investbot.log")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    result = append_run_log(args.run_dir, args.conclusion, args.next_trigger, args.log)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
