"""Gate 5 / trigger T3: tests for the AMECO archive vintage readers and the S4 feasibility statistics.

Fixture tests build tiny zips in ``tmp_path`` (offline, no raw data needed); the ``real`` tests read the
archived vintages under ``data/raw/ameco_archive`` and are skipped if the archive is absent. Nothing here
relates outcomes to elections.
"""
from __future__ import annotations

import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import ameco_vintages as av  # noqa: E402

HEADER = "CODE;COUNTRY;SUB-CHAPTER;TITLE;UNIT;2012;2013;2014;2015"
ROWS_OLD = "\r\n".join(
    [
        HEADER,
        "EU28.1.0.319.0.UBLGBP;European Union (28 countries);01 Based on potential GDP (ESA95);Net lending CAPB ;(Percentage of potential GDP at current prices) ;NA;NA;-1.5;-0.5",
        "ROM.1.0.319.0.UBLGBP;Romania;01 Based on potential GDP (ESA95);Net lending CAPB ;(Percentage of potential GDP at current prices) ;NA;-3.25;-2.0;NA",
        "GRC.1.0.319.0.UBLGBP;Greece;01 Based on potential GDP (ESA95);Net lending CAPB ;(Percentage of potential GDP at current prices) ;1.0;2.0;3.0;4.0",
        "GRC.1.0.319.0.UBLGAP;Greece;01 Based on potential GDP (ESA95);Cyclically adjusted ;(Percentage of potential GDP at current prices) ;9.0;9.0;9.0;9.0",
        "AUT.1.0.319.0.UBLGEE;Austria;01 x;Other item ;(Percentage) ;1;2;3;4",
        "",
    ]
).encode("latin-1")


def _zip_with(member: str, payload: bytes, nested: bool) -> bytes:
    """Return the bytes of a zip holding ``member`` either directly or inside a nested ``ameco17.zip``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as outer:
        if nested:
            inner_buffer = io.BytesIO()
            with zipfile.ZipFile(inner_buffer, "w") as inner:
                inner.writestr(member, payload)
            outer.writestr("ameco17.zip", inner_buffer.getvalue())
            outer.writestr("ameco1.zip", b"")
        else:
            outer.writestr(member, payload)
            outer.writestr("AMECO1.TXT", b"x")
    return buffer.getvalue()


def test_parse_semicolon_na_and_trailing_spaces() -> None:
    long = av.parse_ameco_txt(ROWS_OLD, items=("UBLGBP",))
    assert set(long["item"]) == {"UBLGBP"}
    assert set(long["area"]) == {"EU28", "ROM", "GRC"}
    rom = long[long["area"] == "ROM"].set_index("year")["value"]
    assert np.isnan(rom[2012]) and rom[2013] == -3.25 and rom[2014] == -2.0 and np.isnan(rom[2015])
    assert set(long["unit_text"]) == {av.POTENTIAL_GDP_TEXT}  # stray space and parentheses removed
    assert set(long["title"]) == {"Net lending CAPB"}


def test_parse_handles_ragged_row_and_crlf_and_latin1() -> None:
    raw = (HEADER + "\nGRC.1.0.319.0.UBLGBP;Gr\xe8ce;s;t\xe9;(u);1.5;2.5\n").encode("latin-1")
    long = av.parse_ameco_txt(raw, items=("UBLGBP",))
    assert list(long["year"]) == [2012, 2013]  # shorter row truncated, not an error
    assert long["title"].iloc[0] == "t\xe9"


def test_read_chapter17_flat_and_nested(tmp_path: Path) -> None:
    for nested in (False, True):
        path = tmp_path / f"v_{nested}.zip"
        path.write_bytes(_zip_with("AMECO17.TXT", ROWS_OLD, nested))
        assert av.read_chapter17_bytes(path) == ROWS_OLD


def test_missing_chapter_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    path.write_bytes(_zip_with("AMECO5.TXT", b"x", False))
    with pytest.raises(KeyError):
        av.read_chapter17_bytes(path)


def test_attach_metadata_drops_aggregates_and_maps_codes() -> None:
    spec = av.VintageSpec("Autumn 2014", 1, "autumn", 2014, Path("x.zip"), date(2014, 11, 6))
    long = av.parse_ameco_txt(ROWS_OLD, items=("UBLGBP", "UBLGAP"))
    out = av._attach_metadata(long, spec)
    assert set(out["eurostat_code"]) == {"RO", "EL"}  # EU28 aggregate dropped, ROM -> RO, GRC -> EL
    assert set(out["vintage_label"]) == {"Autumn 2014"}
    assert out["printed_date"].iloc[0] == pd.Timestamp("2014-11-06")


def test_vintage_specs_order_and_count() -> None:
    specs = av.vintage_specs()
    assert len(specs) == 26
    assert [s.order for s in specs] == list(range(1, 27))
    assert specs[0].label == "Autumn 2014" and specs[-1].label == "Autumn 2025"
    assert specs[-1].printed_date_suspect and sum(s.printed_date_suspect for s in specs) == 1
    dates = [s.printed_date for s in specs]
    assert dates == sorted(dates)
    assert (specs[-1].printed_date - specs[-2].printed_date).days == 15  # the printed-date anomaly (Appendix B 1.3)


def test_printed_dates_match_acquisition_toml() -> None:
    from_toml = av.printed_dates_from_toml()
    for spec in av.vintage_specs():
        assert from_toml[f"{spec.season.capitalize()} {spec.year}"] == spec.printed_date


@pytest.mark.parametrize(
    ("season", "max_year", "expected"),
    [("autumn", 2016, 2013), ("spring", 2016, 2014), ("winter", 2016, 2013), ("autumn", 2027, 2024)],
)
def test_last_observed_year_rule(season: str, max_year: int, expected: int) -> None:
    assert av.last_observed_year(max_year, season) == expected


real = pytest.mark.skipif(not av.ARCHIVE_DIR.exists(), reason="archive not present")


@real
def test_real_every_vintage_has_ubl_gbp_for_27_countries() -> None:
    long = av.build_long_table(items=("UBLGBP",))
    archived = long[long["vintage_order"] < av.FINAL_ORDER]
    counts = archived.dropna(subset=["value"]).groupby("vintage_label")["eurostat_code"].nunique()
    assert len(counts) == 26 and counts.min() == 27
    assert set(long["unit_text"]) == {av.POTENTIAL_GDP_TEXT}


@real
def test_real_final_snapshot_matches_pinned_sdmx_extract() -> None:
    import ameco  # noqa: PLC0415

    final = av.load_final_snapshot(items=("UBLGBP",)).dropna(subset=["value"])
    sdmx = ameco.read_sdmx_csv(ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER17-01_UBLGBP.csv")
    merged = final.merge(
        sdmx.rename(columns={"REF_AREA": "area", "TIME_PERIOD": "year", "OBS_VALUE": "sdmx"})[["area", "year", "sdmx"]],
        on=["area", "year"],
    )
    assert len(merged) > 900
    assert np.allclose(merged["value"], merged["sdmx"], atol=5e-5)


# ---------------------------------------------------------------- analytic helpers on synthetic data
def _long(rows: list[tuple[int, str, int, float]], unit: str = av.POTENTIAL_GDP_TEXT, title: str = "T") -> pd.DataFrame:
    """Synthetic long table: (vintage_order, eurostat_code, year, value) -> full schema."""
    return pd.DataFrame(
        {
            "vintage_label": [f"V{o}" for o, *_ in rows],
            "vintage_order": [o for o, *_ in rows],
            "printed_date": pd.Timestamp("2020-01-01"),
            "area": [c for _, c, *_ in rows],
            "eurostat_code": [c for _, c, *_ in rows],
            "item": av.CAPB_ITEM,
            "year": [y for _, _, y, _ in rows],
            "value": [v for *_, v in rows],
            "unit_text": unit,
            "sub_chapter": "s",
            "title": title,
        }
    )


def test_t3_summary_counts_flags_and_verdict() -> None:
    rows = [(1, c, 2014, 1.0) for c in "ABC"] + [(2, c, 2014, 1.0) for c in "AB"]
    summary = av.t3_summary(_long(rows))
    assert list(summary["n_countries"]) == [3, 2]
    assert av.t3_verdict(summary)["pass"] is False  # 3 and 2 countries are below the 20 threshold
    assert "fewer than 20" in summary["flag"].iloc[0]


def test_t3_detects_changed_denominator_and_label() -> None:
    first = _long([(1, "A", 2014, 1.0)])
    second = _long([(2, "A", 2014, 1.0)], unit="Percentage of GDP at current prices", title="Other")
    summary = av.t3_summary(pd.concat([first, second], ignore_index=True))
    assert summary["label_identical"].tolist() == [True, False]
    assert summary["denominator_identical"].tolist() == [True, False]


def test_sign_check_detects_flipped_convention() -> None:
    base = [("A", 0, 2.0), ("A", 1, -1.5), ("B", 0, 3.0)]
    same = _long([(1, c, 2014 + i, v) for c, i, v in base] + [(2, c, 2014 + i, v + 0.1) for c, i, v in base])
    flipped = _long([(1, c, 2014 + i, v) for c, i, v in base] + [(2, c, 2014 + i, -v) for c, i, v in base])
    assert av.adjacent_sign_check(same)["share_same_sign"].iloc[0] == 1.0
    assert av.adjacent_sign_check(flipped)["share_same_sign"].iloc[0] == 0.0
    assert av.adjacent_sign_check(flipped)["pearson_r"].iloc[0] == pytest.approx(-1.0)


def _specs3() -> list[av.VintageSpec]:
    return [
        av.VintageSpec("V1", 1, "autumn", 2014, Path("a.zip"), date(2014, 11, 6)),
        av.VintageSpec("V2", 2, "spring", 2015, Path("b.zip"), date(2015, 5, 7)),
        av.VintageSpec("V3", 3, "autumn", 2015, Path("c.zip"), date(2015, 11, 5)),
    ]


def test_revision_pairs_exact_numbers() -> None:
    rows = []
    for order, shift in ((1, 0.0), (2, 0.5), (3, 0.5)):
        for country, base in (("A", 1.0), ("B", -2.0)):
            for year in (2012, 2013, 2014, 2015):
                rows.append((order, country, year, base + (shift if country == "A" else 0.0)))
    pairs = av.revision_pairs(_long(rows), _specs3())
    first = pairs.iloc[0]
    assert first["n"] == 8 and first["mean_signed"] == pytest.approx(0.25)
    assert first["mean_abs"] == pytest.approx(0.25) and first["max_abs"] == pytest.approx(0.5)
    assert pairs.iloc[1]["mean_abs"] == pytest.approx(0.0)
    # outturn_only keeps years <= last observed year of the earlier vintage (Autumn: max 2015 -> 2015-3 = 2012)
    out = av.revision_pairs(_long(rows), _specs3(), outturn_only=True)
    assert out.iloc[0]["n"] == 2
    assert av.revision_pairs(_long(rows), _specs3(), min_year=2015).iloc[0]["n"] == 2


def test_first_release_table_and_summary() -> None:
    specs = _specs3()
    rows = []
    # V1 (autumn, last year 2016 -> last observed 2013): 2014 is a forecast; V2 (spring, 2016 -> 2014): outturn
    for order, max_year, v2014 in ((1, 2016, 1.0), (2, 2016, 2.0), (3, 2017, 2.5)):
        for year in range(2013, max_year + 1):
            rows.append((order, "A", year, v2014 if year == 2014 else 0.0))
    rows.append((99, "A", 2014, 3.0))
    rows.append((99, "A", 2013, 0.0))
    table = av.first_release_table(_long(rows), specs, window=(2014, 2014))
    rec = table.iloc[0]
    assert rec["first_any_vintage"] == "V1" and rec["first_any_value"] == 1.0
    assert rec["first_outturn_vintage"] == "V2" and rec["first_outturn_value"] == 2.0
    assert rec["revision_outturn"] == pytest.approx(1.0) and rec["revision_any"] == pytest.approx(2.0)
    summary = av.summarise_revisions(table, "outturn")
    assert summary["mean_abs_revision"].iloc[0] == pytest.approx(1.0)
    assert summary["share_sign_change"].iloc[0] == 0.0


def test_sign_change_share() -> None:
    first = pd.Series([1.0, -1.0, 0.0, 2.0])
    final = pd.Series([-1.0, -2.0, 1.0, 3.0])
    assert av._sign_change(first, final).tolist() == [True, False, False, False]


def test_pre_election_vintage_is_strictly_before() -> None:
    specs = _specs3()
    assert av.pre_election_vintage(date(2015, 5, 7), specs).label == "V1"  # same day is not "before"
    assert av.pre_election_vintage(date(2015, 5, 8), specs).label == "V2"
    assert av.pre_election_vintage(date(2014, 11, 6), specs) is None


def test_election_availability_flags() -> None:
    rows = []
    for order, max_year in ((1, 2016), (2, 2016), (3, 2017)):
        for year in range(2013, max_year + 1):
            rows.append((order, "A", year, 1.0))
    calendar = pd.DataFrame(
        {"eurostat_code": ["A", "A"], "election_date": [date(2015, 6, 1), date(2015, 1, 15)], "election_class": ["early", "scheduled"]}
    )
    out = av.election_availability(calendar, _long(rows), _specs3(), start=date(2015, 1, 1), end=date(2015, 12, 31))
    june = out[out["election_class"] == "early"].iloc[0]
    assert june["vintage"] == "V2" and june["has_t"] and june["has_t_plus_1"] and june["t_minus_1_is_outturn"]
    jan = out[out["election_class"] == "scheduled"].iloc[0]
    assert jan["vintage"] == "V1" and not jan["t_minus_1_is_outturn"]  # 2014 is still a forecast in the autumn vintage
    counts = av.availability_by_class(out)
    assert counts.loc["total", "n_elections"] == 2


def test_realtime_window_coverage() -> None:
    keys = pd.DataFrame({"eurostat_code": ["A"] * 4, "year": [2013, 2015, 2020, 2021]})
    assert av.realtime_window_coverage(keys, 2015, 2021) == {"n_total": 4, "n_inside": 3, "share": 0.75}


def test_interim_csv_schema(tmp_path: Path) -> None:
    out = tmp_path / "x" / "v.csv"
    av.to_interim_csv(_long([(1, "A", 2014, 1.0)]), out)
    frame = pd.read_csv(out)
    assert list(frame.columns) == [
        "vintage_label", "vintage_order", "printed_date", "area", "eurostat_code", "item", "year", "value", "unit_text"
    ]
    assert frame["printed_date"].iloc[0] == "2020-01-01"


@real
def test_real_t3_pass_and_known_facts() -> None:
    long = av.build_long_table()
    summary = av.t3_summary(long)
    verdict = av.t3_verdict(summary)
    assert verdict["pass"] and verdict["n_vintages"] == 26 and verdict["min_countries"] == 27
    assert summary["label_identical"].all() and summary["denominator_identical"].all()
    assert summary["flag"].eq("").all()


@real
def test_real_autumn_2025_is_a_distinct_autumn_vintage() -> None:
    long = av.build_long_table(items=("UBLGBP",))
    last_year = long.dropna(subset=["value"]).groupby("vintage_label")["year"].max()
    assert last_year["Autumn 2025"] == 2027 and last_year["Spring 2025"] == 2026  # three versus two forecast years
    wide = av.capb_wide(long)
    both = wide[[25, 26]].dropna()
    assert (both[25] != both[26]).all()  # not a duplicate of Spring 2025
    info = av.inventory_vintage(next(s for s in av.vintage_specs() if s.label == "Autumn 2025"))
    assert info["latest_member_stamp"] == "2025-12-11"


@real
def test_real_sign_convention_stable_across_vintages() -> None:
    long = av.build_long_table(items=("UBLGBP",))
    check = av.adjacent_sign_check(long)
    assert (check["pearson_r"] > 0.9).all() and (check["share_same_sign"] > 0.95).all()
    wide = av.capb_wide(long)
    assert (wide.loc[("EL", 2016)].dropna() > 0).all()  # Appendix B: EL 2016 = +10.58 in the pinned vintage
    assert wide.loc[("EL", 2016), av.FINAL_ORDER] == pytest.approx(10.58, abs=0.01)
    assert wide.loc[("DE", 2009), av.FINAL_ORDER] == pytest.approx(1.89, abs=0.01)
    assert wide.loc[("EL", 2009)].dropna().lt(0).all()  # deficit year is negative in every vintage (surplus positive)


@real
def test_real_gate3a_sample_has_715_rows() -> None:
    keys = av.gate3a_sample_keys()
    assert len(keys) == 715 and keys["eurostat_code"].nunique() == 27
    cov = av.realtime_window_coverage(keys, *av.SAMPLE_WINDOW_YEARS)
    assert cov["n_inside"] == 7 * 27


def test_compare_to_final_exact() -> None:
    rows = [(1, "A", 2010, 1.0), (1, "A", 2011, -1.0), (1, "B", 2010, 2.0), (99, "A", 2010, 2.0), (99, "A", 2011, 1.0), (99, "B", 2010, 2.0)]
    out = av.compare_to_final(_long(rows), 1, (2010, 2011))
    assert out["n"] == 3 and out["mean_revision"] == pytest.approx(1.0)
    assert out["mean_abs_revision"] == pytest.approx(1.0) and out["share_sign_change"] == pytest.approx(1 / 3)
    assert av.compare_to_final(_long(rows), 1, (2011, 2011))["n"] == 1
