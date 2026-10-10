"""Readers and metadata helpers for the pinned AMECO Spring 2026 snapshot.

Everything here reads local files under ``data/raw/ameco/2026_spring/``; nothing touches
the network. The denominator of every ratio series is taken from the official text
(SDMX ``COMMENT`` or the zip's ``UNIT`` column), never inferred from the numeric unit
code 319, which is shared by %-of-GDP and %-of-potential-GDP series.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AMECO_DIR = PROJECT_ROOT / "data" / "raw" / "ameco" / "2026_spring"

CAPB_ITEM = "UBLGBP"
CAPB_LABEL = (
    "Net lending (+) or net borrowing (-) excluding interest of general government adjusted "
    "for the cyclical component :- Adjustment based on potential GDP Excessive deficit procedure"
)
POTENTIAL_GDP_TEXT = "(Percentage of potential GDP at current prices)"
ACTUAL_GDP_EDP_TEXT = "(Percentage of GDP at current prices (excessive deficit procedure))"
TREND_GDP_TEXT = "(Percentage of trend GDP at current prices)"

# AMECO chapter-flow area codes for the 27 EU members (ISO-3-like; Romania is ROM, not ROU).
EU27_AMECO = (
    "AUT BEL BGR CYP CZE DEU DNK ESP EST FIN FRA GRC HRV HUN IRL ITA LTU LUX LVA MLT "
    "NLD POL PRT ROM SVK SVN SWE"
).split()

# Forecast years at the end of a vintage (AMECO Reference Metadata): two for a Spring
# forecast, three for an Autumn forecast. AMECO publishes no per-observation forecast flag.
FORECAST_YEARS_BY_SEASON = {"spring": 2, "autumn": 3}


def read_sdmx_csv(path: Path) -> pd.DataFrame:
    """Read an ECFIN Redisstat SDMX-CSV extract with typed columns."""
    frame = pd.read_csv(path)
    frame["TIME_PERIOD"] = frame["TIME_PERIOD"].astype(int)
    return frame


def read_dsd_label(dsd_xml: Path, item: str) -> str:
    """Return the official English label of an AMECO item from the DSD code list."""
    ns_xml = "{http://www.w3.org/XML/1998/namespace}lang"
    for code in ET.parse(dsd_xml).getroot().iter():
        if code.tag.endswith("}Code") and code.attrib.get("id") == item and "CL_AMECO_ITEM" in code.attrib.get("urn", ""):
            for name in code:
                if name.tag.endswith("}Name") and name.attrib.get(ns_xml) == "en":
                    return (name.text or "").strip()
    raise KeyError(f"item {item} not found in {dsd_xml}")


def read_zip_item(zip_path: Path, chapter_file: str, item: str) -> pd.DataFrame:
    """Long table (area, year, value, unit_text, title) for one item from a chapter CSV in the zip."""
    with zipfile.ZipFile(zip_path) as archive:
        wide = pd.read_csv(io.BytesIO(archive.read(chapter_file)), encoding="latin-1")
    wide["ITEM"] = wide["CODE"].str.split(".").str[-1]
    wide["AREA"] = wide["CODE"].str.split(".").str[0]
    wide = wide[wide["ITEM"] == item]
    year_cols = [c for c in wide.columns if c.isdigit()]
    long = wide.melt(
        id_vars=["AREA", "ITEM", "UNIT", "TITLE"], value_vars=year_cols, var_name="year", value_name="value"
    )
    long["year"] = long["year"].astype(int)
    return long.rename(columns={"UNIT": "unit_text", "TITLE": "title"})


def last_observed_year(max_year_in_vintage: int, season: str) -> int:
    """Last non-forecast year of a vintage by the AMECO rule (see module docstring)."""
    return max_year_in_vintage - FORECAST_YEARS_BY_SEASON[season.lower()]
