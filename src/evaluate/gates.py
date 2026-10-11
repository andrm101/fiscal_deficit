"""Failing quality gates for the gold country-year panel (remediation R03).

An earlier pipeline only *warned* when coverage was low and wrote its output anyway. Here every gate either
passes or the build stops: :func:`enforce_gates` raises :class:`GateFailure`, the command-line entry point exits
with status 1, and the writer in ``src/features/panel.py`` calls the gates *before* it creates any file, so a
failing panel leaves nothing behind.

Parameters are read from ``config/contracts/contracts.toml`` (table ``[gold.panel_country_year.gates]``) through
:meth:`GateConfig.from_contract`; tests build a :class:`GateConfig` directly for synthetic panels.

Definitions
-----------
*window panel*
    The gold panel: the retained countries times the years ``year_min .. year_max`` (27 x 27 = 729 rows). Coverage
    is measured here, before complete-case selection; after selection it would be 100 per cent by construction.
*confirmatory extract*
    The rows with ``in_confirmatory`` true (the Gate 3a sample, 715 rows).

Gates (all must pass)
---------------------
1. unique ``(eurostat_code, year)``;
2. coverage of ``capb`` on the window panel >= ``coverage_min`` (0.97);
3. coverage of ``olddep1_lag`` on the window panel >= ``coverage_min``;
4. every country of the window panel has >= ``min_obs_per_country`` (20) confirmatory observations;
5. ``capb`` inside the open interval (-50, 30) (percentage points of potential GDP);
6. the five exposure columns inside [0, 1], and non-missing on the extract;
7. no row after ``year_max`` (2021) and none before ``year_min`` (1995);
8. no AMECO forecast year (a year after the last observed year of the vintage);
9. ``exposure_complete_cv`` true on every extract row;
10. the extract has exactly ``confirmatory_rows`` rows and ``confirmatory_countries`` countries;
11. extract rows carry non-missing ``capb`` and ``olddep1_lag``;
12. no negative CAPB removed: the extract's CAPB equals the source value for each of its keys, so the count of
    negative values in the extract equals the count in the source for the same keys.

No randomness is involved (no seeds).
"""
from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TOML = PROJECT_ROOT / "config" / "contracts" / "contracts.toml"

KEY = ["eurostat_code", "year"]
EXPOSURE_COLUMNS = ["W_S", "W_E", "W_D", "W_U", "Post"]
REQUIRED_COLUMNS = KEY + ["capb", "olddep1_lag", "exposure_complete_cv", "in_confirmatory"] + EXPOSURE_COLUMNS


@dataclass(frozen=True)
class GateConfig:
    """Numeric gate parameters (defaults mirror ``[gold.panel_country_year.gates]`` of the contract)."""

    confirmatory_rows: int = 715
    confirmatory_countries: int = 27
    year_min: int = 1995
    year_max: int = 2021
    coverage_min: float = 0.97
    min_obs_per_country: int = 20
    capb_lower_exclusive: float = -50.0
    capb_upper_exclusive: float = 30.0
    w_lower: float = 0.0
    w_upper: float = 1.0

    @classmethod
    def from_contract(cls, path: Path = CONTRACT_TOML) -> GateConfig:
        """Read the parameters from the gold-panel contract."""
        with path.open("rb") as handle:
            table = tomllib.load(handle)["gold"]["panel_country_year"]["gates"]
        return cls(**table)


@dataclass(frozen=True)
class GateResult:
    """Outcome of one gate."""

    name: str
    passed: bool
    detail: str


class GateFailure(Exception):
    """Raised when at least one gate fails; ``results`` holds every gate outcome."""

    def __init__(self, results: list[GateResult]) -> None:
        self.results = results
        failed = [r for r in results if not r.passed]
        super().__init__("gate failure: " + "; ".join(f"{r.name} ({r.detail})" for r in failed))


def _coverage(panel: pd.DataFrame, column: str) -> float:
    return float(panel[column].notna().mean()) if len(panel) else 0.0


def run_gates(
    panel: pd.DataFrame,
    source_capb: pd.DataFrame,
    last_observed_year: int,
    config: GateConfig | None = None,
) -> list[GateResult]:
    """Evaluate every gate and return all outcomes (never raises on a failing gate).

    ``source_capb`` is the unfiltered observed CAPB series ``(eurostat_code, year, capb)`` read from AMECO;
    ``last_observed_year`` is the last non-forecast year of the vintage (2025 for AMECO Spring 2026).
    """
    cfg = GateConfig.from_contract() if config is None else config
    missing = [c for c in REQUIRED_COLUMNS if c not in panel.columns]
    if missing:
        return [GateResult("schema", False, f"missing columns {missing}")]
    results: list[GateResult] = []

    def add(name: str, passed: bool, detail: str) -> None:
        results.append(GateResult(name, bool(passed), detail))

    extract = panel[panel["in_confirmatory"].astype(bool)]

    duplicated = int(panel.duplicated(KEY).sum())
    add("unique_key", duplicated == 0, f"{duplicated} duplicated (eurostat_code, year) rows")

    for column in ("capb", "olddep1_lag"):
        share = _coverage(panel, column)
        add(f"coverage_{column}", share >= cfg.coverage_min, f"{100 * share:.2f}% of {len(panel)} window cells (threshold {100 * cfg.coverage_min:.0f}%)")

    per_country = extract.groupby("eurostat_code").size().reindex(sorted(panel["eurostat_code"].unique()), fill_value=0)
    short = per_country[per_country < cfg.min_obs_per_country]
    add("country_min_obs", short.empty, "all countries >= %d observations" % cfg.min_obs_per_country if short.empty else f"below {cfg.min_obs_per_country}: {short.to_dict()}")

    capb = panel["capb"].dropna()
    outside = capb[~((capb > cfg.capb_lower_exclusive) & (capb < cfg.capb_upper_exclusive))]
    add("capb_range", outside.empty, f"capb inside ({cfg.capb_lower_exclusive:g}, {cfg.capb_upper_exclusive:g}); {len(outside)} values outside" + (f", e.g. {outside.iloc[0]:.2f}" if len(outside) else ""))

    bad_w = {}
    for column in EXPOSURE_COLUMNS:
        values = panel[column].dropna()
        count = int(((values < cfg.w_lower) | (values > cfg.w_upper)).sum())
        if count:
            bad_w[column] = count
    null_w = {c: int(extract[c].isna().sum()) for c in EXPOSURE_COLUMNS if extract[c].isna().any()}
    add("exposure_range", not bad_w and not null_w, f"outside [{cfg.w_lower:g}, {cfg.w_upper:g}]: {bad_w or 'none'}; missing on the extract: {null_w or 'none'}")

    years = panel["year"]
    late = int((years > cfg.year_max).sum())
    early = int((years < cfg.year_min).sum())
    add("year_window", late == 0 and early == 0, f"{late} rows after {cfg.year_max}, {early} rows before {cfg.year_min}")
    forecast = int((years > last_observed_year).sum())
    add("no_forecast_year", forecast == 0, f"{forecast} rows after the last observed AMECO year {last_observed_year}")

    incomplete = int((~extract["exposure_complete_cv"].astype(bool)).sum())
    add("exposure_complete_on_extract", incomplete == 0, f"{incomplete} extract rows without complete exposure")

    n_rows, n_countries = len(extract), int(extract["eurostat_code"].nunique())
    add("extract_row_count", n_rows == cfg.confirmatory_rows, f"{n_rows} rows (contract {cfg.confirmatory_rows})")
    add("extract_country_count", n_countries == cfg.confirmatory_countries, f"{n_countries} countries (contract {cfg.confirmatory_countries})")

    incomplete_cases = int((extract["capb"].isna() | extract["olddep1_lag"].isna()).sum())
    add("extract_complete_cases", incomplete_cases == 0, f"{incomplete_cases} extract rows miss capb or olddep1_lag")

    merged = extract[KEY + ["capb"]].merge(
        source_capb[KEY + ["capb"]].rename(columns={"capb": "capb_source"}), on=KEY, how="left", validate="many_to_one"
    )
    neg_extract = int((merged["capb"] < 0).sum())
    neg_source = int((merged["capb_source"] < 0).sum())
    differs = int((~np.isclose(merged["capb"], merged["capb_source"], rtol=0.0, atol=0.0, equal_nan=True)).sum())
    add(
        "negative_capb_preserved",
        neg_extract == neg_source and differs == 0,
        f"{neg_extract} negative values in the extract, {neg_source} in the source for the same keys; {differs} keys differ",
    )
    return results


def enforce_gates(
    panel: pd.DataFrame,
    source_capb: pd.DataFrame,
    last_observed_year: int,
    config: GateConfig | None = None,
) -> list[GateResult]:
    """Run :func:`run_gates` and raise :class:`GateFailure` when any gate fails; otherwise return the outcomes."""
    results = run_gates(panel, source_capb, last_observed_year, config)
    if not all(r.passed for r in results):
        raise GateFailure(results)
    return results


def format_results(results: list[GateResult]) -> str:
    """Plain-text table of gate outcomes."""
    return "\n".join(f"{'PASS' if r.passed else 'FAIL'}  {r.name:<30} {r.detail}" for r in results)


def main() -> int:
    """Build the gold panel in memory, run the gates, print them, and return the exit status (0 pass, 1 fail). Writes nothing."""
    sys.path.insert(0, str(PROJECT_ROOT / "src" / "features"))
    import panel as panel_module  # noqa: E402  (lazy: panel imports this module)

    build = panel_module.build_gold_panel()
    try:
        results = enforce_gates(build.panel, build.source_capb, build.last_observed_year)
    except GateFailure as failure:
        print(format_results(failure.results))
        print("GATE FAILURE: nothing written", file=sys.stderr)
        return 1
    print(format_results(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
