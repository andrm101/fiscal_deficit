"""Pre-registration freeze: check, manifest and tag (milestone M3).

Usage (run with the project environment, ``.venv/Scripts/python.exe scripts/freeze.py ...``)::

    freeze.py check [--run-tests]   read-only; prints a PASS/FAIL table; exit status 1 when any check fails
    freeze.py manifest              write docs/freeze_manifest.json (deterministic: sorted keys, LF, one trailing newline)
    freeze.py tag --confirm         create the ANNOTATED local git tag ``preregistration-v1``; NEVER pushes (prints the command)

Checks (``check``; ``tag`` runs them all, including the test suite)
-------------------------------------------------------------------
1. git working tree clean (ignored files excepted; untracked files count as dirty);
2. the four registries and the contracts parse with the expected structure (confirmatory family {H1, H2B}, H2W descriptive,
   ``estimator_status`` starts with 'SELECTED', ``controls = []``, ``[interpretation]`` and ``[freeze]`` tables present);
3. no open items: no ``status`` equal to PROPOSED or OPEN anywhere in ``config/registry/*.toml`` and ``[freeze] open_items = []``;
4. the gold extract hash recomputed from ``panel_country_year.parquet`` equals ``panel_country_year.sha256``, and the panel rebuilt
   from the raw files reproduces that hash and passes every gate of ``src/evaluate/gates.py``;
5. the exposure files exist (``data/interim``) and ``tests/test_elections.py`` exists; with ``--run-tests`` the whole suite is run
   with the pinned interpreter (``.venv``) and must pass (otherwise this check is reported as SKIP);
6. no results artefacts: ``reports/results`` does not exist and ``reports/`` holds no file matching ``*event*study*`` or ``*election_window*``;
7. ``docs/preregistration.md`` exists and contains 'H1', 'H2B', 'H2W', 'Holm', 'preregistration-v1' and the extract hash;
8. the installed packages match the ``==`` pins of ``requirements.in``.

Manifest
--------
``docs/freeze_manifest.json`` records the ISO date, the git HEAD SHA at the time of writing, the Python version and, for each frozen
file, its SHA-256 and size. TEXT FILES ARE HASHED WITH LF-NORMALISED LINE ENDINGS (CRLF and lone CR become LF; the working copies on
Windows may be CRLF) and ``size`` is the byte length of that normalised content. The manifest itself is committed afterwards, so its
``git_head`` is the parent of the freeze commit; ``tag`` therefore compares only the ``python_version`` and ``files`` sections with a
fresh computation, requires ``git_head`` to be an ancestor of (or equal to) HEAD, and requires HEAD to contain the manifest unchanged.

Tag
---
``tag --confirm`` refuses unless: every check passes; the manifest on disk matches a fresh computation; HEAD contains the committed
manifest; the working tree is clean; the tag does not exist. It then runs ``git tag -a preregistration-v1`` locally and prints
``git push origin preregistration-v1`` for the researcher to run: this script never pushes.
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import importlib.metadata as importlib_metadata
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAG = "preregistration-v1"
MANIFEST_REL = "docs/freeze_manifest.json"
MANIFEST_VERSION = 1
HASH_NOTE = "SHA-256 of the file content with CRLF/CR line endings normalised to LF; size = byte length of that normalised content"
OPEN_STATUSES = {"PROPOSED", "OPEN"}
REGISTRIES = ("confirmatory", "secondary", "exploratory", "predictive")
REQUIRED_PREREG_STRINGS = ("H1", "H2B", "H2W", "Holm", TAG)
FORBIDDEN_REPORT_PATTERNS = ("*event*study*", "*election_window*")
GOLD_REL = "data/processed/gold"
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][^\s#]*)")

# Frozen files: exact paths or glob patterns, relative to the project root, POSIX separators.
MANIFEST_PATTERNS = (
    "config/registry/*.toml", "config/contracts/contracts.toml", "config/countries.csv", "config/acquisition/*.toml", "data/raw/**/manifest.jsonl",
    f"{GOLD_REL}/panel_country_year.sha256", "requirements.in", "requirements.lock",
    "docs/preregistration.md", "docs/decision_log.md", "docs/stage_c_blueprint.md",
    "reports/gate3_calendar_and_sample.md", "reports/gate3_election_exclusions.csv", "reports/gate3_power_update.md", "reports/gate3c_specification_power.md",
    "reports/gate3d_v7_candidate.md", "reports/gold_panel_audit.md", "reports/tier1_descriptives.md",
    "src/normalize/elections.py", "src/normalize/countries.py", "src/normalize/ameco.py", "src/normalize/eurostat.py", "src/features/panel.py",
    "src/evaluate/sample.py", "src/evaluate/gates.py", "src/evaluate/power.py", "src/evaluate/power_variants.py", "src/models/py/m1.py", "scripts/freeze.py",
)


# ---------------------------------------------------------------------------------------------
# git and hashing helpers
# ---------------------------------------------------------------------------------------------
def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run ``git -C root <args>`` capturing text output (the single entry point for git; tests wrap it to record every call)."""
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=300)


def normalised_bytes(path: Path) -> bytes:
    """File content with CRLF and lone CR replaced by LF."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def file_record(path: Path) -> dict[str, object]:
    """``{'sha256', 'size'}`` of the LF-normalised content."""
    data = normalised_bytes(path)
    return {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def head_sha(root: Path) -> str:
    """Current HEAD commit SHA ('' when the repository has no commit)."""
    done = git(root, "rev-parse", "HEAD")
    return done.stdout.strip() if done.returncode == 0 else ""


def tag_present(root: Path, tag: str = TAG) -> bool:
    """True when ``git tag --list <tag>`` lists exactly that tag."""
    done = git(root, "tag", "--list", tag)
    return done.returncode == 0 and tag in done.stdout.split()


def resolve_patterns(root: Path, patterns: Iterable[str] | None = None) -> tuple[list[str], list[str]]:
    """``(existing relative paths, patterns that matched nothing)``; each pattern is a path or a glob (``**`` allowed)."""
    found: set[str] = set()
    empty: list[str] = []
    for pattern in MANIFEST_PATTERNS if patterns is None else patterns:
        matches = [p for p in root.glob(pattern) if p.is_file()]
        if not matches:
            empty.append(pattern)
        found.update(p.relative_to(root).as_posix() for p in matches)
    return sorted(found), empty


def build_manifest(root: Path = PROJECT_ROOT, today: datetime.date | None = None, patterns: Iterable[str] | None = None) -> dict:
    """Manifest dictionary. Raises ``FileNotFoundError`` listing every required file or pattern that does not exist."""
    paths, empty = resolve_patterns(root, patterns)
    if empty:
        raise FileNotFoundError("required files missing: " + ", ".join(empty))
    return {
        "manifest_version": MANIFEST_VERSION, "tag": TAG, "date": (today or datetime.date.today()).isoformat(), "git_head": head_sha(root),
        "python_version": ".".join(str(v) for v in sys.version_info[:3]), "hash_note": HASH_NOTE,
        "files": {rel: file_record(root / rel) for rel in paths},
    }


def manifest_bytes(manifest: dict) -> bytes:
    """Deterministic serialisation: sorted keys, two-space indent, LF, one trailing newline."""
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def write_manifest(root: Path = PROJECT_ROOT, today: datetime.date | None = None, patterns: Iterable[str] | None = None) -> Path:
    """Write ``docs/freeze_manifest.json`` and return its path."""
    path = root / MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest_bytes(build_manifest(root, today, patterns)))
    return path


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckResult:
    """Outcome of one check; ``status`` is 'PASS', 'FAIL' or 'SKIP' (not run; does not fail the table)."""

    name: str
    status: str
    detail: str

    @property
    def passed(self) -> bool:
        """True unless the check failed (SKIP is not a failure)."""
        return self.status != "FAIL"


def _result(name: str, ok: bool, detail: str) -> CheckResult:
    return CheckResult(name, "PASS" if ok else "FAIL", detail)


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def check_clean_tree(root: Path) -> CheckResult:
    """1. ``git status --porcelain`` is empty (ignored files are not listed by git)."""
    done = git(root, "status", "--porcelain")
    if done.returncode != 0:
        return _result("git working tree clean", False, "git status failed: " + done.stderr.strip()[:200])
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return _result("git working tree clean", not lines, "clean" if not lines else f"{len(lines)} changed or untracked paths, e.g. {lines[0].strip()}")


def check_registries(root: Path) -> CheckResult:
    """2. Registries and contracts parse and have the expected structure."""
    name = "registries and contracts parse"
    problems: list[str] = []
    docs: dict[str, dict] = {}
    for reg in REGISTRIES:
        try:
            docs[reg] = _load_toml(root / "config" / "registry" / f"{reg}.toml")
        except (OSError, tomllib.TOMLDecodeError) as error:
            problems.append(f"{reg}.toml: {error}")
            continue
        if docs[reg].get("registry", {}).get("class") != reg:
            problems.append(f"{reg}.toml: registry.class is not {reg!r}")
    try:
        contracts = _load_toml(root / "config" / "contracts" / "contracts.toml")
        if set(contracts) != {"bronze", "silver", "gold"}:
            problems.append(f"contracts.toml layers are {sorted(contracts)}")
    except (OSError, tomllib.TOMLDecodeError) as error:
        problems.append(f"contracts.toml: {error}")
    conf = docs.get("confirmatory")
    if conf is not None:
        family = {h.get("id") for h in conf.get("hypothesis", []) if h.get("family") == "holm2"}
        if family != {"H1", "H2B"} or {h.get("id") for h in conf.get("hypothesis", [])} != {"H1", "H2B"}:
            problems.append(f"confirmatory family is {sorted(family)}, expected H1 and H2B")
        if [d.get("id") for d in conf.get("descriptive", [])] != ["H2W"]:
            problems.append("H2W is not the single descriptive entry")
        models = conf.get("model", [])
        if len(models) != 1 or models[0].get("id") != "M1":
            problems.append("confirmatory registry must define exactly the model M1")
        else:
            if not str(models[0].get("estimator_status", "")).startswith("SELECTED"):
                problems.append("estimator_status does not start with 'SELECTED'")
            if models[0].get("controls") != []:
                problems.append(f"controls is {models[0].get('controls')!r}, expected []")
        for table in ("interpretation", "freeze"):
            if table not in conf:
                problems.append(f"table [{table}] missing")
    return _result(name, not problems, "4 registries + contracts OK" if not problems else "; ".join(problems))


def _status_values(node: object, path: str = "") -> Iterable[tuple[str, str]]:
    """Every ``status`` string found anywhere in a parsed TOML document, with its path."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "status" and isinstance(value, str):
                yield f"{path}.{key}".lstrip("."), value
            else:
                yield from _status_values(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _status_values(value, f"{path}[{i}]")


def check_open_items(root: Path) -> CheckResult:
    """3. No PROPOSED/OPEN status in any registry and an empty ``[freeze] open_items`` list."""
    name = "no open items"
    problems: list[str] = []
    for file in sorted((root / "config" / "registry").glob("*.toml")):
        try:
            doc = _load_toml(file)
        except (OSError, tomllib.TOMLDecodeError) as error:
            problems.append(f"{file.name}: {error}")
            continue
        for where, value in _status_values(doc):
            if value.strip().upper() in OPEN_STATUSES:
                problems.append(f"{file.name}: {where} = {value!r}")
        if file.name == "confirmatory.toml":
            items = doc.get("freeze", {}).get("open_items")
            if not isinstance(items, list):
                problems.append("confirmatory.toml: [freeze] open_items missing")
            elif items:
                problems.extend(f"open item: {item}" for item in items)
    return _result(name, not problems, "none" if not problems else "; ".join(problems))


def recorded_extract_hash(root: Path) -> str:
    """First token of ``panel_country_year.sha256`` ('' when absent)."""
    path = root / GOLD_REL / "panel_country_year.sha256"
    return path.read_text(encoding="utf-8").split()[0] if path.exists() and path.read_text(encoding="utf-8").split() else ""


def _default_gold_tools(root: Path):
    """Import the project modules lazily (``panel`` imports a lot) and return ``(read_parquet, extract_hash, rebuild_and_gate)``."""
    for sub in ("normalize", "evaluate", "features"):
        sys.path.insert(0, str(root / "src" / sub))
    import pandas as pd
    import gates
    import panel

    def rebuild() -> tuple[str, list]:
        build = panel.build_gold_panel()
        return panel.extract_hash(build.panel), gates.run_gates(build.panel, build.source_capb, build.last_observed_year)

    return pd.read_parquet, panel.extract_hash, rebuild


def check_gold(root: Path, tools: Callable[[Path], tuple] | None = None) -> CheckResult:
    """4. Parquet hash == recorded hash; the panel rebuilt from the raw files has the same hash and passes every gate.

    ``tools(root)`` returns ``(read_parquet, extract_hash, rebuild)`` and is injectable for tests.
    """
    name = "gold extract hash and gates"
    parquet = root / GOLD_REL / "panel_country_year.parquet"
    recorded = recorded_extract_hash(root)
    if not parquet.exists() or not recorded:
        return _result(name, False, "gold parquet or its .sha256 file is missing")
    try:
        read_parquet, extract_hash, rebuild = (tools or _default_gold_tools)(root)
        recomputed = extract_hash(read_parquet(parquet))
        if recomputed != recorded:
            return _result(name, False, f"parquet hash {recomputed[:16]}... differs from recorded {recorded[:16]}...")
        rebuilt, results = rebuild()
    except Exception as error:  # noqa: BLE001  (any failure to rebuild or gate is a failed check, reported verbatim)
        return _result(name, False, f"{type(error).__name__}: {str(error)[:300]}")
    failed = [r.name for r in results if not r.passed]
    if rebuilt != recorded:
        return _result(name, False, f"panel rebuilt from raw has hash {rebuilt[:16]}..., recorded {recorded[:16]}...")
    return _result(name, not failed, f"hash {recorded[:16]}... reproduced; {len(results)} gates pass" if not failed else f"gates failed: {failed}")


def venv_python(root: Path) -> Path | None:
    """The project virtual environment's interpreter (Windows or POSIX layout), if present."""
    for rel in (Path(".venv") / "Scripts" / "python.exe", Path(".venv") / "bin" / "python"):
        if (root / rel).exists():
            return root / rel
    return None


def run_test_suite(root: Path) -> tuple[bool, str]:
    """Run the whole suite with the pinned interpreter; returns ``(all passed, last output line)``."""
    python = venv_python(root)
    if python is None:
        return False, "no .venv interpreter found"
    done = subprocess.run([str(python), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=root, capture_output=True, text=True, check=False)
    tail = [line for line in done.stdout.strip().splitlines() if line.strip()]
    return done.returncode == 0, tail[-1] if tail else done.stderr.strip()[-200:]


def check_exposure_and_tests(root: Path, run_tests: bool, runner: Callable[[Path], tuple[bool, str]] = run_test_suite) -> list[CheckResult]:
    """5. Exposure files and the exposure builder's test file exist; the suite passes when ``run_tests``."""
    needed = ["data/interim/election_calendar_eu27.csv", "data/interim/exposure_eu27.csv", "tests/test_elections.py"]
    missing = [rel for rel in needed if not (root / rel).exists()]
    results = [_result("exposure files and builder test exist", not missing, "present" if not missing else "missing: " + ", ".join(missing))]
    if run_tests:
        ok, tail = runner(root)
        results.append(_result("full test suite passes (pinned interpreter)", ok, tail))
    else:
        results.append(CheckResult("full test suite passes (pinned interpreter)", "SKIP", "not run (use --run-tests)"))
    return results


def check_no_results(root: Path) -> CheckResult:
    """6. No ``reports/results`` and no event-study or election-window files under ``reports/``."""
    problems = []
    if (root / "reports" / "results").exists():
        problems.append("reports/results exists")
    reports = root / "reports"
    if reports.exists():
        for path in reports.rglob("*"):
            if path.is_file() and any(fnmatch.fnmatch(path.name.lower(), pat) for pat in FORBIDDEN_REPORT_PATTERNS):
                problems.append(f"forbidden artefact {path.relative_to(root).as_posix()}")
    return _result("no results artefacts", not problems, "none" if not problems else "; ".join(problems))


def check_preregistration(root: Path) -> CheckResult:
    """7. ``docs/preregistration.md`` exists and contains the required strings and the extract hash."""
    name = "preregistration.md complete"
    path = root / "docs" / "preregistration.md"
    if not path.exists():
        return _result(name, False, "docs/preregistration.md does not exist")
    text = path.read_text(encoding="utf-8")
    needed = list(REQUIRED_PREREG_STRINGS)
    digest = recorded_extract_hash(root)
    missing = [s for s in needed if s not in text]
    if not digest:
        missing.append("extract hash (no recorded hash available)")
    elif digest not in text:
        missing.append("extract hash " + digest[:16] + "...")
    return _result(name, not missing, "all required strings present" if not missing else "missing: " + ", ".join(missing))


def check_environment(root: Path) -> CheckResult:
    """8. Installed versions equal the ``==`` pins of ``requirements.in``."""
    name = "environment matches requirements.in"
    path = root / "requirements.in"
    if not path.exists():
        return _result(name, False, "requirements.in missing")
    mismatches = []
    pins = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PIN.match(line.strip())
        if not match:
            continue
        pins += 1
        try:
            installed = importlib_metadata.version(match.group(1))
        except importlib_metadata.PackageNotFoundError:
            installed = "not installed"
        if installed != match.group(2):
            mismatches.append(f"{match.group(1)}: pinned {match.group(2)}, installed {installed}")
    if pins == 0:
        mismatches.append("no pins found")
    return _result(name, not mismatches, f"{pins} pins match" if not mismatches else f"{sys.executable}: " + "; ".join(mismatches))


def run_checks(root: Path = PROJECT_ROOT, run_tests: bool = False) -> list[CheckResult]:
    """All eight checks in order (read-only)."""
    return [
        check_clean_tree(root), check_registries(root), check_open_items(root), check_gold(root),
        *check_exposure_and_tests(root, run_tests), check_no_results(root), check_preregistration(root), check_environment(root),
    ]


def format_table(results: list[CheckResult]) -> str:
    """Plain-text PASS/FAIL table."""
    return "\n".join(f"{r.status:<4}  {r.name:<46} {r.detail}" for r in results)


# ---------------------------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------------------------
def manifest_problems(root: Path) -> list[str]:
    """Why the committed manifest does not justify a tag (empty list: it does)."""
    path = root / MANIFEST_REL
    if not path.exists():
        return [f"{MANIFEST_REL} does not exist (run 'manifest', review and commit it)"]
    try:
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        fresh = build_manifest(root)
    except (ValueError, FileNotFoundError) as error:
        return [f"manifest unreadable or inputs missing: {error}"]
    problems = []
    if path.read_bytes() != manifest_bytes(on_disk):
        problems.append("manifest on disk is not in the deterministic serialisation")
    for section in ("manifest_version", "tag", "python_version", "files"):
        if on_disk.get(section) != fresh.get(section):
            if section == "files":
                changed = sorted({k for k in (*on_disk.get("files", {}), *fresh["files"]) if on_disk.get("files", {}).get(k) != fresh["files"].get(k)})
                problems.append(f"manifest files differ from a fresh computation: {changed[:5]}")
            else:
                problems.append(f"manifest {section} differs from a fresh computation")
    recorded_head = on_disk.get("git_head", "")
    if not recorded_head or git(root, "merge-base", "--is-ancestor", recorded_head, "HEAD").returncode != 0:
        problems.append("manifest git_head is not an ancestor of (or equal to) HEAD")
    committed = git(root, "show", f"HEAD:{MANIFEST_REL}")
    if committed.returncode != 0:
        problems.append("HEAD does not contain the committed manifest (commit docs/freeze_manifest.json first)")
    elif committed.stdout.replace("\r\n", "\n") != path.read_bytes().decode("utf-8").replace("\r\n", "\n"):
        problems.append("the manifest committed at HEAD differs from the one on disk")
    return problems


def create_tag(root: Path = PROJECT_ROOT, checks: Callable[[Path], list[CheckResult]] | None = None, out: Callable[[str], None] = print) -> int:
    """Create the annotated tag locally when every condition holds. Returns the exit status (0 created, 1 refused). Never pushes."""
    results = (checks or (lambda r: run_checks(r, run_tests=True)))(root)
    out(format_table(results))
    failures = [r.name for r in results if not r.passed]
    if failures:
        out(f"REFUSED: checks failed: {', '.join(failures)}")
        return 1
    if tag_present(root):
        out(f"REFUSED: tag {TAG} already exists")
        return 1
    problems = manifest_problems(root)
    if problems:
        out("REFUSED: " + "; ".join(problems))
        return 1
    status = check_clean_tree(root)  # re-checked last: nothing may change between the checks and the tag
    if not status.passed:
        out("REFUSED: " + status.detail)
        return 1
    manifest_hash = file_record(root / MANIFEST_REL)["sha256"]
    message = f"Pre-registration freeze v1\n\nfreeze manifest sha256 (LF-normalised): {manifest_hash}\nextract hash: {recorded_extract_hash(root)}\n"
    done = git(root, "tag", "-a", TAG, "-m", message)
    if done.returncode != 0:
        out("REFUSED: git tag failed: " + done.stderr.strip())
        return 1
    out(f"created local annotated tag {TAG} on {head_sha(root)[:12]}")
    out(f"NOT pushed. To publish it, run yourself:  git push origin {TAG}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Pre-registration freeze (check, manifest, tag).")
    sub = parser.add_subparsers(dest="mode", required=True)
    check = sub.add_parser("check", help="read-only checks; non-zero exit on any failure")
    check.add_argument("--run-tests", action="store_true", help="also run the whole test suite with the pinned interpreter")
    sub.add_parser("manifest", help="write docs/freeze_manifest.json")
    tag = sub.add_parser("tag", help="create the local annotated tag (never pushes)")
    tag.add_argument("--confirm", action="store_true", help="required: acknowledge that the registry and code are final")
    args = parser.parse_args(argv)
    if args.mode == "check":
        results = run_checks(PROJECT_ROOT, args.run_tests)
        print(format_table(results))
        return 0 if all(r.passed for r in results) else 1
    if args.mode == "manifest":
        try:
            path = write_manifest(PROJECT_ROOT)
        except FileNotFoundError as error:
            print(f"cannot write the manifest: {error}", file=sys.stderr)
            return 1
        print(f"written {path.relative_to(PROJECT_ROOT).as_posix()}")
        return 0
    if not args.confirm:
        print("REFUSED: 'tag' requires --confirm", file=sys.stderr)
        return 2
    return create_tag(PROJECT_ROOT)


if __name__ == "__main__":
    sys.exit(main())
