"""The test run must use the pinned environment (requirements.in / requirements.lock).

On the development machine the ``pytest`` found on PATH belongs to a different Anaconda interpreter (older pandas and pyarrow, which cannot read
Parquet written by pyarrow 24). Fail with a clear message instead of an obscure Parquet error. Run the suite with the project environment:
``.venv/Scripts/python.exe -m pytest`` (Windows) or ``.venv/bin/python -m pytest``.
"""
from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][^\s#]*)")


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (ROOT / "requirements.in").read_text(encoding="utf-8").splitlines():
        match = PIN.match(line.strip())
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def test_requirements_in_pins_the_core_libraries():
    assert {"pandas", "numpy", "scipy", "statsmodels", "linearmodels", "pyarrow", "duckdb"} <= set(_pins())


def test_installed_versions_match_the_pins():
    mismatches = []
    for package, pinned in _pins().items():
        try:
            installed = md.version(package)
        except md.PackageNotFoundError:
            installed = "not installed"
        if installed != pinned:
            mismatches.append(f"{package}: pinned {pinned}, installed {installed}")
    assert not mismatches, (
        f"interpreter {sys.executable} does not match requirements.in: {mismatches}. "
        "Run the tests with the project environment (.venv)."
    )


def test_python_minor_version_matches_the_lock():
    lock_header = (ROOT / "requirements.lock").read_text(encoding="utf-8")[:600]
    assert f"python-version 3.{sys.version_info.minor}" in lock_header.replace("--python-version ", "python-version "), (
        "requirements.lock was compiled for a different Python minor version"
    )
