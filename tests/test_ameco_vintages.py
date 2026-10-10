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
