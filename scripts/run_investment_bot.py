#!/usr/bin/env python3
"""Launch the autonomous Saxo SIM investment bot with live, sanitized progress."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MINIMUM_CODEX_VERSION = (0, 148, 0)
DEFAULT_PROMPT = (
    "$saxo-investment-bot Run a complete autonomous Saxo SIM portfolio review. "
    "Pull the complete current portfolio and assess every position individually as add, "
    "hold, trim, or exit; write and validate holdings-review.json before plan validation, "
    "with no implicit holds. Research freely, including unusual public web signals and "
    "differentiated company-specific ideas; do not default to broad beta before the "
    "alternative-signal gate is complete. Validate the resulting plan, execute only "
    "through the SIM-only agent executor, and reconcile the run."
)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SENSITIVE_PATTERN = re.compile(
    r"access[ _-]?token|refresh[ _-]?token|authorization[ _-]?url|"
    r"account[ _-]?key|client[ _-]?key|bearer\s+[A-Za-z0-9._~-]+|"
    r"https?://\S*(?:authorize|oauth)",
    re.IGNORECASE,
)
VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_text(value, limit=8000) -> str:
    text = ANSI_ESCAPE.sub("", str(value or ""))
    text = " ".join(text.split()).replace("|", "/").strip()
    if SENSITIVE_PATTERN.search(text):
        return "[redacted sensitive output]"
    if len(text) > limit:
        return text[: limit - 14] + "... [truncated]"
    return text


class ActivityReporter:
    def __init__(self, log_path: Path, stream=None):
        self.log_path = log_path
        self.stream = stream or sys.stdout

    def emit(self, event: str, message) -> None:
        safe_event = re.sub(r"[^a-z0-9_-]", "_", event.casefold()) or "activity"
        safe_message = _safe_text(message)
        if not safe_message:
            return
        now = datetime.now().astimezone()
        print(
            f"[{now.strftime('%H:%M:%S')}] {safe_event.upper():<10} {safe_message}",
            file=self.stream,
            flush=True,
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"{_utc_timestamp()} | launcher | event={safe_event} | message={safe_message}\n"
            )


def _version(executable: Path) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = VERSION_PATTERN.search(result.stdout + result.stderr)
    return tuple(map(int, match.groups())) if result.returncode == 0 and match else None


def find_codex() -> tuple[Path, tuple[int, int, int]]:
    candidates = []
    configured = os.environ.get("CODEX_EXECUTABLE")
    if configured:
        candidates.append(Path(configured))
    on_path = shutil.which("codex")
    if on_path:
        candidates.append(Path(on_path))
    extension_root = Path.home() / ".vscode" / "extensions"
    patterns = (
        "openai.chatgpt-*/bin/windows-x86_64/codex.exe",
        "openai.chatgpt-*/bin/linux-x86_64/codex",
        "openai.chatgpt-*/bin/darwin-*/codex",
    )
    for pattern in patterns:
        candidates.extend(extension_root.glob(pattern))

    compatible = []
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        version = _version(candidate)
        if version and version >= MINIMUM_CODEX_VERSION:
            compatible.append((candidate.resolve(), version))
    if not compatible:
        raise RuntimeError("No Luna-compatible Codex binary was found. Update Codex first.")
    return max(compatible, key=lambda item: item[1])


def find_saxo_cli(repo_root: Path) -> Path:
    candidates = (
        repo_root / ".venv" / "Scripts" / "saxo-cli.exe",
        repo_root / ".venv" / "bin" / "saxo-cli",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "The repository virtual environment is missing saxo-cli. "
        "Run 'python -m pip install -e .[cli]' inside .venv first."
    )


def saxo_credential_dir() -> Path:
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "Saxo"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Saxo"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "saxo"


def run_preflight(saxo_cli: Path, environment: dict[str, str]) -> dict:
    result = subprocess.run(
        [str(saxo_cli), "--env", "sim", "agent", "snapshot", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Saxo SIM authentication preflight failed. Run "
            "'saxo-cli --env sim auth login' interactively first."
        )
    try:
        snapshot = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Saxo SIM preflight did not return valid JSON.") from exc
    if not isinstance(snapshot, dict) or snapshot.get("error") or snapshot.get("environment") != "sim":
        raise RuntimeError("Saxo SIM preflight did not return a valid SIM snapshot.")
    return snapshot


def build_codex_command(codex: Path, repo_root: Path, credential_dir: Path, prompt: str) -> list[str]:
    return [
        str(codex),
        "exec",
        "--json",
        "--color",
        "never",
        "-C",
        str(repo_root),
        "--add-dir",
        str(credential_dir),
        "-m",
        "gpt-5.6-luna",
        "-c",
        'model_reasoning_effort="medium"',
        "-c",
        "sandbox_workspace_write.network_access=true",
        prompt,
    ]


def event_messages(event: dict) -> list[tuple[str, str]]:
    event_type = str(event.get("type", ""))
    if event_type == "thread.started":
        return [("activity", "Codex session started.")]
    if event_type == "turn.started":
        return [("progress", "Portfolio review started.")]
    if event_type in {"turn.failed", "error"}:
        return [("error", event.get("message") or event.get("error") or "Codex reported an error.")]
    if event_type == "turn.completed":
        usage = event.get("usage") or {}
        tokens = usage.get("output_tokens")
        detail = "Portfolio review turn completed."
        if isinstance(tokens, int):
            detail += f" Output tokens: {tokens}."
        return [("progress", detail)]
    if event_type not in {"item.started", "item.updated", "item.completed"}:
        return []

    item = event.get("item") or {}
    item_type = str(item.get("type", "activity"))
    completed = event_type == "item.completed"
    if item_type == "reasoning" and completed:
        return [("progress", item.get("text") or item.get("summary") or "Analysis updated.")]
    if item_type in {"agent_message", "message"} and completed:
        return [("conclusion", item.get("text") or item.get("content") or "Agent response completed.")]
    if item_type == "command_execution":
        command = item.get("command") or "repository command"
        if completed:
            return [("activity", f"Command completed: {command}")]
        if event_type == "item.started":
            return [("activity", f"Running: {command}")]
    if item_type in {"mcp_tool_call", "tool_call", "web_search"}:
        name = item.get("tool") or item.get("name") or item_type.replace("_", " ")
        state = "completed" if completed else "started"
        return [("activity", f"{name} {state}.")]
    return []


def stream_codex(command: list[str], environment: dict[str, str], reporter: ActivityReporter) -> int:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        bufsize=1,
    )
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            reporter.emit("activity", line)
            continue
        for kind, message in event_messages(event):
            reporter.emit(kind, message)
    return process.wait()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def summarize_run(repo_root: Path, previous_run_id: str | None) -> str:
    current_file = repo_root / "agent" / ".current_run_id"
    try:
        run_id = current_file.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "Codex exited without recording a run ID."
    if not run_id or run_id == previous_run_id:
        return "Codex exited without creating a new investment run."
    run_dir = repo_root / "agent" / "runs" / run_id
    execution = _read_json(run_dir / "execution.json")
    status = _read_json(run_dir / "run-status.json")
    plan = _read_json(run_dir / "plan.json")
    review = _read_json(run_dir / "holdings-review.json")
    terminal_status = execution.get("status") or status.get("status") or "unknown"
    orders = execution.get("orders")
    if not isinstance(orders, list):
        orders = plan.get("orders") if isinstance(plan.get("orders"), list) else []
    assessments = review.get("positions") if isinstance(review.get("positions"), list) else []
    counts = {decision: 0 for decision in ("add", "hold", "trim", "exit")}
    for assessment in assessments:
        decision = str(assessment.get("decision", "")).casefold()
        if decision in counts:
            counts[decision] += 1
    dispositions = ", ".join(f"{key}={value}" for key, value in counts.items())
    return (
        f"Run {run_id}: status={terminal_status}, orders={len(orders)}, "
        f"positions reviewed={len(assessments)} ({dispositions}). Artifacts: {run_dir}"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        help="Additional portfolio-review direction appended to the standard safe prompt.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    reporter = ActivityReporter(repo_root / "investbot.log")
    current_file = repo_root / "agent" / ".current_run_id"
    try:
        previous_run_id = current_file.read_text(encoding="utf-8-sig").strip()
    except OSError:
        previous_run_id = None
    prompt = DEFAULT_PROMPT
    if args.prompt:
        prompt += f" Additional user direction: {args.prompt.strip()}"

    try:
        reporter.emit("activity", "Checking Codex installation and login.")
        codex, version = find_codex()
        login = subprocess.run(
            [str(codex), "login", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if login.returncode != 0:
            raise RuntimeError(f"Codex is not logged in. Run '{codex} login' first.")
        reporter.emit("activity", login.stdout.strip() or "Codex login confirmed.")
        reporter.emit("activity", f"Using Codex {'.'.join(map(str, version))} at {codex}.")

        saxo_cli = find_saxo_cli(repo_root)
        environment = os.environ.copy()
        environment["PATH"] = str(saxo_cli.parent) + os.pathsep + environment.get("PATH", "")
        environment["TRADING_ENABLED"] = "false"
        reporter.emit("activity", "Checking Saxo SIM authentication and current portfolio.")
        snapshot = run_preflight(saxo_cli, environment)
        balance = snapshot.get("balance") or {}
        reporter.emit(
            "progress",
            f"Saxo SIM ready: {len(snapshot.get('positions') or [])} positions, "
            f"cash={balance.get('cash', 'unknown')}, net equity={balance.get('net_equity', 'unknown')}.",
        )

        environment["TRADING_ENABLED"] = "true"
        credential_dir = saxo_credential_dir()
        reporter.emit("prompt", prompt)
        reporter.emit("activity", "Launching Luna portfolio manager with live progress output.")
        command = build_codex_command(codex, repo_root, credential_dir, prompt)
        exit_code = stream_codex(command, environment, reporter)
        summary = summarize_run(repo_root, previous_run_id)
        reporter.emit("conclusion" if exit_code == 0 else "error", summary)
        if exit_code != 0:
            reporter.emit("error", f"The Saxo investment bot exited with code {exit_code}.")
        return exit_code
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        reporter.emit("error", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
