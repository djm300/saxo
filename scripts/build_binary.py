#!/usr/bin/env python3
"""Build the standalone Saxo CLI executable locally with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the standalone saxo-cli binary")
    parser.add_argument(
        "--clean", action="store_true", help="Remove the previous build directory first"
    )
    args = parser.parse_args(argv)

    executable = shutil.which("pyinstaller")
    runner = [executable] if executable else [sys.executable, "-m", "PyInstaller"]
    command = runner + [
        "--onefile",
        "--name",
        "saxo-cli",
        "--paths",
        str(ROOT),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
    ]
    if args.clean:
        command.append("--clean")
    command.append(str(ROOT / "saxo_entry.py"))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
