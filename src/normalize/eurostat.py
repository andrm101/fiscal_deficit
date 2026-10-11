"""Eurostat SDMX-CSV reader (silver.eurostat_long) and a defensive parser for the legacy bulk-TSV cell format.

Regression R01 (blueprint section 5): an earlier pipeline stripped the flag from a bulk-TSV cell with a regular
expression that also removed the minus sign, so every negative value (a deficit, a negative balance) vanished.
The SDMX-CSV format carries ``OBS_VALUE`` and ``OBS_FLAG`` in separate columns, so no cell ever needs to be
split; this module reads that format only. :func:`parse_legacy_tsv_cell` exists solely so the legacy cell
format ('-3.2 p', ': c', '1 234.5 e') has a regression test: it must keep the sign, return a missing value for
':' and carry the flag.

The long table follows ``config/contracts/contracts.toml`` [silver.eurostat_long]: ``geo`` (Eurostat code; Greece
is ``EL``), ``year``, ``dataset``, ``unit``, ``na_item`` (the contract's ``na_item_or_indic``), ``value`` (float,
NaN where the source cell is empty; negative values are preserved), ``obs_flag`` (``p``, ``b``, ``e``, ... or
missing). ``sector`` and ``cofog99`` are kept when the dataset has them (they are part of the key in
``gov_10a_main`` / ``gov_10a_exp``). Duplicate keys are rejected. No network access, no randomness.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EUROSTAT_DIR = PROJECT_ROOT / "data" / "raw" / "eurostat_controls"

REQUIRED_COLUMNS = ("DATAFLOW", "geo", "TIME_PERIOD", "OBS_VALUE", "OBS_FLAG")
OPTIONAL_KEY_COLUMNS = {"unit": "unit", "sector": "sector", "cofog99": "cofog99", "na_item": "na_item"}
KEY_COLUMNS = ["geo", "year", "dataset", "unit", "sector", "cofog99", "na_item"]
OUTPUT_COLUMNS = ["geo", "year", "dataset", "unit", "sector", "cofog99", "na_item", "value", "obs_flag"]
_DATAFLOW_PATTERN = re.compile(r"^(?:[A-Z0-9_]+:)?(?P<code>[A-Za-z0-9_]+)(?:\([^)]*\))?$")


def dataset_code(dataflow: str) -> str:
    """Lower-case dataset code from an SDMX ``DATAFLOW`` cell, e.g. ``ESTAT:GOV_10A_MAIN(1.0)`` -> ``gov_10a_main``."""
    match = _DATAFLOW_PATTERN.match(dataflow.strip())
    if match is None:
        raise ValueError(f"cannot parse DATAFLOW value {dataflow!r}")
    return match.group("code").lower()


def read_eurostat_sdmx_csv(path: Path) -> pd.DataFrame:
    """Read one Eurostat SDMX-CSV file into the typed long table.

    Raises ``ValueError`` when required columns are missing (for example a bulk-TSV export, whose header is
    ``freq,unit,geo\\TIME_PERIOD`` with flags inside the cells), when ``OBS_VALUE`` holds a non-numeric string,
    when ``TIME_PERIOD`` is not an integer year, or when two rows share a key. Negative values and observation
    flags are kept. Empty ``OBS_VALUE`` cells become NaN and keep their flag.
    """
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"{path.name}: not an Eurostat SDMX-CSV extract; missing columns {missing}")
    cell = raw["OBS_VALUE"].str.strip()
    value = pd.to_numeric(cell.where(cell != ""), errors="raise").astype(float)
    year = pd.to_numeric(raw["TIME_PERIOD"], errors="raise")
    if not (year == year.round()).all():
        raise ValueError(f"{path.name}: TIME_PERIOD must be an annual integer year")
    flag_cell = raw["OBS_FLAG"].str.strip()
    flag = flag_cell.where(flag_cell != "")
    out = pd.DataFrame(
        {
            "geo": raw["geo"].str.strip(),
            "year": year.astype(int),
            "dataset": raw["DATAFLOW"].map(dataset_code),
            "value": value,
            "obs_flag": flag,
        }
    )
    for column in ("unit", "sector", "cofog99", "na_item"):
        out[column] = raw[column].str.strip() if column in raw.columns else None
    out = out[OUTPUT_COLUMNS].reset_index(drop=True)
    assert_unique_key(out, path.name)
    return out


def assert_unique_key(frame: pd.DataFrame, what: str = "table") -> None:
    """Raise ``ValueError`` when two rows share ``(geo, year, dataset, unit, sector, cofog99, na_item)``."""
    key = frame[KEY_COLUMNS].astype("object").where(frame[KEY_COLUMNS].notna(), "<NA>")
    duplicated = key.duplicated(keep=False)
    if duplicated.any():
        example = key[duplicated].iloc[0].to_dict()
        raise ValueError(f"{what}: {int(duplicated.sum())} rows share a duplicate key, e.g. {example}")


def read_eurostat_dir(directory: Path = EUROSTAT_DIR) -> pd.DataFrame:
    """Concatenate every ``*.csv`` extract of a directory (each file validated on its own)."""
    frames = [read_eurostat_sdmx_csv(p) for p in sorted(directory.glob("*.csv"))]
    return pd.concat(frames, ignore_index=True)


def select_series(long: pd.DataFrame, *, dataset: str, unit: str, na_item: str, cofog99: str | None = None) -> pd.DataFrame:
    """One series ``(geo, year, value, obs_flag)`` from the long table; raises if it is empty or not unique."""
    mask = (long["dataset"] == dataset) & (long["unit"] == unit) & (long["na_item"] == na_item)
    if cofog99 is not None:
        mask &= long["cofog99"] == cofog99
    series = long.loc[mask, ["geo", "year", "value", "obs_flag"]]
    if series.empty:
        raise KeyError(f"no rows for dataset={dataset} unit={unit} na_item={na_item} cofog99={cofog99}")
    if series.duplicated(["geo", "year"]).any():
        raise ValueError(f"series dataset={dataset} unit={unit} na_item={na_item} is not unique by (geo, year)")
    return series.reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Legacy bulk-TSV cell format (regression test for R01 only; never used by the pipeline)
# ---------------------------------------------------------------------------------------------
_MINUS_SIGNS = {"−": "-", "–": "-", "‒": "-"}  # unicode minus, en dash, figure dash
_SPACES = {" ": " ", " ": " ", " ": " "}  # no-break, narrow no-break, thin space
_CELL = re.compile(r"^(?P<num>[-+]?\d[\d ]*(?:\.\d+)?)\s*(?P<flag>[A-Za-z]{0,3})$")
_MISSING = re.compile(r"^:\s*(?P<flag>[A-Za-z]{0,3})$")


def parse_legacy_tsv_cell(cell: str) -> tuple[float, str | None]:
    """Split a bulk-TSV cell into ``(value, flag)`` without ever losing the sign.

    Examples: ``'-3.2 p' -> (-3.2, 'p')``, ``'-0.5' -> (-0.5, None)``, ``': c' -> (nan, 'c')``, ``':' -> (nan, None)``,
    ``'1 234.5 e' -> (1234.5, 'e')`` (a space is a thousands separator when digits follow). Raises ``ValueError``
    for anything else rather than guessing.
    """
    text = cell.strip()
    for old, new in {**_MINUS_SIGNS, **_SPACES}.items():
        text = text.replace(old, new)
    missing = _MISSING.match(text)
    if missing is not None:
        return float("nan"), (missing.group("flag") or None)
    parsed = _CELL.match(text)
    if parsed is None:
        raise ValueError(f"cannot parse legacy cell {cell!r}")
    return float(parsed.group("num").replace(" ", "")), (parsed.group("flag") or None)


def coverage_by_country_year(series: pd.DataFrame, years: range) -> pd.DataFrame:
    """Boolean country x year table of non-missing values for a ``(geo, year, value)`` series."""
    present = series.dropna(subset=["value"]).assign(ok=True).pivot(index="geo", columns="year", values="ok")
    return present.reindex(columns=list(years)).fillna(False).astype(bool)
