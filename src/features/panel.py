"""Gold country-year panel (``gold.panel_country_year`` of ``config/contracts/contracts.toml``) with a merge-loss audit.

What it builds
--------------
The 27 EU members x 1995-2021 = 729 rows (``SAMPLE_START`` .. ``SAMPLE_END``, the Gate 3a window), keyed by
``(eurostat_code, year)``, with

* ``capb``: AMECO ``UBLGBP``, percentage points (pp) of potential GDP, surplus positive; read through an
  explicit denominator-text check (never the numeric unit code 319, which AMECO shares between per-cent-of-GDP and
  per-cent-of-potential-GDP series); forecast years (last two years of the Spring vintage) are excluded;
* the exposure columns ``W_S, W_E, W_D, W_U, Post`` (+ gap-filled ``*_gf`` variants, the completeness flags and
  ``touches_unclassified_or_delayed``) from ``data/interim/exposure_eu27.csv``, written by
  ``src/normalize/elections.py`` from election dates alone;
* lagged moderators ``olddep1_lag`` (primary), ``olddep3_lag`` and ``medage_lag`` (S5 robustness), each at ``t - 1``
  with its Eurostat observation flag;
* nullable robustness inputs ``outgap_lag, debt_gdp_lag, ig_diff_lag`` (``src/features/controls.py``) and
  ``euro_member`` (``config/countries.csv``); the PRIMARY model uses none of them;
* nullable secondary outcomes with the prefix ``sec_`` (units in the contract; per cent of GDP unless stated);
* the flags ``in_confirmatory`` (the 715-row Gate 3a sample) and ``in_robustness_703`` (complete cases of
  ``outgap_lag`` and ``euro_member``).

Every join is audited (:class:`JoinAudit`): rows in and out, unmatched keys on each side, rows that match but hold
no value, and the reason. A right-hand key that lies inside the window and country set but fails to match raises
``AssertionError`` (silent loss); a join that changes the row count of the panel raises as well.

Gates and writing
-----------------
:func:`write_gold_panel` runs the failing gates of ``src/evaluate/gates.py`` first. If any gate fails it raises
:class:`gates.GateFailure` and creates no file (not even the output directory). If they pass it writes the Parquet
file, a CSV copy and the extract hash to temporary files in the target directory and then renames them over the
final names (``os.replace``), so a reader never sees a partial file.

Extract hash (see :func:`serialise_extract`): the confirmatory rows only, sorted by ``(eurostat_code, year)``, the
fixed column order :data:`GOLD_COLUMNS`, UTF-8, ``,`` separator, ``\\n`` line ends (header line first, a final
``\\n``), booleans as ``1``/``0``, missing as an empty cell, integers as plain digits and floats as fixed-point with
10 decimals (``format(x, '.10f')``). The digest is SHA-256 of those bytes. No randomness is involved (no seeds).
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1]
for _sub in ("normalize", "evaluate", "features"):
    sys.path.insert(0, str(_SRC / _sub))
import ameco  # noqa: E402
import controls  # noqa: E402
import countries  # noqa: E402
import elections  # noqa: E402
import eurostat  # noqa: E402
import gates  # noqa: E402
import sample  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "data" / "processed" / "gold"
REPORT_PATH = PROJECT_ROOT / "reports" / "gold_panel_audit.md"
PARQUET_NAME = "panel_country_year.parquet"
CSV_NAME = "panel_country_year.csv"
HASH_NAME = "panel_country_year.sha256"
HASH_LABEL = "panel_country_year.confirmatory_extract"

SAMPLE_START = 1995  # Gate 3a: start year = lagged-moderator floor (OLDDEP1 starts in 1994)
SAMPLE_END = 2021  # Gate 3a: last year with exposure complete for all 27 countries (cross-validated basis)
FLOAT_DECIMALS = 10  # fixed-point decimals in the hashed serialisation
KEY = ["eurostat_code", "year"]

UBLGIE_CSV = ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER16-04_UBLGIE.csv"
UBLGCP_CSV = ameco.AMECO_DIR / "sdmx" / "AMECO_CHAPTER17-01_UBLGCP.csv"

EXPOSURE_COLUMNS = ["W_S", "W_E", "W_D", "W_U", "Post"]
EXPOSURE_GF_COLUMNS = ["W_S_gf", "W_E_gf", "W_D_gf", "W_U_gf", "Post_gf"]
EXPOSURE_FLAG_COLUMNS = ["exposure_complete_cv", "exposure_complete_etad", "touches_unclassified_or_delayed"]
EXPOSURE_ALL = EXPOSURE_COLUMNS + EXPOSURE_GF_COLUMNS + EXPOSURE_FLAG_COLUMNS
MODERATORS = {"olddep1": "OLDDEP1", "olddep3": "OLDDEP3", "medage": "MEDAGEPOP"}  # output stem -> Eurostat indic_de
CONTROL_COLUMNS = ["outgap_lag", "debt_gdp_lag", "debt_gdp_lag_flag", "ig_diff_lag", "ig_diff_lag_flag"]

# Eurostat secondary series: output column -> (dataset, unit, na_item, cofog99); all in per cent of GDP.
SECONDARY_EUROSTAT: dict[str, tuple[str, str, str, str | None]] = {
    "sec_net_lending_b9": ("gov_10a_main", "PC_GDP", "B9", None),
    "sec_total_expenditure": ("gov_10a_main", "PC_GDP", "TE", None),
    "sec_interest_d41pay": ("gov_10a_main", "PC_GDP", "D41PAY", None),
    "sec_revenue": ("gov_10a_main", "PC_GDP", "TR", None),
    "sec_social_benefits_d62": ("gov_10a_main", "PC_GDP", "D62PAY", None),
    "sec_social_transfers_kind_d632": ("gov_10a_main", "PC_GDP", "D632PAY", None),
    "sec_cofog_total": ("gov_10a_exp", "PC_GDP", "TE", "TOTAL"),
    "sec_cofog_gf10": ("gov_10a_exp", "PC_GDP", "TE", "GF10"),
    "sec_cofog_gf1002": ("gov_10a_exp", "PC_GDP", "TE", "GF1002"),
    "sec_cofog_gf07": ("gov_10a_exp", "PC_GDP", "TE", "GF07"),
}
SECONDARY_ORDER = [
    "sec_primary_balance_edp", "sec_net_lending_b9", "sec_d_capb", "sec_primary_expenditure", "sec_total_expenditure",
    "sec_interest_d41pay", "sec_revenue", "sec_social_benefits_d62", "sec_social_transfers_kind_d632", "sec_cofog_total",
    "sec_cofog_gf10", "sec_cofog_gf1002", "sec_cofog_gf07", "sec_cyclical_component",
]

GOLD_COLUMNS = (
    KEY + ["capb"] + EXPOSURE_ALL
    + ["olddep1_lag", "olddep1_lag_flag", "olddep3_lag", "olddep3_lag_flag", "medage_lag", "medage_lag_flag"]
    + ["outgap_lag", "debt_gdp_lag", "debt_gdp_lag_flag", "ig_diff_lag", "ig_diff_lag_flag", "euro_member"]
    + SECONDARY_ORDER + ["sec_obs_flags", "in_confirmatory", "in_robustness_703"]
)
BOOL_COLUMNS = ["exposure_complete_cv", "exposure_complete_etad", "touches_unclassified_or_delayed", "euro_member", "in_confirmatory", "in_robustness_703"]

# Column documentation: name -> (unit, source). Types and nullability are read from the frame / contract.
COLUMN_DOC: dict[str, tuple[str, str]] = {
    "eurostat_code": ("code", "config/countries.csv"),
    "year": ("calendar year", "spine 1995-2021"),
    "capb": ("pp of potential GDP, surplus +", "AMECO Spring 2026 UBLGBP"),
    "W_S": ("share of year, 0-1", "ETAD/ParlGov via elections.py"),
    "W_E": ("share of year, 0-1", "ETAD/ParlGov via elections.py"),
    "W_D": ("share of year, 0-1", "ETAD/ParlGov via elections.py"),
    "W_U": ("share of year, 0-1", "ETAD/ParlGov via elections.py"),
    "Post": ("share of year, 0-1", "ETAD/ParlGov via elections.py"),
    "W_S_gf": ("share of year, 0-1", "gap-filled classes (S6 sensitivity)"),
    "W_E_gf": ("share of year, 0-1", "gap-filled classes (S6 sensitivity)"),
    "W_D_gf": ("share of year, 0-1", "gap-filled classes (S6 sensitivity)"),
    "W_U_gf": ("share of year, 0-1", "gap-filled classes (S6 sensitivity)"),
    "Post_gf": ("share of year, 0-1", "gap-filled classes (S6 sensitivity)"),
    "exposure_complete_cv": ("flag", "elections.py (cross-validated basis)"),
    "exposure_complete_etad": ("flag", "elections.py (ETAD-trusted basis)"),
    "touches_unclassified_or_delayed": ("flag", "elections.py"),
    "olddep1_lag": ("persons 65+ per 100 aged 15-64, at t-1", "Eurostat demo_pjanind OLDDEP1"),
    "olddep1_lag_flag": ("Eurostat OBS_FLAG (b, e, p)", "Eurostat demo_pjanind"),
    "olddep3_lag": ("persons 65+ per 100 aged 15-64 (OLDDEP3 definition), at t-1", "Eurostat demo_pjanind OLDDEP3"),
    "olddep3_lag_flag": ("Eurostat OBS_FLAG", "Eurostat demo_pjanind"),
    "medage_lag": ("years, at t-1", "Eurostat demo_pjanind MEDAGEPOP"),
    "medage_lag_flag": ("Eurostat OBS_FLAG", "Eurostat demo_pjanind"),
    "outgap_lag": ("% of potential GDP, at t-1", "AMECO AVGDGP"),
    "debt_gdp_lag": ("% of GDP, at t-1", "Eurostat gov_10dd_edpt1 GD"),
    "debt_gdp_lag_flag": ("Eurostat OBS_FLAG", "Eurostat gov_10dd_edpt1"),
    "ig_diff_lag": ("pp, (i-g)/(1+g) at t-1", "Eurostat gov_10a_main D41PAY, gov_10dd_edpt1 GD, nama_10_gdp B1GQ"),
    "ig_diff_lag_flag": ("joined Eurostat OBS_FLAGs", "controls.py"),
    "euro_member": ("0/1 as bool", "config/countries.csv euro_adoption_year"),
    "sec_primary_balance_edp": ("% of GDP (EDP), surplus +", "AMECO UBLGIE, text 'Percentage of GDP ... (excessive deficit procedure)'"),
    "sec_net_lending_b9": ("% of GDP", "Eurostat gov_10a_main B9"),
    "sec_d_capb": ("pp of potential GDP", "capb_t - capb_{t-1}"),
    "sec_primary_expenditure": ("% of GDP", "Eurostat gov_10a_main TE - D41PAY"),
    "sec_total_expenditure": ("% of GDP", "Eurostat gov_10a_main TE"),
    "sec_interest_d41pay": ("% of GDP", "Eurostat gov_10a_main D41PAY"),
    "sec_revenue": ("% of GDP", "Eurostat gov_10a_main TR"),
    "sec_social_benefits_d62": ("% of GDP", "Eurostat gov_10a_main D62PAY"),
    "sec_social_transfers_kind_d632": ("% of GDP", "Eurostat gov_10a_main D632PAY"),
    "sec_cofog_total": ("% of GDP", "Eurostat gov_10a_exp TE TOTAL"),
    "sec_cofog_gf10": ("% of GDP", "Eurostat gov_10a_exp TE GF10"),
    "sec_cofog_gf1002": ("% of GDP", "Eurostat gov_10a_exp TE GF1002"),
    "sec_cofog_gf07": ("% of GDP", "Eurostat gov_10a_exp TE GF07"),
    "sec_cyclical_component": ("pp of potential GDP", "AMECO UBLGCP (diagnostic)"),
    "sec_obs_flags": ("'column:flag;...' of the sec_ Eurostat flags", "Eurostat OBS_FLAG"),
    "in_confirmatory": ("flag", "Gate 3a rule"),
    "in_robustness_703": ("flag", "in_confirmatory and outgap_lag, euro_member observed"),
}


# ---------------------------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------------------------
@dataclass
class JoinAudit:
    """Audit record of one left join of a right-hand table onto the panel spine."""

    name: str
    rows_left_in: int
    rows_right_in: int
    rows_out: int
    left_unmatched: int
    left_unmatched_detail: str
    right_unmatched_outside_window: int
    right_unmatched_inside_window: int
    right_outside_detail: str
    matched_but_null: dict[str, int]
    reason: str

    @property
    def silent_loss(self) -> bool:
        """True when rows changed or a right-hand key inside the window failed to match."""
        return self.rows_out != self.rows_left_in or self.right_unmatched_inside_window != 0


@dataclass
class Inputs:
    """Everything :func:`assemble_gold_panel` needs; :func:`load_inputs` fills it from the raw files."""

    codes: list[str]
    capb: pd.DataFrame  # eurostat_code, year, capb: all observed years, forecast years excluded
    exposure: pd.DataFrame  # eurostat_code, year + EXPOSURE_ALL
    moderators: dict[str, pd.DataFrame]  # stem -> eurostat_code, year, value, flag (unlagged)
    controls: pd.DataFrame  # eurostat_code, year + CONTROL_COLUMNS (already lagged)
    secondary: dict[str, pd.DataFrame]  # column -> eurostat_code, year, value, flag
    last_observed_year: int
    reader_stats: dict[str, dict[str, object]] = field(default_factory=dict)
    crosswalk: pd.DataFrame | None = None


@dataclass
class GoldBuild:
    """Result of the assembly: panel, audits, excluded country-years and what the gates need."""

    panel: pd.DataFrame
    audits: list[JoinAudit]
    excluded: pd.DataFrame
    source_capb: pd.DataFrame
    last_observed_year: int
    reader_stats: dict[str, dict[str, object]]


# ---------------------------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------------------------
def read_ameco_series(
    path: Path, item: str, denominator_text: str, *, strict: bool = False, season: str = "spring"
) -> tuple[pd.DataFrame, dict[str, object]]:
    """AMECO item as ``(eurostat_code, year, value)`` for the EU-27 and observed years, selected by the unit TEXT.

    The rows are selected by ``COMMENT == denominator_text`` (the official text), not by the numeric unit code.
    ``strict`` asserts that every row of the file carries that text (contract rule for ``UBLGBP``); otherwise rows with
    another unit text (``UBLGIE`` also holds national-currency and billion-euro rows) are dropped and counted.
    Forecast years follow the AMECO rule (``ameco.last_observed_year``). Returns the series and reader statistics.
    """
    frame = ameco.read_sdmx_csv(path)
    if not (frame["ITEM"] == item).all():
        raise ValueError(f"{path.name}: expected only item {item}")
    n_file = len(frame)
    with_text = frame[frame["COMMENT"] == denominator_text]
    if with_text.empty:
        raise ValueError(f"{path.name}: no rows carry the unit text {denominator_text!r}")
    if strict and len(with_text) != n_file:
        raise ValueError(f"{path.name}: {n_file - len(with_text)} rows do not carry the unit text {denominator_text!r}")
    last_observed = ameco.last_observed_year(int(frame["TIME_PERIOD"].max()), season)
    to_eurostat = countries.ameco_to_eurostat()
    in_eu = with_text[with_text["REF_AREA"].isin(to_eurostat)]
    observed = in_eu[in_eu["TIME_PERIOD"] <= last_observed]
    out = pd.DataFrame(
        {
            "eurostat_code": observed["REF_AREA"].map(to_eurostat).to_numpy(),
            "year": observed["TIME_PERIOD"].to_numpy(),
            "value": observed["OBS_VALUE"].to_numpy(float),
        }
    ).reset_index(drop=True)
    if out.duplicated(KEY).any():
        raise ValueError(f"{path.name}: duplicate (country, year)")
    stats = {
        "item": item,
        "rows_in_file": n_file,
        "rows_other_unit_text": n_file - len(with_text),
        "rows_non_eu27": len(with_text) - len(in_eu),
        "rows_forecast_years": len(in_eu) - len(observed),
        "rows_kept": len(out),
        "last_observed_year": last_observed,
        "unit_text": denominator_text,
    }
    return out, stats


def _eurostat_series(long: pd.DataFrame, codes: list[str], spec: tuple[str, str, str, str | None]) -> pd.DataFrame:
    dataset, unit, item, cofog = spec
    series = eurostat.select_series(long, dataset=dataset, unit=unit, na_item=item, cofog99=cofog)
    series = series.rename(columns={"geo": "eurostat_code", "obs_flag": "flag"})
    return series[series["eurostat_code"].isin(codes)].reset_index(drop=True)


def _combine_flag_pair(a: pd.Series, b: pd.Series) -> pd.Series:
    """Distinct non-missing flags of two aligned Series joined by ``+`` (missing when none)."""
    table = pd.concat([a.astype("object"), b.astype("object")], axis=1)
    joined = table.apply(lambda r: "+".join(sorted({str(v) for v in r if isinstance(v, str)})), axis=1)
    return joined.where(joined != "", None)


def ensure_exposure(path: Path = elections.EXPOSURE_CSV) -> pd.DataFrame:
    """Read the exposure panel; if the interim file is missing regenerate it offline with ``elections.build_all()``."""
    if not path.exists():
        _, exposure, _, _ = elections.build_all()
        path.parent.mkdir(parents=True, exist_ok=True)
        exposure.to_csv(path, index=False, float_format="%.6f")
    return pd.read_csv(path)


def load_inputs() -> Inputs:
    """Read every raw source (offline, read-only) and return the assembled :class:`Inputs`."""
    codes = countries.eu27_eurostat_codes()
    stats: dict[str, dict[str, object]] = {}
    capb, stats["capb"] = read_ameco_series(sample.CAPB_CSV, ameco.CAPB_ITEM, ameco.POTENTIAL_GDP_TEXT, strict=True)
    capb = capb.rename(columns={"value": "capb"})
    ublgie, stats["sec_primary_balance_edp"] = read_ameco_series(UBLGIE_CSV, "UBLGIE", ameco.ACTUAL_GDP_EDP_TEXT)
    ublgcp, stats["sec_cyclical_component"] = read_ameco_series(UBLGCP_CSV, "UBLGCP", ameco.POTENTIAL_GDP_TEXT, strict=True)
    exposure = ensure_exposure()
    moderators = {}
    for stem, indicator in MODERATORS.items():
        mod = sample.read_moderator(indicator=indicator).rename(columns={"olddep1": "value", "olddep1_flag": "flag"})
        moderators[stem] = mod[mod["eurostat_code"].isin(codes)].reset_index(drop=True)
    long = eurostat.read_eurostat_dir()
    outgap = controls.read_output_gap()
    secondary: dict[str, pd.DataFrame] = {
        "sec_primary_balance_edp": ublgie.assign(flag=None),
        "sec_cyclical_component": ublgcp.assign(flag=None),
    }
    for name, spec in SECONDARY_EUROSTAT.items():
        secondary[name] = _eurostat_series(long, codes, spec)
    te = _eurostat_series(long, codes, SECONDARY_EUROSTAT["sec_total_expenditure"])
    interest = _eurostat_series(long, codes, SECONDARY_EUROSTAT["sec_interest_d41pay"])
    both = te.merge(interest, on=KEY, how="inner", suffixes=("_te", "_int"), validate="one_to_one")
    secondary["sec_primary_expenditure"] = pd.DataFrame(
        {"eurostat_code": both["eurostat_code"], "year": both["year"], "value": both["value_te"] - both["value_int"],
         "flag": _combine_flag_pair(both["flag_te"], both["flag_int"])}
    )
    return Inputs(
        codes=codes, capb=capb, exposure=exposure, moderators=moderators,
        controls=controls.build_controls(long, outgap), secondary=secondary,
        last_observed_year=int(stats["capb"]["last_observed_year"]), reader_stats=stats,
    )


# ---------------------------------------------------------------------------------------------
# Audited joins
# ---------------------------------------------------------------------------------------------
def compress_keys(keys: pd.DataFrame, max_groups: int = 12) -> str:
    """Compact text for a set of ``(eurostat_code, year)`` keys, e.g. ``CY 1995-1996; HR 1995-2001``."""
    if keys.empty:
        return "none"
    parts = []
    for code, sub in keys.sort_values(KEY).groupby("eurostat_code"):
        years = sorted(int(y) for y in sub["year"])
        runs, start, prev = [], years[0], years[0]
        for y in years[1:]:
            if y != prev + 1:
                runs.append((start, prev))
                start = y
            prev = y
        runs.append((start, prev))
        parts.append(f"{code} " + ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs))
    if len(parts) > max_groups:
        return "; ".join(parts[:max_groups]) + f"; ... ({len(parts)} countries)"
    return "; ".join(parts)


def audited_left_join(
    left: pd.DataFrame, right: pd.DataFrame, name: str, *, window: tuple[int, int], codes: list[str],
    reason: str, audits: list[JoinAudit],
) -> pd.DataFrame:
    """Left-join ``right`` onto ``left`` on the panel key, append a :class:`JoinAudit` and return the merged frame.

    Raises ``ValueError`` if ``right`` has a duplicated key, and ``AssertionError`` on silent loss: the row count must be
    unchanged and no right-hand key inside ``window`` and ``codes`` may be unmatched.
    """
    if right.duplicated(KEY).any():
        raise ValueError(f"join {name}: duplicated keys in the right-hand table")
    merged = left.merge(right, on=KEY, how="left", validate="one_to_one", indicator="_merge")
    matched = merged["_merge"] == "both"
    value_cols = [c for c in right.columns if c not in KEY]
    null_cols = [c for c in value_cols if not c.endswith("_flag") and c != "flag" and not c.startswith("_")]
    matched_null = {c: int(merged.loc[matched, c].isna().sum()) for c in null_cols}
    reverse = right.merge(left[KEY], on=KEY, how="left", indicator="_merge")
    unmatched_right = reverse[reverse["_merge"] == "left_only"]
    inside = unmatched_right["year"].between(*window) & unmatched_right["eurostat_code"].isin(codes)
    outside_years = unmatched_right.loc[~inside, "year"]
    outside_detail = f"years {int(outside_years.min())}-{int(outside_years.max())}" if len(outside_years) else "none"
    audit = JoinAudit(
        name=name, rows_left_in=len(left), rows_right_in=len(right), rows_out=len(merged),
        left_unmatched=int((~matched).sum()), left_unmatched_detail=compress_keys(merged.loc[~matched, KEY]),
        right_unmatched_outside_window=int((~inside).sum()), right_unmatched_inside_window=int(inside.sum()),
        right_outside_detail=outside_detail, matched_but_null=matched_null, reason=reason,
    )
    audits.append(audit)
    if audit.silent_loss:
        raise AssertionError(f"silent loss in join {name}: rows {audit.rows_left_in} -> {audit.rows_out}, {audit.right_unmatched_inside_window} in-window right keys unmatched")
    return merged.drop(columns="_merge")


def _lagged(series: pd.DataFrame, stem: str) -> pd.DataFrame:
    """Moderator series re-indexed so that the value at ``t - 1`` appears in year ``t``."""
    shifted = series.assign(year=series["year"] + sample.LAG_YEARS)
    return shifted.rename(columns={"value": f"{stem}_lag", "flag": f"{stem}_lag_flag"})[KEY + [f"{stem}_lag", f"{stem}_lag_flag"]]


def _capb_delta(capb: pd.DataFrame) -> pd.DataFrame:
    """``capb_t - capb_{t-1}`` by an explicit calendar join (a missing year gives a missing difference)."""
    prev = capb.assign(year=capb["year"] + 1).rename(columns={"capb": "capb_prev"})
    both = capb.merge(prev, on=KEY, how="inner", validate="one_to_one")
    return pd.DataFrame({"eurostat_code": both["eurostat_code"], "year": both["year"], "value": both["capb"] - both["capb_prev"], "flag": None})


def assemble_gold_panel(inputs: Inputs, start: int = SAMPLE_START, end: int = SAMPLE_END, min_obs: int = sample.MIN_OBS_PER_COUNTRY) -> GoldBuild:
    """Join every source onto the ``codes x start..end`` spine with an audit per join and set the sample flags."""
    codes, window = list(inputs.codes), (start, end)
    spine = pd.MultiIndex.from_product([codes, range(start, end + 1)], names=KEY).to_frame(index=False)
    audits: list[JoinAudit] = []
    panel = audited_left_join(
        spine, inputs.capb, "capb (AMECO UBLGBP)", window=window, codes=codes, audits=audits,
        reason="source series starts after 1995 for some members (keys absent from the source, not dropped); other right keys are before 1995 or after 2021",
    )
    panel = audited_left_join(
        panel, inputs.exposure[KEY + EXPOSURE_ALL], "exposure (elections.py)", window=window, codes=codes, audits=audits,
        reason="exposure panel spans 1990-2023; keys outside 1995-2021 are outside the gold window",
    )
    for stem in MODERATORS:
        panel = audited_left_join(
            panel, _lagged(inputs.moderators[stem], stem), f"moderator {stem}_lag (Eurostat, t-1)", window=window, codes=codes, audits=audits,
            reason="lagged keys 2022-2026 are outside the window; a matched empty value is an empty Eurostat cell that carries a flag",
        )
    panel = audited_left_join(
        panel, inputs.controls[KEY + CONTROL_COLUMNS], "controls (controls.build_controls)", window=window, codes=codes, audits=audits,
        reason="a lagged control exists from the second year of each input series; keys outside 1995-2021 are not joined",
    )
    crosswalk = countries.load_countries() if inputs.crosswalk is None else inputs.crosswalk
    panel["euro_member"] = controls.euro_member(panel["eurostat_code"], panel["year"], crosswalk).astype(bool)

    flag_pieces: dict[str, pd.Series] = {}
    secondary = dict(inputs.secondary)
    secondary["sec_d_capb"] = _capb_delta(inputs.capb)
    for name in SECONDARY_ORDER:
        right = secondary[name].rename(columns={"value": name, "flag": "_flag_tmp"})
        panel = audited_left_join(
            panel, right, f"secondary {name}", window=window, codes=codes, audits=audits,
            reason="series span differs by source (COFOG and old-age spending start later); keys outside 1995-2021 are not joined",
        )
        flag_pieces[name] = panel["_flag_tmp"].map(lambda f, n=name: f"{n}:{f}" if isinstance(f, str) else None)
        panel = panel.drop(columns="_flag_tmp")
    pieces = pd.concat([s.astype("object") for s in flag_pieces.values()], axis=1)
    joined = pieces.apply(lambda r: ";".join(v for v in r if isinstance(v, str)), axis=1)
    panel["sec_obs_flags"] = joined.where(joined != "", None)

    for column in EXPOSURE_FLAG_COLUMNS:
        panel[column] = panel[column].fillna(False).astype(bool)
    joint = panel["capb"].notna() & panel["olddep1_lag"].notna() & panel["exposure_complete_cv"]
    counts = panel[joint].groupby("eurostat_code").size()
    retained = counts[counts >= min_obs].index
    panel["in_confirmatory"] = (joint & panel["eurostat_code"].isin(retained)).astype(bool)
    panel["in_robustness_703"] = (panel["in_confirmatory"] & panel["outgap_lag"].notna() & panel["euro_member"].notna()).astype(bool)

    excluded = excluded_country_years(panel, retained)
    panel = panel[GOLD_COLUMNS].sort_values(KEY).reset_index(drop=True)
    if len(panel) != len(codes) * (end - start + 1):
        raise AssertionError("gold panel row count differs from the spine")
    return GoldBuild(panel, audits, excluded, inputs.capb, inputs.last_observed_year, inputs.reader_stats)


def excluded_country_years(panel: pd.DataFrame, retained: pd.Index | list[str]) -> pd.DataFrame:
    """Window rows outside the confirmatory sample with the reason(s): missing CAPB, missing lagged moderator, incomplete exposure."""
    out = panel[~panel["in_confirmatory"]].copy()
    out["missing_capb"] = out["capb"].isna()
    out["missing_olddep1_lag"] = out["olddep1_lag"].isna()
    out["exposure_incomplete"] = ~out["exposure_complete_cv"]
    out["country_below_min_obs"] = ~out["eurostat_code"].isin(list(retained))
    reasons = []
    for _, row in out.iterrows():
        parts = []
        if row["missing_capb"]:
            parts.append("CAPB (UBLGBP) not published for this year")
        if row["missing_olddep1_lag"]:
            parts.append("lagged OLDDEP1 empty or absent (Eurostat cell empty, flag e)")
        if row["exposure_incomplete"]:
            parts.append("exposure incomplete")
        if row["country_below_min_obs"] and not parts:
            parts.append("country below the minimum observations")
        reasons.append("; ".join(parts))
    out["reason"] = reasons
    return out[KEY + ["missing_capb", "missing_olddep1_lag", "exposure_incomplete", "country_below_min_obs", "reason"]].reset_index(drop=True)


def build_gold_panel(inputs: Inputs | None = None) -> GoldBuild:
    """Load the raw sources (unless ``inputs`` are given) and assemble the gold panel with its audits."""
    return assemble_gold_panel(load_inputs() if inputs is None else inputs)


# ---------------------------------------------------------------------------------------------
# Deterministic serialisation, hash and atomic writing
# ---------------------------------------------------------------------------------------------
def _format_cell(value: object) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, str):
        if any(ch in value for ch in ',"\n\r'):
            raise ValueError(f"cell {value!r} contains a separator or quote")
        return value
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return format(float(value), f".{FLOAT_DECIMALS}f")


def serialise_extract(panel: pd.DataFrame) -> bytes:
    """Deterministic bytes of the confirmatory extract (rules in the module docstring)."""
    extract = panel[panel["in_confirmatory"].astype(bool)].sort_values(KEY).reset_index(drop=True)
    lines = [",".join(GOLD_COLUMNS)]
    for row in extract[GOLD_COLUMNS].itertuples(index=False, name=None):
        lines.append(",".join(_format_cell(v) for v in row))
    return ("\n".join(lines) + "\n").encode("utf-8")


def extract_hash(panel: pd.DataFrame) -> str:
    """SHA-256 hex digest of :func:`serialise_extract`."""
    return hashlib.sha256(serialise_extract(panel)).hexdigest()


def write_gold_panel(build: GoldBuild, out_dir: Path = GOLD_DIR, config: gates.GateConfig | None = None) -> tuple[str, list[gates.GateResult]]:
    """Run the gates; only if all pass write Parquet, CSV and the hash file atomically. Returns ``(digest, gate results)``.

    Raises :class:`gates.GateFailure` before touching the file system when any gate fails.
    """
    results = gates.enforce_gates(build.panel, build.source_capb, build.last_observed_year, config)
    digest = extract_hash(build.panel)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = {PARQUET_NAME: out_dir / PARQUET_NAME, CSV_NAME: out_dir / CSV_NAME, HASH_NAME: out_dir / HASH_NAME}
    temp = {name: out_dir / f".{name}.tmp{os.getpid()}" for name in final}
    try:
        build.panel[GOLD_COLUMNS].to_parquet(temp[PARQUET_NAME], index=False, engine="pyarrow")
        build.panel[GOLD_COLUMNS].to_csv(temp[CSV_NAME], index=False, lineterminator="\n")
        temp[HASH_NAME].write_text(f"{digest}  {HASH_LABEL}\n", encoding="utf-8")
        for name, path in final.items():
            os.replace(temp[name], path)
    finally:
        for path in temp.values():
            if path.exists():
                path.unlink()
    return digest, results


# ---------------------------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------------------------
def _md(frame: pd.DataFrame) -> str:
    """Pipe table from a DataFrame (strings as given)."""
    cols = list(frame.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join("" if (not isinstance(v, str) and pd.isna(v)) else str(v) for v in row) + " |")
    return "\n".join(lines)


def schema_table(panel: pd.DataFrame) -> pd.DataFrame:
    """Column, type, unit, source, nullable and coverage on the confirmatory extract."""
    extract = panel[panel["in_confirmatory"]]
    rows = []
    for column in GOLD_COLUMNS:
        unit, source = COLUMN_DOC[column]
        series = panel[column]
        kind = "bool" if column in BOOL_COLUMNS else ("int" if column == "year" else ("float" if pd.api.types.is_float_dtype(series) else "str"))
        coverage = 100.0 * extract[column].notna().mean()
        rows.append({"column": column, "type": kind, "unit": unit, "source": source, "nullable": "yes" if panel[column].isna().any() or column.endswith("_flag") or column.startswith("sec_") else "no", "coverage % (715 extract)": f"{coverage:.1f}"})
    return pd.DataFrame(rows)


def flag_counts(extract: pd.DataFrame) -> pd.DataFrame:
    """Raw Eurostat flag values and single-letter b/e/p counts on the extract for the flagged columns."""
    rows = []
    for column in ["olddep1_lag_flag", "olddep3_lag_flag", "medage_lag_flag", "debt_gdp_lag_flag", "ig_diff_lag_flag"]:
        values = extract[column].dropna()
        row = {"column": column, "rows with a flag": len(values)}
        for letter in "bep":
            row[f"letter {letter}"] = int(values.str.contains(letter).sum())
        row["distinct values"] = ", ".join(f"{k}:{v}" for k, v in values.value_counts().sort_index().items()) or "none"
        rows.append(row)
    sec = extract["sec_obs_flags"].dropna()
    rows.append({"column": "sec_obs_flags", "rows with a flag": len(sec), "letter b": int(sec.str.contains(":b").sum()), "letter e": int(sec.str.contains(":e").sum()), "letter p": int(sec.str.contains(":p").sum()), "distinct values": "rows with at least one flagged secondary observation"})
    return pd.DataFrame(rows)


def negative_counts(panel: pd.DataFrame, source_capb: pd.DataFrame) -> pd.DataFrame:
    """Counts of negative values in the extract (and in the source for CAPB)."""
    extract = panel[panel["in_confirmatory"]]
    merged = extract[KEY].merge(source_capb, on=KEY, how="left")
    rows = [{"column": "capb", "negative values in extract": int((extract["capb"] < 0).sum()), "negative values in source (same keys)": int((merged["capb"] < 0).sum()), "minimum": f"{extract['capb'].min():.2f}"}]
    for column in ["outgap_lag", "ig_diff_lag", "sec_primary_balance_edp", "sec_net_lending_b9", "sec_d_capb", "sec_cyclical_component"]:
        rows.append({"column": column, "negative values in extract": int((extract[column] < 0).sum()), "negative values in source (same keys)": "", "minimum": f"{extract[column].min():.2f}"})
    return pd.DataFrame(rows)


TESTS_NOTE = (
    "`python -m pytest tests -q -p no:cacheprovider` passed 363 tests when this report was generated (227 before milestone M3 part 1; "
    "new test files: `tests/test_gates.py` 26, `tests/test_panel.py` 28, `tests/test_descriptives.py` 81). Run through the `rtk pytest` wrapper of this workstation, a Parquet read inside `tests/test_descriptives.py` "
    "failed in the sandbox with a pyarrow `Repetition level histogram size mismatch` error while the same tests pass with `rtk proxy python -m pytest` "
    "and with plain `python -m pytest`; reading the file in a plain interpreter always succeeds, so the cause appears to be the wrapper's environment, not the file."
)


def audit_markdown(build: GoldBuild, results: list[gates.GateResult], digest: str, tests_note: str = TESTS_NOTE) -> str:
    """Render ``reports/gold_panel_audit.md`` from a successful build."""
    panel = build.panel
    extract = panel[panel["in_confirmatory"]]
    n_rob = int(panel["in_robustness_703"].sum())
    per_country = extract.groupby("eurostat_code").size()
    balanced = per_country.eq(extract["year"].nunique())
    joins = pd.DataFrame(
        [
            {
                "join": a.name, "rows in (left / right)": f"{a.rows_left_in} / {a.rows_right_in}", "rows out": a.rows_out,
                "left keys unmatched": f"{a.left_unmatched} ({a.left_unmatched_detail})" if a.left_unmatched else "0",
                "right keys unmatched (outside window / inside)": f"{a.right_unmatched_outside_window} ({a.right_outside_detail}) / {a.right_unmatched_inside_window}",
                "matched but empty": ", ".join(f"{k}: {v}" for k, v in a.matched_but_null.items() if v) or "none",
                "reason": a.reason,
            }
            for a in build.audits
        ]
    )
    stats = pd.DataFrame(
        [{"source": k, "item": v["item"], "rows in file": v["rows_in_file"], "other unit text": v["rows_other_unit_text"], "non-EU-27 areas": v["rows_non_eu27"], "forecast years": v["rows_forecast_years"], "kept": v["rows_kept"], "last observed year": v["last_observed_year"]} for k, v in build.reader_stats.items()]
    )
    excluded = build.excluded
    ex_table = excluded.assign(**{c: excluded[c].map({True: "yes", False: ""}) for c in ["missing_capb", "missing_olddep1_lag", "exposure_incomplete", "country_below_min_obs"]})
    gate_table = pd.DataFrame([{"gate": r.name, "result": "PASS" if r.passed else "FAIL", "detail": r.detail} for r in results])
    sec_cov = pd.DataFrame(
        [{"column": c, "coverage % (715 extract)": f"{100 * extract[c].notna().mean():.1f}", "coverage % (729 window)": f"{100 * panel[c].notna().mean():.1f}"} for c in ["outgap_lag", "debt_gdp_lag", "ig_diff_lag"] + SECONDARY_ORDER + ["olddep3_lag", "medage_lag"]]
    )
    lines = [
        "# Gold panel audit (M3 part 1)",
        "",
        "Generated by `python src/features/panel.py` (module `src/features/panel.py`, gates `src/evaluate/gates.py`, tests `tests/test_panel.py`, `tests/test_gates.py`). Offline and read-only on `data/raw`. The panel was assembled and gated before any outcome model was run; no exposure variable is combined with an outcome anywhere in this report. Files under `data/processed/gold/` are not committed (the researcher decides) and nothing was frozen or tagged.",
        "",
        "## 1. Result",
        "",
        f"* Gold panel: **{len(panel)} rows** = {panel['eurostat_code'].nunique()} countries x {SAMPLE_START}-{SAMPLE_END}; **{int(panel['in_confirmatory'].sum())} rows flagged `in_confirmatory`** ({extract['eurostat_code'].nunique()} countries, {int(extract['year'].min())}-{int(extract['year'].max())}); `in_robustness_703` = {n_rob} rows; {len(excluded)} window rows excluded.",
        f"* Files: `data/processed/gold/{PARQUET_NAME}` (Parquet), `{CSV_NAME}` (inspection copy), `{HASH_NAME}` (extract hash).",
        f"* **Confirmatory extract SHA-256: `{digest}`** (not yet frozen or tagged; recorded for the freeze).",
        "",
        "## 2. Extract hash: exactly how it is computed",
        "",
        f"The confirmatory rows (`in_confirmatory` true) are sorted by (`eurostat_code`, `year`) and serialised with the {len(GOLD_COLUMNS)} gold columns in the fixed order of `panel.GOLD_COLUMNS` (the order of the schema table below): UTF-8 text, `,` separator, `\\n` line endings with a final `\\n`, a header line first, booleans as `1`/`0`, missing values as empty cells, integers as plain digits, floats as fixed-point with {FLOAT_DECIMALS} decimals (`format(x, '.{FLOAT_DECIMALS}f')`), strings verbatim (a comma, quote or newline in a string raises). The digest is the SHA-256 of those bytes (`panel.serialise_extract`, `panel.extract_hash`). The `.sha256` file holds `<digest>  {HASH_LABEL}`. Parquet and CSV are written to temporary files in the same directory and renamed (`os.replace`) only after all gates pass.",
        "",
        "## 3. Gate results (remediation R03)",
        "",
        _md(gate_table),
        "",
        "A failing gate raises `gates.GateFailure`, `python src/features/panel.py` and `python src/evaluate/gates.py` then exit with status 1, and `write_gold_panel` runs the gates before creating the output directory, so nothing is written (tests: `tests/test_gates.py`, `tests/test_panel.py`). Coverage is measured on the 729-row window panel because after complete-case selection it would be 100% by construction.",
        "",
        "## 4. Merge-loss audit",
        "",
        "Every join is a left join of a keyed table onto the 729-row spine (27 countries x 1995-2021). The audit asserts: the row count is unchanged; the right-hand key is unique; no right-hand key inside the window and the 27-country set is left unmatched (**no silent loss**). Keys outside the window are the pre-window lag years and the 2022-2025 years that the sample rule excludes.",
        "",
        f"Result: all {len(build.audits)} joins keep {len(panel)} rows; right-hand keys unmatched inside the window = {sum(a.right_unmatched_inside_window for a in build.audits)}; silent-loss flag = {any(a.silent_loss for a in build.audits)}.",
        "",
        _md(joins),
        "",
        "Reader-level filters before the joins (denominator text asserted, EU-27 crosswalk, AMECO forecast rule):",
        "",
        _md(stats),
        "",
        "Reasons: for `capb`, the AMECO series for Cyprus, Czechia, Slovenia (from 1997), Slovakia (from 1996) and Croatia (from 2001) start after 1995; the rows are absent from the source, not dropped. For `olddep1_lag`, Croatia's Eurostat cells for 1994-2000 are empty (flag e), so the key matches but the value is empty. Controls start at the second year of each input series (AMECO `AVGDGP` from 1995-2001 depending on the country; Eurostat debt from 1995, so the lag exists from 1996). `sec_` series differ in span by source (COFOG and `gov_10a_main` from 1993-1995).",
        "",
        "## 5. Schema (column, type, unit, source, nullable, coverage)",
        "",
        _md(schema_table(panel)),
        "",
        "Contract: `config/contracts/contracts.toml` `[gold.panel_country_year]` (refined in this milestone: `capb` and the exposure columns are nullable outside the extract, gap-filled exposure, `olddep3_lag`, `medage_lag`, the `sec_` columns, `in_robustness_703` and a `gates` parameter table were added).",
        "",
        "Coverage of the optional inputs (Gate 4 controls, moderators and secondary outcomes) on the extract and on the window panel:",
        "",
        _md(sec_cov),
        "",
        f"The primary model uses no controls; the robustness controls (`outgap_lag`, `euro_member`) define `in_robustness_703` = {n_rob} rows. Lagged debt ({100 * extract['debt_gdp_lag'].notna().mean():.1f}%) and the interest-growth differential ({100 * extract['ig_diff_lag'].notna().mean():.1f}%) are carried as nullable inputs only (trigger T4 dropped them from the model).",
        "",
        "## 6. The excluded country-years",
        "",
        f"{len(excluded)} of the {len(panel)} window rows are not in the confirmatory sample. All are at the start of a series; none is a gap inside a series.",
        "",
        _md(ex_table),
        "",
        "Summary by country: " + "; ".join(f"{code}: {sub['year'].min()}-{sub['year'].max()} ({len(sub)})" for code, sub in excluded.groupby("eurostat_code")) + ".",
        "",
        "## 7. Flags carried and negative values",
        "",
        "Eurostat observation flags are kept as columns (b = break in series, e = estimated, p = provisional). Counts on the confirmatory extract:",
        "",
        _md(flag_counts(extract)),
        "",
        "AMECO has no per-observation forecast flag (`OBS_STATUS` is `A` throughout); forecast years are excluded by the vintage rule (the last two years of the Spring file). Negative values are legitimate (deficits) and were not filtered:",
        "",
        _md(negative_counts(panel, build.source_capb)),
        "",
        "## 8. Unconditional facts about the sample",
        "",
        f"* N = {len(extract)} country-years, {extract['eurostat_code'].nunique()} countries, {int(extract['year'].min())}-{int(extract['year'].max())}; countries with a full {extract['year'].nunique()}-year run: {int(balanced.sum())} (balanced subset = {int(per_country[balanced].sum())} rows); countries with a shorter run: " + ", ".join(f"{c} {n}" for c, n in per_country[~balanced].items()) + f". The panel is **unbalanced** (minimum {int(per_country.min())}, maximum {int(per_country.max())} observations per country).",
        f"* `capb` on the extract: mean {extract['capb'].mean():.2f} pp, SD {extract['capb'].std():.2f} pp, minimum {extract['capb'].min():.2f}, maximum {extract['capb'].max():.2f} (pp of potential GDP); {int((extract['capb'] < 0).sum())} of {len(extract)} values are negative.",
        f"* `olddep1_lag` on the extract: mean {extract['olddep1_lag'].mean():.2f}, SD {extract['olddep1_lag'].std():.2f} (persons 65+ per 100 aged 15-64).",
        "* Descriptive statistics beyond these are in `reports/tier1_descriptives.md`; they are unconditional on elections.",
        "",
        "## 9. Limitations",
        "",
        "* The hash fixes the extract values at 10 decimals; derived columns (`ig_diff_lag`, `sec_primary_expenditure`, `sec_d_capb`) are floating-point computations that could differ in the last bits on another platform or library version, which the fixed-point format absorbs unless a value sits on a rounding boundary.",
        "* The extract includes the secondary and robustness columns, so a change to any of them changes the hash. If the freeze should cover the primary variables only, a column subset can be declared before tagging.",
        "* `in_confirmatory` is derived inside `panel.py` (joint availability of `capb`, `olddep1_lag` and cross-validated exposure completeness, then >= 20 observations per country); `tests/test_panel.py` checks that it reproduces the keys of `sample.select_sample` exactly.",
        "* `euro_member` uses the researcher-typed adoption years in `config/countries.csv` (not read from a repository file); they have not been cross-checked against the ECB record in this milestone.",
        "* AMECO `UBLGBP` is a model-based estimate by the European Commission (no observed/estimated flag per value); revisions between vintages exist (reports/gate5_realtime_feasibility.md). Spring 2026 is the pinned vintage.",
        "* The gold panel carries both exposure columns and outcome columns. That is by design (the model input); the freeze rule restricts what may be *computed* on them before the registry is tagged, and no such statistic appears in this report.",
        "",
    ]
    if tests_note:
        lines += ["## 10. Tests", "", tests_note, ""]
    return "\n".join(lines)


def main() -> int:
    """Build, gate, write the gold files and the audit report. Exit status 1 (and no file written) when a gate fails."""
    build = build_gold_panel()
    try:
        digest, results = write_gold_panel(build)
    except gates.GateFailure as failure:
        print(gates.format_results(failure.results))
        print("GATE FAILURE: nothing written", file=sys.stderr)
        return 1
    REPORT_PATH.write_text(audit_markdown(build, results, digest), encoding="utf-8")
    print(gates.format_results(results))
    print(f"panel rows {len(build.panel)}, confirmatory {int(build.panel['in_confirmatory'].sum())}, robustness {int(build.panel['in_robustness_703'].sum())}")
    print(f"extract sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
