"""Offline tests for the Eurostat SDMX-CSV reader (R01: negative values must survive, flags must be carried)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "normalize"))
import eurostat  # noqa: E402

HEADER = "DATAFLOW,LAST UPDATE,freq,unit,sector,na_item,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG,CONF_STATUS"


def write_csv(tmp_path: Path, rows: list[str], header: str = HEADER, name: str = "x.csv") -> Path:
    """Write a small SDMX-CSV file and return its path."""
    path = tmp_path / name
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def row(geo: str, year: int, value: str, flag: str = "", item: str = "B9", unit: str = "PC_GDP") -> str:
    """One SDMX-CSV data row for ``gov_10a_main``."""
    return f"ESTAT:GOV_10A_MAIN(1.0),21/07/26 11:00:00,A,{unit},S13,{item},{geo},{year},{value},{flag},"


def test_negative_values_survive_and_flags_are_kept(tmp_path):
    path = write_csv(tmp_path, [row("AT", 2000, "-3.2", "p"), row("AT", 2001, "-0.5"), row("EL", 2000, "12.4", "b")])
    long = eurostat.read_eurostat_sdmx_csv(path)
    assert long["value"].tolist() == [-3.2, -0.5, 12.4]
    assert int((long["value"] < 0).sum()) == 2
    assert long["obs_flag"].tolist()[0] == "p" and pd.isna(long["obs_flag"].iloc[1]) and long["obs_flag"].iloc[2] == "b"
    assert long["year"].dtype.kind == "i" and long["dataset"].unique().tolist() == ["gov_10a_main"]
    assert long["geo"].tolist() == ["AT", "AT", "EL"]  # Greece stays EL


def test_empty_value_is_nullable_and_keeps_its_flag(tmp_path):
    long = eurostat.read_eurostat_sdmx_csv(write_csv(tmp_path, [row("AT", 2000, "", "c"), row("AT", 2001, "1.0")]))
    assert math.isnan(long["value"].iloc[0]) and long["obs_flag"].iloc[0] == "c"
    assert long["value"].iloc[1] == 1.0


def test_duplicate_keys_are_rejected(tmp_path):
    path = write_csv(tmp_path, [row("AT", 2000, "1.0"), row("AT", 2000, "2.0")])
    with pytest.raises(ValueError, match="duplicate key"):
        eurostat.read_eurostat_sdmx_csv(path)


def test_same_period_different_item_is_not_a_duplicate(tmp_path):
    long = eurostat.read_eurostat_sdmx_csv(write_csv(tmp_path, [row("AT", 2000, "1.0", item="B9"), row("AT", 2000, "2.0", item="TR")]))
    assert len(long) == 2


def test_bulk_tsv_export_is_rejected(tmp_path):
    path = tmp_path / "bulk.tsv"
    path.write_text("freq,unit,sector,na_item,geo\\TIME_PERIOD\t2000 \t2001\nA,PC_GDP,S13,B9,AT\t-3.2 p\t-0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SDMX-CSV"):
        eurostat.read_eurostat_sdmx_csv(path)


def test_non_numeric_value_is_an_error_not_a_silent_drop(tmp_path):
    with pytest.raises(ValueError):
        eurostat.read_eurostat_sdmx_csv(write_csv(tmp_path, [row("AT", 2000, "-3.2 p")]))


def test_dataset_code_parsing():
    assert eurostat.dataset_code("ESTAT:GOV_10DD_EDPT1(1.0)") == "gov_10dd_edpt1"
    assert eurostat.dataset_code("ESTAT:NAMA_10_GDP(1.0)") == "nama_10_gdp"
    with pytest.raises(ValueError):
        eurostat.dataset_code("???")


@pytest.mark.parametrize(
    "cell, value, flag",
    [("-3.2 p", -3.2, "p"), ("-0.5", -0.5, None), ("1 234.5 e", 1234.5, "e"), ("0.0", 0.0, None), ("12 b", 12.0, "b"),
     ("1 234 e", 1234.0, "e"), ("−3.2 p", -3.2, "p"), ("1 234.5 e", 1234.5, "e")],
)
def test_legacy_cell_regression_r01_keeps_sign_and_flag(cell, value, flag):
    got_value, got_flag = eurostat.parse_legacy_tsv_cell(cell)
    assert got_value == value and got_flag == flag


@pytest.mark.parametrize("cell, flag", [(": c", "c"), (":", None), (": ", None)])
def test_legacy_missing_cell(cell, flag):
    value, got_flag = eurostat.parse_legacy_tsv_cell(cell)
    assert math.isnan(value) and got_flag == flag


def test_legacy_column_keeps_its_negative_count():
    """A CAPB-like column: the count of negative values must be the same before and after parsing (R01)."""
    cells = ["-3.2 p", "-0.5", "1.1", ": c", "-12 e", "4.0 b", "-0.1"]
    parsed = [eurostat.parse_legacy_tsv_cell(c)[0] for c in cells]
    assert sum(1 for v in parsed if v < 0) == sum(1 for c in cells if c.startswith("-")) == 4


def test_legacy_garbage_raises():
    with pytest.raises(ValueError):
        eurostat.parse_legacy_tsv_cell("abc def")


def test_select_series_filters_and_checks_uniqueness(tmp_path):
    rows = [row("AT", 2000, "1.0", item="B9"), row("AT", 2000, "2.0", item="TR"), row("AT", 2001, "3.0", item="B9")]
    long = eurostat.read_eurostat_sdmx_csv(write_csv(tmp_path, rows))
    series = eurostat.select_series(long, dataset="gov_10a_main", unit="PC_GDP", na_item="B9")
    assert series["value"].tolist() == [1.0, 3.0]
    with pytest.raises(KeyError):
        eurostat.select_series(long, dataset="gov_10a_main", unit="MIO_EUR", na_item="B9")


# ---------------------------------------------------------------------------------------------
# Real raw files (read-only); skipped when absent
# ---------------------------------------------------------------------------------------------
needs_raw = pytest.mark.skipif(not (eurostat.EUROSTAT_DIR / "gov_10a_main_pc_gdp_1993_2025.csv").exists(), reason="raw Eurostat files absent")


@needs_raw
def test_real_gov_10a_main_keeps_negative_balances_and_flags():
    long = eurostat.read_eurostat_sdmx_csv(eurostat.EUROSTAT_DIR / "gov_10a_main_pc_gdp_1993_2025.csv")
    b9 = eurostat.select_series(long, dataset="gov_10a_main", unit="PC_GDP", na_item="B9")
    assert (b9["value"] < 0).sum() > 100  # deficits are the norm in B9
    assert set(long["obs_flag"].dropna().unique()) <= {"p", "b", "e", "c"}
    raw_negatives = int((pd.read_csv(eurostat.EUROSTAT_DIR / "gov_10a_main_pc_gdp_1993_2025.csv")["OBS_VALUE"] < 0).sum())
    assert int((long["value"] < 0).sum()) == raw_negatives


@needs_raw
def test_real_directory_keys_unique_and_countries_are_eurostat_codes():
    long = eurostat.read_eurostat_dir()
    assert "EL" in set(long["geo"]) and "GR" not in set(long["geo"])
    assert long["geo"].nunique() == 27
    assert set(long["unit"]) == {"PC_GDP", "MIO_EUR", "CP_MEUR"}
