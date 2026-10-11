"""Run the Quarto CLI with the project's pinned Python, without touching PATH or hard-coding a location.

Quarto is a separate binary (not a pip package). It is located, in order, through:
  1. the QUARTO_PATH environment variable (full path to the executable);
  2. ``quarto`` on PATH;
  3. the user-level install folder ``%LOCALAPPDATA%/Programs/Quarto/<version>/bin`` (highest version).
Its Python engine is pointed at ``.venv`` (QUARTO_PYTHON) when that environment exists.

Usage:  python scripts/quarto.py render reports/thesis/index.qmd --to typst
        python scripts/quarto.py check jupyter
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def venv_python(root: Path = PROJECT_ROOT) -> Path | None:
    """The project virtual environment's interpreter, if it exists (Windows or POSIX layout)."""
    for rel in (Path(".venv") / "Scripts" / "python.exe", Path(".venv") / "bin" / "python"):
        if (root / rel).exists():
            return root / rel
    return None


def _version_key(path: Path) -> tuple[int, ...]:
    parts = path.parent.parent.name.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def find_quarto(env: dict[str, str] | None = None, local_appdata: Path | None = None) -> Path | None:
    """Locate the Quarto executable; None if it cannot be found."""
    env = dict(os.environ) if env is None else env
    explicit = env.get("QUARTO_PATH")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    on_path = shutil.which("quarto", path=env.get("PATH"))
    if on_path:
        return Path(on_path)
    base = local_appdata if local_appdata is not None else (Path(env["LOCALAPPDATA"]) if "LOCALAPPDATA" in env else None)
    if base is not None:
        candidates = sorted((base / "Programs" / "Quarto").glob("*/bin/quarto*"), key=_version_key)
        candidates = [c for c in candidates if c.suffix in {".exe", ""} and c.is_file()]
        if candidates:
            return candidates[-1]
    return None


def main(argv: list[str]) -> int:
    """Run Quarto with the given arguments; returns its exit code (2 if Quarto is not found)."""
    quarto = find_quarto()
    if quarto is None:
        print("Quarto not found: set QUARTO_PATH, put quarto on PATH, or install it under %LOCALAPPDATA%/Programs/Quarto.", file=sys.stderr)
        return 2
    env = dict(os.environ)
    python = venv_python()
    if python is not None:
        env["QUARTO_PYTHON"] = str(python)
    return subprocess.run([str(quarto), *argv], env=env, cwd=PROJECT_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
