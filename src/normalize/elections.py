"""Gate 3a: EU-27 national election calendar and fractional election-exposure variables.

Design source: ``reports/proposal.md`` section 9.1 (exposure frozen before outcomes are touched) and
``reports/acquisition_manifest_2026-10-10.md`` section 6. This module reads ONLY the election
sources (ETAD v1.0.0, ParlGov 2024 stable) and ``config/countries.csv``. It must not import or read
any fiscal-outcome series; ``tests/test_elections.py`` checks that in a fresh interpreter.

Sources and the facts this code relies on (all read from the raw files or their codebooks):

* ETAD codebook (v1, 16 Jul 2025): ``etype2`` in {presidential, legislative}; ``etype3`` in
  {presidential, lower house, upper house}; ``timing1`` 1 = on schedule, 2 = put ahead or behind,
  3 = unknown; ``timing2`` -1 = early, 0 = on schedule, 1 = delayed; ``reason`` 0 = no change,
  1 = first election under a new constitution or state, 2 = invalid election, 3 = coup,
  4 = natural death of the leader, 5 = assassination, 6 = civil war, 7 = no confidence, 9 = other;
  ``dif_days`` = held minus scheduled (negative = early); ``termlength`` in years. ETAD records the
  first polling day (first round).
* ParlGov codebook (12 Aug 2024): election_date is recoded to the LAST date of the election for
  CZE and FRA (and elsewhere), which explains the 1-day and 7-day differences to ETAD; the
  ``election_type`` column separates ``parliament`` from ``ep`` (European Parliament) rows.

Conventions (all constants below are documented where they are defined):

* The exposure window is the 12 months before the election day, ``[d - 1 year, d)``, and the post
  window the 12 months from the election day, ``[d, d + 1 year)``, computed on calendar days.
* ``W_*`` is the share of calendar year ``t`` inside the UNION of the 12-month pre-windows of the
  elections of that class (so 0 <= W <= 1 as the proposal states); the plain per-election sum is kept
  in ``W_*_add`` columns and flagged when it exceeds 1 (``additive_exceeds_one``), which happens only
  when two same-class windows overlap (election bursts such as Bulgaria 2021).
* No seeds are needed: nothing here is stochastic.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import countries  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "elections_ageing"
ETAD_CSV = RAW_DIR / "etad" / "ETAD_v_1_0_0.csv"
PARLGOV_TAB = RAW_DIR / "parlgov_2024_stable" / "view_election.tab"
RAW_MANIFEST = RAW_DIR / "manifest.jsonl"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
CALENDAR_CSV = INTERIM_DIR / "election_calendar_eu27.csv"
EXPOSURE_CSV = INTERIM_DIR / "exposure_eu27.csv"
EXCLUSIONS_CSV = PROJECT_ROOT / "reports" / "gate3_election_exclusions.csv"

# ---------------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------------
ARTICLE_N_ELECTIONS = 3127  # ETAD codebook section 1.1: "3,127 legislative and presidential elections"
ARTICLE_N_COUNTRIES = 148  # same section (150 names, 148 countries, footnote 1)
CALENDAR_START = pd.Timestamp("1990-01-01")  # task scope: elections 1990-2023
CALENDAR_END = pd.Timestamp("2023-12-31")  # ETAD nominal end (codebook 1.1: "between 1945 and 2023")
PARLGOV_COVERAGE_END = pd.Timestamp("2023-06-30")  # manifest E03: "data to June 2023"; file maximum is 2023-06-25
SAMPLE_WINDOW_START = pd.Timestamp("1994-01-01")  # first election that can touch 1995 (post-window or pre-window)

EARLY_REASONS = (7, 9)  # proposal 9.1: reason 7 = no confidence, 9 = other
# Reconciling ETAD dates with ParlGov dates:
MATCH_TOLERANCE_DAYS = 92  # one quarter; reciprocal-nearest matching, so wide enough for the observed
#   month-keying slip (61 days) yet each ETAD election can match at most one ParlGov election
DATE_OVERRIDE_MIN_DAYS = 7  # a one-week difference is explained by multi-day polling; larger ones need a test
GAP_TOLERANCE_YEARS = 0.5  # half a year: wide enough for fixed-date and month-window election rules
GAP_TOLERANCE_SENSITIVITY = (0.25, 0.5, 1.0)
DAYS_PER_YEAR = 365.25
MIN_WEEKDAY_SHARE = 0.5  # a country's modal polling weekday must cover half its dates to arbitrate dates

CLASSES = ("scheduled", "early", "delayed", "unclassified")
KNOWN_CLASSES = ("scheduled", "early", "delayed")
REASON_TEXT = {
    0: "no change",
    1: "first election under new constitution or state",
    2: "re-election after invalid election",
    3: "coup",
    4: "natural death of the leader",
    5: "assassination of the leader",
    6: "civil war",
    7: "no confidence",
    9: "other",
}


# ---------------------------------------------------------------------------------------------
# Readers and audits
# ---------------------------------------------------------------------------------------------
def read_etad_raw(path: Path = ETAD_CSV) -> pd.DataFrame:
    """Read ETAD v1.0.0 unchanged (no rows dropped) with date columns parsed."""
    raw = pd.read_csv(path)
    raw["held_ts"] = pd.to_datetime(raw["held_date"])
    raw["sche_ts"] = pd.to_datetime(raw["sche_date"])
    return raw


def etad_audit(raw: pd.DataFrame) -> dict[str, object]:
    """Row count, coverage and schema anomalies of the raw ETAD file, compared with the codebook text."""
    keys = ["cowcode", "etype2", "held_date"]
    placeholder = raw["held_date"].isna() & raw["etype2"].eq("presidential") & raw["sche_date"].isna()
    dup_key = raw.dropna(subset=["held_date"]).duplicated(keys, keep="first")
    cutoff = pd.Timestamp("2023-12-31")
    return {
        "n_rows": int(len(raw)),
        "article_n_elections": ARTICLE_N_ELECTIONS,
        "n_countries_iso3": int(raw["iso3"].nunique()),
        "n_country_names": int(raw["country"].nunique()),
        "article_n_countries": ARTICLE_N_COUNTRIES,
        "held_year_min": int(raw["held_year"].min()),
        "held_year_max": int(raw["held_year"].max()),
        "held_date_max": str(raw["held_ts"].max().date()),
        "n_legislative": int(raw["etype2"].eq("legislative").sum()),
        "n_presidential": int(raw["etype2"].eq("presidential").sum()),
        "n_missing_held_date": int(raw["held_date"].isna().sum()),
        "n_missing_etype2": int(raw["etype2"].isna().sum()),
        "n_missing_etype3": int(raw["etype3"].isna().sum()),
        "n_all_empty_placeholder_rows": int(placeholder.sum()),
        "n_duplicate_election_keys": int(dup_key.sum()),
        "n_fully_identical_rows": int(raw.drop(columns=["held_ts", "sche_ts"]).duplicated().sum()),
        "rows_minus_placeholders_minus_dup_keys": int(len(raw) - placeholder.sum() - dup_key.sum()),
        "n_timing1_unknown": int(raw["timing1"].eq(3).sum()),
        "n_timing1_missing": int(raw["timing1"].isna().sum()),
        "n_timing2_missing": int(raw["timing2"].isna().sum()),
        "n_reason_missing": int(raw["reason"].isna().sum()),
        "n_sche_date_missing": int(raw["sche_date"].isna().sum()),
        "n_sche_date_after_2023": int((raw["sche_ts"] > cutoff).sum()),
        "n_iso3_with_two_country_names": int((raw.groupby("iso3")["country"].nunique() > 1).sum()),
        "n_elections_held_2023": int((raw["held_year"] == 2023).sum()),
        "mean_elections_per_year_2019_2022": float(raw[raw["held_year"].between(2019, 2022)].groupby("held_year").size().mean()),
    }


def raw_file_hashes_match_manifest() -> dict[str, bool]:
    """Compare SHA-256 of the election raw files with ``data/raw/elections_ageing/manifest.jsonl``."""
    import hashlib

    expected = {}
    for line in RAW_MANIFEST.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        expected[PROJECT_ROOT / record["dest"]] = record["sha256"]
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() == digest
        for path, digest in expected.items()
        if path.exists()
    }


def read_parlgov_elections(path: Path = PARLGOV_TAB) -> pd.DataFrame:
    """ParlGov ``view_election`` collapsed to one row per national lower-house (``parliament``) election.

    The raw view has one row per party and election; European Parliament rows (``ep``) are dropped.
    Adds ``prev_date`` from ``previous_parliament_election_id``.
    """
    view = pd.read_csv(path, sep="\t")
    view = view[view["election_type"] == "parliament"]
    elections = view.drop_duplicates("election_id")[
        ["country_name_short", "election_id", "election_date", "previous_parliament_election_id"]
    ].copy()
    elections = elections.rename(columns={"country_name_short": "iso3", "election_date": "pg_date"})
    elections["pg_date"] = pd.to_datetime(elections["pg_date"])
    dates = elections.set_index("election_id")["pg_date"]
    elections["prev_pg_date"] = elections["previous_parliament_election_id"].map(dates)
    return elections.reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Calendar assembly
# ---------------------------------------------------------------------------------------------
def etad_eu27_legislative(raw: pd.DataFrame, table: pd.DataFrame | None = None) -> pd.DataFrame:
    """ETAD national lower-house (or only-chamber) legislative elections of the EU-27, 1990-2023.

    ETAD v1.0.0 holds no upper-house rows (codebook 2.2.3). Rows with a missing ``held_date`` are dropped
    (none occur for EU-27 legislative rows).
    """
    table = countries.load_countries() if table is None else table
    to_eurostat = dict(zip(table["iso3"], table["eurostat_code"], strict=True))
    frame = raw[raw["iso3"].isin(to_eurostat) & raw["etype2"].eq("legislative")].copy()
    frame = frame[frame["held_ts"].between(CALENDAR_START, CALENDAR_END)]
    frame["eurostat_code"] = frame["iso3"].map(to_eurostat)
    return frame.reset_index().rename(columns={"index": "etad_row"})


def match_dates(etad: pd.DataFrame, parlgov: pd.DataFrame) -> pd.DataFrame:
    """One-to-one matching of ETAD and ParlGov elections by country and date.

    Greedy by increasing absolute day difference within ``MATCH_TOLERANCE_DAYS`` (equivalent to
    reciprocal-nearest-neighbour matching). Returns columns ``etad_row``, ``election_id``, ``diff_days``
    (ParlGov minus ETAD).
    """
    pairs: list[tuple[int, int, int]] = []
    for iso3, e_group in etad.groupby("iso3"):
        p_group = parlgov[parlgov["iso3"] == iso3]
        candidates = []
        for e_row, e_date in zip(e_group["etad_row"], e_group["held_ts"], strict=True):
            for p_id, p_date in zip(p_group["election_id"], p_group["pg_date"], strict=True):
                diff = int((p_date - e_date).days)
                if abs(diff) <= MATCH_TOLERANCE_DAYS:
                    candidates.append((abs(diff), diff, int(e_row), int(p_id)))
        used_e: set[int] = set()
        used_p: set[int] = set()
        for _, diff, e_row, p_id in sorted(candidates):
            if e_row not in used_e and p_id not in used_p:
                used_e.add(e_row)
                used_p.add(p_id)
                pairs.append((e_row, p_id, diff))
    return pd.DataFrame(pairs, columns=["etad_row", "election_id", "diff_days"])


def classify_etad(timing1: float, timing2: float, reason: float, dif_days: float) -> tuple[str, str]:
    """Primary classification of one election from ETAD fields; returns ``(class, rule)``.

    Rules, applied in order (proposal 9.1; ETAD codebook 2.4):

    1. ``timing1`` missing or 3 (unknown) -> unclassified; ``timing2`` missing -> unclassified.
    2. ``timing2`` = 1 (delayed) with ``dif_days`` < 0 (held before the scheduled date) or with
       ``reason`` in {7, 9} -> unclassified (internal contradiction); otherwise delayed.
    3. ``timing2`` = -1 with ``dif_days`` > 0 -> unclassified (contradiction); otherwise early.
    4. ``timing2`` = 0: ``reason`` in {7, 9} -> early (proposal rule, flagged as an override);
       ``timing1`` = 2 -> unclassified; otherwise scheduled.
    """
    if pd.isna(timing1) or timing1 == 3:
        return "unclassified", "timing1_unknown"
    if pd.isna(timing2):
        return "unclassified", "timing2_missing"
    in_early_reasons = (not pd.isna(reason)) and int(reason) in EARLY_REASONS
    if timing2 == 1:
        if not pd.isna(dif_days) and dif_days < 0:
            return "unclassified", "delayed_vs_dif_days_sign"
        if in_early_reasons:
            return "unclassified", "delayed_vs_early_reason"
        return "delayed", "timing2_delayed"
    if timing2 == -1:
        if not pd.isna(dif_days) and dif_days > 0:
            return "unclassified", "early_vs_dif_days_sign"
        return "early", "timing2_early"
    if in_early_reasons:
        return "early", "reason_overrides_timing2_on_time"
    if timing1 == 2:
        return "unclassified", "timing1_moved_but_timing2_on_time"
    return "scheduled", "timing2_on_time"


def classify_gap(gap_years: float, term_years: float, tolerance: float = GAP_TOLERANCE_YEARS) -> str:
    """Second classification: ParlGov inter-election gap against the constitutional term length.

    early if gap < term - tolerance; delayed if gap > term + tolerance; else scheduled;
    ``unavailable`` when either input is missing.
    """
    if pd.isna(gap_years) or pd.isna(term_years):
        return "unavailable"
    if gap_years < term_years - tolerance:
        return "early"
    if gap_years > term_years + tolerance:
        return "delayed"
    return "scheduled"


def modal_weekday_by_country(dates: pd.DataFrame) -> pd.DataFrame:
    """Modal polling weekday and its share, per ISO3, from a frame with ``iso3`` and ``date`` columns."""
    work = dates.assign(weekday=dates["date"].dt.dayofweek)
    rows = []
    for iso3, group in work.groupby("iso3"):
        counts = group["weekday"].value_counts()
        rows.append((iso3, int(counts.index[0]), float(counts.iloc[0] / len(group))))
    return pd.DataFrame(rows, columns=["iso3", "modal_weekday", "modal_share"])


def build_calendar(raw: pd.DataFrame | None = None, parlgov: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assemble the reconciled EU-27 election calendar with both classifications.

    Returned columns (one row per election): identifiers, both source dates, ``date_used`` and the rule
    that chose it, ETAD fields, ``class_primary``/``class_rule``, the gap-based ``class_gap``,
    ``class_gapfill`` (primary, with unclassified elections filled from the gap class when available),
    and coverage flags. ParlGov elections that are excluded from the calendar are returned with
    ``in_calendar`` = False and an ``exclusion_note``.
    """
    raw = read_etad_raw() if raw is None else raw
    parlgov = read_parlgov_elections() if parlgov is None else parlgov
    table = countries.load_countries()
    to_eurostat = dict(zip(table["iso3"], table["eurostat_code"], strict=True))
    parlgov = parlgov[parlgov["iso3"].isin(to_eurostat)].copy()
    parlgov = parlgov[parlgov["pg_date"].between(CALENDAR_START, CALENDAR_END)]
    etad = etad_eu27_legislative(raw, table)
    matches = match_dates(etad, parlgov)

    merged = etad.merge(matches, on="etad_row", how="left")
    merged = merged.merge(
        parlgov[["election_id", "pg_date", "previous_parliament_election_id", "prev_pg_date"]], on="election_id", how="left"
    )
    pg_only = parlgov[~parlgov["election_id"].isin(matches["election_id"])].copy()
    pg_only["eurostat_code"] = pg_only["iso3"].map(to_eurostat)

    # ParlGov-only inclusion rule: keep when the country has no ETAD coverage at all, or the election is not
    # earlier than the country's first ETAD election (so successor-state federal sub-unit rows before
    # independence are excluded, but late-ETAD gaps such as GRC 2023 are kept).
    first_etad = etad.groupby("iso3")["held_ts"].min()
    pg_only["first_etad"] = pg_only["iso3"].map(first_etad)
    pg_only["in_calendar"] = pg_only["first_etad"].isna() | (pg_only["pg_date"] >= pg_only["first_etad"])
    pg_only["exclusion_note"] = np.where(
        pg_only["in_calendar"], "", "ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row)"
    )
    pg_only["source"] = "parlgov_only"

    merged["source"] = np.where(merged["election_id"].notna(), "both", "etad_only")
    merged["in_calendar"] = True
    merged["exclusion_note"] = ""
    merged = merged.rename(columns={"held_ts": "etad_date", "pg_date": "parlgov_date"})
    pg_only = pg_only.rename(columns={"pg_date": "parlgov_date"})
    pg_only["etad_date"] = pd.NaT
    calendar = pd.concat([merged, pg_only.drop(columns=["first_etad"])], ignore_index=True)

    # ParlGov coverage of each country, used to separate "ETAD-only because ParlGov lacks the country span"
    # from genuine disagreements.
    pg_first_any = read_parlgov_elections().groupby("iso3")["pg_date"].min()
    calendar["parlgov_country_start"] = calendar["iso3"].map(pg_first_any)
    reference_date = calendar["etad_date"].fillna(calendar["parlgov_date"])
    calendar["etad_only_in_parlgov_range"] = (
        calendar["source"].eq("etad_only")
        & (reference_date >= calendar["parlgov_country_start"])
        & (reference_date <= PARLGOV_COVERAGE_END)
    )

    # Date used: ETAD is primary; ParlGov overrides only when the dates differ by more than
    # DATE_OVERRIDE_MIN_DAYS and the weekday test favours ParlGov.
    pooled = pd.concat(
        [
            etad[["iso3", "held_ts"]].rename(columns={"held_ts": "date"}),
            parlgov[["iso3", "pg_date"]].rename(columns={"pg_date": "date"}),
        ]
    )
    weekday = modal_weekday_by_country(pooled).set_index("iso3")
    calendar["modal_weekday"] = calendar["iso3"].map(weekday["modal_weekday"])
    calendar["modal_weekday_share"] = calendar["iso3"].map(weekday["modal_share"])
    informative = calendar["modal_weekday_share"] >= MIN_WEEKDAY_SHARE
    differs = calendar["diff_days"].abs() > DATE_OVERRIDE_MIN_DAYS
    etad_off_day = calendar["etad_date"].dt.dayofweek != calendar["modal_weekday"]
    pg_on_day = calendar["parlgov_date"].dt.dayofweek == calendar["modal_weekday"]
    override = differs & informative & etad_off_day & pg_on_day
    calendar["date_used"] = np.where(override | calendar["etad_date"].isna(), calendar["parlgov_date"], calendar["etad_date"])
    calendar["date_used"] = pd.to_datetime(calendar["date_used"])
    calendar["date_rule"] = np.select(
        [calendar["etad_date"].isna(), override, calendar["diff_days"].abs() > 0],
        ["parlgov_only", "parlgov_weekday_override", "etad_primary_dates_differ"],
        default=np.where(calendar["source"].eq("both"), "etad_primary_dates_equal", "etad_primary_etad_only"),
    )

    # Primary classification (ETAD fields).
    classes = [
        classify_etad(t1, t2, rs, dd) if not pd.isna(es) else ("unclassified", "no_etad_row")
        for t1, t2, rs, dd, es in zip(
            calendar["timing1"], calendar["timing2"], calendar["reason"], calendar["dif_days"], calendar["etad_row"], strict=True
        )
    ]
    calendar["class_primary"] = [c for c, _ in classes]
    calendar["class_rule"] = [r for _, r in classes]

    # Second classification from ParlGov gaps.
    calendar = _add_gap_classification(calendar)
    fill = calendar["class_primary"].eq("unclassified") & calendar["class_gap"].isin(KNOWN_CLASSES)
    calendar["class_gapfill"] = np.where(fill, calendar["class_gap"], calendar["class_primary"])
    calendar["eurostat_code"] = calendar["eurostat_code"].astype(str)
    calendar["year"] = calendar["date_used"].dt.year
    calendar = calendar.sort_values(["eurostat_code", "date_used"]).reset_index(drop=True)
    return calendar


def _add_gap_classification(calendar: pd.DataFrame) -> pd.DataFrame:
    """Attach ParlGov gap, expected term and ``class_gap`` columns (see :func:`classify_gap`).

    Expected term: ETAD ``termlength`` of the previous election's row (the term the sitting parliament was
    elected for) when that election is in ETAD, else the election's own row; for countries absent from ETAD
    (CY, MT) the term is inferred as the modal rounded ParlGov gap, and the row is flagged
    ``term_inferred`` (an assumption, reported).
    """
    calendar = calendar.copy()
    calendar["gap_years"] = (calendar["parlgov_date"] - calendar["prev_pg_date"]).dt.days / DAYS_PER_YEAR
    by_pg_date = calendar.dropna(subset=["parlgov_date"]).set_index(["iso3", "parlgov_date"])["termlength"]
    by_pg_date = by_pg_date[~by_pg_date.index.duplicated()]
    prev_term = [
        by_pg_date.get((iso3, prev), np.nan) if not pd.isna(prev) else np.nan
        for iso3, prev in zip(calendar["iso3"], calendar["prev_pg_date"], strict=True)
    ]
    calendar["expected_term_years"] = pd.Series(prev_term, index=calendar.index, dtype="float64").fillna(calendar["termlength"])
    # ParlGov-only elections inside an ETAD country (e.g. GRC 2023) inherit the country's latest earlier ETAD term.
    ordered = calendar.sort_values(["iso3", "parlgov_date"])
    carried = ordered.groupby("iso3")["expected_term_years"].ffill()
    calendar["expected_term_years"] = carried.reindex(calendar.index)
    calendar["term_inferred"] = False
    no_etad = calendar.groupby("iso3")["etad_row"].transform(lambda s: s.notna().sum() == 0)
    for iso3 in calendar.loc[no_etad, "iso3"].unique():
        mask = calendar["iso3"] == iso3
        inferred = float(calendar.loc[mask, "gap_years"].dropna().round().mode().iloc[0])
        calendar.loc[mask, "expected_term_years"] = inferred
        calendar.loc[mask, "term_inferred"] = True
    calendar["class_gap"] = [classify_gap(g, t) for g, t in zip(calendar["gap_years"], calendar["expected_term_years"], strict=True)]
    return calendar


# ---------------------------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------------------------
def _year_shares(start: pd.Timestamp, end: pd.Timestamp) -> dict[int, float]:
    """Share of the half-open day window ``[start, end)`` that falls in each calendar year."""
    total = (end - start).days
    shares: dict[int, float] = {}
    for year in range(start.year, end.year + 1):
        lo = max(start, pd.Timestamp(year, 1, 1))
        hi = min(end, pd.Timestamp(year + 1, 1, 1))
        overlap = (hi - lo).days
        if overlap > 0:
            shares[year] = overlap / total
    return shares


def pre_window_shares(election_day: pd.Timestamp) -> dict[int, float]:
    """Shares of the 12 months before ``election_day`` (``[d - 1 year, d)``) falling in each calendar year."""
    return _year_shares(election_day - pd.DateOffset(years=1), election_day)


def post_window_shares(election_day: pd.Timestamp) -> dict[int, float]:
    """Shares of the 12 months from ``election_day`` (``[d, d + 1 year)``) falling in each calendar year."""
    return _year_shares(election_day, election_day + pd.DateOffset(years=1))


def _union_year_share(windows: list[tuple[pd.Timestamp, pd.Timestamp]], years: range) -> dict[int, float]:
    """Share of each calendar year covered by the union of half-open day windows ``[start, end)``."""
    first = pd.Timestamp(years[0], 1, 1)
    last = pd.Timestamp(years[-1] + 1, 1, 1)
    mask = np.zeros((last - first).days, dtype=bool)
    for start, end in windows:
        lo = max((start - first).days, 0)
        hi = min((end - first).days, len(mask))
        if hi > lo:
            mask[lo:hi] = True
    shares = {}
    for year in years:
        lo = (pd.Timestamp(year, 1, 1) - first).days
        hi = (pd.Timestamp(year + 1, 1, 1) - first).days
        shares[year] = float(mask[lo:hi].mean())
    return shares


def build_exposure(calendar: pd.DataFrame, class_col: str = "class_primary", suffix: str = "", additive: bool = False) -> pd.DataFrame:
    """Country-year exposure ``W_S, W_E, W_D, W_U`` (pre-windows by class) and ``Post`` (any class).

    Default (``additive=False``): ``W`` is the share of calendar year ``t`` that lies inside the UNION of the
    12-month pre-windows of the elections of that class, so 0 <= W <= 1 holds by construction (proposal 9.1).
    For one election this equals the share of its 12-month window that falls in year ``t`` up to leap-day rounding
    (< 0.3 per cent); it differs from the plain sum only when two same-class windows overlap.
    ``additive=True`` returns the plain sum of per-election window shares (can exceed 1).
    ``class_col`` selects the classification (``class_primary``, ``class_gapfill`` or ``class_gap``;
    ``unavailable`` and ``unclassified`` both go to ``W_U``). Only rows with ``in_calendar`` are used. Panel years
    run 1990 to 2023 for all 27 countries; completeness is flagged by :func:`completeness_flags`.
    """
    table = countries.load_countries()
    years = range(CALENDAR_START.year, CALENDAR_END.year + 1)
    names = [f"W_{c}{suffix}" for c in "SEDU"] + [f"Post{suffix}"]
    letter_of = {"scheduled": "S", "early": "E", "delayed": "D"}
    records: list[dict[str, object]] = []
    used = calendar[calendar["in_calendar"]]
    for code in table["eurostat_code"]:
        sub = used[used["eurostat_code"] == code]
        shares: dict[str, dict[int, float]] = {}
        for letter in "SEDU":
            days = [d for d, c in zip(sub["date_used"], sub[class_col], strict=True) if letter_of.get(c, "U") == letter]
            if additive:
                total = dict.fromkeys(years, 0.0)
                for day in days:
                    for year, share in pre_window_shares(day).items():
                        if year in total:
                            total[year] += share
                shares[letter] = total
            else:
                shares[letter] = _union_year_share([(d - pd.DateOffset(years=1), d) for d in days], years)
        if additive:
            post = dict.fromkeys(years, 0.0)
            for day in sub["date_used"]:
                for year, share in post_window_shares(day).items():
                    if year in post:
                        post[year] += share
        else:
            post = _union_year_share([(d, d + pd.DateOffset(years=1)) for d in sub["date_used"]], years)
        for year in years:
            records.append(
                {"eurostat_code": code, "year": year, names[0]: shares["S"][year], names[1]: shares["E"][year],
                 names[2]: shares["D"][year], names[3]: shares["U"][year], names[4]: post[year]}
            )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------------------------
# Right-censoring and completeness
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Coverage:
    """Evidence about how far each country's calendar can be trusted."""

    obs_through_cross_validated: dict[str, pd.Timestamp]  # ParlGov end for everyone
    obs_through_etad_trusted: dict[str, pd.Timestamp]  # ETAD end unless a proven gap exists
    proven_gaps: dict[str, str]  # code -> evidence


def coverage_evidence(calendar: pd.DataFrame, etad: pd.DataFrame) -> Coverage:
    """Derive per-country calendar coverage ends from the data only.

    Cross-validated basis: every country is covered through ``PARLGOV_COVERAGE_END`` (both sources overlap).
    ETAD-trusted basis: through ``CALENDAR_END`` except for (i) countries where ParlGov shows an election that ETAD lacks
    inside the ETAD span (calendar rows with source ``parlgov_only`` after the country's first ETAD election),
    (ii) countries whose last observed election plus its term length lies before ``CALENDAR_END`` with no later
    election in either source (an election must then be missing), and (iii) countries absent from ETAD.
    """
    codes = countries.eu27_eurostat_codes()
    cross = {code: PARLGOV_COVERAGE_END for code in codes}
    trusted = {code: CALENDAR_END for code in codes}
    gaps: dict[str, str] = {}
    in_cal = calendar[calendar["in_calendar"]]
    for code in codes:
        sub = in_cal[in_cal["eurostat_code"] == code]
        if sub["etad_row"].notna().sum() == 0:
            trusted[code] = PARLGOV_COVERAGE_END
            gaps[code] = "country absent from ETAD: calendar rests on ParlGov (ends 2023-06-30)"
            continue
        pg_only_late = sub[sub["source"].eq("parlgov_only") & (sub["date_used"] > sub["etad_date"].max())]
        if len(pg_only_late):
            trusted[code] = PARLGOV_COVERAGE_END
            gaps[code] = "ParlGov records an election after the last ETAD election: " + ", ".join(
                str(d.date()) for d in pg_only_late["date_used"]
            )
            continue
        last = sub.sort_values("date_used").iloc[-1]
        term = last["termlength"] if not pd.isna(last["termlength"]) else last["expected_term_years"]
        term_end = last["date_used"] + pd.DateOffset(years=int(term))
        if term_end <= CALENDAR_END:
            trusted[code] = PARLGOV_COVERAGE_END
            gaps[code] = (
                f"last observed election {last['date_used'].date()} + term {int(term)} years = {term_end.date()} "
                f"<= {CALENDAR_END.date()} but no later election in either source"
            )
    return Coverage(cross, trusted, gaps)


def exposure_complete(year: int, observed_through: pd.Timestamp) -> bool:
    """Year ``t`` exposure needs all elections up to 31 December of ``t + 1`` (pre-window reaches back 12 months)."""
    return bool(observed_through >= pd.Timestamp(year + 1, 12, 31))


def completeness_flags(exposure: pd.DataFrame, coverage: Coverage) -> pd.DataFrame:
    """Add ``exposure_complete_cv`` (cross-validated) and ``exposure_complete_etad`` (ETAD-trusted) flags."""
    out = exposure.copy()
    out["exposure_complete_cv"] = [
        exposure_complete(y, coverage.obs_through_cross_validated[c]) for c, y in zip(out["eurostat_code"], out["year"], strict=True)
    ]
    out["exposure_complete_etad"] = [
        exposure_complete(y, coverage.obs_through_etad_trusted[c]) for c, y in zip(out["eurostat_code"], out["year"], strict=True)
    ]
    return out


def last_complete_year(coverage: Coverage, basis: str = "cv") -> int:
    """Last year for which every EU-27 country has complete exposure on the chosen basis (``cv`` or ``etad``)."""
    ends = coverage.obs_through_cross_validated if basis == "cv" else coverage.obs_through_etad_trusted
    return min(int(end.year) - 1 if end >= pd.Timestamp(end.year, 12, 31) else int(end.year) - 2 for end in ends.values())


# ---------------------------------------------------------------------------------------------
# Disagreement and exclusion register
# ---------------------------------------------------------------------------------------------
def build_exclusion_table(calendar: pd.DataFrame) -> pd.DataFrame:
    """One row per exceptional election: unclassified, delayed, rule overrides, source disagreements.

    ``proposed_treatment`` is the default stated in the Gate 3 plan (keep as ``unclassified``, report with
    and without) unless a row-specific reason applies.
    """
    rows: list[dict[str, object]] = []

    def add(row: pd.Series, category: str, detail: str, treatment: str) -> None:
        rows.append(
            {
                "category": category,
                "eurostat_code": row["eurostat_code"],
                "iso3": row["iso3"],
                "election_date_used": row["date_used"].date(),
                "etad_date": row["etad_date"].date() if not pd.isna(row["etad_date"]) else "",
                "parlgov_date": row["parlgov_date"].date() if not pd.isna(row["parlgov_date"]) else "",
                "date_diff_days_parlgov_minus_etad": row["diff_days"] if not pd.isna(row["diff_days"]) else "",
                "source": row["source"],
                "in_calendar": bool(row["in_calendar"]),
                "class_primary": row["class_primary"],
                "class_rule": row["class_rule"],
                "class_gap": row["class_gap"],
                "timing1": row["timing1"],
                "timing2": row["timing2"],
                "reason": row["reason"],
                "etad_reason_text": REASON_TEXT.get(int(row["reason"]), "") if not pd.isna(row["reason"]) else "",
                "dif_days": row["dif_days"],
                "gap_years": round(row["gap_years"], 2) if not pd.isna(row["gap_years"]) else "",
                "expected_term_years": row["expected_term_years"],
                "detail": detail,
                "proposed_treatment": treatment,
                "within_exposure_reach_1994_2023": bool(row["date_used"] >= SAMPLE_WINDOW_START),
            }
        )

    unclass_treatment = (
        "Keep in the exposure as 'unclassified' (W_U and Post); report main results with W_U as a separate "
        "regressor and with country-years where W_U > 0 dropped; sensitivity: reassign by the ParlGov gap class (W_*_gf)."
    )
    for _, row in calendar.iterrows():
        if not row["in_calendar"]:
            add(row, "parlgov_only_excluded", row["exclusion_note"], "Exclude: not a national election of the sovereign state in the sample window.")
            continue
        if row["class_primary"] == "unclassified":
            category = "unclassified_no_etad_row" if row["class_rule"] == "no_etad_row" else "unclassified_" + row["class_rule"]
            detail = {
                "timing1_unknown": "ETAD timing1 = 3: cannot tell whether the election was on schedule; sche_date missing.",
                "no_etad_row": "No ETAD row (country absent from ETAD, or election missing from ETAD); date from ParlGov only.",
                "delayed_vs_dif_days_sign": "timing2 = 1 (delayed) but dif_days < 0 (held before scheduled date).",
                "delayed_vs_early_reason": "timing2 = 1 (delayed) but reason is no-confidence/other (early-type).",
                "timing1_moved_but_timing2_on_time": "timing1 = 2 (moved) but timing2 = 0 (on time).",
            }.get(row["class_rule"], row["class_rule"])
            add(row, category, detail, unclass_treatment)
        elif row["class_primary"] == "delayed":
            add(row, "delayed", "ETAD timing2 = 1 and consistent with dif_days.", "Keep as W_D (own regressor); not merged into scheduled or early; listed per proposal 9.1.")
        if row["class_rule"] == "reason_overrides_timing2_on_time":
            add(row, "rule_override_early", "timing2 = 0 but reason in {7, 9}: early by the proposal rule.", "Keep as early (proposal rule); sensitivity: treat as unclassified.")
        if row["source"] == "both" and row["diff_days"] != 0:
            used = "ParlGov date used (weekday override)" if row["date_rule"] == "parlgov_weekday_override" else "ETAD date used"
            add(row, "date_differs", f"ETAD {row['etad_date'].date()} vs ParlGov {row['parlgov_date'].date()}; {used}.", "None needed when |difference| <= 21 days (exposure shifts by <= 0.06); see report for the 61-day and 10-day cases.")
        if row["source"] == "etad_only":
            kind = "within ParlGov coverage (genuine disagreement)" if row["etad_only_in_parlgov_range"] else "outside ParlGov coverage (not cross-checkable)"
            add(row, "etad_only", kind, "Keep the ETAD election; cannot be cross-checked." if not row["etad_only_in_parlgov_range"] else "Keep ETAD election; investigate.")
        if row["source"] == "parlgov_only" and row["in_calendar"] and not row["class_rule"] == "no_etad_row":
            add(row, "parlgov_only_included", "ParlGov election missing from ETAD", unclass_treatment)
        known = row["class_primary"] in KNOWN_CLASSES
        if known and row["class_gap"] in KNOWN_CLASSES and row["class_gap"] != row["class_primary"]:
            add(row, "gap_class_disagrees", f"ETAD {row['class_primary']} vs gap-based {row['class_gap']} (gap {row['gap_years']:.2f}y vs term {row['expected_term_years']:.0f}y, tolerance {GAP_TOLERANCE_YEARS}y).", "Keep ETAD classification (primary); report the gap-based classification as a robustness run.")
    table = pd.DataFrame(rows)
    return table.sort_values(["eurostat_code", "election_date_used", "category"]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------------
def build_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Coverage]:
    """Build calendar, exposure panel (primary + gap-fill variant), exclusion table and coverage evidence."""
    raw = read_etad_raw()
    calendar = build_calendar(raw)
    primary = build_exposure(calendar, "class_primary")
    gapfill = build_exposure(calendar, "class_gapfill", suffix="_gf")
    additive = build_exposure(calendar, "class_primary", suffix="_add", additive=True)
    exposure = primary.merge(gapfill, on=["eurostat_code", "year"]).merge(additive, on=["eurostat_code", "year"])
    etad = etad_eu27_legislative(raw)
    coverage = coverage_evidence(calendar, etad)
    exposure = completeness_flags(exposure, coverage)
    exposure["W_S_plus_U"] = exposure["W_S"] + exposure["W_U"]
    exposure["touches_unclassified_or_delayed"] = (exposure["W_U"] > 0) | (exposure["W_D"] > 0)
    additive_cols = ["W_S_add", "W_E_add", "W_D_add", "W_U_add", "Post_add"]
    exposure["additive_exceeds_one"] = exposure[additive_cols].gt(1 + 1e-9).any(axis=1)
    held = calendar[calendar["in_calendar"]].groupby(["eurostat_code", "year"]).size().rename("n_elections_held")
    exposure = exposure.merge(held.reset_index(), on=["eurostat_code", "year"], how="left")
    exposure["n_elections_held"] = exposure["n_elections_held"].fillna(0).astype(int)
    country_source = calendar[calendar["in_calendar"]].groupby("eurostat_code")["etad_row"].apply(lambda s: "etad+parlgov" if s.notna().any() else "parlgov_only")
    exposure["calendar_source"] = exposure["eurostat_code"].map(country_source)
    exposure["calendar_gap_evidence"] = exposure["eurostat_code"].map(coverage.proven_gaps).fillna("")
    exclusions = build_exclusion_table(calendar)
    return calendar, exposure, exclusions, coverage


CALENDAR_COLUMNS = [
    "eurostat_code", "iso3", "year", "date_used", "date_rule", "source", "in_calendar", "exclusion_note",
    "etad_date", "parlgov_date", "diff_days", "etad_row", "election_id", "timing1", "timing2", "reason",
    "sche_date", "dif_days", "termlength", "class_primary", "class_rule", "gap_years", "expected_term_years",
    "term_inferred", "class_gap", "class_gapfill", "etad_only_in_parlgov_range",
]


def calendar_for_csv(calendar: pd.DataFrame) -> pd.DataFrame:
    """Select, order and type the calendar columns for ``data/interim/election_calendar_eu27.csv``.

    ``diff_days`` is ParlGov date minus ETAD date; ``election_id`` is the ParlGov election id.
    """
    out = calendar[CALENDAR_COLUMNS].copy()
    for column in ("date_used", "etad_date", "parlgov_date"):
        out[column] = out[column].dt.strftime("%Y-%m-%d")
    for column in ("diff_days", "etad_row", "election_id", "timing1", "timing2", "reason", "dif_days", "termlength"):
        out[column] = out[column].astype("Int64")
    out["gap_years"] = out["gap_years"].round(3)
    return out.rename(columns={"election_id": "parlgov_election_id", "diff_days": "date_diff_days_parlgov_minus_etad"})


def gap_agreement(calendar: pd.DataFrame, tolerances: tuple[float, ...] = GAP_TOLERANCE_SENSITIVITY) -> pd.DataFrame:
    """Agreement between the ETAD class and the ParlGov-gap class at several tolerances.

    Counts only elections that ETAD classified (scheduled/early/delayed) and for which a gap class exists.
    """
    used = calendar[calendar["in_calendar"] & calendar["class_primary"].isin(KNOWN_CLASSES)]
    rows = []
    for tol in tolerances:
        gap_class = [classify_gap(g, t, tol) for g, t in zip(used["gap_years"], used["expected_term_years"], strict=True)]
        frame = pd.DataFrame({"primary": used["class_primary"].to_numpy(), "gap": gap_class})
        comparable = frame[frame["gap"] != "unavailable"]
        rows.append(
            {
                "tolerance_years": tol,
                "n_comparable": len(comparable),
                "n_agree": int((comparable["primary"] == comparable["gap"]).sum()),
                "agree_share": float((comparable["primary"] == comparable["gap"]).mean()),
                "n_etad_early_gap_scheduled": int(((comparable["primary"] == "early") & (comparable["gap"] == "scheduled")).sum()),
                "n_etad_scheduled_gap_early": int(((comparable["primary"] == "scheduled") & (comparable["gap"] == "early")).sum()),
                "n_other_disagree": int(
                    ((comparable["primary"] != comparable["gap"])
                     & ~((comparable["primary"] == "early") & (comparable["gap"] == "scheduled"))
                     & ~((comparable["primary"] == "scheduled") & (comparable["gap"] == "early"))).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """Write the three Gate 3a election outputs (the only files this module writes)."""
    calendar, exposure, exclusions, _ = build_all()
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    calendar_for_csv(calendar).to_csv(CALENDAR_CSV, index=False)
    exposure.to_csv(EXPOSURE_CSV, index=False, float_format="%.6f")
    exclusions.to_csv(EXCLUSIONS_CSV, index=False)


if __name__ == "__main__":
    main()
