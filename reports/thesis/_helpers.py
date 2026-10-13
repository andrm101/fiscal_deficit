"""Shared helpers for the thesis chapters (Quarto Python engine).

Every number in the results chapters is read from the committed JSON files under
``reports/results/`` and formatted here; nothing is typed into the chapter text.
All paths are relative to the repository root, resolved from this file's location.
Missing or incomplete inputs produce a visible "not yet available" note, never an
exception, so the book renders while upstream files are still changing.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from IPython.display import Markdown, display

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = ROOT / "reports" / "results"
FIGS = ROOT / "reports" / "figures"
DOCS = ROOT / "docs"
REPORTS = ROOT / "reports"
LOCAL_FIGS = HERE / "_figures"

MINUS = "\u2212"
PM = "\u00b1"
NA = "n/a"


# ----------------------------------------------------------------------------- loading
def load_json(name: str) -> dict[str, Any]:
    """Read a committed results file; an empty dict if absent or unreadable."""
    try:
        return json.loads((RESULTS / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_text(path: Path) -> str:
    """Read a text file; empty string if absent."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


M1 = load_json("m1_confirmatory.json")
SEC = load_json("secondary.json")
ROB = load_json("robustness.json")
EXP = load_json("exploratory.json")
S4 = load_json("s4_revisions.json")


# ----------------------------------------------------------------------------- formatting
def _bad(x: Any) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def num(x: Any, d: int = 2, sign: bool = False) -> str:
    """Format a number with a true minus sign; NA for missing values."""
    if _bad(x):
        return NA
    s = f"{abs(float(x)):.{d}f}"
    if float(x) < 0 and float(s) != 0.0:
        return MINUS + s
    return ("+" if sign and float(x) > 0 and float(s) != 0.0 else "") + s


def ival(lo: Any, hi: Any, d: int = 2) -> str:
    """Interval as [lo, hi]."""
    if _bad(lo) or _bad(hi):
        return NA
    return f"[{num(lo, d)}, {num(hi, d)}]"


def est_ci(t: dict[str, Any] | None, d: int = 2, sign: bool = False) -> str:
    """Estimate followed by its interval."""
    if not t:
        return NA
    return f"{num(t.get('estimate'), d, sign)} {ival(t.get('ci_lo'), t.get('ci_hi'), d)}"


def pval(p: Any, d: int = 3) -> str:
    """P-value with a floor."""
    if _bad(p):
        return NA
    p = float(p)
    return "<0.001" if p < 0.001 else f"{p:.{d}f}"


def sci(x: Any, d: int = 1) -> str:
    """Scientific notation for very small p-values."""
    return NA if _bad(x) else f"{float(x):.{d}e}"


def pct(x: Any, d: int = 0) -> str:
    return NA if _bad(x) else f"{100 * float(x):.{d}f}%"


def cnt(k: Any, n: Any) -> str:
    """'k of n' or NA."""
    return NA if k is None or n is None else f"{k} of {n}"


def reading_of(t: dict[str, Any] | None) -> str:
    """Pre-registered three-way reading from the stored flags (precedence: excludes zero, equivalent, inconclusive)."""
    if not t or t.get("excludes_zero") is None:
        return "descriptive"
    if t.get("excludes_zero"):
        return "excludes zero"
    if t.get("equivalent_within_sesoi"):
        return f"equivalent ({PM}0.5)"
    return "inconclusive"


# ----------------------------------------------------------------------------- tables
def md_table(df: pd.DataFrame, align: str | None = None, widths: list[int] | None = None) -> str:
    """Pipe table whose dash counts set the relative column widths (pandoc rule)."""
    cols = [str(c) for c in df.columns]
    n = len(cols)
    widths = widths or [max(4, min(30, max([len(c)] + [len(str(v)) for v in df.iloc[:, i]]))) for i, c in enumerate(cols)]
    align = align or "l" + "r" * (n - 1)
    seps = []
    for w, a in zip(widths, align):
        d = "-" * max(3, w)
        seps.append(":" + d[1:] if a == "l" else d[1:] + ":" if a == "r" else ":" + d[2:] + ":")

    def cell(v: Any) -> str:
        s = NA if _bad(v) else str(v)
        return s.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(seps) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def show_table(df: pd.DataFrame, align: str | None = None, widths: list[int] | None = None) -> None:
    """Display a DataFrame as a markdown pipe table."""
    display(Markdown(md_table(df, align, widths)))


def not_yet(what: str) -> None:
    """Visible note for a section that the upstream files do not contain (yet)."""
    display(Markdown(f"> **Not yet available:** {what}. This chapter reads `reports/results/` at render time and fills in once the file contains it."))


# ----------------------------------------------------------------------------- figures
def _placeholder(dst: Path, fname: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 2.2))
    ax.text(0.5, 0.5, f"Figure pending\n{fname}", ha="center", va="center", fontsize=12)
    ax.set_axis_off()
    fig.savefig(dst, dpi=120)
    plt.close(fig)


def figure(label: str, fname: str, caption: str, width: str = "100%") -> None:
    """Emit a markdown figure with a cross-reference label.

    If ``reports/figures/<fname>`` exists it is copied next to the book (Typst only reads
    inside the project) and shown; otherwise a placeholder image and an explicit note appear.
    """
    LOCAL_FIGS.mkdir(exist_ok=True)
    src = FIGS / fname
    if src.exists():
        dst = LOCAL_FIGS / fname
        shutil.copyfile(src, dst)
        note = ""
    else:
        dst = LOCAL_FIGS / (Path(fname).stem + "_pending.png")
        _placeholder(dst, fname)
        note = f" (Figure pending: {fname} has not been generated yet.)"
    cap = " ".join(caption.split()) + note
    print(f"![{cap}](_figures/{dst.name}){{#{label} width={width}}}")


def fig_exists(fname: str) -> bool:
    return (FIGS / fname).exists()


# ----------------------------------------------------------------------------- facts typed once, checked against sources
_FACTS = {
    "n_obs": ("715", "docs/preregistration.md", r"N = 715"),
    "n_ctry": ("27", "docs/preregistration.md", r"27 EU member states"),
    "balanced": ("22", "docs/preregistration.md", r"22 countries have all 27 years"),
    "dropped": ("14", "docs/preregistration.md", r"14 country-years are excluded"),
    "el_total": ("248", "reports/tier1_descriptives.md", r"248 national lower-house elections"),
    "el_sched": ("143", "docs/preregistration.md", r"143 scheduled, 75 early, 1 delayed, 29 unclassified"),
    "el_early": ("75", "docs/preregistration.md", r"143 scheduled, 75 early, 1 delayed, 29 unclassified"),
    "el_del": ("1", "docs/preregistration.md", r"143 scheduled, 75 early, 1 delayed, 29 unclassified"),
    "el_unc": ("29", "docs/preregistration.md", r"143 scheduled, 75 early, 1 delayed, 29 unclassified"),
    "el_both": ("225", "reports/gate3_calendar_and_sample.md", r"225 in both ETAD and ParlGov"),
    "revision": ("0.64", "docs/preregistration.md", r"typical first-outturn revision of the CAPB is 0\.64 pp"),
    "b_bednar": ("0.41", "docs/preregistration.md", r"0\.41 pp: Bedn"),
    "b_afonso": ("0.49", "docs/preregistration.md", r"0\.49 pp: Afonso"),
    "tag": ("preregistration-v1", "docs/post_freeze_log.md", r"preregistration-v1"),
    "tag_commit": ("dca415b", "docs/post_freeze_log.md", r"dca415b"),
    "n_rt": ("189", "docs/decision_log.md", r"189 of 715"),
    "n_scoping": ("24", "docs/post_freeze_log.md", r"identified from 24 countries"),
    "irl": (f"{MINUS}27.6", "reports/tier1_descriptives.md", r"CAPB -27\.6 pp"),
    "g1_sd": ("1.25", "docs/decision_log.md", r"1\.25 pp"),
    "e1_changes": ("30", "docs/exploratory_spec.md", r"30 consecutive-year changes"),
    "wcb_size": ("11\u201312", "docs/preregistration.md", r"11.12%"),
}
FACT_FAILS: list[str] = []
for _k, (_v, _src, _rx) in _FACTS.items():
    if not re.search(_rx, read_text(ROOT / _src)):
        FACT_FAILS.append(f"{_k} ({_src})")


def fact(key: str) -> str:
    """A fact typed once in this module and verified against its source document at import."""
    return _FACTS[key][0]


def fact_warning() -> None:
    """Visible warning when a typed fact no longer matches its source."""
    if FACT_FAILS:
        display(Markdown("> **Fact check failed** against the source documents: " + ", ".join(FACT_FAILS)))


# ----------------------------------------------------------------------------- parsing committed markdown tables
def md_tables(path: Path) -> list[pd.DataFrame]:
    """All pipe tables in a markdown file as DataFrames of strings."""
    out: list[pd.DataFrame] = []
    block: list[str] = []
    for line in read_text(path).splitlines() + [""]:
        if line.strip().startswith("|"):
            block.append(line.strip())
            continue
        if len(block) >= 3:
            rows = [[c.strip() for c in r.strip("|").split("|")] for r in block]
            out.append(pd.DataFrame(rows[2:], columns=rows[0]))
        block = []
    return out


def tier1_table(first_col: str, second_col: str | None = None) -> pd.DataFrame | None:
    """Find a table in the Tier-1 descriptives by its first (and optional second) header."""
    for t in md_tables(REPORTS / "tier1_descriptives.md"):
        cols = list(t.columns)
        if cols and cols[0] == first_col and (second_col is None or (len(cols) > 1 and cols[1] == second_col)):
            return t
    return None


def tier1_value(table: pd.DataFrame | None, row_key: str, col: str, row_col: str | None = None) -> float | None:
    """One float from a parsed Tier-1 table (None if absent)."""
    if table is None or col not in table.columns:
        return None
    rc = row_col or table.columns[0]
    hit = table[table[rc].str.startswith(row_key)]
    if hit.empty:
        return None
    try:
        return float(hit.iloc[0][col])
    except ValueError:
        return None


def tier1_exposure(var: str, sample: str = "confirmatory 715") -> dict[str, float | None]:
    """Row of the exposure-distribution table for one variable in the confirmatory sample."""
    for t in md_tables(REPORTS / "tier1_descriptives.md"):
        if "share > 0 (%)" in t.columns and "sample" in t.columns:
            hit = t[(t.iloc[:, 0] == var) & (t["sample"] == sample)]
            if not hit.empty:
                r = hit.iloc[0]

                def f(c: str) -> float | None:
                    try:
                        return float(r[c])
                    except ValueError:
                        return None

                return {"share_pos": f("share > 0 (%)"), "mean": f("mean"), "sd": f("SD"), "max": f("max"), "mean_pos": f("mean if > 0")}
    return {}


def prereg_power() -> dict[str, dict[str, Any]]:
    """Power table of the pre-registration (section 8), parsed from the committed document."""
    out: dict[str, dict[str, Any]] = {}
    txt = read_text(DOCS / "preregistration.md")
    for key, label in (("beta_S", r"\u03b2_S"), ("gamma_B", r"\u03b3_B \(per SD\)"), ("gamma_W", r"\u03b3_W \(per SD\)")):
        m = re.search(r"\|\s*" + label + r"\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|", txt)
        if m:
            out[key] = {"rho": float(m.group(1)), "rho0": float(m.group(2)), "g2": m.group(3)}
    m = re.search(r"against 0\.41 pp is ([\d.]+)% \(([\d.]+)% with no persistence\) and against 0\.49 pp ([\d.]+)% \(([\d.]+)%\)", txt)
    if m:
        out["power"] = {"p41": float(m.group(1)), "p41_0": float(m.group(2)), "p49": float(m.group(3)), "p49_0": float(m.group(4))}
    return out


# ----------------------------------------------------------------------------- headline, secondary, robustness accessors
def head(name: str) -> dict[str, Any]:
    """Confirmatory target (beta_S, gamma_B, gamma_W) from the committed headline file."""
    return M1.get("targets", {}).get(name, {})


def sesoi() -> float:
    return float(M1.get("sesoi_pp", 0.5))


def rob_rows(group: str) -> list[dict[str, Any]]:
    """Specification rows of a robustness section ('A', 'C', 'D'); empty if not yet written."""
    return [r for r in ROB.get("sections", {}).get(group, {}).get("rows", []) if r.get("status") == "ok"]


def rob_section(group: str) -> dict[str, Any]:
    return ROB.get("sections", {}).get(group, {})


def rob_count(group: str, target: str, key: str) -> tuple[int | None, int | None]:
    """(k, n) from the robustness summary: k specifications with property ``key`` out of n."""
    s = ROB.get("summary", {}).get(group, {}).get(target)
    if not s or not s.get("n"):
        return None, None
    return s.get(key), s.get("n")


def spec_table(rows: list[dict[str, Any]], with_gamma: bool = True) -> pd.DataFrame:
    """Compact table of specification rows: one cell per target with estimate and interval."""
    recs = []
    for r in rows:
        b = r["targets"]["beta_S"]
        g = r["targets"]["gamma_B"]
        rec = {
            "Specification": r["label"] + (f" ({r.get('inference')})" if r.get("group") == "A" else ""),
            "N": r.get("n_obs"),
            "$\\beta_S$ [95% interval]": est_ci(b),
            "p": pval(b.get("p")),
            "Reading": reading_of(b),
        }
        if with_gamma:
            rec["$\\gamma_B$ [95% interval]"] = est_ci(g)
        recs.append(rec)
    return pd.DataFrame(recs)


def sec_outcomes(role: str) -> list[dict[str, Any]]:
    return [o for o in SEC.get("outcomes", []) if o.get("role") == role and o.get("status") == "ok"]


# ----------------------------------------------------------------------------- exploratory (E1-E6) and S4 accessors
def exp_rows() -> list[dict[str, Any]]:
    """The seven family coefficients of the exploratory run (with BH and BY q-values)."""
    return [r for r in EXP.get("multiplicity", {}).get("rows", []) if r.get("status") == "ok"]


def exp_mde(r: dict[str, Any]) -> tuple[float | None, bool]:
    """MDE at the estimated persistence: (value, is_wild_bootstrap). Falls back to the size-adjusted CR1 value."""
    m = r.get("mde", {}).get("ar1_rho_hat", {})
    if m.get("wild_bootstrap_mde") is not None:
        return m["wild_bootstrap_mde"], True
    return m.get("cr1_mde_size_adjusted"), False


def s4_stat(key: str) -> tuple[float | None, list[float] | None]:
    """(estimate, [lo, hi]) of a primary-sample revision statistic."""
    p = S4.get("primary", {})
    return p.get("stats", {}).get(key), p.get("bootstrap_ci", {}).get(key)


def s4_ci(key: str, d: int = 2, as_pct: bool = False) -> str:
    """'estimate [lo, hi]' for a revision statistic."""
    est, ci = s4_stat(key)
    if est is None or not ci:
        return NA
    if as_pct:
        return f"{pct(est)} [{pct(ci[0])}, {pct(ci[1])}]"
    return f"{num(est, d)} {ival(ci[0], ci[1], d)}"
