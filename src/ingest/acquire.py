"""Opt-in acquisition layer (ADR-001).

Downloads the immutable raw files listed in a TOML manifest, verifies them, hashes
them and appends one provenance line per file to ``<manifest_dir>/manifest.jsonl``.
This is the ONLY module in the project that may use the network, and only when
``--allow-network`` is passed. Every other stage reads the resulting local files offline.

Rules enforced here:
  * destinations must lie under ``data/raw/`` and are never overwritten;
  * downloads go to ``<dest>.partial`` and are promoted atomically only after checks pass;
  * the response Content-Type must match the manifest (rejects HTML error pages);
  * ``size_basis = "measured"`` entries must match their expected size exactly;
  * accepted files are set read-only.

Usage:
    python src/ingest/acquire.py --manifest config/acquisition/gate1_ameco_2026_spring.toml --dry-run
    python src/ingest/acquire.py --manifest ... --allow-network [--only A01 A05] [--include-optional]
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import stat
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_REL = Path("data") / "raw"
USER_AGENT = "fiscal-deficit-capstone/0.1 (academic research; static-data acquisition)"
CHUNK_BYTES = 1 << 20
STRICT_SIZE_BASES = {"measured"}
MAX_ATTEMPTS = 3  # transient transport errors (truncated chunked bodies, resets, timeouts) are retried
RETRY_SLEEP_SECONDS = 2.0  # multiplied by the attempt number


class AcquisitionError(RuntimeError):
    """Raised when a file cannot be acquired without breaking an invariant."""


@dataclass(frozen=True)
class FileSpec:
    """One manifest entry."""

    id: str
    url: str
    dest: str
    content_type: str
    expected_size_bytes: int
    size_basis: str
    licence_status: str
    role: str = ""
    note: str = ""
    optional: bool = False


@dataclass(frozen=True)
class Release:
    """Manifest header plus its files."""

    source_id: str
    vintage: str
    manifest_dir: str
    files: tuple[FileSpec, ...]


def load_manifest(path: Path) -> Release:
    """Parse and validate a TOML acquisition manifest."""
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    head: dict[str, Any] = raw["release"]
    files: list[FileSpec] = []
    for entry in raw["file"]:
        files.append(
            FileSpec(
                id=entry["id"],
                url=entry["url"],
                dest=entry["dest"],
                content_type=entry["content_type"],
                expected_size_bytes=int(entry.get("expected_size_bytes", 0)),
                size_basis=entry.get("size_basis", "unknown"),
                licence_status=entry.get("licence_status", "unknown"),
                role=entry.get("role", ""),
                note=entry.get("note", ""),
                optional=bool(entry.get("optional", False)),
            )
        )
    ids = [f.id for f in files]
    if len(ids) != len(set(ids)):
        raise AcquisitionError("duplicate file ids in manifest")
    for f in files:
        if not f.url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise AcquisitionError(f"{f.id}: only https (or localhost for tests) URLs are allowed")
    return Release(head["source_id"], head["vintage"], head["manifest_dir"], tuple(files))


def resolve_dest(root: Path, rel: str) -> Path:
    """Return the absolute destination, refusing anything outside ``data/raw``."""
    candidate = (root / rel).resolve()
    allowed = (root / RAW_REL).resolve()
    if allowed != candidate and allowed not in candidate.parents:
        raise AcquisitionError(f"destination escapes data/raw: {rel}")
    return candidate


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest_lines(manifest_path: Path) -> list[dict[str, Any]]:
    """Read existing provenance lines (empty list if none)."""
    if not manifest_path.exists():
        return []
    return [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line]


def _media_type(header_value: str | None) -> str:
    return (header_value or "").split(";")[0].strip().lower()


def _download_once(spec: FileSpec, partial: Path) -> tuple[int, str, dict[str, Any]]:
    """One download attempt into ``partial``. Returns (size, sha256 hex, response metadata)."""
    request = urllib.request.Request(spec.url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as resp:  # noqa: S310 (scheme validated above)
        got_type = _media_type(resp.headers.get("Content-Type"))
        if got_type != _media_type(spec.content_type):
            raise AcquisitionError(f"{spec.id}: content type {got_type!r}, expected {spec.content_type!r}")
        with partial.open("wb") as out:
            for block in iter(lambda: resp.read(CHUNK_BYTES), b""):
                out.write(block)
                digest.update(block)
                size += len(block)
        declared = resp.headers.get("Content-Length")
        if declared is not None and declared.strip().isdigit() and size != int(declared):
            # http.client does not raise on a short body when read(n) is used with a declared length
            raise http.client.IncompleteRead(b"", int(declared) - size)
        meta = {
            "final_url": resp.geturl(),
            "http_status": getattr(resp, "status", 200),
            "content_type": got_type,
            "last_modified": resp.headers.get("Last-Modified"),
            "etag": resp.headers.get("ETag"),
        }
    return size, digest.hexdigest(), meta


def acquire_file(spec: FileSpec, release: Release, root: Path) -> dict[str, Any]:
    """Download one file, or confirm it is already acquired. Returns the provenance record."""
    dest = resolve_dest(root, spec.dest)
    manifest_path = resolve_dest(root, release.manifest_dir) / "manifest.jsonl"
    existing = {rec["id"]: rec for rec in read_manifest_lines(manifest_path)}

    if dest.exists():
        recorded = existing.get(spec.id)
        local_hash = sha256_file(dest)
        if recorded and recorded["sha256"] == local_hash:
            return {**recorded, "status": "already_acquired"}
        raise AcquisitionError(
            f"{spec.id}: {spec.dest} exists but does not match the recorded hash; refusing to overwrite"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    last_error: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        partial.unlink(missing_ok=True)
        try:
            size, digest_hex, meta = _download_once(spec, partial)
            break
        except (http.client.HTTPException, ConnectionError, TimeoutError) as exc:  # transient: retry
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_SLEEP_SECONDS * attempt)
        except (urllib.error.URLError, OSError, AcquisitionError):  # permanent: fail this file now
            partial.unlink(missing_ok=True)
            raise
    else:
        raise AcquisitionError(f"{spec.id}: download failed after {MAX_ATTEMPTS} attempts: {last_error!r}")

    if size == 0:
        partial.unlink(missing_ok=True)
        raise AcquisitionError(f"{spec.id}: empty response")
    if spec.size_basis in STRICT_SIZE_BASES and size != spec.expected_size_bytes:
        partial.unlink(missing_ok=True)
        raise AcquisitionError(f"{spec.id}: size {size} != measured {spec.expected_size_bytes}")

    if spec.expected_size_bytes and spec.size_basis not in STRICT_SIZE_BASES:
        size_check = "match" if size == spec.expected_size_bytes else "differs_from_expected"
    else:
        size_check = "not_checked"

    os.replace(partial, dest)
    dest.chmod(stat.S_IREAD)
    record = {
        "id": spec.id,
        "source_id": release.source_id,
        "vintage": release.vintage,
        "requested_url": spec.url,
        "dest": spec.dest.replace("\\", "/"),
        "size_bytes": size,
        "expected_size_bytes": spec.expected_size_bytes,
        "size_basis": spec.size_basis,
        "size_check": size_check,
        "sha256": digest_hex,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence_status": spec.licence_status,
        **meta,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return {**record, "status": "downloaded"}


def select(release: Release, only: list[str] | None, include_optional: bool) -> list[FileSpec]:
    """Apply --only and --include-optional filters."""
    chosen = [f for f in release.files if (include_optional or not f.optional)]
    if only:
        unknown = set(only) - {f.id for f in release.files}
        if unknown:
            raise AcquisitionError(f"unknown ids: {sorted(unknown)}")
        chosen = [f for f in release.files if f.id in only]
    return chosen


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="project root (default: auto)")
    parser.add_argument("--allow-network", action="store_true", help="required to download anything")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; no network, no writes")
    parser.add_argument("--only", nargs="+", metavar="ID")
    parser.add_argument("--include-optional", action="store_true")
    args = parser.parse_args(argv)

    try:
        release = load_manifest(args.manifest)
        chosen = select(release, args.only, args.include_optional)
        for spec in chosen:
            resolve_dest(args.root, spec.dest)
    except (AcquisitionError, KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        for spec in chosen:
            print(f"{spec.id}\t{spec.size_basis}:{spec.expected_size_bytes}\t{spec.dest}\t{spec.url}")
        return 0
    if not args.allow_network:
        print("refusing to use the network without --allow-network (see ADR-001)", file=sys.stderr)
        return 2

    failures = 0
    for spec in chosen:
        try:
            rec = acquire_file(spec, release, args.root)
            print(f"{rec['status']}\t{spec.id}\t{rec['size_bytes']} B\t{rec['sha256']}")
        except (AcquisitionError, urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            failures += 1
            print(f"FAILED\t{spec.id}\t{exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
