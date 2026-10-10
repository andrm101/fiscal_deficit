"""Gate 1: automated metadata test for UBLGBP in the pinned AMECO Spring 2026 snapshot.

``UBLGBP`` stays the provisional primary outcome only while every test here passes.
The denominator is established from official text (SDMX COMMENT, zip UNIT column), never
from unit code 319 alone. Reads local raw files only (offline).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import ameco  # noqa: E402

SDMX = ameco.AMECO_DIR / "sdmx"
ZIP = ameco.AMECO_DIR / "ameco_all_csv.zip"
DSD = SDMX / "DSD_AMECO_1.4.xml"

pytestmark = pytest.mark.skipif(not ZIP.exists(), reason="run the Gate 1 acquisition first (ADR-001)")


@pytest.fixture(scope="module")
def capb() -> pd.DataFrame:
    return ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER17-01_UBLGBP.csv")


@pytest.fixture(scope="module")
def capb_zip() -> pd.DataFrame:
    return ameco.read_zip_item(ZIP, "AMECO17.CSV", "UBLGBP")


def test_1_exact_official_label_in_code_list_and_zip(capb_zip):
    assert ameco.read_dsd_label(DSD, "UBLGBP") == ameco.CAPB_LABEL
    assert set(capb_zip["title"]) == {ameco.CAPB_LABEL}


def test_2_denominator_is_potential_gdp_from_official_text(capb, capb_zip):
    assert set(capb["COMMENT"]) == {ameco.POTENTIAL_GDP_TEXT}
    assert set(capb_zip["unit_text"]) == {ameco.POTENTIAL_GDP_TEXT}
    assert (capb["UNIT"] == 319).all()  # documents the trap: 319 alone does not identify the denominator
    headline = ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER16-04_UBLGIE.csv")
    assert ameco.ACTUAL_GDP_EDP_TEXT in set(headline["COMMENT"])
    assert ameco.POTENTIAL_GDP_TEXT not in set(headline["COMMENT"])
    trend = ameco.read_zip_item(ZIP, "AMECO17.CSV", "UBLGB")
    assert set(trend["unit_text"]) == {ameco.TREND_GDP_TEXT}


def test_2b_headline_extract_mixes_units_so_consumers_must_filter_by_text():
    headline = ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER16-04_UBLGIE.csv")
    assert headline["COMMENT"].nunique() == 3


def test_3_percentage_scaling(capb):
    assert (capb["UNIT_MULT"] == 0).all()
    values = capb["OBS_VALUE"].dropna()
    assert 1 < np.percentile(values.abs(), 99) < 30  # percentage points, not fractions
    assert -50 < values.min() and values.max() < 30


def test_4_surplus_positive_sign(capb):
    assert ameco.CAPB_LABEL.startswith("Net lending (+) or net borrowing (-)")
    pivot = capb.pivot(index="TIME_PERIOD", columns="REF_AREA", values="OBS_VALUE")
    # Pinned-vintage spot values (also seen by the scout on the FDMS flow): surplus > 0, deficit < 0.
    assert pivot.loc[2016, "GRC"] == pytest.approx(10.58, abs=0.01)
    assert pivot.loc[2009, "GRC"] == pytest.approx(-8.79, abs=0.01)
    assert pivot.loc[2009, "DEU"] == pytest.approx(1.89, abs=0.01)
    # Cyclically adjusted net lending minus CAPB = minus cyclically adjusted interest <= 0 everywhere.
    net = ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER17-01_UBLGAP.csv")
    merged = capb.merge(net, on=["REF_AREA", "TIME_PERIOD"], suffixes=("_pb", "_nl")).dropna(subset=["OBS_VALUE_pb", "OBS_VALUE_nl"])
    assert len(merged) > 1000
    assert ((merged["OBS_VALUE_nl"] - merged["OBS_VALUE_pb"]) <= 1e-6).all()


def test_5_vintage_and_zip_sdmx_parity(capb, capb_zip):
    assert set(capb["LAST UPDATE"]) == {"03/06/26 09:31:17"}  # dd/mm/yy: 3 June 2026 (Spring 2026)
    zip_long = capb_zip.rename(columns={"AREA": "REF_AREA", "year": "TIME_PERIOD"})
    merged = capb.merge(zip_long, on=["REF_AREA", "TIME_PERIOD"], how="outer", indicator=True)
    both = merged[merged["_merge"] == "both"].dropna(subset=["OBS_VALUE", "value"])
    assert len(both) > 1000
    assert np.abs(both["OBS_VALUE"] - both["value"]).max() < 1e-4  # both rounded to 5 decimals
    only_one = merged[(merged["_merge"] != "both") & (merged["OBS_VALUE"].notna() | merged["value"].notna())]
    assert only_one.empty  # no observation exists in just one of the two artefacts


def test_6_observed_versus_estimated_status(capb):
    assert set(capb["OBS_STATUS"]) == {"A"}  # flag carries no information (AMECO Reference Metadata)
    max_year = int(capb["TIME_PERIOD"].max())
    assert max_year == 2027
    assert ameco.last_observed_year(max_year, "spring") == 2025
    eu = capb[capb["REF_AREA"].isin(ameco.EU27_AMECO)]
    forecast = eu[eu["TIME_PERIOD"] > 2025]
    assert forecast["OBS_VALUE"].notna().sum() > 0  # forecast-year values exist, so the cut is mandatory


def test_7_country_codes_and_coverage(capb):
    areas = set(capb["REF_AREA"])
    assert set(ameco.EU27_AMECO) <= areas
    assert len(ameco.EU27_AMECO) == 27
    assert {"ROM", "GRC"} <= areas
    assert not ({"ROU", "GR", "EL", "GB"} & areas)
    window = capb[capb["REF_AREA"].isin(ameco.EU27_AMECO) & capb["TIME_PERIOD"].between(1995, 2025)]
    assert window["OBS_VALUE"].notna().sum() >= 0.97 * 27 * 31


def test_8_informational_identity_residual_is_reported_not_asserted(capb, capsys):
    """UBLGIE - UBLGCP vs UBLGBP: the identity is unverified, so only report its residual."""
    headline = ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER16-04_UBLGIE.csv")
    headline = headline[headline["COMMENT"] == ameco.ACTUAL_GDP_EDP_TEXT]
    cyc = ameco.read_sdmx_csv(SDMX / "AMECO_CHAPTER17-01_UBLGCP.csv")
    merged = (
        headline.merge(cyc, on=["REF_AREA", "TIME_PERIOD"], suffixes=("_h", "_c"))
        .merge(capb, on=["REF_AREA", "TIME_PERIOD"])
        .dropna(subset=["OBS_VALUE_h", "OBS_VALUE_c", "OBS_VALUE"])
    )
    residual = merged["OBS_VALUE_h"] - merged["OBS_VALUE_c"] - merged["OBS_VALUE"]
    print(f"identity residual UBLGIE-UBLGCP-UBLGBP: n={len(residual)}, mean={residual.mean():.3f}, max|.|={residual.abs().max():.3f}")
    assert len(residual) > 500
