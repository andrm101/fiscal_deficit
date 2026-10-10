"""Offline tests for the EU-27 country crosswalk (config/countries.csv)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import ameco  # noqa: E402
import countries  # noqa: E402

KEY_COLUMNS = ["eurostat_code", "iso2", "iso3", "ameco_code", "name"]


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return countries.load_countries()


def test_exactly_27_members(table):
    assert len(table) == countries.N_EU27 == 27


@pytest.mark.parametrize("column", KEY_COLUMNS)
def test_keys_are_unique_and_non_empty(table, column):
    assert table[column].notna().all()
    assert table[column].is_unique


def test_croatia_and_slovenia_included(table):
    assert {"HR", "SI"} <= set(table["eurostat_code"])
    assert {"HRV", "SVN"} <= set(table["iso3"])


def test_no_uk_and_no_non_members(table):
    for forbidden in ("UK", "GB", "GBR", "NO", "NOR", "IS", "CH", "TR"):
        for column in ("eurostat_code", "iso2", "iso3", "ameco_code"):
            assert forbidden not in set(table[column])


def test_greece_and_romania_special_codes(table):
    greece = table.set_index("name").loc["Greece"]
    assert (greece["eurostat_code"], greece["iso2"], greece["iso3"], greece["ameco_code"]) == ("EL", "GR", "GRC", "GRC")
    romania = table.set_index("name").loc["Romania"]
    assert (romania["iso3"], romania["ameco_code"]) == ("ROU", "ROM")
    assert "GR" not in set(table["eurostat_code"])


def test_round_trips(table):
    for code, iso3 in countries.eurostat_to_iso3().items():
        assert countries.iso3_to_eurostat()[iso3] == code
    for code, ameco_code in countries.eurostat_to_ameco().items():
        assert countries.ameco_to_eurostat()[ameco_code] == code


def test_ameco_codes_match_the_ameco_module_list(table):
    """The AMECO list hard-coded in src/normalize/ameco.py (tested against the raw file) must agree."""
    assert set(table["ameco_code"]) == set(ameco.EU27_AMECO)


def test_years_are_plausible(table):
    assert table["eu_accession_year"].between(1958, 2013).all()
    adopted = table["euro_adoption_year"].dropna()
    assert adopted.between(1999, 2023).all()
    # Euro adoption never precedes accession.
    both = table.dropna(subset=["euro_adoption_year"])
    assert (both["euro_adoption_year"] >= both["eu_accession_year"]).all()
    # Croatia joined the euro area last, in 2023 (proposal section 4: the 27 members of 2023).
    assert table.set_index("eurostat_code").loc["HR", "euro_adoption_year"] == 2023


def test_crosswalk_covers_the_raw_eurostat_and_ameco_files(table):
    eurostat_csv = ROOT / "data" / "raw" / "elections_ageing" / "eurostat_demo_pjanind" / "demo_pjanind_EU27_OLDDEP_1994_2025.csv"
    ameco_csv = ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER17-01_UBLGBP.csv"
    if not (eurostat_csv.exists() and ameco_csv.exists()):
        pytest.skip("raw inputs not present")
    assert set(pd.read_csv(eurostat_csv, usecols=["geo"])["geo"]) == set(table["eurostat_code"])
    assert set(table["ameco_code"]) <= set(pd.read_csv(ameco_csv, usecols=["REF_AREA"])["REF_AREA"])
