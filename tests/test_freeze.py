"""Offline tests for ``scripts/freeze.py``: checks, deterministic manifest, tag creation and every refusal.

Tag creation is tested only in TEMPORARY git repositories (never in the project repository), with ``freeze.git`` wrapped so that
the test can assert that no ``push`` is ever attempted. The project repository is only read.
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import freeze  # noqa: E402

TODAY = datetime.date(2026, 10, 12)
MINI = ("data.txt", "cfg/*.toml")
EXTRACT_HASH = "ab" * 32


def sh(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    sh(path, "init", "-q")
    for key, value in (("user.name", "t"), ("user.email", "t@example.org"), ("commit.gpgsign", "false"), ("tag.gpgsign", "false"), ("core.autocrlf", "false")):
        sh(path, "config", key, value)
    return path


def commit_all(repo: Path, message: str) -> None:
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", message)


@pytest.fixture
def mini(monkeypatch) -> None:
    monkeypatch.setattr(freeze, "MANIFEST_PATTERNS", MINI)


@pytest.fixture
def frozen_repo(tmp_path, mini) -> Path:
    """Temporary repository: files committed, then the manifest computed from them and committed (the state before 'tag')."""
    repo = init_repo(tmp_path / "repo")
    (repo / "data.txt").write_bytes(b"alpha\r\nbeta\r\n")
    (repo / "cfg").mkdir()
    (repo / "cfg" / "a.toml").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "files")
    freeze.write_manifest(repo, today=TODAY)
    commit_all(repo, "manifest")
    return repo


@pytest.fixture
def git_log(monkeypatch) -> list[tuple[str, ...]]:
    """Record every git invocation made through ``freeze.git``."""
    calls: list[tuple[str, ...]] = []
    original = freeze.git

    def recording(root: Path, *args: str):
        calls.append(args)
        return original(root, *args)

    monkeypatch.setattr(freeze, "git", recording)
    return calls


def passing(_root: Path) -> list[freeze.CheckResult]:
    return [freeze.CheckResult("stub", "PASS", "ok")]


# ---------------------------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------------------------
def test_manifest_is_deterministic_and_lf_normalised(frozen_repo):
    first = freeze.manifest_bytes(freeze.build_manifest(frozen_repo, TODAY))
    second = freeze.manifest_bytes(freeze.build_manifest(frozen_repo, TODAY))
    assert first == second and first.endswith(b"\n") and b"\r" not in first
    data = json.loads(first)
    assert list(data["files"]) == sorted(data["files"]) == ["cfg/a.toml", "data.txt"]
    assert data["date"] == "2026-10-12" and data["tag"] == freeze.TAG and data["git_head"] == sh(frozen_repo, "rev-parse", "HEAD")
    assert data["python_version"] == ".".join(map(str, sys.version_info[:3]))
    assert "LF" in data["hash_note"]
    assert data["files"]["data.txt"] == {"sha256": freeze.file_record(frozen_repo / "data.txt")["sha256"], "size": len(b"alpha\nbeta\n")}  # CRLF normalised
    on_disk = json.loads((frozen_repo / freeze.MANIFEST_REL).read_text(encoding="utf-8"))  # written before the manifest commit existed
    assert on_disk["git_head"] == sh(frozen_repo, "rev-parse", "HEAD~1") and {**on_disk, "git_head": data["git_head"]} == data
    assert (frozen_repo / freeze.MANIFEST_REL).read_bytes() == freeze.manifest_bytes(on_disk)


def test_crlf_and_lf_copies_hash_identically(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"x\r\ny\r\n")
    b.write_bytes(b"x\ny\n")
    assert freeze.file_record(a) == freeze.file_record(b)
    b.write_bytes(b"x\ny\nz\n")
    assert freeze.file_record(a) != freeze.file_record(b)


def test_manifest_lists_missing_required_files(tmp_path, mini):
    repo = init_repo(tmp_path / "r")
    (repo / "data.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=r"cfg/\*\.toml"):
        freeze.build_manifest(repo, TODAY)


def test_every_required_pattern_resolves_in_the_project_repository():
    paths, empty = freeze.resolve_patterns(ROOT)
    assert not empty, f"required frozen files missing: {empty}"
    for expected in ("src/models/py/m1.py", "scripts/freeze.py", "config/registry/confirmatory.toml", "data/processed/gold/panel_country_year.sha256", "requirements.lock"):
        assert expected in paths
    assert any(p.startswith("data/raw/") and p.endswith("manifest.jsonl") for p in paths)
    assert "docs/freeze_manifest.json" not in paths  # the manifest does not hash itself


def test_manifest_mode_writes_the_file(tmp_path, mini, monkeypatch):
    repo = init_repo(tmp_path / "r")
    (repo / "data.txt").write_text("x", encoding="utf-8")
    (repo / "cfg").mkdir()
    (repo / "cfg" / "a.toml").write_text("y = 2\n", encoding="utf-8")
    monkeypatch.setattr(freeze, "PROJECT_ROOT", repo)
    assert freeze.main(["manifest"]) == 0
    assert json.loads((repo / freeze.MANIFEST_REL).read_text(encoding="utf-8"))["manifest_version"] == 1
    (repo / "cfg" / "a.toml").unlink()
    assert freeze.main(["manifest"]) == 1  # a required file is missing


# ---------------------------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------------------------
def config_copy(tmp_path: Path) -> Path:
    """Copy of the real registries and contracts (read-only source) in a temporary project root."""
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    shutil.copytree(ROOT / "config" / "registry", root / "config" / "registry")
    shutil.copytree(ROOT / "config" / "contracts", root / "config" / "contracts")
    return root


def edit_confirmatory(root: Path, old: str, new: str) -> None:
    path = root / "config" / "registry" / "confirmatory.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def test_real_registries_and_contracts_have_the_expected_structure():
    result = freeze.check_registries(ROOT)
    assert result.status == "PASS", result.detail


@pytest.mark.parametrize("old, new, needle", [
    ('id = "H2B"', 'id = "H2X"', "family"),
    ('controls = []', 'controls = ["outgap_lag"]', "controls"),
    ('estimator_status = "SELECTED', 'estimator_status = "CANDIDATE', "SELECTED"),
    ('id = "H2W"', 'id = "H2Q"', "H2W"),
])
def test_registry_structure_failures_are_detected(tmp_path, old, new, needle):
    root = config_copy(tmp_path)
    edit_confirmatory(root, old, new)
    result = freeze.check_registries(root)
    assert result.status == "FAIL" and needle in result.detail


def test_open_items_block_while_proposed_or_listed(tmp_path):
    root = config_copy(tmp_path)
    edit_confirmatory(root, 'status = "PROPOSED"', 'status = "CONFIRMED"')
    edit_confirmatory(root, 'open_items = ["D-A smallest effect size of interest to be confirmed by the researcher"]', "open_items = []")
    assert freeze.check_open_items(root).status == "PASS"  # a confirmed SESOI and an empty list: nothing blocks
    edit_confirmatory(root, 'status = "CONFIRMED"', 'status = "PROPOSED"')
    proposed = freeze.check_open_items(root)
    assert proposed.status == "FAIL" and "PROPOSED" in proposed.detail
    edit_confirmatory(root, 'status = "PROPOSED"', 'status = "OPEN"')
    assert "OPEN" in freeze.check_open_items(root).detail
    edit_confirmatory(root, 'status = "OPEN"', 'status = "CONFIRMED"')
    edit_confirmatory(root, "open_items = []", 'open_items = ["something else"]')
    listed = freeze.check_open_items(root)
    assert listed.status == "FAIL" and "something else" in listed.detail
    (root / "config" / "registry" / "secondary.toml").write_text('[registry]\nclass = "secondary"\n[[model]]\nid = "S1"\nstatus = "open"\n', encoding="utf-8")
    edit_confirmatory(root, 'open_items = ["something else"]', "open_items = []")
    assert "secondary.toml" in freeze.check_open_items(root).detail  # status anywhere in any registry counts (case-insensitive)


def test_open_item_registered_in_the_real_confirmatory_registry_is_visible_to_the_check():
    doc = json.loads(json.dumps(freeze._load_toml(ROOT / "config" / "registry" / "confirmatory.toml")))
    statuses = dict(freeze._status_values(doc))
    assert "interpretation.status" in statuses
    result = freeze.check_open_items(ROOT)
    assert (result.status == "PASS") == (statuses["interpretation.status"] not in freeze.OPEN_STATUSES and doc["freeze"]["open_items"] == [])


def test_gold_check_with_injected_tools(tmp_path):
    root = tmp_path / "p"
    gold = root / freeze.GOLD_REL
    gold.mkdir(parents=True)
    (gold / "panel_country_year.parquet").write_bytes(b"x")
    (gold / "panel_country_year.sha256").write_text(f"{EXTRACT_HASH}  label\n", encoding="utf-8")
    gate = type("Gate", (), {"passed": True, "name": "g"})
    bad_gate = type("Gate", (), {"passed": False, "name": "coverage"})

    def tools(extract: str, rebuilt: str, gates: list):
        return lambda _root: (lambda path: "frame", lambda frame: extract, lambda: (rebuilt, gates))

    assert freeze.check_gold(root, tools(EXTRACT_HASH, EXTRACT_HASH, [gate])).status == "PASS"
    assert "differs from recorded" in freeze.check_gold(root, tools("cd" * 32, EXTRACT_HASH, [gate])).detail
    assert "rebuilt from raw" in freeze.check_gold(root, tools(EXTRACT_HASH, "cd" * 32, [gate])).detail
    failed = freeze.check_gold(root, tools(EXTRACT_HASH, EXTRACT_HASH, [gate, bad_gate]))
    assert failed.status == "FAIL" and "coverage" in failed.detail

    def explode(_root):
        raise FileNotFoundError("raw AMECO missing")

    assert "raw AMECO missing" in freeze.check_gold(root, explode).detail
    (gold / "panel_country_year.sha256").unlink()
    assert freeze.check_gold(root, tools(EXTRACT_HASH, EXTRACT_HASH, [gate])).status == "FAIL"


def test_exposure_files_and_the_optional_test_run(tmp_path):
    root = tmp_path / "p"
    (root / "data" / "interim").mkdir(parents=True)
    (root / "tests").mkdir()
    missing, skipped = freeze.check_exposure_and_tests(root, run_tests=False)
    assert missing.status == "FAIL" and "exposure_eu27.csv" in missing.detail and skipped.status == "SKIP" and skipped.passed
    for rel in ("data/interim/election_calendar_eu27.csv", "data/interim/exposure_eu27.csv", "tests/test_elections.py"):
        (root / rel).write_text("x", encoding="utf-8")
    assert freeze.check_exposure_and_tests(root, False)[0].status == "PASS"
    assert freeze.check_exposure_and_tests(root, True, runner=lambda r: (True, "10 passed"))[1].status == "PASS"
    assert freeze.check_exposure_and_tests(root, True, runner=lambda r: (False, "1 failed"))[1].status == "FAIL"
    assert freeze.run_test_suite(root) == (False, "no .venv interpreter found")


def test_results_artefacts_are_detected(tmp_path):
    root = tmp_path / "p"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "gate3_power_update.md").write_text("x", encoding="utf-8")
    assert freeze.check_no_results(root).status == "PASS"
    (root / "reports" / "results").mkdir()
    assert freeze.check_no_results(root).status == "FAIL"
    (root / "reports" / "results").rmdir()
    for name in ("Event_Study_plot.png", "election_window_2.csv"):
        (root / "reports" / name).write_text("x", encoding="utf-8")
        assert freeze.check_no_results(root).status == "FAIL"
        (root / "reports" / name).unlink()
    assert freeze.check_no_results(root).status == "PASS"


def test_real_repository_has_no_results_artefacts():
    assert freeze.check_no_results(ROOT).status == "PASS"


def test_preregistration_document_requirements(tmp_path):
    root = tmp_path / "p"
    (root / "docs").mkdir(parents=True)
    (root / freeze.GOLD_REL).mkdir(parents=True)
    (root / freeze.GOLD_REL / "panel_country_year.sha256").write_text(f"{EXTRACT_HASH}  label\n", encoding="utf-8")
    assert "does not exist" in freeze.check_preregistration(root).detail
    doc = root / "docs" / "preregistration.md"
    doc.write_text("H1 H2B H2W Holm preregistration-v1\n", encoding="utf-8")
    missing = freeze.check_preregistration(root)
    assert missing.status == "FAIL" and "extract hash" in missing.detail
    doc.write_text(f"H1 H2B H2W Holm preregistration-v1 {EXTRACT_HASH}\n", encoding="utf-8")
    assert freeze.check_preregistration(root).status == "PASS"
    doc.write_text(f"H1 H2B H2W preregistration-v1 {EXTRACT_HASH}\n", encoding="utf-8")
    assert "Holm" in freeze.check_preregistration(root).detail


def test_environment_check_against_pins(tmp_path):
    assert freeze.check_environment(ROOT).status == "PASS"  # tests run in the pinned environment (see tests/test_environment.py)
    (tmp_path / "requirements.in").write_text("numpy==0.0.1\n# comment\nnot-a-real-package-xyz==1.0\n", encoding="utf-8")
    result = freeze.check_environment(tmp_path)
    assert result.status == "FAIL" and "numpy" in result.detail and "not installed" in result.detail


def test_clean_tree_check(frozen_repo):
    assert freeze.check_clean_tree(frozen_repo).status == "PASS"
    (frozen_repo / "new.txt").write_text("x", encoding="utf-8")
    assert freeze.check_clean_tree(frozen_repo).status == "FAIL"  # untracked counts as dirty
    (frozen_repo / "new.txt").unlink()
    (frozen_repo / "data.txt").write_bytes(b"changed\n")
    assert freeze.check_clean_tree(frozen_repo).status == "FAIL"
    sh(frozen_repo, "checkout", "--", "data.txt")
    (frozen_repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    commit_all(frozen_repo, "ignore")
    (frozen_repo / "ignored.txt").write_text("x", encoding="utf-8")
    assert freeze.check_clean_tree(frozen_repo).status == "PASS"  # ignored files are allowed


def test_check_mode_exit_status_and_table(monkeypatch, capsys):
    ok = [freeze.CheckResult("a", "PASS", "fine"), freeze.CheckResult("b", "SKIP", "not run")]
    monkeypatch.setattr(freeze, "run_checks", lambda root, run_tests=False: ok)
    assert freeze.main(["check"]) == 0
    assert "PASS" in capsys.readouterr().out
    monkeypatch.setattr(freeze, "run_checks", lambda root, run_tests=False: [*ok, freeze.CheckResult("c", "FAIL", "broken")])
    assert freeze.main(["check"]) == 1
    assert "FAIL  c" in capsys.readouterr().out


def test_run_checks_returns_every_check_in_order_on_the_real_repository():
    names = [r.name for r in freeze.run_checks(ROOT, run_tests=False)]
    assert names[0] == "git working tree clean" and "no results artefacts" in names and "environment matches requirements.in" in names
    assert len(names) == 9  # eight checks, the exposure check contributes the suite line


# ---------------------------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------------------------
def test_tag_is_created_annotated_locally_and_never_pushed(frozen_repo, git_log):
    lines: list[str] = []
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 0
    assert freeze.tag_present(frozen_repo)
    assert sh(frozen_repo, "cat-file", "-t", f"refs/tags/{freeze.TAG}") == "tag"  # annotated, not lightweight
    message = sh(frozen_repo, "tag", "-l", "--format=%(contents)", freeze.TAG)
    assert freeze.file_record(frozen_repo / freeze.MANIFEST_REL)["sha256"] in message
    assert any(f"git push origin {freeze.TAG}" in line and "NOT pushed" in "\n".join(lines) for line in lines)
    assert not any("push" in call for call in git_log) and not any(call[0] in ("push", "remote", "fetch") for call in git_log)
    assert sh(frozen_repo, "rev-parse", f"{freeze.TAG}^{{commit}}") == sh(frozen_repo, "rev-parse", "HEAD")


def test_tag_refused_when_a_check_fails(frozen_repo):
    lines: list[str] = []
    failing = lambda root: [freeze.CheckResult("open items", "FAIL", "D-A")]  # noqa: E731
    assert freeze.create_tag(frozen_repo, checks=failing, out=lines.append) == 1
    assert not freeze.tag_present(frozen_repo) and "REFUSED" in lines[-1]


def test_tag_refused_on_a_dirty_tree(frozen_repo):
    (frozen_repo / "untracked.txt").write_text("x", encoding="utf-8")
    lines: list[str] = []
    assert freeze.create_tag(frozen_repo, checks=lambda r: [freeze.check_clean_tree(r)], out=lines.append) == 1
    assert not freeze.tag_present(frozen_repo)
    # the final clean-tree guard also fires when only the stubbed checks pass
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 1 and not freeze.tag_present(frozen_repo)


def test_tag_refused_when_it_already_exists(frozen_repo):
    sh(frozen_repo, "tag", "-a", freeze.TAG, "-m", "earlier")
    before = sh(frozen_repo, "rev-parse", f"refs/tags/{freeze.TAG}")
    lines: list[str] = []
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 1
    assert "already exists" in lines[-1] and sh(frozen_repo, "rev-parse", f"refs/tags/{freeze.TAG}") == before


def test_tag_refused_while_open_items_remain(tmp_path, mini):
    repo = init_repo(tmp_path / "r")
    shutil.copytree(ROOT / "config" / "registry", repo / "cfg2")
    (repo / "cfg2" / "confirmatory.toml").write_text('[registry]\nclass = "confirmatory"\n[freeze]\nopen_items = ["D-A"]\n', encoding="utf-8")
    (repo / "data.txt").write_text("x\n", encoding="utf-8")
    (repo / "cfg").mkdir()
    (repo / "cfg" / "a.toml").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "files")
    freeze.write_manifest(repo, today=TODAY)
    commit_all(repo, "manifest")
    (repo / "config" / "registry").mkdir(parents=True)
    shutil.copy(repo / "cfg2" / "confirmatory.toml", repo / "config" / "registry" / "confirmatory.toml")
    commit_all(repo, "registry")
    lines: list[str] = []
    assert freeze.create_tag(repo, checks=lambda r: [freeze.check_open_items(r)], out=lines.append) == 1
    assert "open item: D-A" in "\n".join(lines) and not freeze.tag_present(repo)


def test_tag_refused_when_the_manifest_is_missing_stale_or_uncommitted(frozen_repo):
    lines: list[str] = []
    # stale: a frozen file changes after the manifest was written and committed
    (frozen_repo / "data.txt").write_text("edited\n", encoding="utf-8")
    commit_all(frozen_repo, "edit after manifest")
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 1
    assert "differ from a fresh computation" in lines[-1] and not freeze.tag_present(frozen_repo)
    # regenerated but not committed
    freeze.write_manifest(frozen_repo, today=TODAY)
    sh(frozen_repo, "add", "-A")  # staged only
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 1
    assert "committed" in lines[-1] and not freeze.tag_present(frozen_repo)
    commit_all(frozen_repo, "regenerated manifest")
    assert freeze.create_tag(frozen_repo, checks=passing, out=lines.append) == 0  # now consistent


def test_tag_refused_without_a_manifest_or_with_a_foreign_head(tmp_path, mini):
    repo = init_repo(tmp_path / "r")
    (repo / "data.txt").write_text("x\n", encoding="utf-8")
    (repo / "cfg").mkdir()
    (repo / "cfg" / "a.toml").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "files")
    lines: list[str] = []
    assert freeze.create_tag(repo, checks=passing, out=lines.append) == 1 and "does not exist" in lines[-1]
    manifest = freeze.build_manifest(repo, TODAY)
    manifest["git_head"] = "0" * 40  # not an ancestor of HEAD
    (repo / "docs").mkdir()
    (repo / freeze.MANIFEST_REL).write_bytes(freeze.manifest_bytes(manifest))
    commit_all(repo, "manifest with foreign head")
    assert freeze.create_tag(repo, checks=passing, out=lines.append) == 1 and "ancestor" in lines[-1]
    assert not freeze.tag_present(repo)


def test_tag_mode_requires_confirm(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(freeze, "create_tag", lambda *a, **k: called.append(1) or 0)
    assert freeze.main(["tag"]) == 2 and not called
    assert "--confirm" in capsys.readouterr().err
    assert freeze.main(["tag", "--confirm"]) == 0 and called


def test_script_never_invokes_push():
    source = (ROOT / "scripts" / "freeze.py").read_text(encoding="utf-8")
    invocations = [line for line in source.splitlines() if "git(" in line and "def git" not in line]
    assert invocations and not any('"push"' in line for line in invocations)
    assert "subprocess.run" in source and source.count("subprocess.run") == 2  # git() and the pytest run only
