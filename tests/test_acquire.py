"""Offline tests for the acquisition layer. Network use is limited to a localhost server."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "ingest"))
import acquire  # noqa: E402

PAYLOAD = b"country,year,value\nDE,2009,-1.89\nEL,2009,-8.79\n"


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[bytes, str]] = {}

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        body, ctype = self.routes.get(self.path, (b"", "text/plain"))
        status = 200 if self.path in self.routes else 404
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence test output
        pass


@pytest.fixture()
def server():
    _Handler.routes = {
        "/ok.csv": (PAYLOAD, "text/csv; charset=utf-8"),
        "/html.csv": (b"<html>error</html>", "text/html"),
    }
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _write_manifest(tmp_path: Path, base: str, **overrides: object) -> Path:
    entry = {
        "id": "T01",
        "url": f"{base}/ok.csv",
        "dest": "data/raw/test/v1/ok.csv",
        "content_type": "text/csv",
        "expected_size_bytes": len(PAYLOAD),
        "size_basis": "measured",
        **overrides,
    }
    lines = [
        "[release]",
        'source_id = "test"',
        'vintage = "v1"',
        'manifest_dir = "data/raw/test/v1"',
        "",
        "[[file]]",
    ]
    lines += [f"{k} = {json.dumps(v)}" for k, v in entry.items()]
    path = tmp_path / "m.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(manifest: Path, tmp_path: Path, *extra: str) -> int:
    return acquire.main(["--manifest", str(manifest), "--root", str(tmp_path), *extra])


def test_refuses_network_without_flag(tmp_path, server):
    assert _run(_write_manifest(tmp_path, server), tmp_path) == 2
    assert not (tmp_path / "data").exists()


def test_dry_run_needs_no_network_flag_and_writes_nothing(tmp_path, server):
    assert _run(_write_manifest(tmp_path, server), tmp_path, "--dry-run") == 0
    assert not (tmp_path / "data").exists()


def test_download_records_hash_size_and_is_read_only(tmp_path, server):
    assert _run(_write_manifest(tmp_path, server), tmp_path, "--allow-network") == 0
    dest = tmp_path / "data/raw/test/v1/ok.csv"
    assert dest.read_bytes() == PAYLOAD
    assert not os.access(dest, os.W_OK)
    rec = json.loads((tmp_path / "data/raw/test/v1/manifest.jsonl").read_text().splitlines()[0])
    assert rec["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    assert rec["size_bytes"] == len(PAYLOAD)
    assert rec["content_type"] == "text/csv"
    assert rec["retrieved_utc"].endswith("+00:00")
    assert not dest.with_name(dest.name + ".partial").exists()


def test_rerun_is_a_noop_and_does_not_duplicate_provenance(tmp_path, server):
    manifest = _write_manifest(tmp_path, server)
    assert _run(manifest, tmp_path, "--allow-network") == 0
    assert _run(manifest, tmp_path, "--allow-network") == 0
    lines = (tmp_path / "data/raw/test/v1/manifest.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_tampered_local_file_is_never_overwritten(tmp_path, server):
    manifest = _write_manifest(tmp_path, server)
    assert _run(manifest, tmp_path, "--allow-network") == 0
    dest = tmp_path / "data/raw/test/v1/ok.csv"
    dest.chmod(0o600)
    dest.write_bytes(PAYLOAD + b"tamper")
    assert _run(manifest, tmp_path, "--allow-network") == 1
    assert dest.read_bytes() == PAYLOAD + b"tamper"


def test_measured_size_mismatch_is_rejected_and_leaves_no_file(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, expected_size_bytes=len(PAYLOAD) + 1)
    assert _run(manifest, tmp_path, "--allow-network") == 1
    folder = tmp_path / "data/raw/test/v1"
    assert not (folder / "ok.csv").exists()
    assert not (folder / "ok.csv.partial").exists()


def test_estimated_size_is_recorded_not_enforced(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, expected_size_bytes=999999, size_basis="estimated")
    assert _run(manifest, tmp_path, "--allow-network") == 0
    rec = json.loads((tmp_path / "data/raw/test/v1/manifest.jsonl").read_text().splitlines()[0])
    assert rec["size_check"] == "differs_from_expected"


def test_html_error_page_with_wrong_content_type_is_rejected(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, url=f"{server}/html.csv")
    assert _run(manifest, tmp_path, "--allow-network") == 1
    assert not (tmp_path / "data/raw/test/v1/ok.csv").exists()


def test_http_404_is_a_failure(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, url=f"{server}/missing.csv")
    assert _run(manifest, tmp_path, "--allow-network") == 1


@pytest.mark.parametrize("bad", ["../escape.csv", "data/processed/x.csv", "/abs/x.csv"])
def test_destinations_outside_data_raw_are_rejected(tmp_path, server, bad):
    assert _run(_write_manifest(tmp_path, server, dest=bad), tmp_path, "--dry-run") == 1


def test_plain_http_to_remote_hosts_is_rejected(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, url="http://example.com/x.csv")
    assert _run(manifest, tmp_path, "--dry-run") == 1


def test_optional_files_are_skipped_by_default(tmp_path, server):
    manifest = _write_manifest(tmp_path, server, optional=True)
    assert _run(manifest, tmp_path, "--allow-network") == 0
    assert not (tmp_path / "data/raw/test/v1/ok.csv").exists()
    assert _run(manifest, tmp_path, "--allow-network", "--include-optional") == 0
    assert (tmp_path / "data/raw/test/v1/ok.csv").exists()


@pytest.mark.parametrize("name", ["gate1_ameco_2026_spring", "gate2_fiscal_governance", "gate3_elections_and_ageing"])
def test_shipped_manifests_are_valid(name):
    release = acquire.load_manifest(ROOT / "config" / "acquisition" / f"{name}.toml")
    assert release.files
    for spec in release.files:
        acquire.resolve_dest(ROOT, spec.dest)
        assert spec.url.startswith("https://")
        assert spec.size_basis in {"measured", "page_stated", "provider_api", "estimated", "unknown"}
        if spec.size_basis == "measured":
            assert spec.expected_size_bytes > 0
        assert Path(spec.dest).as_posix().startswith(release.manifest_dir)
