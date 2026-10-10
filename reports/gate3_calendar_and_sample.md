# Gate 3a: EU-27 election calendar, exposure variables and final-sample selection

Generated 2026-10-10 from `src/normalize/elections.py` and `src/evaluate/sample.py` (offline, deterministic, no seeds). Raw inputs are read-only; SHA-256 of all five election/ageing raw files match `data/raw/elections_ageing/manifest.jsonl` (ETAD_v_1_0_0.csv, ETAD_codebook_ver_1.pdf, view_election.tab, codebook.pdf, demo_pjanind_EU27_OLDDEP_1994_2025.csv). Outputs: `data/interim/election_calendar_eu27.csv`, `data/interim/exposure_eu27.csv`, `reports/gate3_election_exclusions.csv`, this file.

## 0. Headline results

- **Calendar:** 248 EU-27 national lower-house elections 1990-2023 (225 in both ETAD and ParlGov, 6 ETAD only, 17 ParlGov only). ETAD alone supplies 231 (25 countries); **Cyprus and Malta are absent from ETAD** and enter from ParlGov only.
- **Classification (ETAD):** scheduled 143, early 75, delayed 1, unclassified 29 (of which 21 are dated 1994 or later and can touch the 1995+ panel).
- **Right-censoring:** exposure for year *t* needs elections up to 31 Dec of *t*+1. The last year with exposure that is complete for all 27 countries is **2021** (ParlGov ends June 2023, ETAD's 2023 coverage is demonstrably partial). 2022 is complete only on trust in ETAD for 22 of 27 countries. All 27 country-years of 2023 are incomplete.
- **Sample (rule):** t0 = **1995**, end = **2021**, **N = 715** country-years, 27 countries (rule binds at the lag floor: exactly 22 countries are jointly observed in 1995).
- **G1 on the final sample:** two-way-demeaned SD of the lagged OLDDEP1 = **1.25 pp** (0.27 z, residual variance share 0.075): GREEN.

## 1. ETAD file audit

ETAD v1.0.0 (`ETAD_v_1_0_0.csv`, 438,778 bytes; page date 2025-07-16, server Last-Modified 2026-10-08 per the acquisition manifest). The codebook (section 1.1) states 3,127 legislative and presidential elections in 148 countries, 1945-2023.

| Check | Value |
|---|---|
| Data rows (excluding header) | 3133 |
| Distinct ISO3 codes (codebook: 148) | 148 |
| Distinct country names (codebook: 150, two pairs overlap) | 150 |
| Earliest held_year | 1945 |
| Latest held_year | 2023 |
| Latest held_date | 2023-12-20 |
| etype2 = legislative | 2144 |
| etype2 = presidential | 988 |
| Rows with missing held_date | 7 |
| Rows that are empty placeholders (Ireland presidential, no dates, no timing) | 5 |
| Duplicate (cowcode, etype2, held_date) keys (Azerbaijan 2000-11-05 legislative) | 1 |
| Rows minus placeholders minus duplicate key | 3127 |
| Rows with missing etype2 (El Salvador 1982) | 1 |
| Rows with missing etype3 | 2 |
| timing1 = 3 (unknown), all rows | 269 |
| timing2 missing | 275 |
| reason missing | 14 |
| sche_date missing | 277 |
| sche_date later than 2023-12-31 (schedule projected past the data end) | 20 |
| Elections held in 2023 (all countries) | 29 |
| Mean elections per year 2019-2022 | 56.0 |

**Reading.** The file has **3,133 rows, 6 more than the 3,127 in the codebook**; the difference reconciles exactly (3,127) after removing 5 empty Irish presidential placeholder rows and 1 duplicate Azerbaijan key. This is an arithmetic reconciliation, not a statement by the authors. The year range 1945-2023 and 148 country codes agree with the codebook. Version identity is not verifiable offline beyond the SHA-256 in the manifest. Other anomalies: `etype3` is missing for 2 rows; `iso3` BIH and MKD each carry two country names; `timing1 = 3` occurs 269 times in all rows and 151 among legislative rows (proposal 9.1 quotes 264, which does not reproduce from this file); `sche_date` values after 2023 show the schedule is extrapolated from term length for recent rows rather than observed. **ETAD 2023 coverage is partial**: only 29 elections are dated 2023 against a 2019-2022 mean of 56 per year.

## 2. Calendar construction and ETAD-versus-ParlGov cross-check

**Scope.** ETAD `etype2 = legislative` (all such rows are `lower house`; ETAD v1 holds no upper-house rows), ISO3 in the 27-country crosswalk (`config/countries.csv`), held_date 1990-01-01 to 2023-12-31. ParlGov `view_election` rows with `election_type = parliament` collapsed to one row per election (European Parliament rows dropped). Czechoslovakia (CSK) elections are not mapped to CZ or SK.

**Matching.** One-to-one, by country, nearest date first, within **92 days** (one quarter). Justification: 92 days exceeds the largest difference between what is evidently the same election (61 days, Netherlands 2017), and it is harmless for close pairs because matching is one-to-one and nearest-first: the closest two elections of one country are 35 days apart in ParlGov and 42 days in ETAD, and every such pair matches at 0 days. Observed differences are listed in the table.

| abs difference (days) | elections |
|---|---|
| 0 | 190 |
| 1 | 15 |
| 2 | 3 |
| 4 | 1 |
| 7 | 7 |
| 10 | 1 |
| 14 | 5 |
| 21 | 2 |
| 61 | 1 |

**Why dates differ.** The ParlGov codebook records that `election_date` is recoded to the *last* date of the election for CZE and FRA (and other cases), whereas ETAD records the first polling day or round: this explains the 1-day (BG, CZ, IT, LV, SK) and 7-day (FR) differences, the 2-day multi-day vote in NL 2021, and the 14-21-day differences in two-round systems (HU, LT; same weekday in both sources). Five differences are not explained by round structure:

- **Netherlands 2017:** ETAD 2017-05-15 (Monday) vs ParlGov 2017-03-15 (Wednesday), 61 days.
- **Luxembourg 2013:** ETAD 2013-10-30 (Wednesday) vs ParlGov 2013-10-20 (Sunday), 10 days.
- **Finland 2023:** ETAD 2023-03-29 (Wednesday) vs ParlGov 2023-04-02 (Sunday), 4 days.
- **Poland 2007** and **Slovenia 2022:** ParlGov is two days earlier than ETAD and falls on a Friday (2007-10-19, 2022-04-22) while the ETAD dates are Sundays, the modal weekday; ETAD is kept.

**Date rule used for the exposure (`date_used`).** ETAD is primary. ParlGov replaces ETAD only if the dates differ by more than 7 days, the ETAD weekday is not the country's modal polling weekday (pooled over both sources, modal share >= 0.5), and the ParlGov weekday is. This overrides exactly two elections (NL 2017: Wednesday is the Dutch norm; LU 2013: Sunday is the Luxembourg norm). Finland 2023 differs by 4 days and keeps the ETAD date (effect on W below 0.011), although the ETAD weekday (Wednesday) is off the Finnish norm. The test uses election weekdays only, never outcome data.

All 35 date differences between matched elections (ETAD date, ParlGov date, ParlGov minus ETAD in days, which date enters the exposure):

| eurostat_code | etad_date | parlgov_date | date_diff_days_parlgov_minus_etad | date_used |
|---|---|---|---|---|
| BG | 2001-06-17 | 2001-06-18 | 1 | ETAD |
| CZ | 1996-05-31 | 1996-06-01 | 1 | ETAD |
| CZ | 1998-06-19 | 1998-06-20 | 1 | ETAD |
| CZ | 2002-06-14 | 2002-06-15 | 1 | ETAD |
| CZ | 2006-06-02 | 2006-06-03 | 1 | ETAD |
| CZ | 2010-05-28 | 2010-05-29 | 1 | ETAD |
| CZ | 2017-10-20 | 2017-10-21 | 1 | ETAD |
| CZ | 2021-10-08 | 2021-10-09 | 1 | ETAD |
| FI | 2023-03-29 | 2023-04-02 | 4 | ETAD |
| FR | 1993-03-21 | 1993-03-28 | 7 | ETAD |
| FR | 1997-05-25 | 1997-06-01 | 7 | ETAD |
| FR | 2002-06-09 | 2002-06-16 | 7 | ETAD |
| FR | 2007-06-10 | 2007-06-17 | 7 | ETAD |
| FR | 2012-06-10 | 2012-06-17 | 7 | ETAD |
| FR | 2017-06-11 | 2017-06-18 | 7 | ETAD |
| FR | 2022-06-12 | 2022-06-19 | 7 | ETAD |
| HU | 1990-03-25 | 1990-04-08 | 14 | ETAD |
| HU | 1994-05-08 | 1994-05-29 | 21 | ETAD |
| HU | 1998-05-10 | 1998-05-24 | 14 | ETAD |
| HU | 2002-04-07 | 2002-04-21 | 14 | ETAD |
| HU | 2010-04-11 | 2010-04-25 | 14 | ETAD |
| IT | 2013-02-24 | 2013-02-25 | 1 | ETAD |
| LT | 1992-10-25 | 1992-11-15 | 21 | ETAD |
| LT | 2004-10-10 | 2004-10-24 | 14 | ETAD |
| LU | 2013-10-30 | 2013-10-20 | -10 | ParlGov |
| LV | 1993-06-05 | 1993-06-06 | 1 | ETAD |
| LV | 1995-09-30 | 1995-10-01 | 1 | ETAD |
| NL | 2017-05-15 | 2017-03-15 | -61 | ParlGov |
| NL | 2021-03-15 | 2021-03-17 | 2 | ETAD |
| PL | 2007-10-21 | 2007-10-19 | -2 | ETAD |
| SI | 2022-04-24 | 2022-04-22 | -2 | ETAD |
| SK | 1994-09-30 | 1994-10-01 | 1 | ETAD |
| SK | 1998-09-25 | 1998-09-26 | 1 | ETAD |
| SK | 2002-09-20 | 2002-09-21 | 1 | ETAD |
| SK | 2016-03-05 | 2016-03-06 | 1 | ETAD |

**Elections in one source only.**

| category | eurostat_code | election_date_used | etad_date | parlgov_date | detail |
|---|---|---|---|---|---|
| parlgov_only_excluded | CZ | 1990-06-09 |  | 1990-06-09 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| parlgov_only_excluded | CZ | 1992-06-06 |  | 1992-06-06 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| unclassified_no_etad_row | EL | 2023-05-21 |  | 2023-05-21 | No ETAD row (country absent from ETAD, or election missing from ETAD); date from ParlGov only. |
| unclassified_no_etad_row | EL | 2023-06-25 |  | 2023-06-25 | No ETAD row (country absent from ETAD, or election missing from ETAD); date from ParlGov only. |
| etad_only | ES | 2023-07-23 | 2023-07-23 |  | outside ParlGov coverage (not cross-checkable) |
| etad_only | HR | 1990-04-22 | 1990-04-22 |  | outside ParlGov coverage (not cross-checkable) |
| etad_only | HR | 1992-08-02 | 1992-08-02 |  | outside ParlGov coverage (not cross-checkable) |
| etad_only | HR | 1995-10-29 | 1995-10-29 |  | outside ParlGov coverage (not cross-checkable) |
| parlgov_only_excluded | LT | 1990-03-10 |  | 1990-03-10 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| etad_only | LU | 2023-10-14 | 2023-10-14 |  | outside ParlGov coverage (not cross-checkable) |
| parlgov_only_excluded | LV | 1990-04-29 |  | 1990-04-29 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| parlgov_only_excluded | SI | 1990-04-12 |  | 1990-04-12 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| parlgov_only_excluded | SK | 1990-06-09 |  | 1990-06-09 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| parlgov_only_excluded | SK | 1992-06-06 |  | 1992-06-06 | ParlGov-only election before the country's first ETAD election (pre-independence or federal sub-unit row) |
| etad_only | SK | 2023-09-30 | 2023-09-30 |  | outside ParlGov coverage (not cross-checkable) |

Cyprus and Malta (no ETAD rows; all elections from ParlGov, `unclassified`, expected term inferred as the modal rounded ParlGov gap, 5 years for both):

| eurostat_code | elections | first | last | inferred_term_years |
|---|---|---|---|---|
| CY | 7 | 1991-05-19 | 2021-05-30 | 5 |
| MT | 8 | 1992-02-22 | 2022-03-26 | 5 |

Reading: ETAD lacks Cyprus and Malta entirely and lacks Greece 2023 (ParlGov has 2023-05-21 and 2023-06-25); ETAD-only elections are either outside ParlGov's country coverage (Croatia 1990, 1992, 1995: ParlGov starts for Croatia in 2000) or after ParlGov's end (Spain 2023-07-23, Slovakia 2023-09-30, Luxembourg 2023-10-14), so none is a within-coverage disagreement. The 7 excluded ParlGov-only rows are pre-independence or federal sub-unit rows earlier than the country's first ETAD election (CZ and SK 1990 and 1992; LT, LV, SI 1990); none can touch 1995+.

## 3. Classification

**Primary (ETAD), applied in this order** (`classify_etad`): (1) `timing1` missing or 3, or `timing2` missing: unclassified. (2) `timing2 = 1` (delayed) with `dif_days < 0` or `reason` in {7, 9}: unclassified (internal contradiction); else delayed. (3) `timing2 = -1` with `dif_days > 0`: unclassified; else early. (4) `timing2 = 0`: `reason` in {7, 9} gives early (proposal rule, flagged as an override); `timing1 = 2` gives unclassified; else scheduled. ParlGov-only elections have no ETAD row and are unclassified. No outcome data are involved.

Counts over the 248 calendar elections: scheduled 143, early 75, delayed 1, unclassified 29. Dated 1994 or later: scheduled 135, early 64, delayed 1, unclassified 21.

| rule | elections |
|---|---|
| no_etad_row | 17 |
| timing1_unknown | 8 |
| delayed_vs_dif_days_sign | 2 |
| delayed_vs_early_reason | 2 |

**Second classification (ParlGov gap against ETAD term length).** Gap = days from the previous ParlGov parliament election (ParlGov's own `previous_parliament_election_id`) / 365.25. Expected term = ETAD `termlength` of the previous election's row (the term the sitting parliament was elected for), the own row if missing, the latest earlier ETAD term for ParlGov-only elections in ETAD countries, and an inferred modal gap for CY and MT. Early if gap < term - 0.5, delayed if gap > term + 0.5, else scheduled (0.5 year: wide enough for fixed-date and month-window election rules; 0.25 and 1.0 are reported). Gap classes over the calendar: scheduled 166, early 67, delayed 4, unavailable 11.

Agreement with ETAD on the elections ETAD classified and for which a gap exists:

| tolerance_years | n_comparable | n_agree | agree_share | n_etad_early_gap_scheduled | n_etad_scheduled_gap_early | n_other_disagree |
|---|---|---|---|---|---|---|
| 0.250 | 212 | 189 | 0.892 | 10 | 9 | 4 |
| 0.500 | 212 | 182 | 0.858 | 19 | 8 | 3 |
| 1 | 212 | 175 | 0.825 | 30 | 6 | 1 |

At the 0.5-year tolerance 30 of 212 disagree; most are ETAD-early elections that came within half a year of the full term (the gap rule has no resolution there) and ETAD-scheduled elections that the gap rule calls early (e.g. PL 1993-09-19, LV 1995-09-30, RO 1992-09-27, EE 1995-03-05, BE 1995-05-21, DK 1998-03-11). All disagreements are rows `gap_class_disagrees` in `reports/gate3_election_exclusions.csv`:

| class_primary | delayed | early | scheduled |
|---|---|---|---|
| early | 0 | 0 | 19 |
| scheduled | 3 | 8 | 0 |

The gap rule is a cross-check only: ETAD stays primary. A sensitivity variant (`*_gf` columns in the exposure file) assigns unclassified elections their gap class when one exists (25 of 29 unclassified elections get a class; 4 stay unclassified because no gap exists).

### 3.1 Unclassified elections (all listed in `reports/gate3_election_exclusions.csv`)

| eurostat_code | date_used | class_rule | class_gap | gap_years | expected_term_years | timing1 | timing2 | reason | dif_days |
|---|---|---|---|---|---|---|---|---|---|
| CY | 1991-05-19 | no_etad_row | scheduled | 5.440 | 5 |  |  |  |  |
| CY | 1996-05-26 | no_etad_row | scheduled | 5.020 | 5 |  |  |  |  |
| CY | 2001-05-27 | no_etad_row | scheduled | 5 | 5 |  |  |  |  |
| CY | 2006-05-21 | no_etad_row | scheduled | 4.980 | 5 |  |  |  |  |
| CY | 2011-05-22 | no_etad_row | scheduled | 5 | 5 |  |  |  |  |
| CY | 2016-05-22 | no_etad_row | scheduled | 5 | 5 |  |  |  |  |
| CY | 2021-05-30 | no_etad_row | scheduled | 5.020 | 5 |  |  |  |  |
| EE | 1992-09-20 | timing1_unknown | unavailable |  | 4 | 3 |  | 1 |  |
| EL | 2012-06-17 | timing1_unknown | early | 0.110 | 4 | 3 |  | 9 |  |
| EL | 2015-09-20 | timing1_unknown | early | 0.650 | 4 | 3 |  | 7 |  |
| EL | 2023-05-21 | no_etad_row | scheduled | 3.870 | 4 |  |  |  |  |
| EL | 2023-06-25 | no_etad_row | early | 0.100 | 4 |  |  |  |  |
| ES | 2008-03-09 | delayed_vs_dif_days_sign | scheduled | 3.990 | 4 | 2 | 1 | 0 | -5 |
| HR | 1990-04-22 | timing1_unknown | unavailable |  | 4 | 3 |  | 1 |  |
| HR | 1992-08-02 | timing1_unknown | unavailable |  | 4 | 3 |  | 1 |  |
| IT | 2006-04-09 | delayed_vs_early_reason | scheduled | 4.910 | 5 | 2 | 1 | 7 | 331 |
| LV | 1993-06-05 | timing1_unknown | early | 3.100 | 4 | 3 |  | 1 |  |
| MT | 1992-02-22 | no_etad_row | scheduled | 4.790 | 5 |  |  |  |  |
| MT | 1996-10-26 | no_etad_row | scheduled | 4.680 | 5 |  |  |  |  |
| MT | 1998-09-05 | no_etad_row | early | 1.860 | 5 |  |  |  |  |
| MT | 2003-04-12 | no_etad_row | scheduled | 4.600 | 5 |  |  |  |  |
| MT | 2008-03-08 | no_etad_row | scheduled | 4.910 | 5 |  |  |  |  |
| MT | 2013-03-09 | no_etad_row | scheduled | 5 | 5 |  |  |  |  |
| MT | 2017-06-03 | no_etad_row | early | 4.240 | 5 |  |  |  |  |
| MT | 2022-03-26 | no_etad_row | scheduled | 4.810 | 5 |  |  |  |  |
| NL | 1994-05-03 | delayed_vs_early_reason | delayed | 4.650 | 4 | 2 | 1 | 7 | 239 |
| PT | 2022-01-30 | delayed_vs_dif_days_sign | early | 2.320 | 4 | 2 | 1 | 7 | -614 |
| RO | 1990-05-20 | timing1_unknown | unavailable |  | 4 | 3 |  | 1 |  |
| SI | 1992-12-06 | timing1_unknown | early | 2.650 | 4 | 3 |  | 1 |  |

**Proposed treatment (default, as agreed in the Gate 3 plan):** keep every unclassified election in the exposure as `W_U` (pre-window) and in `Post`; report the main model (a) with `W_U` as a separate regressor (or added to `W_S`: column `W_S_plus_U`) and (b) after dropping country-years with `W_U > 0` or `W_D > 0` (`touches_unclassified_or_delayed`); sensitivity (c) uses the gap-filled classes. Delayed and rule-override elections:

| category | eurostat_code | election_date_used | timing1 | timing2 | reason | dif_days | class_gap |
|---|---|---|---|---|---|---|---|
| delayed | HR | 2000-01-03 | 2 | 1 | 4 | 12 | unavailable |
| rule_override_early | IT | 2022-09-25 | 2 | 0 | 9 | -160 | scheduled |

Only HR 2000-01-03 is classified delayed (timing2 = 1, reason 4 = death of the leader, consistent with dif_days = +12). Italy 2022-09-25 is early only through the proposal's `reason in {7, 9}` rule (ETAD timing2 = 0 but dif_days = -160 and timing1 = 2).

Exclusion-table row counts (a row can carry several categories; `from_1994` = election date 1994-01-01 or later):

| category | rows | rows_from_1994 |
|---|---|---|
| date_differs | 35 | 31 |
| gap_class_disagrees | 30 | 22 |
| unclassified_no_etad_row | 17 | 15 |
| unclassified_timing1_unknown | 8 | 2 |
| parlgov_only_excluded | 7 | 0 |
| etad_only | 6 | 4 |
| unclassified_delayed_vs_dif_days_sign | 2 | 2 |
| unclassified_delayed_vs_early_reason | 2 | 2 |
| delayed | 1 | 1 |
| rule_override_early | 1 | 1 |

**Consequence of the default for Cyprus and Malta.** Because their whole calendar is unclassified, dropping `W_U > 0` country-years removes 10 (CY) and 13 (MT) of their country-years in the final sample, leaving fewer than 20 observations each: under the rule, the 'without' sample then has 25 countries (CY and MT fall out), t0 = 1996, N = 633. The gap-filled variant keeps both countries (it labels all their elections scheduled except 1998-09-05 and 2017-06-03 early for Malta).

## 4. Exposure variables

Definition (proposal 9.1, unchanged): pre-window = the 12 months before the election day, `[d - 1 year, d)`; post-window = `[d, d + 1 year)`; day-level arithmetic. `W_S`, `W_E`, `W_D`, `W_U` are the pre-window exposure of scheduled, early, delayed and unclassified elections; `Post` is the post-window exposure of any election. A March election puts about 80 per cent of its pre-window in the previous year; an election on 1 January puts all of it there.

**Two elections in one year / bursts.** `W` is the share of calendar year *t* inside the *union* of same-class pre-windows, which keeps the proposal's bound 0 <= W <= 1. The plain per-election sum is kept in `*_add` columns and exceeds 1 in 13 country-years (Bulgaria 2021-2023, Greece 2012, 2015, 2022-23, Spain 2016, 2019-20, Croatia 2016, Latvia 2011, Netherlands 2003); for a single election union and sum coincide up to leap-day rounding (< 0.3 per cent). Elections of different classes are kept in different columns and may overlap in time.

Exposure panel: 27 countries x 34 years (1990-2023) = 918 rows. On the final sample: W_S > 0 in 240 country-years (mean 0.168), W_E > 0 in 103 (mean 0.073), W_U > 0 in 32, W_D > 0 in 0, Post > 0 in 367.

**Window gate.** The construction was fixed from the election sources alone. Disclosure: before the exposure code was final I printed the AMECO CAPB file's header, row counts and first and last year per country to plan the join; no CAPB value informed any classification, date rule, window or tolerance, and `elections.py` neither imports nor reads CAPB (enforced by a test in a fresh interpreter).

## 5. Right-censoring

A pre-window reaches back 12 months from the election, so the exposure of year *t* depends on every election up to 31 December of *t*+1 (`exposure_complete`). Coverage evidence from the data:

- ParlGov's latest election is 2023-06-25 (data to June 2023): cross-validated coverage ends **2023-06-30**.
- ETAD nominally ends 2023 (latest date 2023-12-20) but is demonstrably incomplete for the EU-27: Greece's two 2023 elections are in ParlGov and not in ETAD, and Poland's last ETAD election (2019-10-13) plus its 4-year term falls on 2023-10-13 with no later election in either source. A term-based test cannot detect a missing *early* election (e.g. the Netherlands, last ETAD election 2021-03-15), so ETAD's H2-2023 coverage is unverifiable for every country.

| country | evidence |
|---|---|
| AT | last observed election 2019-09-29 + term 4 years = 2023-09-29 <= 2023-12-31 but no later election in either source |
| CY | country absent from ETAD: calendar rests on ParlGov (ends 2023-06-30) |
| EL | ParlGov records an election after the last ETAD election: 2023-05-21, 2023-06-25 |
| MT | country absent from ETAD: calendar rests on ParlGov (ends 2023-06-30) |
| PL | last observed election 2019-10-13 + term 4 years = 2023-10-13 <= 2023-12-31 but no later election in either source |

The Austria flag follows from ETAD's own `termlength = 4` for Austria (the 2008-2013 gap in both sources is 5.0 years), so it is conservative and probably a false positive; it only matters on the ETAD-trusted basis.

**Finding.** Cross-validated basis: last year with complete exposure for all 27 countries = **2021**. ETAD-trusted basis: 2022 is complete for 22 of 27 countries (incomplete: AT, CY, EL, MT, PL). **2023: all 27 country-years are incomplete on both bases** (7 have a non-zero known W and 16 a non-zero Post; W is understated by any unobserved 2024 elections, Post only by unobserved H2-2023 ones). AMECO CAPB is observed through 2025, so the outcome does not constrain the end year; the election data do.

**Proposed sample-end rule.** A country-year enters the sample only if its exposure is complete; the common end year is the last year complete for all countries on the cross-validated basis (**2021**). The ETAD-trusted extension to 2022 (22 more country-years, 22 countries) is a sensitivity run, as is a 2021 common end. 2023 is excluded from the confirmatory sample; 2024-25 elections are not hand-coded. Note this shortens the proposal's 1995-2023 window by two years (783 country-years become 729 before missing data).

## 6. Joint coverage and sample selection

Rule (decision log #2): earliest t0 such that from t0 to the end year at least 22 retained countries are jointly observed in every year and every retained country has at least 20 observations. Jointly observed = CAPB (`UBLGBP`, observed years only, 2026-27 forecasts excluded) and the one-year-lagged OLDDEP1 and complete exposure. Negative CAPB values are kept (330 of 715 are negative; minimum -27.62 pp, IE 2010).

**Result: t0 = 1995, end = 2021, N = 715, 27 countries.** t0 = 1995 is the earliest possible year because OLDDEP1 starts in 1994 and is lagged; the rule is satisfied there with zero slack (22 countries). Trace of candidate start years:

| t0 | n_retained | min_yearly_joint_count | passes |
|---|---|---|---|
| 1995 | 27 | 22 | True |
| 1996 | 27 | 23 | True |
| 1997 | 27 | 26 | True |
| 1998 | 27 | 26 | True |
| 1999 | 27 | 26 | True |
| 2000 | 27 | 26 | True |
| 2001 | 27 | 26 | True |
| 2002 | 27 | 27 | True |
| 2003 | 0 | 0 | False |
| 2004 | 0 | 0 | False |

Per-country first and last year, and observations:

| eurostat_code | first_year | last_year | n_obs | n_gaps_inside_span |
|---|---|---|---|---|
| AT | 1995 | 2021 | 27 | 0 |
| BE | 1995 | 2021 | 27 | 0 |
| BG | 1995 | 2021 | 27 | 0 |
| CY | 1997 | 2021 | 25 | 0 |
| CZ | 1997 | 2021 | 25 | 0 |
| DE | 1995 | 2021 | 27 | 0 |
| DK | 1995 | 2021 | 27 | 0 |
| EE | 1995 | 2021 | 27 | 0 |
| EL | 1995 | 2021 | 27 | 0 |
| ES | 1995 | 2021 | 27 | 0 |
| FI | 1995 | 2021 | 27 | 0 |
| FR | 1995 | 2021 | 27 | 0 |
| HR | 2002 | 2021 | 20 | 0 |
| HU | 1995 | 2021 | 27 | 0 |
| IE | 1995 | 2021 | 27 | 0 |
| IT | 1995 | 2021 | 27 | 0 |
| LT | 1995 | 2021 | 27 | 0 |
| LU | 1995 | 2021 | 27 | 0 |
| LV | 1995 | 2021 | 27 | 0 |
| MT | 1995 | 2021 | 27 | 0 |
| NL | 1995 | 2021 | 27 | 0 |
| PL | 1995 | 2021 | 27 | 0 |
| PT | 1995 | 2021 | 27 | 0 |
| RO | 1995 | 2021 | 27 | 0 |
| SE | 1995 | 2021 | 27 | 0 |
| SI | 1997 | 2021 | 25 | 0 |
| SK | 1996 | 2021 | 26 | 0 |

Missingness inside the 1995-2021 window (all gaps are at the start of a series):

| eurostat_code | years_in_window | missing_capb | missing_moderator_lag | exposure_incomplete | not_jointly_observed |
|---|---|---|---|---|---|
| CY | 27 | 2 | 0 | 0 | 2 |
| CZ | 27 | 2 | 0 | 0 | 2 |
| HR | 27 | 6 | 7 | 0 | 7 |
| SI | 27 | 2 | 0 | 0 | 2 |
| SK | 27 | 1 | 0 | 0 | 1 |

Missing cells match the proposal: HR lacks CAPB 1995-2000 and the moderator lag through 2001 (Eurostat flag `e`, value empty, 1994-2000); CY, CZ, SI lack CAPB 1995-96 and SK 1995. Croatia has exactly 20 observations, the minimum the rule allows.

Eurostat flags carried on the lagged moderator (`olddep1_lag_flag`) in the final sample: {'none': 697, 'b': 15, 'e': 2, 'p': 1}. AMECO `capb_obs_status`: all 'A'. Flag meanings follow Eurostat: b = break in time series, e = estimated, p = provisional.

### 6.1 Sensitivity of the sample

| sample | t0 | end_year | n_countries | n_country_years | g1_sd_two_way_pp | g1_share_two_way_residual | g1_status |
|---|---|---|---|---|---|---|---|
| rule (cross-validated end) | 1995 | 2021 | 27 | 715 | 1.246 | 0.075 | GREEN |
| rule, balanced subset | 1995 | 2021 | 22 | 594 | 1.287 | 0.086 | GREEN |
| t0=1996 (same end, retained countries >= 20 obs) | 1996 | 2021 | 27 | 693 | 1.218 | 0.072 | GREEN |
| t0=1997 (same end, retained countries >= 20 obs) | 1997 | 2021 | 27 | 670 | 1.188 | 0.068 | GREEN |
| t0=2002 (same end, retained countries >= 20 obs) | 2002 | 2021 | 27 | 540 | 1.039 | 0.053 | GREEN |
| ETAD-trusted end (country-level completeness) | 1995 | 2022 | 27 | 737 | 1.288 | 0.075 | GREEN |

Notes: the rule and t0 = 1995 coincide (the lag floor binds). The 'balanced subset' is the 22 countries observed in all 27 years (the ones with CAPB from 1995 and a complete lag: AT, BE, BG, DE, DK, EE, EL, ES, FI, FR, HU, IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE). Later starts keep the same end year and drop countries below 20 observations (none). ETAD-trusted end = 2022 per country completeness (AT, CY, EL, MT, PL lose 2022). Dropping `W_U > 0 or W_D > 0` country-years: t0 = 1996, 25 countries, N = 633.

## 7. G1 statistics for the lagged moderator on the final sample

OLDDEP1 at t-1, per cent. Shares are sums of squares about the grand mean; 'year after country' is the extra sum of squares explained by year effects once country effects are in (sequential; equal to the exact orthogonal share on the balanced subset). SD uses RSS/N, as in Appendix D.

| statistic | final sample (unbalanced) | balanced 22 (exact) | Appendix D (1995-2023, 26 balanced) |
|---|---|---|---|
| N country-years | 715 | 594 |  |
| countries | 27 | 22 | 26 |
| mean (pp) | 24.378 | 24.874 | 25.090 |
| total SD (pp) | 4.549 | 4.390 | 5.010 |
| share between countries | 0.506 | 0.462 | 0.443 |
| share common year (after country) | 0.418 | 0.452 | 0.483 |
| share two-way residual | 0.075 | 0.086 | 0.074 |
| SD of country means (pp) | 3.237 | 2.984 | 3.330 |
| two-way-demeaned SD (pp) | 1.246 | 1.287 | 1.360 |
| two-way-demeaned SD, df-corrected (pp) | 1.295 | 1.343 |  |
| two-way-demeaned SD (z units) | 0.274 | 0.293 | 0.270 |
| G1 status | GREEN | GREEN | GREEN |

G1 threshold (Appendix D): two-way-demeaned SD >= 1.0 pp and >= 0.20 z and residual share >= 5 per cent. **Passed on the final sample (1.25 pp) and on every sensitivity sample** (smallest 1.04 pp for t0 = 2002). The margin over the 1.0 pp threshold on the final sample is about 25 per cent.

### 7.1 Between- versus within-country variation of the moderator at the real election dates

For each in-calendar election whose election-year row is in the final sample, the lagged moderator is split into the country mean over the sample (between) and the deviation from it (within); the last column is the SD after removing country and year means from the sample (two-way residual) at those rows.

| elections | n | SD level (pp) | SD between (pp) | SD within (pp) | within share of variance | SD two-way residual (pp) |
|---|---|---|---|---|---|---|
| all | 188 | 4.574 | 3.142 | 3.287 | 0.516 | 1.184 |
| scheduled | 120 | 4.479 | 2.982 | 3.303 | 0.544 | 1.224 |
| early | 53 | 4.480 | 3.016 | 3.306 | 0.545 | 1.151 |

Placeholder dates in Appendix D gave SD level 4.96, between 3.31, within 3.71. With real dates the between SD is about 3.0-3.1 pp and the within SD about 3.3 pp (within share of variance 0.52-0.54): cross-country and within-country variation are of similar size at election dates. But most of the within part is the common upward trend: the two-way residual at election dates is only about 1.2 pp (1.2^2 / 3.3^2 is about 13 per cent of within variance). The within-country interaction therefore rests on about 1.2 pp of trend-free variation and will be imprecise; the between-country interaction draws on 27 cross-sectional units.

## 8. Caveats

- Elections in the sample window dated 1994+ that are unclassified (21) and the Cyprus/Malta dependence on ParlGov alone are the main calendar risks; both are carried as `W_U`.
- ETAD's `timing2`/`reason` are judgemental and internally inconsistent in 4 EU-27 rows; the rule treats these as unclassified rather than resolving them by hand.
- Euro adoption and accession years in `config/countries.csv` are typed from the public record, not read from a repository file, and feed no Gate 3a result.
- Raw sources are untouched; all derived files are regenerated by `python src/normalize/elections.py` followed by `python src/evaluate/sample.py` (prints the selection). The sample panel itself is not persisted by this gate (write scope); `sample.build_panel()` and `select_sample()` rebuild it.

## 9. Files

`config/countries.csv`, `src/normalize/countries.py`, `src/normalize/elections.py`, `src/evaluate/sample.py`, `tests/test_countries.py`, `tests/test_elections.py`, `tests/test_sample.py`, `data/interim/election_calendar_eu27.csv`, `data/interim/exposure_eu27.csv`, `reports/gate3_election_exclusions.csv`, this report.
