#!/usr/bin/env python3
"""Run the test suite under stdlib tracing and write a coverage summary.

This keeps the repo self-contained when pytest-cov/coverage.py are not
installed. It traces our project code, ignores the standard library and
site-packages, and writes per-module .cover files into .coverage-trace/.
"""

from __future__ import annotations

import pathlib
import site
import sys
import sysconfig
from typing import Iterable
from trace import Trace

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COVERDIR = ROOT / ".coverage-trace"


def _unique_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if not path:
            continue
        resolved = str(pathlib.Path(path).resolve())
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def _ignored_dirs() -> list[str]:
    paths = []
    paths.extend(
        sysconfig.get_path(name)
        for name in ("stdlib", "platstdlib", "purelib", "platlib")
    )
    paths.extend(site.getsitepackages() if hasattr(site, "getsitepackages") else [])
    paths.append(site.getusersitepackages())
    return _unique_paths(paths)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    tracer = Trace(count=True, trace=False, ignoredirs=_ignored_dirs())
    exit_code = tracer.runfunc(pytest.main, args)
    COVERDIR.mkdir(parents=True, exist_ok=True)
    tracer.results().write_results(show_missing=True, summary=True, coverdir=str(COVERDIR))
    return int(exit_code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
