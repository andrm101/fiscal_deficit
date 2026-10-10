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


# ------------------------------------------------------------------------------- T3 and sign checks
SIGN_TOLERANCE_PP = 0.5  # |value| below this is too close to zero to test a sign convention
OUTSIZED_RATIO = 2.0  # a pair's mean absolute revision >= this multiple of the median across pairs is "outsized"
CAPB_FIRST_WINDOW = (2014, 2021)  # years for first-release versus final comparisons (blueprint step 6)


def _norm(text: str) -> str:
    """Whitespace-normalised, case-preserving text for exact label comparison."""
    return re.sub(r"\s+", " ", str(text)).strip()


def archived(long: pd.DataFrame) -> pd.DataFrame:
    """Rows of the 26 archived vintages (excludes the Spring 2026 pinned snapshot)."""
    return long[long["vintage_order"] < FINAL_ORDER]


def t3_summary(long: pd.DataFrame, item: str = CAPB_ITEM) -> pd.DataFrame:
    """Per-vintage coverage of ``item`` for the EU-27 plus label, denominator and flag checks (trigger T3).

    ``label_identical`` and ``denominator_identical`` compare against the first vintage's text after
    whitespace normalisation. ``flag`` collects: fewer than ``MIN_COUNTRIES_T3`` countries, label or
    denominator differing from the reference.
    """
    sub = long[long["item"] == item]
    ordered = sub.sort_values("vintage_order")
    ref_title = _norm(ordered["title"].iloc[0])
    ref_unit = _norm(ordered["unit_text"].iloc[0])
    rows = []
    for (order, label), group in sub.groupby(["vintage_order", "vintage_label"], sort=True):
        observed = group.dropna(subset=["value"])
        title_ok = {_norm(t) for t in group["title"]} == {ref_title}
        unit_ok = {_norm(u) for u in group["unit_text"]} == {ref_unit}
        flags = []
        if observed["eurostat_code"].nunique() < MIN_COUNTRIES_T3:
            flags.append("fewer than 20 countries")
        if not title_ok:
            flags.append("label differs")
        if not unit_ok:
            flags.append("denominator differs")
        rows.append(
            {
                "vintage_label": label,
                "vintage_order": order,
                "n_countries": observed["eurostat_code"].nunique(),
                "n_years": observed["year"].nunique(),
                "n_observed_cells": len(observed),
                "first_year": int(observed["year"].min()),
                "last_year": int(observed["year"].max()),
                "sub_chapter": "; ".join(sorted({s for s in group["sub_chapter"] if s})),
                "label_identical": title_ok,
                "denominator_identical": unit_ok and ref_unit == POTENTIAL_GDP_TEXT,
                "flag": "; ".join(flags),
            }
        )
    return pd.DataFrame(rows)


def t3_verdict(summary: pd.DataFrame, archived_only: bool = True) -> dict[str, object]:
    """PASS/FAIL for T3: ``UBLGBP`` for >= ``MIN_COUNTRIES_T3`` EU-27 countries in every archived vintage."""
    table = summary[summary["vintage_order"] < FINAL_ORDER] if archived_only else summary
    return {
        "pass": bool((table["n_countries"] >= MIN_COUNTRIES_T3).all()),
        "n_vintages": len(table),
        "min_countries": int(table["n_countries"].min()),
        "max_countries": int(table["n_countries"].max()),
    }


def capb_wide(long: pd.DataFrame, item: str = CAPB_ITEM) -> pd.DataFrame:
    """Wide table indexed by (eurostat_code, year) with one column per ``vintage_order``."""
    sub = long[long["item"] == item]
    return sub.pivot_table(index=["eurostat_code", "year"], columns="vintage_order", values="value", aggfunc="first")


def adjacent_sign_check(long: pd.DataFrame, item: str = CAPB_ITEM) -> pd.DataFrame:
    """Compare identical country-years across adjacent vintages: correlation, regression slope and sign agreement.

    A flipped sign convention would give a correlation near -1 and a sign-agreement share near 0. Sign
    agreement is computed only where both values exceed ``SIGN_TOLERANCE_PP`` in absolute value.
    """
    wide = capb_wide(long, item)
    orders = list(wide.columns)
    rows = []
    for earlier, later in zip(orders[:-1], orders[1:], strict=True):
        both = wide[[earlier, later]].dropna()
        x, y = both[earlier].to_numpy(), both[later].to_numpy()
        big = (np.abs(x) > SIGN_TOLERANCE_PP) & (np.abs(y) > SIGN_TOLERANCE_PP)
        rows.append(
            {
                "from_order": earlier,
                "to_order": later,
                "n_overlap": len(both),
                "pearson_r": float(np.corrcoef(x, y)[0, 1]),
                "slope_later_on_earlier": float(np.polyfit(x, y, 1)[0]),
                "n_sign_testable": int(big.sum()),
                "share_same_sign": float((np.sign(x[big]) == np.sign(y[big])).mean()),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------- revisions
def _season_by_order(specs: list[VintageSpec]) -> dict[int, VintageSpec]:
    """Lookup ``vintage_order -> VintageSpec`` including the pinned final (treated as a Spring vintage)."""
    lookup = {s.order: s for s in specs}
    lookup[FINAL_ORDER] = VintageSpec(FINAL_LABEL, FINAL_ORDER, "spring", 2026, FINAL_SNAPSHOT_ZIP, date(2026, 6, 3))
    return lookup


def last_observed_by_order(long: pd.DataFrame, specs: list[VintageSpec]) -> dict[int, int]:
    """Last non-forecast year of each vintage: the vintage's last observed column year minus its horizon."""
    lookup = _season_by_order(specs)
    last_year = long.dropna(subset=["value"]).groupby("vintage_order")["year"].max()
    return {int(o): last_observed_year(int(y), lookup[int(o)].season) for o, y in last_year.items()}


def revision_pairs(
    long: pd.DataFrame,
    specs: list[VintageSpec],
    item: str = CAPB_ITEM,
    min_year: int | None = None,
    outturn_only: bool = False,
) -> pd.DataFrame:
    """Revision distribution of the same country-year between consecutive vintages (including the pinned final).

    Revision = later minus earlier value (pp of potential GDP). ``outturn_only`` keeps country-years that are
    non-forecast in the *earlier* vintage; ``min_year`` restricts the year window. ``mean_signed_t`` is the
    t-statistic of the mean of country-average signed revisions across countries (descriptive level-shift
    screen, not an inference about causes). ``outsized`` flags pairs whose mean absolute revision is at least
    ``OUTSIZED_RATIO`` times the median across pairs.
    """
    wide = capb_wide(long, item)
    last_obs = last_observed_by_order(long, specs)
    lookup = _season_by_order(specs)
    rows = []
    orders = list(wide.columns)
    for earlier, later in zip(orders[:-1], orders[1:], strict=True):
        pair = wide[[earlier, later]].dropna()
        yrs = pair.index.get_level_values("year")
        keep = np.ones(len(pair), dtype=bool)
        if min_year is not None:
            keep &= yrs >= min_year
        if outturn_only:
            keep &= yrs <= last_obs[earlier]
        pair = pair[keep]
        rev = (pair[later] - pair[earlier]).rename("rev")
        if rev.empty:
            continue
        by_country = rev.groupby(level="eurostat_code").mean()
        spread = by_country.std(ddof=1)
        t_stat = float(by_country.mean() / (spread / np.sqrt(len(by_country)))) if spread > 0 and len(by_country) > 1 else np.nan
        rows.append(
            {
                "from_label": lookup[earlier].label,
                "to_label": lookup[later].label,
                "from_order": earlier,
                "to_order": later,
                "n": len(rev),
                "mean_signed": float(rev.mean()),
                "sd": float(rev.std(ddof=1)),
                "mean_abs": float(rev.abs().mean()),
                "max_abs": float(rev.abs().max()),
                "mean_signed_t": t_stat,
            }
        )
    out = pd.DataFrame(rows)
    out["outsized"] = out["mean_abs"] >= OUTSIZED_RATIO * out["mean_abs"].median()
    return out


def top_revisions(long: pd.DataFrame, specs: list[VintageSpec], from_label: str, to_label: str, n: int = 3) -> pd.DataFrame:
    """Largest absolute revisions between two named vintages (used to characterise outsized pairs)."""
    wide = capb_wide(long)
    lookup = {s.label: s.order for s in specs} | {FINAL_LABEL: FINAL_ORDER}
    pair = wide[[lookup[from_label], lookup[to_label]]].dropna()
    rev = (pair[lookup[to_label]] - pair[lookup[from_label]]).rename("revision")
    return rev.reindex(rev.abs().sort_values(ascending=False).index).head(n).reset_index()


# -------------------------------------------------------------------------- first release vs final
def first_release_table(
    long: pd.DataFrame, specs: list[VintageSpec], window: tuple[int, int] = CAPB_FIRST_WINDOW, item: str = CAPB_ITEM
) -> pd.DataFrame:
    """First-release CAPB per country-year in ``window`` versus the pinned Spring 2026 final.

    Two definitions: ``first_outturn_*`` is the earliest archived vintage where the year is non-forecast under
    the Spring/Autumn rule (see ``FORECAST_YEARS_BY_SEASON``); ``first_any_*`` is the earliest vintage that
    contains a value for the year at all (a forecast, here). Revisions are final minus first.
    """
    wide = capb_wide(long, item)
    last_obs = last_observed_by_order(long, specs)
    lookup = _season_by_order(specs)
    archived_orders = [o for o in wide.columns if o != FINAL_ORDER]
    rows = []
    for (code, year), values in wide.iterrows():
        if not window[0] <= year <= window[1] or pd.isna(values.get(FINAL_ORDER)):
            continue
        any_order = next((o for o in archived_orders if pd.notna(values[o])), None)
        out_order = next((o for o in archived_orders if pd.notna(values[o]) and year <= last_obs[o]), None)
        rows.append(
            {
                "eurostat_code": code,
                "year": int(year),
                "first_any_vintage": lookup[any_order].label if any_order else None,
                "first_any_value": values[any_order] if any_order else np.nan,
                "first_outturn_vintage": lookup[out_order].label if out_order else None,
                "first_outturn_value": values[out_order] if out_order else np.nan,
                "final_value": values[FINAL_ORDER],
            }
        )
    table = pd.DataFrame(rows)
    for tag in ("any", "outturn"):
        table[f"revision_{tag}"] = table["final_value"] - table[f"first_{tag}_value"]
    return table


def _sign_change(first: pd.Series, final: pd.Series) -> pd.Series:
    """True where the sign differs between first release and final (both non-zero)."""
    return (np.sign(first) * np.sign(final)) < 0


def summarise_revisions(table: pd.DataFrame, tag: str, by: str | None = None) -> pd.DataFrame:
    """Mean, SD, mean absolute revision, sign-change share and first/final correlation (overall or per ``by``)."""
    first, rev = f"first_{tag}_value", f"revision_{tag}"

    def one(group: pd.DataFrame) -> pd.Series:
        valid = group.dropna(subset=[first, "final_value"])
        n = len(valid)
        corr = float(np.corrcoef(valid[first], valid["final_value"])[0, 1]) if n > 2 else np.nan
        return pd.Series(
            {
                "n": n,
                "mean_revision": valid[rev].mean(),
                "sd_revision": valid[rev].std(ddof=1),
                "mean_abs_revision": valid[rev].abs().mean(),
                "share_sign_change": _sign_change(valid[first], valid["final_value"]).mean(),
                "corr_first_final": corr,
            }
        )

    if by is None:
        return one(table).to_frame().T
    return table.groupby(by).apply(one, include_groups=False).reset_index()


# ------------------------------------------------------------------ real-time availability (counts)
ELECTION_WINDOW = (date(2015, 1, 1), date(2021, 12, 31))  # Gate 3a sample years that a real-time panel can reach
SAMPLE_WINDOW_YEARS = (2015, 2021)
CALENDAR_CSV = PROJECT_ROOT / "data" / "interim" / "election_calendar_eu27.csv"
CLASSES = ("scheduled", "early", "delayed", "unclassified")


def conservative_release_dates(specs: list[VintageSpec]) -> dict[int, date]:
    """Later of the printed date and the chapter 17 file timestamp: a conservative availability date per vintage."""
    out = {}
    for spec in specs:
        stamp = date.fromisoformat(str(inventory_vintage(spec)["chapter17_stamp"]))
        out[spec.order] = max(spec.printed_date, stamp)
    return out


def pre_election_vintage(
    election_date: date, specs: list[VintageSpec], release_dates: dict[int, date] | None = None
) -> VintageSpec | None:
    """Latest vintage released strictly before ``election_date`` (printed dates unless ``release_dates`` is given).

    The vintage with the suspect printed date is excluded from the printed-date rule only if it would otherwise
    be selected on the strength of an implausible date; here it simply follows its printed date, and the report
    flags it.
    """
    dates = release_dates or {s.order: s.printed_date for s in specs}
    candidates = [s for s in specs if dates[s.order] < election_date]
    return max(candidates, key=lambda s: dates[s.order]) if candidates else None


def read_calendar(path: Path = CALENDAR_CSV) -> pd.DataFrame:
    """Election calendar rows that are in the calendar, with ``election_date`` parsed (columns used: code, date, class)."""
    cal = pd.read_csv(path)
    cal = cal[cal["in_calendar"].astype(bool)].copy()
    cal["election_date"] = pd.to_datetime(cal["date_used"]).dt.date
    return cal[["eurostat_code", "election_date", "class_primary"]].rename(columns={"class_primary": "election_class"})


def election_availability(
    calendar: pd.DataFrame,
    long: pd.DataFrame,
    specs: list[VintageSpec],
    start: date = ELECTION_WINDOW[0],
    end: date = ELECTION_WINDOW[1],
    release_dates: dict[int, date] | None = None,
    item: str = CAPB_ITEM,
) -> pd.DataFrame:
    """For each election in ``[start, end]``: the pre-election vintage and whether it carries CAPB for t-1, t, t+1.

    ``t`` is the election year. ``t1_outturn`` marks whether year t-1 is non-forecast in that vintage. Pure
    descriptive availability; no outcome is related to election timing.
    """
    wide = capb_wide(long, item)
    last_obs = last_observed_by_order(long, specs)
    rows = []
    sel = calendar[calendar["election_date"].between(start, end)]
    for rec in sel.itertuples(index=False):
        vintage = pre_election_vintage(rec.election_date, specs, release_dates)
        year = rec.election_date.year
        row = {
            "eurostat_code": rec.eurostat_code,
            "election_date": rec.election_date,
            "election_year": year,
            "election_class": rec.election_class,
            "vintage": vintage.label if vintage else None,
            "has_vintage": vintage is not None,
        }
        for tag, offset in (("t_minus_1", -1), ("t", 0), ("t_plus_1", 1)):
            key = (rec.eurostat_code, year + offset)
            row[f"has_{tag}"] = bool(vintage and key in wide.index and pd.notna(wide.at[key, vintage.order]))
        row["t_minus_1_is_outturn"] = bool(vintage and row["has_t_minus_1"] and year - 1 <= last_obs[vintage.order])
        rows.append(row)
    return pd.DataFrame(rows)


def availability_by_class(avail: pd.DataFrame) -> pd.DataFrame:
    """Counts of elections per class with a pre-election vintage and with CAPB for t-1, outturn t-1, t and t+1."""
    flags = ["has_vintage", "has_t_minus_1", "t_minus_1_is_outturn", "has_t", "has_t_plus_1"]
    out = avail.groupby("election_class")[flags].sum().astype(int)
    out.insert(0, "n_elections", avail.groupby("election_class").size())
    out = out.reindex([c for c in CLASSES if c in out.index])
    total = out.sum().to_frame("total").T
    return pd.concat([out, total])


def gate3a_sample_keys(end_year: int = 2021) -> pd.DataFrame:
    """Country-year keys (eurostat_code, year) of the Gate 3a confirmatory sample (715 rows to 2021).

    Reuses ``evaluate.sample`` (keys only: no outcome value and no exposure value leaves this function).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluate"))
    import sample  # noqa: PLC0415

    selection = sample.select_sample(sample.build_panel(), end_year)
    return selection.sample[["eurostat_code", "year"]].reset_index(drop=True)


def realtime_window_coverage(keys: pd.DataFrame, first_year: int, last_year: int) -> dict[str, float]:
    """Share of the confirmatory sample country-years whose year falls in ``[first_year, last_year]``."""
    inside = keys["year"].between(first_year, last_year)
    return {"n_total": int(len(keys)), "n_inside": int(inside.sum()), "share": float(inside.mean())}


def to_interim_csv(long: pd.DataFrame, path: Path) -> None:
    """Write the long table (all vintages, three items) with the requested schema, sorted for stable diffs."""
    cols = ["vintage_label", "vintage_order", "printed_date", "area", "eurostat_code", "item", "year", "value", "unit_text"]
    out = long[cols].sort_values(["vintage_order", "item", "eurostat_code", "year"]).copy()
    out["printed_date"] = out["printed_date"].dt.strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
