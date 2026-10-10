"""Structure checks for the Stage C configuration files (contracts, registries, pending manifest)."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "ingest"))
import acquire  # noqa: E402

REGISTRY = ROOT / "config" / "registry"


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def test_gate4_manifest_is_valid_and_acquired_files_match_their_hashes():
    """Gate 4 was approved and acquired on 2026-10-10; every file must match its provenance line."""
    import hashlib
    import json

    release = acquire.load_manifest(ROOT / "config" / "acquisition" / "gate4_controls_and_secondary.toml")
    assert {f.id for f in release.files} == {"S01", "S02", "S03", "S04", "S05", "S06"}
    records = {
        rec["id"]: rec
        for rec in map(json.loads, (ROOT / release.manifest_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines())
    }
    for spec in release.files:
        acquire.resolve_dest(ROOT, spec.dest)
        assert "startPeriod=1993" in spec.url and "format=SDMX-CSV" in spec.url
        assert spec.size_basis == "estimated"  # the manifest's sizes were estimates; actuals are in manifest.jsonl
        local = ROOT / spec.dest
        assert local.exists(), f"{spec.id} missing: re-acquire with --allow-network"
        assert hashlib.sha256(local.read_bytes()).hexdigest() == records[spec.id]["sha256"]


def test_registries_have_expected_classes_and_unique_ids():
    seen: set[str] = set()
    for name in ("confirmatory", "secondary", "exploratory", "predictive"):
        doc = _load(REGISTRY / f"{name}.toml")
        assert doc["registry"]["class"] == name
        assert doc["registry"]["seed"] == 42
        for model in doc.get("model", []):
            assert model["id"] not in seen, f"duplicate model id {model['id']}"
            seen.add(model["id"])


def test_confirmatory_family_is_exactly_three_tests_under_holm():
    doc = _load(REGISTRY / "confirmatory.toml")
    hyp = {h["id"]: h for h in doc["hypothesis"]}
    assert set(hyp) == {"H1", "H2B", "H2W"}
    assert {h["family"] for h in hyp.values()} == {"holm3"}
    assert "Holm" in doc["registry"]["multiplicity"]
    formula = doc["model"][0]["formula_fixest"]
    for term in ("W_S", "W_E", "W_D", "W_U", "Post", "W_S:abar", "W_S:adev", "a_lag", "eurostat_code + year"):
        assert term in formula


def test_ageing_interaction_direction_is_not_pre_registered():
    doc = _load(REGISTRY / "confirmatory.toml")
    for hid in ("H2B", "H2W"):
        text = next(h for h in doc["hypothesis"] if h["id"] == hid)["test"]
        assert "direction withheld" in text


def test_fiscal_rule_moderation_is_exploratory_only():
    secondary = _load(REGISTRY / "secondary.toml")
    exploratory = _load(REGISTRY / "exploratory.toml")
    assert not any("fiscal-rule" in m.get("description", "").lower() for m in secondary["model"])
    e1 = next(m for m in exploratory["model"] if m["id"] == "E1")
    assert "2016-2021" in e1["window"]
    assert "never zero" in e1["moderator"]


def test_predictive_registry_forbids_causal_language():
    doc = _load(REGISTRY / "predictive.toml")
    assert doc["registry"]["causal_language"] == "forbidden"
    assert doc["validation"]["scheme"].startswith("expanding-window")


def test_contracts_define_all_layers_and_keys():
    doc = _load(ROOT / "config" / "contracts" / "contracts.toml")
    assert set(doc) == {"bronze", "silver", "gold"}
    gold = doc["gold"]["panel_country_year"]
    assert gold["key"] == ["eurostat_code", "year"]
    names = {c["name"] for c in gold["columns"]}
    assert {"capb", "W_S", "W_E", "W_D", "W_U", "Post", "olddep1_lag", "in_confirmatory"} <= names
    capb = next(c for c in gold["columns"] if c["name"] == "capb")
    assert "surplus positive" in capb["rule"]
    assert any("715" in r for r in gold["rules"])
    exposure = doc["silver"]["exposure_country_year"]
    assert "no CAPB column present" in exposure["rules"]
