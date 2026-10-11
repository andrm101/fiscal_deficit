"""Discovery logic of scripts/quarto.py (offline; uses temporary folders, never runs Quarto)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import quarto as qw  # noqa: E402


def _fake_install(base: Path, version: str) -> Path:
    exe = base / "Programs" / "Quarto" / version / "bin" / "quarto.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    return exe


def test_explicit_environment_variable_wins(tmp_path):
    exe = tmp_path / "custom" / "quarto.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    assert qw.find_quarto({"QUARTO_PATH": str(exe), "PATH": ""}) == exe


def test_missing_explicit_path_falls_through_to_none(tmp_path):
    assert qw.find_quarto({"QUARTO_PATH": str(tmp_path / "nope.exe"), "PATH": ""}, local_appdata=tmp_path) is None


def test_user_level_install_is_found_and_highest_version_chosen(tmp_path):
    _fake_install(tmp_path, "1.9.2")
    newest = _fake_install(tmp_path, "1.10.19")
    assert qw.find_quarto({"PATH": ""}, local_appdata=tmp_path) == newest  # 1.10 sorts above 1.9 numerically


def test_no_install_anywhere_returns_none(tmp_path):
    assert qw.find_quarto({"PATH": ""}, local_appdata=tmp_path) is None


def test_venv_python_detected_only_when_present(tmp_path):
    assert qw.venv_python(tmp_path) is None
    py = tmp_path / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    assert qw.venv_python(tmp_path) == py


def test_wrapper_contains_no_absolute_user_paths():
    text = (ROOT / "scripts" / "quarto.py").read_text(encoding="utf-8")
    assert "C:\\Users" not in text and "/Users/" not in text
