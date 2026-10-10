"""Offline tests for the EU-27 election calendar and exposure construction (Gate 3a)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import countries  # noqa: E402
import elections  # noqa: E402

RAW_PRESENT = elections.ETAD_CSV.exists() and elections.PARLGOV_TAB.exists()
needs_raw = pytest.mark.skipif(not RAW_PRESENT, reason="election raw files not present (ADR-001 acquisition)")


# ---------------------------------------------------------------------------------------------
# Pure-logic tests (no files)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("timing1", "timing2", "reason", "dif", "expected"),
    [
        (1, 0, 0, 0, ("scheduled", "timing2_on_time")),
        (2, -1, 7, -300, ("early", "timing2_early")),
        (2, -1, 0, -300, ("early", "timing2_early")),
        (2, 0, 9, -160, ("early", "reason_overrides_timing2_on_time")),
        (2, 1, 4, 12, ("delayed", "timing2_delayed")),
        (2, 1, 0, -5, ("unclassified", "delayed_vs_dif_days_sign")),
        (2, 1, 7, 331, ("unclassified", "delayed_vs_early_reason")),
        (2, 1, 7, -614, ("unclassified", "delayed_vs_dif_days_sign")),
        (3, np.nan, 1, np.nan, ("unclassified", "timing1_unknown")),
        (np.nan, np.nan, np.nan, np.nan, ("unclassified", "timing1_unknown")),
        (1, np.nan, 0, 0, ("unclassified", "timing2_missing")),
        (2, 0, 0, -10, ("unclassified", "timing1_moved_but_timing2_on_time")),
        (2, -1, 7, 5, ("unclassified", "early_vs_dif_days_sign")),
    ],
)
def test_classify_etad_rules(timing1, timing2, reason, dif, expected):
    assert elections.classify_etad(timing1, timing2, reason, dif) == expected


def test_classify_gap_thresholds():
    assert elections.classify_gap(4.0, 4.0) == "scheduled"
    assert elections.classify_gap(3.6, 4.0) == "scheduled"  # inside the half-year tolerance
    assert elections.classify_gap(3.4, 4.0) == "early"
    assert elections.classify_gap(4.6, 4.0) == "delayed"
    assert elections.classify_gap(np.nan, 4.0) == "unavailable"
    assert elections.classify_gap(4.0, np.nan) == "unavailable"
    assert elections.classify_gap(3.8, 4.0, tolerance=0.1) == "early"


def test_pre_window_march_election_is_mostly_in_previous_year():
    shares = elections.pre_window_shares(pd.Timestamp("2001-03-15"))
    assert set(shares) == {2000, 2001}
    assert shares[2000] == pytest.approx(292 / 365, abs=1e-9)  # 15 Mar to 31 Dec 2000 (leap year) is 292 days
    assert shares[2001] == pytest.approx(73 / 365, abs=1e-9)  # 1 Jan to 14 Mar 2001 is 73 days
    assert sum(shares.values()) == pytest.approx(1.0)


def test_pre_window_shares_sum_to_one_for_every_calendar_day_type():
    for day in ["2000-02-29", "2004-02-29", "2011-01-01", "2011-12-31", "1995-06-15"]:
        assert sum(elections.pre_window_shares(pd.Timestamp(day)).values()) == pytest.approx(1.0)
        assert sum(elections.post_window_shares(pd.Timestamp(day)).values()) == pytest.approx(1.0)


def test_election_on_new_year_day_loads_entirely_on_previous_year_and_next_post():
    assert elections.pre_window_shares(pd.Timestamp("2010-01-01")) == {2009: 1.0}
    assert elections.post_window_shares(pd.Timestamp("2010-01-01")) == {2010: 1.0}


def _calendar_stub(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "eurostat_code": [r[0] for r in rows],
            "date_used": pd.to_datetime([r[1] for r in rows]),
            "class_primary": [r[2] for r in rows],
            "in_calendar": True,
        }
    )


def test_exposure_single_scheduled_election():
    exposure = elections.build_exposure(_calendar_stub([("AT", "2001-03-15", "scheduled")]))
    at = exposure[exposure["eurostat_code"] == "AT"].set_index("year")
    assert at.loc[2000, "W_S"] == pytest.approx(292 / 366, abs=0.005)
    assert at.loc[2001, "W_S"] == pytest.approx(73 / 365, abs=0.005)
    assert at["W_S"].sum() == pytest.approx(1.0, abs=0.01)
    assert at["W_E"].sum() == 0 and at["W_U"].sum() == 0
    assert at.loc[2001, "Post"] == pytest.approx(0.8, abs=0.01)
    assert at.loc[2002, "Post"] == pytest.approx(0.2, abs=0.01)
    other = exposure[exposure["eurostat_code"] == "BE"]
    assert other[["W_S", "W_E", "W_D", "W_U", "Post"]].to_numpy().sum() == 0


def test_two_elections_in_one_year_and_union_bound():
    stub = _calendar_stub([("EL", "2012-05-06", "early"), ("EL", "2012-06-17", "early")])
    union = elections.build_exposure(stub).query("eurostat_code == 'EL'").set_index("year")
    summed = elections.build_exposure(stub, additive=True).query("eurostat_code == 'EL'").set_index("year")
    assert union["W_E"].max() <= 1.0 and union["Post"].max() <= 1.0
    assert summed.loc[2011, "W_E"] > union.loc[2011, "W_E"]  # overlapping windows are double counted when additive
    assert summed["W_E"].sum() == pytest.approx(2.0, abs=0.01)
    assert union.loc[2012, "W_E"] == pytest.approx(168 / 366, abs=0.005)  # covered until the second election


def test_scheduled_and_early_are_kept_apart():
    stub = _calendar_stub([("FR", "2002-06-16", "scheduled"), ("FR", "2003-02-01", "early")])
    exposure = elections.build_exposure(stub).query("eurostat_code == 'FR'").set_index("year")
    assert exposure.loc[2001, "W_S"] > 0 and exposure.loc[2001, "W_E"] == 0
    assert exposure.loc[2002, "W_E"] > 0 and exposure.loc[2002, "W_S"] > 0


def test_exposure_complete_rule():
    end_etad = pd.Timestamp("2023-12-31")
    end_parlgov = pd.Timestamp("2023-06-30")
    assert elections.exposure_complete(2022, end_etad)
    assert not elections.exposure_complete(2023, end_etad)
    assert elections.exposure_complete(2021, end_parlgov)
    assert not elections.exposure_complete(2022, end_parlgov)


def test_matching_is_one_to_one_and_nearest():
    etad = pd.DataFrame({"etad_row": [1, 2], "iso3": ["GRC", "GRC"], "held_ts": pd.to_datetime(["2012-05-06", "2012-06-17"])})
    parlgov = pd.DataFrame(
        {"iso3": ["GRC", "GRC"], "election_id": [10, 11], "pg_date": pd.to_datetime(["2012-06-17", "2012-05-06"])}
    )
    matched = elections.match_dates(etad, parlgov).set_index("etad_row")
    assert matched.loc[1, "election_id"] == 11 and matched.loc[2, "election_id"] == 10
    assert (matched["diff_days"] == 0).all()


# ---------------------------------------------------------------------------------------------
# Independence from outcome data
# ---------------------------------------------------------------------------------------------
def test_elections_module_never_touches_outcome_data():
    source = (ROOT / "src" / "normalize" / "elections.py").read_text(encoding="utf-8").lower()
    for forbidden in ("ameco", "ublgbp", "capb", "import ameco", "ameco_chapter"):
        assert forbidden not in source
    code = (
        "import sys; sys.path.insert(0, r'%s'); import elections; "
        "bad = [m for m in sys.modules if m.split('.')[0] in ('ameco',)]; "
        "assert not bad, bad"
    ) % (ROOT / "src" / "normalize")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)


# ---------------------------------------------------------------------------------------------
# Tests on the real files
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def built():
    return elections.build_all()


@needs_raw
def test_raw_files_match_manifest_hashes():
    result = elections.raw_file_hashes_match_manifest()
    assert result and all(result.values()), result


@needs_raw
def test_etad_audit_reconciles_to_article_count():
    audit = elections.etad_audit(elections.read_etad_raw())
    assert audit["n_rows"] == 3133  # 6 more rows than the 3,127 stated in the codebook
    assert audit["article_n_elections"] == 3127
    assert audit["rows_minus_placeholders_minus_dup_keys"] == 3127
    assert audit["n_all_empty_placeholder_rows"] == 5 and audit["n_duplicate_election_keys"] == 1
    assert audit["n_countries_iso3"] == 148 and audit["n_country_names"] == 150
    assert (audit["held_year_min"], audit["held_year_max"]) == (1945, 2023)
    assert audit["n_timing1_unknown"] == 269


@needs_raw
def test_calendar_covers_the_27_members_without_duplicates(built):
    calendar = built[0]
    used = calendar[calendar["in_calendar"]]
    assert set(used["eurostat_code"]) == set(countries.eu27_eurostat_codes())
    assert not used.duplicated(["eurostat_code", "date_used"]).any()
    assert used["date_used"].between(elections.CALENDAR_START, elections.CALENDAR_END).all()
    assert not used["iso3"].isin(["GBR", "CSK", "YUG"]).any()
    # Cyprus and Malta are absent from ETAD and therefore come from ParlGov only.
    for code in ("CY", "MT"):
        sub = used[used["eurostat_code"] == code]
        assert sub["etad_row"].isna().all() and len(sub) >= 7
        assert (sub["class_primary"] == "unclassified").all()


@needs_raw
def test_classes_are_exhaustive_and_known(built):
    calendar = built[0]
    used = calendar[calendar["in_calendar"]]
    assert set(used["class_primary"]) <= set(elections.CLASSES)
    assert set(used["class_gap"]) <= {"scheduled", "early", "delayed", "unavailable"}
    assert set(used["class_gapfill"]) <= set(elections.CLASSES)
    # The gap fill never changes an election that ETAD classified.
    classified = used["class_primary"].isin(elections.KNOWN_CLASSES)
    assert (used.loc[classified, "class_gapfill"] == used.loc[classified, "class_primary"]).all()


@needs_raw
def test_known_date_disagreements_are_resolved_as_documented(built):
    used = built[0].query("in_calendar")
    nl = used[(used["eurostat_code"] == "NL") & (used["year"] == 2017)].iloc[0]
    assert nl["date_used"] == pd.Timestamp("2017-03-15") and nl["date_rule"] == "parlgov_weekday_override"
    lux = used[(used["eurostat_code"] == "LU") & (used["year"] == 2013)].iloc[0]
    assert lux["date_used"] == pd.Timestamp("2013-10-20")
    fra = used[(used["eurostat_code"] == "FR") & (used["year"] == 2022)].iloc[0]
    assert fra["date_used"] == pd.Timestamp("2022-06-12") and fra["date_rule"] == "etad_primary_dates_differ"
    el = used[(used["eurostat_code"] == "EL") & (used["year"] == 2023)]
    assert len(el) == 2 and (el["source"] == "parlgov_only").all()


@needs_raw
def test_exposure_panel_shape_bounds_and_flags(built):
    exposure = built[1]
    assert len(exposure) == 27 * 34
    for column in ["W_S", "W_E", "W_D", "W_U", "Post", "W_S_gf", "W_E_gf", "W_D_gf", "W_U_gf", "Post_gf"]:
        assert exposure[column].between(0, 1).all()
    assert exposure["additive_exceeds_one"].sum() >= 1
    assert exposure[["W_S", "W_E", "W_D", "W_U"]].sum(axis=1).max() <= 4  # sanity only; classes may overlap in time
    y2023 = exposure[exposure["year"] == 2023]
    assert not y2023["exposure_complete_cv"].any() and not y2023["exposure_complete_etad"].any()
    assert exposure.query("year <= 2021")["exposure_complete_cv"].all()
    assert not exposure.query("year == 2022")["exposure_complete_cv"].any()


@needs_raw
def test_additive_pre_exposure_mass_equals_sum_of_window_shares_inside_panel(built):
    calendar, exposure = built[0], built[1]
    used = calendar[calendar["in_calendar"]]
    expected = sum(
        share
        for day in used["date_used"]
        for year, share in elections.pre_window_shares(day).items()
        if elections.CALENDAR_START.year <= year <= elections.CALENDAR_END.year
    )
    assert exposure[["W_S_add", "W_E_add", "W_D_add", "W_U_add"]].sum().sum() == pytest.approx(expected)


@needs_raw
def test_right_censoring_evidence(built):
    coverage = built[3]
    assert elections.last_complete_year(coverage, "cv") == 2021
    # With Cyprus, Malta, Greece, Poland and Austria carrying coverage evidence only to ParlGov's end,
    # the all-27 minimum on the ETAD-trusted basis is also 2021 (23 or fewer countries reach 2022).
    assert {"CY", "MT", "EL", "PL"} <= set(coverage.proven_gaps)
    trusted = [c for c, end in coverage.obs_through_etad_trusted.items() if end == elections.CALENDAR_END]
    assert len(trusted) >= 20


@needs_raw
def test_exclusion_table_lists_every_unclassified_election(built):
    calendar, _, exclusions, _ = built
    used = calendar[calendar["in_calendar"]]
    unclassified = used[used["class_primary"] == "unclassified"]
    listed = exclusions[exclusions["category"].str.startswith("unclassified")]
    assert len(listed) == len(unclassified)
    assert set(exclusions["category"]) >= {"delayed", "unclassified_timing1_unknown", "unclassified_no_etad_row", "date_differs", "etad_only"}
    assert exclusions["proposed_treatment"].str.len().gt(0).all()


@needs_raw
def test_gap_agreement_table_is_monotone_in_scope_and_internally_consistent(built):
    table = elections.gap_agreement(built[0])
    assert list(table["tolerance_years"]) == list(elections.GAP_TOLERANCE_SENSITIVITY)
    assert (table["n_comparable"] == table["n_comparable"].iloc[0]).all()
    comparable = table["n_agree"] + table["n_etad_early_gap_scheduled"] + table["n_etad_scheduled_gap_early"] + table["n_other_disagree"]
    assert (comparable == table["n_comparable"]).all()
    assert table["agree_share"].between(0.7, 1.0).all()
