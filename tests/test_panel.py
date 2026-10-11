"""Tests for the gold panel assembly, the merge-loss audit, the deterministic extract hash and the atomic writer."""
from __future__ import annotations

import hashlib
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("features", "evaluate", "normalize"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import gates  # noqa: E402
import panel  # noqa: E402
import sample  # noqa: E402

REAL = sample.CAPB_CSV.exists() and sample.OLDDEP_CSV.exists() and (ROOT / "data" / "raw" / "eurostat_controls").exists()
needs_raw = pytest.mark.skipif(not REAL, reason="raw inputs not present")

CODES = ["AA", "BB", "CC"]
START, END = 1995, 2000


def _series(code: str, years: range, values: list[float] | float, flag: dict[int, str] | None = None) -> pd.DataFrame:
    vals = values if isinstance(values, list) else [values] * len(years)
    flag = flag or {}
    return pd.DataFrame({"eurostat_code": code, "year": list(years), "value": vals, "flag": [flag.get(y) for y in years]})


def synthetic_inputs() -> panel.Inputs:
    """Three countries, window 1995-2000. BB lacks CAPB before 1997; CC's moderator is empty (flag e) in 1994."""
    capb = pd.concat(
        [
            pd.DataFrame({"eurostat_code": "AA", "year": range(1990, 2006), "capb": np.linspace(-3.0, 2.0, 16)}),
            pd.DataFrame({"eurostat_code": "BB", "year": range(1997, 2006), "capb": np.linspace(1.0, -4.0, 9)}),
            pd.DataFrame({"eurostat_code": "CC", "year": [1994, 1995, 1997, 1998, 1999, 2000, 2001], "capb": [0.5, -0.5, 1.5, 2.5, -9.5, 0.0, 1.0]}),
        ],
        ignore_index=True,
    )
    exposure = pd.MultiIndex.from_product([CODES, range(1993, 2004)], names=panel.KEY).to_frame(index=False)
    for column in panel.EXPOSURE_COLUMNS + panel.EXPOSURE_GF_COLUMNS:
        exposure[column] = 0.25
    exposure["exposure_complete_cv"] = exposure["year"] <= END
    exposure["exposure_complete_etad"] = exposure["year"] <= END + 1
    exposure["touches_unclassified_or_delayed"] = False
    moderators = {}
    for stem, base in (("olddep1", 20.0), ("olddep3", 10.0), ("medage", 38.0)):
        frames = []
        for i, code in enumerate(CODES):
            years = range(1994, 2005)
            values = [base + i + 0.1 * (y - 1994) for y in years]
            frame = _series(code, years, values, {1996: "b"})
            if code == "CC":
                frame.loc[frame["year"] == 1994, ["value", "flag"]] = [np.nan, "e"]
            frames.append(frame)
        moderators[stem] = pd.concat(frames, ignore_index=True)
    controls_table = pd.MultiIndex.from_product([CODES, range(1995, 2005)], names=panel.KEY).to_frame(index=False)
    controls_table = controls_table[~((controls_table["eurostat_code"] == "BB") & (controls_table["year"] == 1995))]
    controls_table["outgap_lag"] = 0.5
    controls_table["debt_gdp_lag"] = 60.0
    controls_table["debt_gdp_lag_flag"] = None
    controls_table["ig_diff_lag"] = -1.0
    controls_table["ig_diff_lag_flag"] = "p"
    secondary = {
        name: pd.concat([_series(c, range(1993, 2004), 10.0, {1999: "p"} if name == "sec_revenue" else None) for c in CODES], ignore_index=True)
        for name in panel.SECONDARY_ORDER
        if name != "sec_d_capb"
    }
    crosswalk = pd.DataFrame({"eurostat_code": CODES, "euro_adoption_year": pd.array([1999, pd.NA, 1997], dtype="Int64")})
    return panel.Inputs(CODES, capb, exposure, moderators, controls_table, secondary, 2005, {}, crosswalk)


@pytest.fixture(scope="module")
def build() -> panel.GoldBuild:
    return panel.assemble_gold_panel(synthetic_inputs(), start=START, end=END, min_obs=4)


def cell(build: panel.GoldBuild, code: str, year: int, column: str):
    return build.panel.set_index(panel.KEY).loc[(code, year), column]


# ---------------------------------------------------------------------------------------------
# Assembly on synthetic inputs
# ---------------------------------------------------------------------------------------------
def test_shape_order_and_key(build):
    assert build.panel.shape == (len(CODES) * (END - START + 1), len(panel.GOLD_COLUMNS))
    assert list(build.panel.columns) == panel.GOLD_COLUMNS
    assert not build.panel.duplicated(panel.KEY).any()
    assert build.panel[panel.KEY].equals(build.panel[panel.KEY].sort_values(panel.KEY).reset_index(drop=True))


def test_capb_join_keeps_negatives_and_leaves_missing_cells_missing(build):
    assert cell(build, "AA", 1995, "capb") == pytest.approx(np.linspace(-3.0, 2.0, 16)[5])
    assert np.isnan(cell(build, "BB", 1995, "capb"))
    assert cell(build, "CC", 1999, "capb") == -9.5  # a negative value is not touched
    assert np.isnan(cell(build, "CC", 1996, "capb"))  # gap inside the series stays a gap, no interpolation


def test_moderator_is_lagged_one_year_with_flag(build):
    # value at 1996 = base + i + 0.1*(1996-1994); lag moves it to 1997
    assert cell(build, "AA", 1997, "olddep1_lag") == pytest.approx(20.0 + 0.2)
    assert cell(build, "AA", 1997, "olddep1_lag_flag") == "b"
    assert cell(build, "AA", 1998, "olddep1_lag_flag") is None or pd.isna(cell(build, "AA", 1998, "olddep1_lag_flag"))
    assert np.isnan(cell(build, "CC", 1995, "olddep1_lag"))  # 1994 cell empty, flag e kept
    assert cell(build, "CC", 1995, "olddep1_lag_flag") == "e"
    assert cell(build, "BB", 1995, "medage_lag") == pytest.approx(38.0 + 1)


def test_euro_member_and_controls(build):
    assert not cell(build, "AA", 1998, "euro_member") and cell(build, "AA", 1999, "euro_member")
    assert not build.panel[build.panel["eurostat_code"] == "BB"]["euro_member"].any()  # never adopted
    assert cell(build, "CC", 1997, "euro_member")
    assert np.isnan(cell(build, "BB", 1995, "outgap_lag"))  # absent control row stays missing
    assert cell(build, "AA", 1995, "ig_diff_lag_flag") == "p"


def test_secondary_delta_capb_uses_consecutive_years_only(build):
    capb = np.linspace(-3.0, 2.0, 16)
    assert cell(build, "AA", 1995, "sec_d_capb") == pytest.approx(capb[5] - capb[4])  # uses 1994 outside the window
    assert np.isnan(cell(build, "CC", 1997, "sec_d_capb"))  # 1996 absent
    assert np.isnan(cell(build, "BB", 1997, "sec_d_capb"))  # first year of BB
    assert cell(build, "CC", 1995, "sec_d_capb") == pytest.approx(-1.0)  # 1994 -> 1995


def test_secondary_flags_are_carried_in_one_column(build):
    assert cell(build, "AA", 1999, "sec_obs_flags") == "sec_revenue:p"
    assert pd.isna(cell(build, "AA", 1998, "sec_obs_flags"))


def test_sample_flags_and_excluded_rows(build):
    p = build.panel.set_index(panel.KEY)
    # AA: six joint years; BB: CAPB from 1997 -> 4 rows (= min_obs); CC: 1995 lag empty, 1996 CAPB absent -> 1997-2000
    assert p.loc["AA", "in_confirmatory"].all()
    assert p.loc["BB", "in_confirmatory"].tolist() == [False, False, True, True, True, True]
    assert p.loc["CC", "in_confirmatory"].tolist() == [False, False, True, True, True, True]
    robust = p["in_robustness_703"]
    assert robust.loc[("BB", 1997)] and not robust.loc[("BB", 1995)]
    assert (robust <= p["in_confirmatory"]).all()  # the robustness sample is a subset
    excluded = build.excluded.set_index(panel.KEY)
    assert set(excluded.index) == set(p.index[~p["in_confirmatory"]])
    assert "CAPB" in excluded.loc[("BB", 1995), "reason"]
    assert "OLDDEP1" in excluded.loc[("CC", 1995), "reason"]


def test_country_with_too_few_observations_is_dropped_from_the_sample():
    inputs = synthetic_inputs()
    result = panel.assemble_gold_panel(inputs, start=START, end=END, min_obs=6)
    assert result.panel.loc[result.panel["eurostat_code"] == "AA", "in_confirmatory"].all()
    assert not result.panel.loc[result.panel["eurostat_code"] != "AA", "in_confirmatory"].any()
    assert result.excluded["country_below_min_obs"].sum() == 12


def test_no_forecast_or_post_window_year_enters_the_panel(build):
    assert build.panel["year"].between(START, END).all()
    assert build.panel["year"].max() == END


# ---------------------------------------------------------------------------------------------
# Merge-loss audit
# ---------------------------------------------------------------------------------------------
def test_every_join_is_audited_and_none_loses_rows(build):
    names = [a.name for a in build.audits]
    assert any("capb" in n for n in names) and any("exposure" in n for n in names) and any("controls" in n for n in names)
    assert sum(n.startswith("moderator") for n in names) == 3 and sum(n.startswith("secondary") for n in names) == len(panel.SECONDARY_ORDER)
    for a in build.audits:
        assert a.rows_out == a.rows_left_in == 18
        assert a.right_unmatched_inside_window == 0 and not a.silent_loss


def test_audit_counts_unmatched_keys_on_each_side(build):
    capb = next(a for a in build.audits if a.name.startswith("capb"))
    assert capb.left_unmatched == 3  # BB 1995-1996 and CC 1996 are absent from the source
    assert capb.left_unmatched_detail == "BB 1995-1996; CC 1996"
    assert capb.right_unmatched_outside_window > 0 and "2005" in capb.right_outside_detail
    moderator = next(a for a in build.audits if a.name.startswith("moderator olddep1"))
    assert moderator.left_unmatched == 0 and moderator.matched_but_null["olddep1_lag"] == 1  # CC 1995: matched, empty


def test_in_window_right_key_that_fails_to_match_is_a_silent_loss():
    left = pd.DataFrame({"eurostat_code": ["AA", "AA"], "year": [1995, 1997]})  # (AA, 1996) missing from the spine
    right = pd.DataFrame({"eurostat_code": ["AA", "AA", "AA"], "year": [1995, 1996, 2005], "v": [1.0, 2.0, 3.0]})
    with pytest.raises(AssertionError, match="silent loss"):
        panel.audited_left_join(left, right, "toy", window=(1995, 2000), codes=["AA"], reason="", audits=[])


def test_duplicate_right_key_is_rejected():
    left = pd.DataFrame({"eurostat_code": ["AA"], "year": [1995]})
    right = pd.DataFrame({"eurostat_code": ["AA", "AA"], "year": [1995, 1995], "v": [1.0, 2.0]})
    with pytest.raises(ValueError, match="duplicated keys"):
        panel.audited_left_join(left, right, "toy", window=(1995, 2000), codes=["AA"], reason="", audits=[])


def test_compress_keys_formats_runs():
    keys = pd.DataFrame({"eurostat_code": ["HR"] * 4 + ["CY"], "year": [1995, 1996, 1997, 2001, 1995]})
    assert panel.compress_keys(keys) == "CY 1995; HR 1995-1997,2001"
    assert panel.compress_keys(keys.iloc[0:0]) == "none"


# ---------------------------------------------------------------------------------------------
# Hash and writer
# ---------------------------------------------------------------------------------------------
def test_serialisation_rules(build):
    text = panel.serialise_extract(build.panel).decode("utf-8")
    lines = text.split("\n")
    assert lines[0] == ",".join(panel.GOLD_COLUMNS) and lines[-1] == ""
    assert len(lines) - 2 == int(build.panel["in_confirmatory"].sum())
    assert "\r" not in text
    header = lines[0].split(",")
    row = dict(zip(header, lines[1].split(","), strict=True))
    assert row["in_confirmatory"] == "1" and row["euro_member"] in ("0", "1") and row["year"] == "1995"
    assert row["capb"].count(".") == 1 and len(row["capb"].split(".")[1]) == panel.FLOAT_DECIMALS


def test_hash_is_independent_of_row_order_and_stable_to_float_noise(build):
    reference = panel.extract_hash(build.panel)
    shuffled = build.panel.sample(frac=1.0, random_state=42).reset_index(drop=True)  # seed: documented test fixture
    assert panel.extract_hash(shuffled) == reference
    noisy = build.panel.copy()
    noisy["capb"] = noisy["capb"] + 1e-13
    assert panel.extract_hash(noisy) == reference
    changed = build.panel.copy()
    changed.loc[changed["capb"].first_valid_index(), "capb"] += 1e-6
    assert panel.extract_hash(changed) != reference
    rows_outside = build.panel.copy()
    rows_outside.loc[~rows_outside["in_confirmatory"], "capb"] = 99.0  # not in the extract
    assert panel.extract_hash(rows_outside) == reference


def test_hash_changes_when_a_negative_sign_is_lost(build):
    flipped = build.panel.copy()
    flipped["capb"] = flipped["capb"].abs()
    assert panel.extract_hash(flipped) != panel.extract_hash(build.panel)


def test_string_cell_with_a_separator_is_rejected(build):
    bad = build.panel.copy()
    bad.loc[0, "olddep1_lag_flag"] = "a,b"
    bad.loc[0, "in_confirmatory"] = True
    with pytest.raises(ValueError, match="separator"):
        panel.serialise_extract(bad)


def _small_config(build: panel.GoldBuild) -> gates.GateConfig:
    extract = build.panel[build.panel["in_confirmatory"]]
    return gates.GateConfig(confirmatory_rows=len(extract), confirmatory_countries=extract["eurostat_code"].nunique(), year_min=START, year_max=END, coverage_min=0.5, min_obs_per_country=3)


def test_writer_writes_three_files_atomically_and_the_hash_matches(build, tmp_path):
    out = tmp_path / "gold"
    digest, results = panel.write_gold_panel(build, out, _small_config(build))
    assert all(r.passed for r in results)
    assert sorted(p.name for p in out.iterdir()) == sorted([panel.PARQUET_NAME, panel.CSV_NAME, panel.HASH_NAME])  # no temp files left
    assert (out / panel.HASH_NAME).read_text(encoding="utf-8").split()[0] == digest == panel.extract_hash(build.panel)
    back = pd.read_parquet(out / panel.PARQUET_NAME)
    assert list(back.columns) == panel.GOLD_COLUMNS and len(back) == len(build.panel)
    assert panel.extract_hash(back) == digest  # the hash survives a Parquet round trip
    csv = pd.read_csv(out / panel.CSV_NAME)
    assert len(csv) == len(build.panel)


def test_writer_leaves_no_file_when_a_gate_fails(build, tmp_path):
    out = tmp_path / "gold"
    bad = build.panel.copy()
    bad.loc[bad.index[0], "capb"] = 75.0  # out of range
    broken = panel.GoldBuild(bad, build.audits, build.excluded, build.source_capb, build.last_observed_year, build.reader_stats)
    with pytest.raises(gates.GateFailure):
        panel.write_gold_panel(broken, out, _small_config(build))
    assert not out.exists()


def test_writer_failure_midway_leaves_no_partial_final_files(build, tmp_path, monkeypatch):
    out = tmp_path / "gold"

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_csv", boom)
    with pytest.raises(OSError):
        panel.write_gold_panel(build, out, _small_config(build))
    assert list(out.iterdir()) == []  # temporaries removed, no final file


def test_contract_column_list_matches_the_panel_columns():
    contract = tomllib.loads((ROOT / "config" / "contracts" / "contracts.toml").read_text(encoding="utf-8"))["gold"]["panel_country_year"]
    assert [c["name"] for c in contract["columns"]] == panel.GOLD_COLUMNS
    assert set(panel.COLUMN_DOC) == set(panel.GOLD_COLUMNS)
    assert not any(c.startswith("sec_") and not next(x for x in contract["columns"] if x["name"] == c).get("nullable") for c in panel.GOLD_COLUMNS)


# ---------------------------------------------------------------------------------------------
# Real data (skipped when the raw files are not present)
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real() -> panel.GoldBuild:
    return panel.build_gold_panel()


@needs_raw
def test_real_panel_shape_flags_and_gates(real):
    p = real.panel
    assert p.shape == (729, len(panel.GOLD_COLUMNS))
    assert int(p["in_confirmatory"].sum()) == 715 and p.loc[p["in_confirmatory"], "eurostat_code"].nunique() == 27
    assert int(p["in_robustness_703"].sum()) == 703
    assert all(r.passed for r in gates.run_gates(p, real.source_capb, real.last_observed_year))
    assert all(not a.silent_loss for a in real.audits)


@needs_raw
def test_real_confirmatory_keys_equal_the_gate3a_selection(real):
    base = sample.build_panel()
    selection = sample.select_sample(base, sample.last_common_complete_year(base, "cv"), "joint_cv")
    ours = real.panel[real.panel["in_confirmatory"]]
    assert set(map(tuple, ours[panel.KEY].to_numpy())) == set(map(tuple, selection.sample[panel.KEY].to_numpy()))
    merged = ours.merge(selection.sample, on=panel.KEY, suffixes=("", "_g3"))
    assert np.allclose(merged["capb"], merged["capb_g3"], rtol=0, atol=0)
    assert np.allclose(merged["olddep1_lag"], merged["olddep1_lag_g3"], rtol=0, atol=0)
    for column in panel.EXPOSURE_COLUMNS:
        assert np.allclose(merged[column], merged[f"{column}_g3"], rtol=0, atol=1e-12)
    assert merged["olddep1_lag_flag"].fillna("-").equals(merged["olddep1_lag_flag_g3"].fillna("-"))


@needs_raw
def test_real_excluded_country_years_are_the_documented_fourteen(real):
    got = {(r.eurostat_code, int(r.year)) for r in real.excluded.itertuples()}
    expected = {("CY", 1995), ("CY", 1996), ("CZ", 1995), ("CZ", 1996), ("SI", 1995), ("SI", 1996), ("SK", 1995)} | {("HR", y) for y in range(1995, 2002)}
    assert got == expected and len(got) == 14
    assert real.excluded["missing_capb"].sum() == 13 and real.excluded["missing_olddep1_lag"].sum() == 7


@needs_raw
def test_real_negative_capb_counts_and_denominator_text(real):
    extract = real.panel[real.panel["in_confirmatory"]]
    assert int((extract["capb"] < 0).sum()) == 330 and extract["capb"].min() == pytest.approx(-27.62, abs=0.01)
    assert real.reader_stats["capb"]["rows_other_unit_text"] == 0
    assert real.reader_stats["capb"]["unit_text"] == panel.ameco.POTENTIAL_GDP_TEXT
    # UBLGIE is selected by the denominator text: the national-currency and billion-euro rows are dropped, so values are plausible percentages
    ublgie = real.reader_stats["sec_primary_balance_edp"]
    assert ublgie["rows_other_unit_text"] > 0 and ublgie["unit_text"] == panel.ameco.ACTUAL_GDP_EDP_TEXT
    assert real.panel["sec_primary_balance_edp"].abs().max() < 50


@needs_raw
def test_real_build_is_reproducible_and_round_trips_through_parquet(real, tmp_path):
    again = panel.build_gold_panel()
    assert panel.extract_hash(again.panel) == panel.extract_hash(real.panel)
    digest, _ = panel.write_gold_panel(real, tmp_path / "gold")
    back = pd.read_parquet(tmp_path / "gold" / panel.PARQUET_NAME)
    assert panel.extract_hash(back) == digest
    assert hashlib.sha256(panel.serialise_extract(real.panel)).hexdigest() == digest


@needs_raw
def test_real_flags_carried_and_no_exposure_in_outcome_free_inputs(real):
    extract = real.panel[real.panel["in_confirmatory"]]
    assert extract["olddep1_lag_flag"].value_counts().to_dict() == {"b": 15, "e": 2, "p": 1}
    # the exposure panel itself must stay outcome-free (silver contract)
    exposure = pd.read_csv(sample.EXPOSURE_CSV)
    assert not any("capb" in c.lower() for c in exposure.columns)
