#!/usr/bin/env python3
"""Run the project's local linter without requiring CI or network access."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local Saxo source linting")
    parser.add_argument("--fix", action="store_true", help="Apply safe Ruff fixes")
    args = parser.parse_args(argv)

    executable = shutil.which("ruff")
    if executable is None:
        try:
            import ruff  # noqa: F401
        except ImportError:
            print("Ruff is not installed. Run: python -m pip install -e '.[dev]'", file=sys.stderr)
            return 2

    runner = [executable] if executable else [sys.executable, "-m", "ruff"]
    format_command = runner + ["format", "."] if args.fix else runner + ["format", "--check", "."]
    check_command = runner + ["check", "."]
    if args.fix:
        check_command.append("--fix")
    format_status = subprocess.call(format_command)
    check_status = subprocess.call(check_command)
    return format_status or check_status


if __name__ == "__main__":
    raise SystemExit(main())
