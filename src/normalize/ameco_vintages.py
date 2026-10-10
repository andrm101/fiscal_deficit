"""Readers for the archived AMECO text vintages (Autumn 2014 to Autumn 2025) and the S4 feasibility statistics.

Scope (Gate 5, trigger T3 of ``docs/stage_c_blueprint.md``): parse chapter 17 (cyclical adjustment) of
every archived vintage zip into one long table, then compute descriptive checks only (country counts,
label/denominator consistency, sign convention, revisions across vintages, real-time availability
around elections). No election effect or outcome-on-election regression lives here.

Everything reads local files under ``data/raw/ameco_archive/`` (read-only). No network access.

Archive format facts (verified on the 26 zips): each zip holds 18 or 19 semicolon-delimited ``AMECO*.TXT``
chapter files, latin-1 encoded; in four vintages (Autumn 2020, Autumn 2021, Spring 2022 and the
nested layout of some others) the chapter files are themselves zips (``ameco17.zip``). Missing values are
the literal ``NA``. Row code is ``AREA.1.0.319.0.ITEM``; the unit text is the denominator description
and may carry stray spaces.
"""
from __future__ import annotations

import io
import re
import sys
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ameco  # noqa: E402
import countries  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = PROJECT_ROOT / "data" / "raw" / "ameco_archive"
ARCHIVE_TOML = PROJECT_ROOT / "config" / "acquisition" / "gate5_ameco_archive.toml"
FINAL_SNAPSHOT_ZIP = ameco.AMECO_DIR / "ameco_all_csv.zip"
FINAL_CHAPTER_FILE = "AMECO17.CSV"

CAPB_ITEM = "UBLGBP"
# AVGDGP (output gap) lives in chapter 6, not chapter 17, and is not parsed here (not needed for T3).
COMPARISON_ITEMS = ("UBLGBP", "UBLGAP", "UBLGCP")
POTENTIAL_GDP_TEXT = "Percentage of potential GDP at current prices"
CHAPTER17_NAME = "AMECO17.TXT"
MISSING_TOKEN = "NA"
FIELD_SEP = ";"
N_META_COLUMNS = 5  # CODE;COUNTRY;SUB-CHAPTER;TITLE;UNIT
FINAL_LABEL = "Spring 2026"
FINAL_ORDER = 99  # sorts after every archived vintage
MIN_COUNTRIES_T3 = 20  # trigger T3 threshold (blueprint section 7.3)
# Forecast years at the end of a vintage. AMECO Reference Metadata states the rule for Spring (2) and Autumn (3)
# only. Winter (published in February) is treated as 3 (assumption, flagged in the report): Eurostat's first
# notification of the previous year's outturn is in April, so a February vintage cannot hold year t-1 outturn.
FORECAST_YEARS_BY_SEASON = {"winter": 3, "spring": 2, "autumn": 3}


@dataclass(frozen=True)
class VintageSpec:
    """One archived vintage: label, chronological order, season, year, zip path and printed date."""

    label: str
    order: int
    season: str
    year: int
    zip_path: Path
    printed_date: date
    printed_date_suspect: bool = False


# Printed release dates as listed on the AMECO archive page (Appendix B section 1.3).
_PRINTED: list[tuple[str, int, date, bool]] = [
    ("autumn", 2014, date(2014, 11, 6), False),
    ("winter", 2015, date(2015, 2, 4), False),
    ("spring", 2015, date(2015, 5, 7), False),
    ("autumn", 2015, date(2015, 11, 5), False),
    ("winter", 2016, date(2016, 2, 4), False),
    ("spring", 2016, date(2016, 5, 3), False),
    ("autumn", 2016, date(2016, 11, 9), False),
    ("winter", 2017, date(2017, 2, 13), False),
    ("spring", 2017, date(2017, 5, 11), False),
    ("autumn", 2017, date(2017, 11, 9), False),
    ("spring", 2018, date(2018, 5, 3), False),
    ("autumn", 2018, date(2018, 11, 8), False),
    ("spring", 2019, date(2019, 5, 7), False),
    ("autumn", 2019, date(2019, 11, 7), False),
    ("spring", 2020, date(2020, 5, 6), False),
    ("autumn", 2020, date(2020, 11, 5), False),
    ("spring", 2021, date(2021, 5, 12), False),
    ("autumn", 2021, date(2021, 11, 11), False),
    ("spring", 2022, date(2022, 5, 16), False),
    ("autumn", 2022, date(2022, 11, 17), False),
    ("spring", 2023, date(2023, 5, 15), False),
    ("autumn", 2023, date(2023, 11, 27), False),
    ("spring", 2024, date(2024, 5, 15), False),
    ("autumn", 2024, date(2024, 11, 15), False),
    ("spring", 2025, date(2025, 5, 19), False),
    ("autumn", 2025, date(2025, 6, 3), True),
]


def vintage_specs(archive_dir: Path = ARCHIVE_DIR) -> list[VintageSpec]:
    """Return the 26 archived vintages in chronological order with zip paths and printed dates."""
    specs = []
    for order, (season, year, printed, suspect) in enumerate(_PRINTED, start=1):
        label = f"{season.capitalize()} {year}"
        path = archive_dir / f"{year}_{season}" / f"ameco_{season}{year}.zip"
        specs.append(VintageSpec(label, order, season, year, path, printed, suspect))
    return specs


def printed_dates_from_toml(path: Path = ARCHIVE_TOML) -> dict[str, date]:
    """Parse the printed dates out of the ``role`` strings of the acquisition TOML (cross-check of ``_PRINTED``)."""
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    pattern = re.compile(r"archived vintage (\w+) (\d{4}) \(printed date (\d+) (\w{3}) (\d{4})")
    months = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)}
    out: dict[str, date] = {}
    for entry in config["file"]:
        found = pattern.search(entry["role"])
        if found:
            season, year, day, month, year2 = found.groups()
            out[f"{season} {year}"] = date(int(year2), months[month], int(day))
    return out


def last_observed_year(max_year_in_vintage: int, season: str) -> int:
    """Last non-forecast year of a vintage: its last column year minus the season's forecast horizon."""
    return max_year_in_vintage - FORECAST_YEARS_BY_SEASON[season.lower()]


# --------------------------------------------------------------------------------------- reading
def _open_member(zip_path: Path, member_name: str = CHAPTER17_NAME) -> tuple[bytes, str, bool, tuple[int, ...]]:
    """Return (bytes, member name used, nested?, zip member timestamp) of chapter 17, unwrapping a nested zip."""
    with zipfile.ZipFile(zip_path) as archive:
        by_lower = {info.filename.lower(): info for info in archive.infolist()}
        key = member_name.lower()
        if key in by_lower:
            info = by_lower[key]
            return archive.read(info), info.filename, False, tuple(info.date_time)
        nested_key = Path(member_name).stem.lower() + ".zip"
        if nested_key in by_lower:
            info = by_lower[nested_key]
            with zipfile.ZipFile(io.BytesIO(archive.read(info))) as inner:
                inner_info = next(i for i in inner.infolist() if i.filename.lower() == key)
                return inner.read(inner_info), f"{info.filename}!{inner_info.filename}", True, tuple(inner_info.date_time)
    raise KeyError(f"chapter 17 member {member_name} not found in {zip_path}")


def read_chapter17_bytes(zip_path: Path) -> bytes:
    """Raw bytes of AMECO chapter 17 (cyclical adjustment) from a vintage zip (nested or flat)."""
    return _open_member(zip_path)[0]


def parse_ameco_txt(raw: bytes, items: tuple[str, ...] = COMPARISON_ITEMS) -> pd.DataFrame:
    """Parse an AMECO semicolon text chapter into a long table for the requested items.

    Returns columns ``area, item, code, sub_chapter, title, unit_text, year, value`` (value is float, NaN for ``NA``).
    Encoding is latin-1; unit text is whitespace-stripped. Rows whose code does not end in a requested item
    are skipped. Handles ragged rows (trailing separators, fewer values than years).
    """
    text = raw.decode("latin-1")
    lines = text.splitlines()
    header = lines[0].split(FIELD_SEP)
    year_cols = [int(c) for c in header[N_META_COLUMNS:] if c.strip().isdigit()]
    wanted = set(items)
    records: list[dict[str, object]] = []
    for line in lines[1:]:
        parts = line.split(FIELD_SEP)
        if len(parts) < N_META_COLUMNS:
            continue
        code = parts[0].strip()
        item = code.split(".")[-1]
        if item not in wanted:
            continue
        values = parts[N_META_COLUMNS:]
        for year, token in zip(year_cols, values, strict=False):
            token = token.strip()
            value = np.nan if token in ("", MISSING_TOKEN) else float(token)
            records.append(
                {
                    "area": code.split(".")[0],
                    "item": item,
                    "code": code,
                    "sub_chapter": parts[2].strip(),
                    "title": parts[3].strip(),
                    "unit_text": parts[4].strip().strip("()").strip(),
                    "year": year,
                    "value": value,
                }
            )
    return pd.DataFrame.from_records(
        records, columns=["area", "item", "code", "sub_chapter", "title", "unit_text", "year", "value"]
    )


def inventory_vintage(spec: VintageSpec) -> dict[str, object]:
    """Zip-level facts for the report: member names, formats, chapter 17 member, timestamps, header span."""
    with zipfile.ZipFile(spec.zip_path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        stamps = sorted({tuple(i.date_time) for i in infos})
    raw, member, nested, stamp = _open_member(spec.zip_path)
    header = raw.decode("latin-1").splitlines()[0].split(FIELD_SEP)
    years = [int(c) for c in header[N_META_COLUMNS:] if c.strip().isdigit()]
    return {
        "vintage": spec.label,
        "n_members": len(names),
        "formats": sorted({Path(n).suffix.lower() for n in names}),
        "nested": nested,
        "chapter17_member": member,
        "earliest_member_stamp": date(*stamps[0][:3]).isoformat(),
        "latest_member_stamp": date(*stamps[-1][:3]).isoformat(),
        "chapter17_stamp": date(*stamp[:3]).isoformat(),
        "header_first_year": min(years),
        "header_last_year": max(years),
    }


def load_vintage(spec: VintageSpec, items: tuple[str, ...] = COMPARISON_ITEMS) -> pd.DataFrame:
    """Long table for one vintage with vintage metadata and Eurostat codes; aggregates are dropped."""
    long = parse_ameco_txt(read_chapter17_bytes(spec.zip_path), items)
    return _attach_metadata(long, spec)


def _attach_metadata(long: pd.DataFrame, spec: VintageSpec) -> pd.DataFrame:
    """Add vintage columns and map AMECO area codes to Eurostat codes (non-EU-27 areas dropped)."""
    mapping = countries.ameco_to_eurostat()
    frame = long.copy()
    frame["eurostat_code"] = frame["area"].map(mapping)
    frame = frame[frame["eurostat_code"].notna()].copy()
    frame["vintage_label"] = spec.label
    frame["vintage_order"] = spec.order
    frame["printed_date"] = pd.Timestamp(spec.printed_date)
    return frame[
        ["vintage_label", "vintage_order", "printed_date", "area", "eurostat_code", "item", "year", "value", "unit_text", "sub_chapter", "title"]
    ]


def load_final_snapshot(items: tuple[str, ...] = COMPARISON_ITEMS, zip_path: Path = FINAL_SNAPSHOT_ZIP) -> pd.DataFrame:
    """Spring 2026 pinned snapshot (the 'final' vintage) in the same long layout, vintage order 99.

    Reuses ``ameco.read_zip_item`` (comma CSV, latin-1); the unit text is normalised like the archive's.
    """
    parts = []
    for item in items:
        part = ameco.read_zip_item(zip_path, FINAL_CHAPTER_FILE, item)
        part = part.rename(columns={"AREA": "area", "ITEM": "item"})
        part["code"] = part["area"] + "." + part["item"]
        part["unit_text"] = part["unit_text"].astype(str).str.strip().str.strip("()").str.strip()
        parts.append(part)
    long = pd.concat(parts, ignore_index=True)
    long["title"] = long["title"].astype(str).str.strip()
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    final = VintageSpec(FINAL_LABEL, FINAL_ORDER, "spring", 2026, zip_path, date(2026, 6, 3))
    long["sub_chapter"] = ""  # not carried by ameco.read_zip_item; the archive's ESA95/ESA 2010 tag is not needed for the final
    return _attach_metadata(long[["area", "item", "code", "sub_chapter", "title", "unit_text", "year", "value"]], final)


def build_long_table(items: tuple[str, ...] = COMPARISON_ITEMS, archive_dir: Path = ARCHIVE_DIR) -> pd.DataFrame:
    """All 26 archived vintages plus the Spring 2026 snapshot in one long table (EU-27 only)."""
    frames = [load_vintage(spec, items) for spec in vintage_specs(archive_dir)]
    frames.append(load_final_snapshot(items))
    return pd.concat(frames, ignore_index=True)
