"""Gate 2 audit of the EC Fiscal Governance Database (numerical fiscal rules).

Offline, read-only. Run from the project root:  python scripts/probes/gate2_fgd_audit.py
Prints every number quoted in reports/gate2_fiscal_governance_audit.md.
Nothing under data/raw/ is modified; nothing is written to disk.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl
import pandas as pd
import xlrd

warnings.simplefilter("ignore")
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 200)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fiscal_governance" / "nfr_2025_update"
F01 = RAW / "Numerical-Fiscal-Rules-database-2025.xlsx"
F02 = RAW / "fiscal_rules_database_en_old_methodology.xls"

EU27 = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE",
        "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]
Y0, Y1 = 1995, 2023          # sample window of the design
SURVEY_BREAK_CANDIDATES = (2012, 2014, 2015, 2016, 2017, 2019, 2022, 2024)
# Tolerance separating numerical jitter (recalculated weights) from real changes; justified in section 8.
TOL_STD = 0.0015             # z units; inside the only clear gap (0.00072 -> 0.00326) in the sorted nonzero changes
TOL_RAW = 0.05               # raw C-FRSI points (0-~22 scale); no clean gap exists, judgement call (strict counts also printed)
# Fraction of total SD below which two-way within variation is judged too thin (judgement; see report).
MIN_TWO_WAY_SD_RATIO = 0.25
FRSI_CRIT_MAX = {"c1": 3.0, "c2": 3.0, "c3": 7.5, "c4": 4.0, "c5": 4.0}


def hdr(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)


# --------------------------------------------------------------------------- loading
def load_xlsx() -> openpyxl.Workbook:
    """Open F01 read-only values (data_only)."""
    return openpyxl.load_workbook(F01, data_only=True)


def grid(ws: Any, r0: int, r1: int, c0: int, c1: int) -> list[list[Any]]:
    """Return a rectangular block of cell values (1-based inclusive bounds)."""
    return [[ws.cell(r, c).value for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


def country_year_frame(ws: Any, r0: int = 7, r1: int = 33, header_row: int = 6,
                       first_col: int = 3, last_col: int = 37) -> pd.DataFrame:
    """Country x year raw cell frame (object dtype) from a F01 country-year sheet."""
    years = [int(ws.cell(header_row, c).value) for c in range(first_col, last_col + 1)]
    idx = [str(ws.cell(r, 2).value).strip() for r in range(r0, r1 + 1)]
    data = grid(ws, r0, r1, first_col, last_col)
    return pd.DataFrame(data, index=idx, columns=years, dtype=object)


def to_num(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric view; '.' / blank / strings become NaN."""
    return df.apply(pd.to_numeric, errors="coerce")


def classify_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Per-cell code: 'num0', 'num', 'dot', 'blank', 'other'."""
    def f(v: Any) -> str:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "blank"
        if isinstance(v, str):
            return "dot" if v.strip() == "." else "other"
        return "num0" if float(v) == 0.0 else "num"
    return df.map(f)


# --------------------------------------------------------------------------- 1 structure
def section1_structure(wb: openpyxl.Workbook) -> None:
    """Sheet inventory for F01 and F02."""
    hdr("1. STRUCTURE")
    wbf = openpyxl.load_workbook(F01, data_only=False)
    print(f"F01 file props: creator={wbf.properties.creator!r} modified={wbf.properties.modified}")
    for ws in wbf.worksheets:
        ncom = [(c.coordinate, c.comment.text.replace('\n', ' / ')) for r in ws.iter_rows() for c in r if c.comment]
        nonempty = sum(1 for r in ws.iter_rows() for c in r if c.value is not None)
        print(f"F01 sheet {ws.title!r:32s} state={ws.sheet_state:8s} dims={ws.dimensions:10s} "
              f"rows={ws.max_row:4d} cols={ws.max_column:3d} nonempty_cells={nonempty:6d} merged={len(ws.merged_cells.ranges)} comments={ncom}")
    xb = xlrd.open_workbook(F02)
    for s in xb.sheets():
        vis = {0: "visible", 1: "hidden", 2: "veryhidden"}[s.visibility]
        print(f"F02 sheet {s.name!r:34s} state={vis:8s} rows={s.nrows:4d} cols={s.ncols:3d}")

    rs = wb["Fiscal Rule database"]
    rules = load_rule_table(wb)
    print(f"\nF01 'Fiscal Rule database': header row 6, data rows 7-{6 + len(rules)} (B..AD), {len(rules)} rule-version rows, "
          f"{rules['country'].nunique()} countries; trailing notes from row 271 ('Data explanation').")
    print("In force (col AC):", rules["in_force"].value_counts(dropna=False).to_dict())
    rl = wb["FRSI 1990-2024 rule level"]
    print(f"F01 'FRSI 1990-2024 rule level': header rows 5-6, data rows 7-130 -> {sum(1 for r in range(7, 131) if rl.cell(r, 2).value)} rule rows x years 1990-2024 (F..AN)")
    rc = wb["C-FRSI reconstruction"]
    print(f"F01 'C-FRSI reconstruction': header rows 5-7, data rows 8-131 -> {sum(1 for r in range(8, 132) if rc.cell(r, 1).value)} rule x sector rows (A..K); step explanations in M5:Q34")
    print("F01 'C-FRSI': country x year raw index 27 x 35 (rows 7-33, C..AK = 1990-2024)")
    print("F01 'Fiscal Rule Index 1990-2024': country x year standardised index 27 x 35 (rows 7-33, C..AK)")
    print("C-FRSI legend (AM1:AN2): AM1 fill theme-8 tint 0.8 = 'scores adjusted for previous years as well to reflect a calculation update'; AM2 yellow = 'scores adjusted as of this year to reflect a substantial change'")
    print("Methodology notes in C-FRSI: AB35 =", repr(wb["C-FRSI"]["AB35"].value)[:300])
    print("                              W38 (source path of publication file) =", repr(wb["C-FRSI"]["W38"].value)[:200])

    # F02 country list / years
    ix = xb.sheet_by_name("Fiscal Rule Index 1990-2015")
    print(f"F02 'Fiscal Rule Index 1990-2015': header row 6, rows 7-34 = {ix.nrows - 6} countries incl. UK, cols C..AB = 1990-2015")


def flagged_cells(wb_path: Path = F01) -> None:
    """List the highlighted (retroactive / substantial change) cells in C-FRSI."""
    wb = openpyxl.load_workbook(wb_path, data_only=True)
    ws = wb["C-FRSI"]
    years = {c: ws.cell(6, c).value for c in range(3, 38)}
    out_retro, out_subst = [], []
    for r in range(7, 34):
        for c in range(3, 38):
            cell = ws.cell(r, c)
            if cell.fill.fill_type != "solid":
                continue
            fg = cell.fill.fgColor
            tag = (ws.cell(r, 2).value, years[c])
            if fg.type == "rgb" and fg.rgb == "FFFFFF00":
                out_subst.append(tag)
            elif fg.type == "theme":
                out_retro.append(tag)
    print(f"C-FRSI highlighted cells: 'calculation update / retroactive' (theme fill) n={len(out_retro)} -> {out_retro}")
    print(f"C-FRSI highlighted cells: 'substantial change' (yellow) n={len(out_subst)} -> {out_subst}")
    rl = wb["FRSI 1990-2024 rule level"]
    r_retro, r_subst = [], []
    for r in range(7, 131):
        for c in range(6, 41):
            cell = rl.cell(r, c)
            if cell.fill.fill_type != "solid":
                continue
            fg = cell.fill.fgColor
            tag = (rl.cell(r, 2).value, rl.cell(r, 3).value, rl.cell(r, 4).value, rl.cell(6, c).value)
            if fg.type == "rgb" and fg.rgb == "FFFFFF00":
                r_subst.append(tag)
            elif fg.type == "theme":
                r_retro.append(tag)
    print(f"Rule-level sheet highlighted cells: retroactive n={len(r_retro)} -> {r_retro}")
    print(f"Rule-level sheet highlighted cells: substantial change n={len(r_subst)} -> {r_subst}")
    rt = wb["Fiscal Rule database"]
    red = [(rt.cell(r, 2).value, rt.cell(r, 3).value) for r in range(7, 270)
           if rt.cell(r, 14).font.color is not None and rt.cell(r, 14).font.color.type == "rgb" and rt.cell(r, 14).font.color.rgb == "FFFF0000"]
    print(f"Rule table rows with red font in 'In force since' (legend F278: 'Rules has been reformed in this year'; year not stated): n={len(red)} -> {red}")
    print("Rule table legend cells: AH1 'Active rule', AH2 'Substantial change in 2024', AH4 'Retroactive change'; AG6 'Reform reported by Member State' column AG is empty for all rows:",
          all(rt.cell(r, 33).value is None for r in range(7, 270)))


# --------------------------------------------------------------------------- rule table
def load_rule_table(wb: openpyxl.Workbook) -> pd.DataFrame:
    """Parse the F01 'Fiscal Rule database' (rule-version level)."""
    ws = wb["Fiscal Rule database"]
    heads = {2: "code", 3: "country", 4: "type", 5: "sector", 6: "target", 7: "descr", 8: "acct", 9: "timeframe",
             10: "statutory", 11: "monitor", 12: "deviation_body", 13: "noncompliance", 14: "since", 15: "until",
             16: "addl", 17: "coverage", 18: "c1", 19: "c2", 20: "c3a", 21: "c3b", 22: "c3c", 23: "c3d", 24: "c4",
             25: "c5a", 26: "c5b", 27: "c5c", 28: "c5d", 29: "in_force", 30: "frsi"}
    rows = []
    r = 7
    while ws.cell(r, 2).value is not None and str(ws.cell(r, 2).value).strip() != "Data explanation":
        rows.append({n: ws.cell(r, c).value for c, n in heads.items()})
        r += 1
    df = pd.DataFrame(rows)
    df["since_n"] = pd.to_numeric(df["since"], errors="coerce")
    df["until_n"] = pd.to_numeric(df["until"].astype(str).str.replace("+", "", regex=False), errors="coerce")
    return df


def section_rule_table(wb: openpyxl.Workbook) -> pd.DataFrame:
    """Recompute FRSI from criteria; summarise score coding and text on EU-level references."""
    hdr("1b/3. RULE TABLE (F01 'Fiscal Rule database') AND FRSI RECOMPUTATION")
    rt = load_rule_table(wb)
    crit = ["c1", "c2", "c3a", "c3b", "c3c", "c3d", "c4", "c5a", "c5b", "c5c", "c5d"]
    num = rt[crit + ["frsi", "coverage"]].apply(pd.to_numeric, errors="coerce")
    scored = num["frsi"].notna()
    print(f"rule-version rows={len(rt)}; with numeric FRSI (new methodology)={int(scored.sum())}; 'n/a' FRSI={int((rt['frsi'] == 'n/a').sum())}; other={int((~scored & (rt['frsi'] != 'n/a')).sum())}")
    print("in_force=Y rows:", int((rt['in_force'] == 'Y').sum()), " | scored & in_force=N (abolished but scored under new method):",
          int((scored & (rt['in_force'] == 'N')).sum()))
    sc = rt[scored & (rt["in_force"] == "N")]
    print("  scored abolished rules: 'until' years ->", sc["until_n"].value_counts().sort_index().to_dict())
    na = rt[rt["frsi"] == "n/a"]
    print("  n/a (old-method-only) rules: 'until' years max =", na["until_n"].max(), "; 'since' range", na["since_n"].min(), "-", na["since_n"].max())

    # recompute
    s = num[scored]
    cr3 = s[["c3a", "c3b", "c3c", "c3d"]].sum(axis=1)
    cr5 = s[["c5a", "c5b", "c5c", "c5d"]].sum(axis=1)
    frsi = 10 * 0.2 * (s["c1"] / 3 + s["c2"] / 3 + cr3 / 7.5 + s["c4"] / 4 + cr5 / 4)
    diff = (frsi - s["frsi"]).abs()
    print(f"FRSI recomputed from components (formula Read-me/'C-FRSI reconstruction' Q10, x10 to the 0-10 scale): n={len(s)}, max|diff|={diff.max():.4f}, "
          f"share |diff|<0.02 = {(diff < 0.02).mean():.3f}")
    bad = pd.DataFrame({"calc": frsi, "stated": s["frsi"], "diff": frsi - s["frsi"]}).join(rt[["code", "country", "since", "until", "in_force"]])
    bad = bad[bad["diff"].abs() >= 0.02]
    print(f"  rules where stated FRSI differs from recomputed by >=0.02: {len(bad)}; |diff| quantiles {bad['diff'].abs().quantile([.5, .9, 1]).round(2).to_dict()}")
    print(bad.round(2).to_string())
    print("component score support (new methodology):")
    for c in crit:
        print(f"  {c:4s}", sorted(num[c].dropna().unique().tolist()))
    print("Component maxima observed:", {c: float(num[c].max()) for c in crit})
    print("FRSI range:", float(s['frsi'].min()), "-", float(s['frsi'].max()))
    print("Component means (scored rules, in force=Y):")
    sy = num[scored & (rt['in_force'] == 'Y')]
    print((sy[crit].mean() / pd.Series({"c1": 3, "c2": 3, "c3a": 3, "c3b": 1, "c3c": 1.5, "c3d": 2, "c4": 4, "c5a": 1, "c5b": 1, "c5c": 1, "c5d": 1})).round(3).to_dict())
    print("Weight of each criterion in FRSI (points on 0-10): C1 2.0, C2 2.0, C3(a-d) 2.0 (shares of 7.5: a 0.8, b 0.267, c 0.4, d 0.533), C4 2.0, C5 (a-d) 2.0 (0.5 each)")

    print("\nStatutory-base text categories:", rt["statutory"].value_counts().to_dict())
    print("Type:", rt["type"].value_counts().to_dict())
    print("Sector:", rt["sector"].value_counts().head(8).to_dict())
    txt = (rt["descr"].fillna("") + " " + rt["addl"].fillna("") + " " + rt["noncompliance"].fillna("") + " "
           + rt["monitor"].fillna("") + " " + rt["deviation_body"].fillna(""))
    for name, pat in [("SGP / Stability and Growth Pact", r"SGP|Stability and Growth"), ("Fiscal Compact / TSCG", r"Fiscal Compact|TSCG|Treaty on Stability"),
                      ("escape", r"escape"), ("European Commission", r"European Commission|EC\b"), ("Council", r"Council Opinion|Council of the EU"),
                      ("Excessive Deficit", r"Excessive Deficit|EDP"), ("Stability Programme / SCP", r"Stability Programme|SCP|Convergence")]:
        m = txt.str.contains(pat, regex=True, case=False)
        print(f"  rule rows whose text mentions {name:35s}: {int(m.sum()):4d}  (of which in force: {int((m & (rt['in_force'] == 'Y')).sum())})")
    print("Rules whose 'deviation_body' / monitor text names the European Commission:",
          int(rt['deviation_body'].fillna('').str.contains('European Commission').sum()),
          int(rt['monitor'].fillna('').str.contains('European Commission').sum()))
    # escape clause prevalence
    ac = num.loc[sy.index]
    print(f"Escape clause (C5a=1) share among {len(ac)} in-force scored rules: {(ac['c5a'] == 1).mean():.3f}; cyc-adj targets (C5c) {(ac['c5c'] == 1).mean():.3f}; "
          f"margin (C5b) {(ac['c5b'] == 1).mean():.3f}; exclusions (C5d) {(ac['c5d'] == 1).mean():.3f}")
    print("Share of FRSI points attributable to criterion 5 (resilience/flexibility), mean over in-force scored rules:",
          round(float((0.2 * 10 * cr5.loc[sy.index] / 4).mean() / s.loc[sy.index, 'frsi'].mean()), 3))
    return rt


# --------------------------------------------------------------------------- aggregation
def section_aggregation(wb: openpyxl.Workbook) -> None:
    """Verify the rule -> country aggregation in 'C-FRSI reconstruction' against 'C-FRSI' (2024)."""
    hdr("3b. AGGREGATION (rule -> country) VERIFICATION, 'C-FRSI reconstruction'")
    ws = wb["C-FRSI reconstruction"]
    rows = []
    for r in range(8, 132):
        rows.append({"country": str(ws.cell(r, 1).value).strip(), "code": str(ws.cell(r, 2).value), "type": ws.cell(r, 3).value,
                     "sector": ws.cell(r, 4).value, "since": ws.cell(r, 5).value, "until": ws.cell(r, 6).value,
                     "frsi": ws.cell(r, 7).value, "cov": ws.cell(r, 8).value, "rank": ws.cell(r, 9).value,
                     "wfrsi": ws.cell(r, 10).value, "cfri": ws.cell(r, 11).value})
    d = pd.DataFrame(rows)
    num_cols = ["frsi", "cov", "rank", "wfrsi", "cfri", "since", "until"]
    d[num_cols] = d[num_cols].apply(pd.to_numeric, errors="coerce")
    print(f"rule x sector rows={len(d)}, countries={d['country'].nunique()}, rule types={d['type'].value_counts().to_dict()}, sectors={d['sector'].value_counts().to_dict()}")
    # (a) J = G*H/I  (documented as FRSI*10*cov/rank, but G already on 0-10)
    j = d["frsi"] * d["cov"] / d["rank"]
    print(f"weighted FRSI = frsi*cov/rank: max|diff|={float((j - d['wfrsi']).abs().max()):.2e}  (so NO further x10: Q13 formula '(FRSI*10)*coverage/ranking' is inconsistent with column G already on 0-10)")
    # (b) dense ranking within country x sector by FRSI desc
    d["rank_chk"] = d.groupby(["country", "sector"])["frsi"].rank(method="dense", ascending=False)
    print(f"dense rank within country x sector reproduces column I: {(d['rank_chk'] == d['rank']).mean():.3f} of rows")
    mism = d[d["rank_chk"] != d["rank"]][["country", "code", "type", "sector", "frsi", "rank", "rank_chk"]]
    print(mism.head(12).to_string(index=False))
    # (c) country sum vs C-FRSI 2024 sheet
    cf = to_num(country_year_frame(wb["C-FRSI"]))
    sums = d.groupby("country")["wfrsi"].sum()
    chk = pd.DataFrame({"sum_rules": sums, "cfrsi_2024": cf[2024].reindex(sums.index)})
    chk["diff"] = chk["sum_rules"] - chk["cfrsi_2024"]
    print(f"country sum of weighted FRSI vs C-FRSI 2024: n={len(chk)}, max|diff|={float(chk['diff'].abs().max()):.2e}")
    print("Countries in C-FRSI with no active rule in reconstruction:", sorted(set(EU27) - set(sums.index)))
    print(f"C-FRSI 2024 range {cf[2024].min():.2f}-{cf[2024].max():.2f} (mean {cf[2024].mean():.2f}); n rules per country 2024: {d.groupby('country').size().describe().round(2).to_dict()}")
    nr = d.groupby("country").size()
    print("Spearman corr (country 2024: number of active rule-sector rows vs C-FRSI):",
          round(float(pd.concat([nr, cf[2024]], axis=1).dropna().corr(method='spearman').iloc[0, 1]), 3))
    # can the country-year series be rebuilt from the rule-level sheet (active-2024 rules only)?
    rl = wb["FRSI 1990-2024 rule level"]
    yrs = [int(rl.cell(6, c).value) for c in range(6, 41)]
    has = pd.DataFrame(0, index=EU27, columns=yrs)
    for r in range(7, 131):
        c = str(rl.cell(r, 2).value).strip()
        for j, y in enumerate(yrs):
            v = rl.cell(r, 6 + j).value
            if isinstance(v, (int, float)):
                has.loc[c, y] += 1
    cfn = to_num(cf_all := country_year_frame(wb["C-FRSI"]))
    have_idx = cfn.notna()
    have_rl = has > 0
    for lab, ys in [("1995-2011", range(1995, 2012)), ("2012-2015", range(2012, 2016)), ("2016-2023", range(2016, 2024))]:
        ys = list(ys)
        n_idx = int(have_idx[ys].sum().sum())
        n_both = int((have_idx[ys] & have_rl[ys]).sum().sum())
        print(f"  {lab}: C-FRSI numeric country-years={n_idx}; of these with >=1 rule value in the rule-level sheet (active-2024 rules)={n_both} ({n_both / n_idx:.3f}); rule-level has value but C-FRSI missing={int((~have_idx[ys] & have_rl[ys]).sum().sum())}")
    # exact rebuild 2016-2023 from rule-level values x coverage / dense rank within country x sector (static coverage col E)
    print("  (rule-level sheet header A4: 'Rules in red are reformed in this year'; Read-me B25: 'evolution of the FRSI per rule that is still active today')")
    # cross-sheet consistency: reconstruction vs rule table, content-matched (country + type + FRSI within 0.02);
    # the reconstruction 'rule number' code (Q7: country, 0, rule, version, sector) does not reproduce the rule-table codes, so codes are not used.
    rt_ = load_rule_table(wb)
    rt_["frsi_n"] = pd.to_numeric(rt_["frsi"], errors="coerce")
    tmap = {"Budget balance rule": "BBR", "Debt rule": "DR", "Expenditure rule": "ER", "Revenue rule": "RR", "Budget balance Rule": "BBR"}
    rt_["t"] = rt_["type"].map(tmap)
    live = rt_[(rt_["in_force"] == "Y") & rt_["frsi_n"].notna()]
    n_match = 0
    unmatched = []
    for _, r in d.iterrows():
        cand = live[(live["country"].str.strip() == r["country"]) & (live["t"] == r["type"]) & ((live["frsi_n"] - r["frsi"]).abs() < 0.02)]
        if len(cand):
            n_match += 1
        else:
            unmatched.append((r["country"], r["code"], r["type"], round(float(r["frsi"]), 2)))
    print(f"reconstruction rows (n={len(d)}) with an in-force rule-table row of same country+type and FRSI within 0.02: {n_match}; unmatched: {len(unmatched)} -> {unmatched}")
    print("Rule-rows by 'since' year (active rules):", d['since'].value_counts().sort_index().to_dict())
    print("Share of active rules with 'since' in 2012-2015:", round(float(d['since'].between(2012, 2015).mean()), 3))


# --------------------------------------------------------------------------- 2 coverage / 4 missing
def section_coverage_missing(raw: pd.DataFrame, std: pd.DataFrame, rt: pd.DataFrame) -> None:
    """Annual coverage by country and missing/zero coding."""
    hdr("2/4. COVERAGE AND MISSING-VALUE CODING (EU-27)")
    cls = classify_cells(raw)
    win = [y for y in raw.columns if Y0 <= y <= Y1]
    print(f"EU-27 countries in F01 C-FRSI: {len(raw)} (missing from EU27 list: {sorted(set(EU27) - set(raw.index))}); years {raw.columns.min()}-{raw.columns.max()}")
    print(f"Window {Y0}-{Y1}: {len(raw) * len(win)} country-years")
    cnt_all = cls.stack().value_counts().to_dict()
    cnt_win = cls[win].stack().value_counts().to_dict()
    print("C-FRSI cell codes, all years 1990-2024:", cnt_all)
    print("C-FRSI cell codes, window 1995-2023  :", cnt_win)
    print("Blank (truly empty) cells in C-FRSI:", [(c, y) for c in cls.index for y in cls.columns if cls.loc[c, y] == "blank"])
    print("Numeric zeros in raw C-FRSI:", int((to_num(raw) == 0).sum().sum()))
    stdn = to_num(std)
    print("Standardised sheet: non-numeric cells:", int(stdn.isna().sum().sum()), "of", stdn.size)
    floor = stdn.min().min()
    print(f"Standardised floor value (min over all cells) = {floor:.6f}; cells equal to floor within 1e-5: {(abs(stdn - floor) < 1e-5).sum().sum()}")
    # relation of std sheet to raw (zeros for '.')
    r0 = to_num(raw).fillna(0.0)
    xs = r0.values.ravel(); ys = stdn.values.ravel()
    b, a = np.polyfit(xs, ys, 1)
    res = ys - (a + b * xs)
    print(f"std = a + b*raw(with '.'->0): b={b:.6f} a={a:.6f}; implied raw mean={-a / b:.4f}, raw SD={1 / b:.4f}; empirical raw mean={xs.mean():.4f}, "
          f"sd(ddof=1)={xs.std(ddof=1):.4f}, sd(ddof=0)={xs.std(ddof=0):.4f}; R2={1 - res.var() / ys.var():.6f}")
    # same, excluding Croatia pre-1991? ; test mean/sd computed on subset
    for lab, mask in [("all 27x35", np.ones(r0.shape, bool))]:
        pass
    resdf = pd.DataFrame(res.reshape(r0.shape), index=r0.index, columns=r0.columns)
    big = (resdf.abs() > 0.002).sum()
    print("Country-years where std deviates >0.002 z-units from the linear map of the raw C-FRSI, by year:", {int(y): int(n) for y, n in big[big > 0].items()})
    big2 = [(c, int(y), round(float(resdf.loc[c, y]), 3)) for c in resdf.index for y in resdf.columns if abs(resdf.loc[c, y]) > 0.05]
    print(f"Country-years where std deviates >0.05 z from the linear map of raw (n={len(big2)}):", big2)
    print("  residual sd (z units):", round(float(res.std()), 4), "; share |res|<=0.002:", round(float((np.abs(res) <= 0.002).mean()), 3))
    print("Max |residual| by year (years with residual >0.002):", {int(y): round(float(resdf[y].abs().max()), 4) for y in resdf.columns if resdf[y].abs().max() > 0.002})

    # coverage by country: first non-missing raw year, years non-missing in window
    rows = []
    for c in raw.index:
        v = to_num(raw.loc[c])
        first = v.first_valid_index()
        n_win = int(v[win].notna().sum())
        n_pos = int((v[win] > 0).sum())
        rows.append({"country": c, "first_nonmissing_raw": first, "n_nonmissing_1995_2023": n_win, "n_missing_1995_2023": len(win) - n_win,
                     "first_year_std_gt_floor": next((y for y in std.columns if abs(to_num(std).loc[c, y] - floor) > 1e-5), None)})
    cov = pd.DataFrame(rows).set_index("country")
    # From rule table: earliest rule 'since', earliest rule that is in force at 1995
    since_min = rt.groupby("country")["since_n"].min()
    cov["earliest_rule_since_in_ruletable"] = since_min.reindex(cov.index)
    print(cov.to_string())
    nm = cov["n_missing_1995_2023"]
    print(f"Countries with 29/29 non-missing raw years in 1995-2023: {(nm == 0).sum()}; with any missing: {(nm > 0).sum()}; total missing country-years: {int(nm.sum())} of {len(raw) * len(win)} ({nm.sum() / (len(raw) * len(win)):.3f})")
    print("Missing raw country-years per year (window):", {int(y): int(v) for y, v in to_num(raw)[win].isna().sum().items() if v})
    print(f"Std index (floor-filled) non-missing country-years in window: {int(stdn[win].notna().sum().sum())} of {len(raw) * len(win)}")
    n_floor = int((abs(stdn[win] - floor) < 1e-5).sum().sum())
    print(f"Std index equals the no-rule floor in {n_floor} of {len(raw) * len(win)} window country-years ({n_floor / (len(raw) * len(win)):.3f})")
    print("By-year count of floor values in window:", {int(y): int((abs(stdn[y] - floor) < 1e-5).sum()) for y in win})

    for a, b in [(1995, 2023), (2000, 2023), (2012, 2023), (2016, 2023)]:
        w = [y for y in raw.columns if a <= y <= b]
        miss = int(to_num(raw)[w].isna().sum().sum())
        cs = to_num(raw)[w].isna().sum(axis=1)
        print(f"Raw C-FRSI missing ('.'/blank) country-years in {a}-{b}: {miss} of {len(raw) * len(w)} ({miss / (len(raw) * len(w)):.3f}); countries affected: {cs[cs > 0].to_dict()}")
    # Croatia
    print("Croatia raw C-FRSI row:", {int(y): v for y, v in raw.loc['HR'].items() if y <= 2013})

    # rule-table presence vs C-FRSI missing (internal consistency)
    hdr("4b. RULE-TABLE PRESENCE vs C-FRSI MISSING (internal consistency of F01)")
    presence = pd.DataFrame(0, index=raw.index, columns=raw.columns)
    for _, r in rt.iterrows():
        if r["country"] in presence.index and pd.notna(r["since_n"]):
            end = r["until_n"] if pd.notna(r["until_n"]) else 2024
            for y in range(int(max(r["since_n"], 1990)), int(min(end, 2024)) + 1):
                presence.loc[r["country"], y] += 1
    pres_win = presence[win] > 0
    miss_win = to_num(raw)[win].isna()
    print(f"window country-years with >=1 rule in rule table (any version, any sector): {int(pres_win.sum().sum())}")
    print(f"  ... of which C-FRSI is '.'/blank (rule exists in table, index missing): {int((pres_win & miss_win).sum().sum())}")
    print(f"window country-years with NO rule in table but C-FRSI numeric: {int((~pres_win & ~miss_win).sum().sum())}")
    both = pres_win & miss_win
    print("  by country (rule in table but C-FRSI missing):", both.sum(axis=1)[both.sum(axis=1) > 0].to_dict())
    # rule presence dummy reconstructed from table: GG-level coverage
    print("Country-years in window with >=1 rule in table:", int(pres_win.sum().sum()), "of", pres_win.size)
    chg = (pres_win.astype(int).diff(axis=1).abs() > 0)
    print("Country-year changes in rule-presence dummy (table-based), window:", int(chg.sum().sum()), "; countries with >=1 change:", int((chg.sum(axis=1) > 0).sum()))


# --------------------------------------------------------------------------- 5 breaks
def old_std() -> pd.DataFrame:
    """F02 standardised index (28 countries x 1990-2015)."""
    s = xlrd.open_workbook(F02).sheet_by_name("Fiscal Rule Index 1990-2015")
    years = [int(float(s.cell_value(5, c))) for c in range(2, s.ncols)]
    idx = [str(s.cell_value(r, 1)).strip() for r in range(6, s.nrows)]
    data = [[s.cell_value(r, c) for c in range(2, s.ncols)] for r in range(6, s.nrows)]
    return pd.DataFrame(data, index=idx, columns=years).apply(pd.to_numeric, errors="coerce")


def old_rule_table() -> pd.DataFrame:
    """F02 'Fiscal Rule database' rule-version table."""
    s = xlrd.open_workbook(F02).sheet_by_name("Fiscal Rule database")
    heads = {2: "country", 3: "type", 4: "sector", 14: "since", 15: "until", 17: "coverage", 18: "c1", 19: "c2", 20: "c3a", 21: "c3b",
             22: "c3c", 23: "c4a", 24: "c4b", 25: "c5", 26: "in_force", 27: "frsi", 28: "dev2014", 29: "dev2015"}
    rows = []
    for r in range(7, s.nrows):
        code = s.cell_value(r, 1)
        if code in ("", None) or not re.match(r"^\d", str(code)):
            continue
        rows.append({n: s.cell_value(r, c) for c, n in heads.items()} | {"code": code})
    d = pd.DataFrame(rows)
    for c in ["since", "until", "coverage", "frsi", "c5", "c1", "c2", "c3a", "c3b", "c3c", "c4a", "c4b"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def section_breaks(raw: pd.DataFrame, std: pd.DataFrame, rt: pd.DataFrame) -> None:
    """Compare F01 and F02 and test level shifts at survey/benchmark years vs rule-event years."""
    hdr("5. METHODOLOGICAL BREAKS: F01 vs F02")
    std = to_num(std)
    o = old_std()
    ot = old_rule_table()
    print(f"F02 index: {o.shape[0]} countries ({[c for c in o.index if c not in EU27]} not in EU-27 list), years {o.columns.min()}-{o.columns.max()}; F02 rule-version rows={len(ot)}")
    print("F02 criteria: C1 statutory (1-4), C2 adjustment margin (1-3), C3a monitoring (1-3, +1 alert), C3c enforcement body (1-3), C4a non-compliance actions (1-4), "
          "C4b escape clauses (+1), C5 media visibility (1-3); weights: random-weights mean ~ equal weights; country: sum coverage-weighted with rank weights 1, 1/2, 1/3 (Explanantion sheet C57:C79)")
    print("F01 criteria: C1 legal base (0-3), C2 room to revise (0,1,3), C3a-d monitoring/alert/body/forecast (max 7.5), C4 correction (0,1,2,4), C5 resilience (4 binary items); media visibility DROPPED; fixed equal weights 0.2; rank weights 1/rank (dense)")
    cmn = [c for c in EU27 if c in o.index]
    wy = [y for y in range(Y0, 2016)]
    n = std[wy].loc[cmn]
    f2 = o[wy].loc[cmn]
    print("\nLevel comparison, overlap 1995-2015, 27 common countries (both files z-scored over their own panels):")
    print(f"  pooled corr(level)={np.corrcoef(n.values.ravel(), f2.values.ravel())[0, 1]:.3f}; "
          f"corr of country means={np.corrcoef(n.mean(axis=1), f2.mean(axis=1))[0, 1]:.3f}")
    dn, d2 = n.diff(axis=1).iloc[:, 1:], f2.diff(axis=1).iloc[:, 1:]
    print(f"  corr of first differences (year-on-year change)={np.corrcoef(dn.values.ravel(), d2.values.ravel())[0, 1]:.3f}")
    fl_n = std.min().min(); fl_o = o.min().min()
    nf, of = (abs(n - fl_n) < 1e-5), (abs(f2 - fl_o) < 1e-5)
    print(f"  floor cells 1995-2015: F01={int(nf.sum().sum())}, F02={int(of.sum().sum())}; F01 floor while F02 above floor = {int((nf & ~of).sum().sum())}; F02 floor while F01 above = {int((~nf & of).sum().sum())}")
    miss = (nf & ~of).sum(axis=1)
    print("  country-years where F01 shows NO rule but F02 shows a rule (history dropped by back-cast), by country:", miss[miss > 0].to_dict())
    byyr = (nf & ~of).sum()
    print("  same, by year:", {int(y): int(v) for y, v in byyr.items() if v})
    # year-by-year change counts
    print("\nNumber of country-years (27) with a change by year, F01-std vs F02-std (tolerance 0.0015 z):")
    c1 = (dn.abs() > TOL_STD).sum(); c2 = (d2.abs() > TOL_STD).sum()
    print(pd.DataFrame({"F01": c1, "F02": c2}).T.to_string())
    # 2015 -> 2016 splice
    s_all = std.loc[EU27]
    for a, b in [(2014, 2015), (2015, 2016), (2016, 2017)]:
        d = (s_all[b] - s_all[a])
        print(f"  F01 std change {a}->{b}: mean={d.mean():+.3f}, mean|d|={d.abs().mean():.3f}, n changed (>tol)={int((d.abs() > TOL_STD).sum())}")

    # FRSI old vs new at rule level where both exist
    both = rt[(pd.to_numeric(rt['frsi'], errors='coerce').notna())].copy()
    print(f"\nRules scored in F01 whose F02 counterpart exists (country+type+since+coverage match): ", end="")
    ot2 = ot.dropna(subset=["frsi"]).copy()
    ot2["key"] = ot2["country"].str.strip() + "|" + ot2["type"].astype(str) + "|" + ot2["since"].astype("Int64").astype(str)
    both["key"] = both["country"].str.strip() + "|" + both["type"].map({"Budget balance rule": "BBR", "Debt rule": "DR", "Expenditure rule": "ER", "Revenue rule": "RR"}).astype(str) + "|" + both["since_n"].astype("Int64").astype(str)
    mrg = both.merge(ot2[["key", "frsi", "c5"]].drop_duplicates("key"), on="key", suffixes=("_new", "_old"))
    mrg["frsi_new"] = pd.to_numeric(mrg["frsi_new"]);
    print(len(mrg))
    if len(mrg):
        print(f"  mean FRSI new={mrg['frsi_new'].mean():.2f}, old={mrg['frsi_old'].mean():.2f}; corr={np.corrcoef(mrg['frsi_new'], mrg['frsi_old'])[0, 1]:.3f}; "
              f"mean diff (new-old)={float((mrg['frsi_new'] - mrg['frsi_old']).mean()):+.2f}, sd diff={float((mrg['frsi_new'] - mrg['frsi_old']).std()):.2f}")
    print("F02 codes for 'Developments to the rule in 2014/2015' (col AC/AD):",
          ot["dev2014"].astype(str).value_counts().to_dict(), "|", ot["dev2015"].astype(str).value_counts().to_dict())
    print("  -> code 1/3 = FRSI changed ONLY because media visibility (criterion 5) changed, with no change in the rule itself (F02 notes rows 264-266)")

    # ---------- event vs survey-year test on F01 raw C-FRSI
    hdr("5b. LEVEL SHIFTS: rule-event years vs survey/benchmark years (F01 raw C-FRSI, 27 countries)")
    rn = to_num(raw).fillna(0.0)
    d = rn.diff(axis=1).iloc[:, 1:]
    events = pd.DataFrame(0, index=rn.index, columns=d.columns)
    for _, r in rt.iterrows():
        c = r["country"]
        if c not in events.index:
            continue
        if pd.notna(r["since_n"]) and int(r["since_n"]) in events.columns:
            events.loc[c, int(r["since_n"])] += 1
        if pd.notna(r["until_n"]) and int(r["until_n"]) + 1 in events.columns:   # abolition shows in the year after 'until'
            events.loc[c, int(r["until_n"]) + 1] += 1
    ev_win = [y for y in d.columns if Y0 <= y <= Y1]
    # event set B: F02 rule table for years <=2015 (the history the back-cast is built on), F01 rule table for >=2016
    events_b = events.copy()
    events_b.loc[:, [y for y in events_b.columns if y <= 2015]] = 0
    for _, r in ot.iterrows():
        c = str(r["country"]).strip()
        if c not in events_b.index:
            continue
        if pd.notna(r["since"]) and 1990 < int(r["since"]) <= 2015:
            events_b.loc[c, int(r["since"])] += 1
        if pd.notna(r["until"]) and int(r["until"]) + 1 <= 2015:
            events_b.loc[c, int(r["until"]) + 1] += 1
    print("Event definition A = F01 rule table only; B = F02 rule table (<=2015) + F01 rule table (>=2016).")
    chg = d.abs() > TOL_RAW
    for lab, ev in [("A (F01 table only)", events > 0), ("B (F02<=2015 + F01>=2016)", events_b > 0)]:
        print(f"\n--- event definition {lab} ---")
        nonev = chg & ~ev
        tab = pd.DataFrame({"n_changed": chg[ev_win].sum(), "n_with_rule_event": (chg & ev)[ev_win].sum(), "n_events": ev[ev_win].sum(),
                            "mean_abs_change": d[ev_win].abs().mean().round(2)})
        print(tab.T.to_string())
        print(f"Window changes (|d|>{TOL_RAW}): {int(chg[ev_win].sum().sum())}; with same-year rule event: {int((chg & ev)[ev_win].sum().sum())}; without: {int(nonev[ev_win].sum().sum())}")
        ev_pre = [y for y in ev_win if y <= 2015]; ev_post = [y for y in ev_win if y >= 2016]
        for lab2, ys in [("<=2015 (back-cast zone)", ev_pre), (">=2016 (current-method zone)", ev_post)]:
            c = int(chg[ys].sum().sum()); u = int(nonev[ys].sum().sum()); e = int(ev[ys].sum().sum())
            print(f"  {lab2:30s}: changes={c:3d}, unexplained={u:3d} ({u / max(c, 1):.2f}), events={e:3d}, events without index change={int((ev & ~chg)[ys].sum().sum())}")
        lst = [(c, int(y), round(float(d.loc[c, y]), 2)) for y in ev_win for c in d.index if nonev.loc[c, y]]
        print("  unexplained changes (country, year, delta raw pts):", lst)
        ne = d.abs().where(~ev)
        bench = [2012, 2014, 2015, 2016, 2017, 2019, 2022, 2024]
        print("  mean |change| among country-years WITHOUT an event, by year (2008+):", ne[[y for y in d.columns if y >= 2008]].mean().round(2).to_dict())
        from scipy import stats
        bm = ne[[y for y in ev_win if y in bench]].stack().dropna(); ot_ = ne[[y for y in ev_win if y not in bench]].stack().dropna()
        u_ = stats.mannwhitneyu(bm, ot_, alternative="two-sided")
        print(f"  non-event |d|: survey/benchmark years {bench} n={len(bm)} mean={bm.mean():.3f} vs other years n={len(ot_)} mean={ot_.mean():.3f}; Mann-Whitney p={u_.pvalue:.3f}")
        evm = d.abs().where(ev)[ev_win].stack().dropna(); nev = ne[ev_win].stack().dropna()
        print(f"  mean |d| in event country-years={evm.mean():.2f} (n={len(evm)}), non-event={nev.mean():.2f} (n={len(nev)}); share of total |d| mass in non-event cells={nev.sum() / (nev.sum() + evm.sum()):.3f}")
        # pre/post 2016 splice: non-event |d| 2008-2015 vs 2016-2023
        pre = ne[list(range(2008, 2016))].stack().dropna(); post = ne[list(range(2016, 2024))].stack().dropna()
        print(f"  non-event mean|d| 2008-2015={pre.mean():.3f} (n={len(pre)}), 2016-2023={post.mean():.3f} (n={len(post)})")
    # residual regression: |d_it| on event dummy and year-class dummies (descriptive, no inference on clustering)
    long = pd.DataFrame({"absd": d[ev_win].abs().stack(), "event": (events_b > 0)[ev_win].astype(int).stack()}).reset_index()
    long.columns = ["country", "year", "absd", "event"]
    for yr in (2012, 2013, 2014, 2015, 2016, 2017):
        long[f"y{yr}"] = (long["year"] == yr).astype(int)
    import statsmodels.formula.api as smf
    m = smf.ols("absd ~ event + y2012 + y2013 + y2014 + y2015 + y2016 + y2017", data=long).fit(cov_type="cluster", cov_kwds={"groups": long["country"].astype("category").cat.codes})
    print("\nOLS |d_it| ~ F02/F01-event + year dummies (cluster by country): ")
    print(m.summary2().tables[1].round(3).to_string())
    # rule 'since' year histogram
    print("\nRule-table starts by year (all rule versions, EU-27, since>=1990):", rt[rt['since_n'] >= 1990]['since_n'].astype(int).value_counts().sort_index().to_dict())
    print("Rule-table share of starts in 2012-2015:", round(float(rt['since_n'].between(2012, 2015).sum() / rt['since_n'].between(1990, 2024).sum()), 3))

    # 2022 / 2024 jitter between std and raw sheets
    print("\nF01 standardised vs raw sheet: years in which std changes by >tol while raw changes by <=tol (country-years):")
    sd_ = to_num(std).loc[EU27].diff(axis=1).iloc[:, 1:]
    rd_ = rn.loc[EU27].diff(axis=1).iloc[:, 1:]
    odd = ((sd_.abs() > 1e-6) & (rd_.abs() < 1e-6))
    print({int(y): int(v) for y, v in odd.sum().items() if v})
    odd2 = ((sd_.abs() > TOL_STD) & (rd_.abs() < 1e-6))
    print("  ... with std change > tolerance:", {int(y): int(v) for y, v in odd2.sum().items() if v})
    mv = (sd_.abs() > TOL_STD) & (rd_.abs() < 1e-6)
    print("  std moves > tol while raw is constant (country, year, d_std z):", [(c, int(y), round(float(sd_.loc[c, y]), 4)) for c in mv.index for y in mv.columns if mv.loc[c, y]])
    mr = (rd_.abs() > TOL_RAW) & (sd_.abs() <= TOL_STD)
    print("  raw moves > tol while std does not (country, year, d_raw, d_std):", [(c, int(y), round(float(rd_.loc[c, y]), 2), round(float(sd_.loc[c, y]), 4)) for c in mr.index for y in mr.columns if mr.loc[c, y]])
    jt = (sd_.abs() > 1e-6) & (sd_.abs() <= TOL_STD) & (rd_.abs() < 1e-6)
    print(f"  sub-tolerance 'jitter' in std with constant raw: n={int(jt.sum().sum())}, max |d|={float(sd_.where(jt).abs().max().max()):.4f} z, by year {{y: n}}:", {int(y): int(v) for y, v in jt.sum().items() if v})
    print("  raw-sheet changes between 1e-6 and TOL_RAW (tiny, weight updates):", int(((rd_.abs() > 1e-6) & (rd_.abs() <= TOL_RAW)).sum().sum()))


# --------------------------------------------------------------------------- 8 variation
def variation_stats(x: pd.DataFrame, tol: float) -> dict[str, Any]:
    """Variation decomposition for a balanced country x year frame."""
    v = x.values.astype(float)
    n, t = v.shape
    gm = v.mean()
    cm = v.mean(axis=1, keepdims=True)
    tm = v.mean(axis=0, keepdims=True)
    two = v - cm - tm + gm
    d = np.diff(v, axis=1)
    chg = np.abs(d) > tol
    return {"N": n, "T": t, "mean": gm, "sd_total": v.std(ddof=1),
            "sd_between_country_means": cm.std(ddof=1),
            "sd_cross_section_avg_by_year": float(np.mean([v[:, j].std(ddof=1) for j in range(t)])),
            "sd_within_country": float(np.sqrt(((v - cm) ** 2).sum() / (n * t - n))),
            "sd_two_way_within": float(np.sqrt((two ** 2).sum() / ((n - 1) * (t - 1)))),
            "two_way_ratio_to_total_sd": float(np.sqrt((two ** 2).sum() / ((n - 1) * (t - 1))) / v.std(ddof=1)),
            "n_changes": int(chg.sum()), "n_changes_strict_nonzero": int((np.abs(d) > 0).sum()), "n_transitions": int(chg.size),
            "countries_with_change": int((chg.sum(axis=1) > 0).sum()),
            "changes_per_country": chg.sum(axis=1).tolist(),
            "years_with_any_change": int((chg.sum(axis=0) > 0).sum()),
            "tw_sd_after_year_means_only": float(np.sqrt(((v - tm) ** 2).sum() / (n * t - t)))}


def section_variation(raw: pd.DataFrame, std: pd.DataFrame, rt: pd.DataFrame) -> None:
    """Variation for the design: EU-27, 1995-2023."""
    hdr("8. VARIATION FOR THE DESIGN (EU-27, 1995-2023)")
    win = list(range(Y0, Y1 + 1))
    stdn = to_num(std).loc[EU27, win]
    rawn = to_num(raw).loc[EU27, win].fillna(0.0)
    # histogram of nonzero |d| to justify tolerance
    d = np.abs(np.diff(stdn.values, axis=1)).ravel()
    nz = np.sort(d[d > 0])
    print("Std index: sorted smallest nonzero |year-on-year change| (z units):", np.round(nz[:50], 5).tolist())
    gaps = np.diff(np.log10(nz)); k = int(np.argmax(gaps[:200]))
    print(f"  largest log-gap in the 200 smallest nonzero changes sits between {nz[k]:.5f} and {nz[k + 1]:.5f}")
    print("  counts of nonzero |d| below 0.001 / 0.005 / 0.01 / 0.05:", [int((nz < t).sum()) for t in (0.001, 0.005, 0.01, 0.05)], "of", len(nz))
    dr = np.abs(np.diff(rawn.values, axis=1)).ravel(); nzr = np.sort(dr[dr > 0])
    print("Raw C-FRSI: counts of nonzero |d| below 0.01 / 0.05 / 0.1 / 0.2:", [int((nzr < t).sum()) for t in (0.01, 0.05, 0.1, 0.2)], "of", len(nzr))
    out = {}
    for lab, frame, tol in [("STD index (headline), tol=0.0015 z", stdn, TOL_STD), ("STD index, strict nonzero (tol=1e-9)", stdn, 1e-9),
                            ("RAW C-FRSI ('.'->0), tol=0.05 pts", rawn, TOL_RAW)]:
        out[lab] = variation_stats(frame, tol)
    tab = pd.DataFrame({k: {kk: vv for kk, vv in v.items() if kk != "changes_per_country"} for k, v in out.items()})
    print(tab.round(4).to_string())
    for lab, v in out.items():
        cpc = pd.Series(v["changes_per_country"], index=EU27)
        print(f"\nDistribution of number of changes per country [{lab}]:")
        print("  histogram (n changes -> n countries):", cpc.value_counts().sort_index().to_dict())
        print("  by country:", cpc.to_dict())
    # restricted windows
    print("\nSensitivity to window (STD index):")
    rows = {}
    for a, b in [(1995, 2023), (2000, 2023), (2005, 2023), (2012, 2023), (2016, 2023), (1995, 2011), (1995, 2015)]:
        w = list(range(a, b + 1))
        s = variation_stats(to_num(std).loc[EU27, w], TOL_STD)
        rows[f"{a}-{b}"] = {k: s[k] for k in ["sd_total", "sd_within_country", "sd_two_way_within", "two_way_ratio_to_total_sd", "n_changes", "countries_with_change", "years_with_any_change"]}
    print(pd.DataFrame(rows).T.round(3).to_string())
    # change distribution by year
    chg_year = pd.Series((np.abs(np.diff(stdn.values, axis=1)) > TOL_STD).sum(axis=0), index=win[1:])
    print("\nCountry-years with a change, by year (STD, tol):", chg_year.to_dict())
    # count of changes by sign
    dd = np.diff(stdn.values, axis=1); m = np.abs(dd) > TOL_STD
    print(f"Signs of changes: increases={int((dd[m] > 0).sum())}, decreases={int((dd[m] < 0).sum())}; mean size={np.abs(dd[m]).mean():.3f} z; median={np.median(np.abs(dd[m])):.3f}")
    # threshold judgement
    for lab, v in out.items():
        verdict = "ADEQUATE" if v["two_way_ratio_to_total_sd"] >= MIN_TWO_WAY_SD_RATIO else "THIN"
        print(f"  [{lab}] two-way SD / total SD = {v['two_way_ratio_to_total_sd']:.3f} (threshold {MIN_TWO_WAY_SD_RATIO}) -> {verdict}; variance share {v['two_way_ratio_to_total_sd'] ** 2:.3f}")
    # where does the two-way residual variance sit in time?
    v = stdn.values
    two = v - v.mean(axis=1, keepdims=True) - v.mean(axis=0, keepdims=True) + v.mean()
    by_year = pd.Series((two ** 2).sum(axis=0) / (two ** 2).sum(), index=win)
    print("\nShare of two-way residual sum of squares by period: 1995-2011 =", round(float(by_year.loc[1995:2011].sum()), 3),
          "| 2012-2015 =", round(float(by_year.loc[2012:2015].sum()), 3), "| 2016-2023 =", round(float(by_year.loc[2016:2023].sum()), 3))
    nrm = pd.Series((two ** 2).sum(axis=1) / (two ** 2).sum(), index=EU27).sort_values(ascending=False)
    print("Top-5 countries' share of two-way residual SS:", nrm.head(5).round(3).to_dict(), "sum =", round(float(nrm.head(5).sum()), 3))
    # rule-presence dummy (fallback measure)
    rawn_ = to_num(raw).loc[EU27, win]
    dum = (rawn_ > 0).astype(int)
    sw = dum.diff(axis=1).iloc[:, 1:].abs()
    print(f"\nRule-presence dummy (raw C-FRSI numeric): mean={dum.values.mean():.3f}; country-years =0: {int((dum == 0).sum().sum())}; "
          f"switches={int(sw.sum().sum())} in {int((sw.sum(axis=1) > 0).sum())} countries; two-way SD={variation_stats(dum.astype(float), 0.5)['sd_two_way_within']:.3f} (total SD {dum.values.std(ddof=1):.3f}); "
          f"all switches 0->1: {int(((dum.diff(axis=1) == -1).sum().sum()) == 0)}")
    print("  years in which dummy switches:", sw.sum()[sw.sum() > 0].astype(int).to_dict())
    # identification: how many changes are 'staggered' (not common to >= half the countries in that year)
    print("\nDifferential timing: share of country-year changes occurring in years where <=5 countries change:",
          round(float(chg_year[chg_year <= 5].sum() / chg_year.sum()), 3))
    # lagged correlation of std with itself, persistence
    ar = np.corrcoef(stdn.values[:, 1:].ravel(), stdn.values[:, :-1].ravel())[0, 1]
    print(f"Lag-1 autocorrelation of the pooled level = {ar:.4f}")


# --------------------------------------------------------------------------- 9 timing
def section_timing(wb: openpyxl.Workbook, rt: pd.DataFrame) -> None:
    """Timing convention evidence."""
    hdr("9. TIMING")
    print("Rule table 'since'/'until' are integer calendar years (no month/day). Searching workbook text for timing words (start of year, end of year, as of, reference date, survey):")
    pat = re.compile(r"start of|end of|beginning of|as of|reference|survey|calendar|1 january|31 december", re.I)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and pat.search(c.value) and ws.title in ("Read-me", "FRI - dimensions and scores", "C-FRSI reconstruction", "C-FRSI", "Fiscal Rule database"):
                    print(f"  {ws.title}!{c.coordinate}: {c.value[:170]!r}")
    # empirical timing: rule 'since' (rule table) vs first year with a rule-level FRSI value, matched on rule code
    rl = wb["FRSI 1990-2024 rule level"]
    yrs = {c: int(rl.cell(6, c).value) for c in range(6, 41)}
    code_since = {str(r["code"]).strip(): r["since_n"] for _, r in rt.iterrows()}
    lag = []
    for r in range(7, 131):
        code = str(rl.cell(r, 1).value).strip()
        first = next((yrs[c] for c in range(6, 41) if isinstance(rl.cell(r, c).value, (int, float))), None)
        since = code_since.get(code)
        if since is not None and pd.notna(since) and first is not None:
            lag.append((code, since, first))
    df = pd.DataFrame(lag, columns=["code", "since", "first_year_with_FRSI"])
    df["lag"] = df["first_year_with_FRSI"] - df["since"].clip(lower=1990)
    print(f"matched {len(df)} of 116 rule-level rows to the rule table by code; first year with numeric rule-level FRSI minus 'in force since' (clipped at 1990):",
          df["lag"].value_counts().sort_index().to_dict())
    print("  share with lag==0 :", round(float((df['lag'] == 0).mean()), 3))
    print("Interpretation: a rule enters the index in the calendar year of 'in force since' (full-year treatment); mid-year dating cannot be distinguished.")
    # also C-FRSI year of change vs rule since for a handful
    print("Latest vintage notes: Read-me B7 'Last update: 03/03/2026'; Read-me B33 'replies are reviewed ... every year'; C-FRSI W38 path says '18th Survey 2025'.")


def main() -> None:
    """Run the full audit."""
    wb = load_xlsx()
    raw = country_year_frame(wb["C-FRSI"])
    std = country_year_frame(wb["Fiscal Rule Index 1990-2024"])
    section1_structure(wb)
    flagged_cells()
    rt = section_rule_table(wb)
    section_aggregation(wb)
    section_coverage_missing(raw, std, rt)
    section_breaks(raw, std, rt)
    section_variation(raw, std, rt)
    section_timing(wb, rt)


if __name__ == "__main__":
    main()
