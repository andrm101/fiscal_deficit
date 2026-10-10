# Gate 2: EC Fiscal Governance Database audit (S2 moderator)

Scope: can the Fiscal Rules Strength Index (FRSI / country FRI) of the EC "Numerical Fiscal Rules database" serve as a pre-specified SECONDARY moderator in S2 (fiscal-rule strength attenuates the association between scheduled-election exposure and the cyclically adjusted primary balance; EU-27 country-year panel, about 1995-2023)?

Evidence base: the workbook itself, read offline and read-only. Every number below is printed by `scripts/probes/gate2_fgd_audit.py` (run from the project root with plain `python`). Cell references are to F01 unless marked F02.

- F01 = `data/raw/fiscal_governance/nfr_2025_update/Numerical-Fiscal-Rules-database-2025.xlsx` (Read-me B7 "Last update: 03/03/2026"; file property modified 2026-03-03; author field "AMARO Ricardo (ECFIN-EXT)"; internal path in C-FRSI W38 names the "18th Survey 2025").
- F02 = `fiscal_rules_database_en_old_methodology.xls` (2016 update, data to 2015).
- The EC page has no user guide, so nothing outside the workbook is used. Items the workbook does not state are marked "not stated in the workbook".

## 0. Verdict

**CONDITIONAL (downgrade by default).** Of the five criteria that must all hold, the full-window (1995-2023) level index fails two (time-varying measure for essentially all EU-27; unambiguous missing/zero coding), passes with caveats on three. S2 may remain a pre-specified secondary analysis only in the restricted form in section 10; the full-window version must be labelled exploratory.

| # | Criterion | Full window 1995-2023 | Restricted form (2016-2023, L1 raw C-FRSI, "." = missing) |
|---|---|---|---|
| 1 | Time-varying country-year measure, essentially all EU-27 | FAIL: 149 of 783 country-years (19.0%) are "." in the raw sheet; 14 of 27 countries affected (CZ 22, MT 19, SI 20, HU 18, EL 17, HR 14 missing years) | PASS: 1 of 216 missing (CZ 2016) |
| 2 | Documented construction interpretable as strength/enforcement | PASS with caveats: de jure design-strength index (legal base, binding character, monitoring, correction, flexibility); no compliance or enforcement-outcome content; country level mixes strength with number and coverage of rules | same |
| 3 | No unexplained discontinuity in the current-methodology file | PARTIAL: pre-2016 values are a chain-linked back-cast (C-FRSI AB35); 15 of 42 post-2015 changes (36%) coincide with no rule entry/exit; NL 2021-22 dip of -6.70 raw points that reverses in 2023 (+6.85) and is absent from the standardised sheet | PARTIAL: same 15 unexplained post-2015 changes remain; NL 2021-22 must be handled |
| 4 | Modest two-way within variation (my threshold in section 8) | PASS: two-way SD 0.424 z = 0.433 of total SD; 179 changes | PASS, thin: two-way SD 0.214 z; 38 changes in 22 countries in 7 distinct years |
| 5 | Unambiguous missing/zero coding | FAIL: "." (= "Answer missing", Abbreviations D50:E50) in the raw sheet becomes the constant floor -1.082949 in the standardised sheet, so "no rule", "answer missing", "state did not yet exist" and "history not back-cast" are one value | PASS if "." is kept as missing (never zero) |

## 1. Sheet structure and unit of observation

F01 has 8 sheets, all visible (no hidden or very hidden sheets), 1 cell comment in total (rule-level sheet Z107: "CARIOU-REYNELL Emily (ECFIN-EXT): entire line"), no defined names.

| Sheet | Dimensions (rows x cols) | Unit | Header layout / content |
|---|---|---|---|
| Read-me | A1:P38 | text | B7 last update; B9-B12 background; B16-B18 and B22-B28 list of sheets; B32-B34 source statement (responses by Ministries of Finance, reviewed annually, checked by DG ECFIN) |
| Abbreviations | A1:H51 | text | country codes A8:B34 (27 states, "EL" for Greece), D7:E50 abbreviations ("." = Answer missing, D50:E50; "n/a" = Not applicable; "NR" = No response) |
| FRI - dimensions and scores | A1:L58 | text | criteria C1, C2, C3a-d, C4, C5 scoring rules (C10:D55) |
| Fiscal Rule database | A1:AH278 | rule-version | header row 6; 263 data rows 7-269 (27 countries; 120 in force "Y", 142 "N", 1 "n/a"); columns B code, C country, D type, E sector, F target, G description, N since, O until, Q coverage, R-AB criterion scores, AC in force, AD FRSI; notes rows 271-278. B5 and F5 still read "Version of the rule in force in 2017" and "New information of 2017 is in red" (stale template text) |
| FRSI 1990-2024 rule level | A1:AR130 | rule (versions merged) x year | header rows 5-6, 116 rule rows 7-130, years F:AN = 1990-2024; per Read-me B25 only rules "still active today" |
| C-FRSI reconstruction | A1:V131 | rule x sector (active rules) | 124 rows 8-131: country, code, type, sector, since, until, FRSI, coverage, ranking, weighted FRSI, C-FRI; step explanations M5:Q34 |
| C-FRSI | A1:AN64 | country x year | raw country index; header row 6; rows 7-33 = 27 countries; C:AK = 1990-2024; notes AB35, AB36, W38; legend AM1:AN2 |
| Fiscal Rule Index 1990-2024 | A1:AK64 | country x year | standardised version of the same (Read-me B28); same grid |

F02 has 5 sheets, all visible: "Fiscal Rule Index Explanantion" (79 x 4), "Fiscal Rule database" (267 x 30; 249 rule rows), "FRSI 1990-2015" (251 x 31), "Fiscal Rule Index 1990-2015" (34 x 28; header row 6; 28 countries = EU-27 + UK; C:AB = 1990-2015; standardised only, no raw sheet), "Abbreviations".

Headline country-year series for S2: `Fiscal Rule Index 1990-2024` (standardised, Read-me B28) and its raw counterpart `C-FRSI`. Both are analysed below.

## 2. Annual coverage by country (EU-27, 1995-2023, 783 country-years)

All 27 states are present in both country-year sheets; the UK appears only in F02 (row 34). Years are 1990-2024 in F01 (35 columns).

Cell codes in the raw `C-FRSI` sheet, window 1995-2023: 634 numeric, 149 "." (string), 0 blank, 0 numeric zero. All years 1990-2024: 707 numeric, 237 ".", 1 truly blank cell (AT 1992, cell E7), 0 numeric zero. The standardised sheet has 945 numeric cells and no missing cells; 238 cells equal the floor value -1.082949 (149 of them in the window).

| Country | First non-missing raw year | Missing raw years 1995-2023 | Std-index changes 1995-2023 (tol 0.0015 z) |
|---|---|---|---|
| AT | 1999 | 4 | 9 |
| BE | 1990 | 0 | 6 |
| BG | 2003 | 8 | 10 |
| CY | 1990 | 0 | 2 |
| CZ | 2017 | 22 | 1 |
| DE | 1991 | 0 | 7 |
| DK | 1992 | 0 | 8 |
| EE | 1993 | 0 | 5 |
| EL | 2012 | 17 | 5 |
| ES | 1990 | 0 | 9 |
| FI | 1995 | 0 | 15 |
| FR | 1990 | 0 | 11 |
| HR | 2009 | 14 | 4 |
| HU | 2013 | 18 | 4 |
| IE | 2000 | 5 | 6 |
| IT | 1999 | 4 | 11 |
| LT | 1990 | 0 | 8 |
| LU | 1990 | 0 | 9 |
| LV | 1994 | 0 | 5 |
| MT | 2014 | 19 | 1 |
| NL | 1994 | 0 | 7 |
| PL | 1997 | 2 | 12 |
| PT | 2002 | 7 | 8 |
| RO | 1990 | 0 | 5 |
| SE | 1997 | 2 | 5 |
| SI | 2015 | 20 | 1 |
| SK | 2002 | 7 | 5 |

- 13 countries are complete (29 of 29 years) in the window; 14 have gaps.
- Missing country-years per year fall from 14 (1995) to 5 (2009), 1 (2015, 2016: CZ) and 0 from 2017. Missing in 2012-2023: 11 of 324 (3.4%: CZ 5, SI 3, MT 2, HU 1); in 2016-2023: 1 of 216 (CZ 2016).
- Croatia: raw "." for 1990-2008 (a span that includes the years before independence and, beyond 2008, nothing on accession; neither is mentioned in the workbook); first numeric value 2009 (3.53), consistent with the rule-table start 2009. In the standardised sheet Croatia carries the floor from 1990. The workbook states no membership or independence convention (not stated in the workbook).
- The first non-missing raw year is not always the first rule: CY has a local-government rule "since 1986" (rule table) and a numeric value of 0.43 from 1990, and ES, RO and LV carry numeric values from 1990/1990/1994 although their earliest rule-table "since" years are 2002, 2007 and 2013. The pre-2012 numbers for such countries come from the old-methodology back-cast, not from rules listed in F01's rule table (see section 5).

## 3. How the index is built

Source statement: Read-me B32-B34 (annual survey of Ministries of Finance, reviewed annually, checked by DG ECFIN). Method statement: sheet "FRI - dimensions and scores" C5-C8 and "C-FRSI reconstruction" M5:Q34. Inspired by Deroose, Moulin and Wierts (2005) (C8).

Rule-level FRSI (formula in reconstruction Q10): each criterion is divided by its maximum and the five criteria are weighted equally (0.2 each), giving a 0-1 score that the sheets show on a 0-10 scale (the Q10 formula omits the x10 and has a missing operator, "(Cr2/3) 0.2").

| Criterion (FRI sheet) | Scores | Max | Weight in 0-10 FRSI |
|---|---|---|---|
| C1 statutory/legal base (C10:D14) | 3 constitutional or higher than ordinary law; 2 ordinary legal act; 1 coalition agreement; 0 political commitment or annual budget law | 3 | 2.0 |
| C2 room for setting or revising objectives (C16:D19) | 3 cannot be changed except in well-defined situations (escape clauses); 1 parliamentary approval; 0 government can change at any time | 3 | 2.0 |
| C3a monitoring body (C21:D25) | 3 independent authority; 2 court of auditors or parliament; 1 ministry of finance or other government body; 0 no regular public monitoring | 3 | 3 of 7.5 of the 2.0 points |
| C3b real-time monitoring (C27:D30) | 1 / 0.5 / 0 | 1 | 1 of 7.5 |
| C3c body monitoring the correction mechanism (C32:D37) | 1.5 / 1 / 0 | 1.5 | 1.5 of 7.5 |
| C3d independent forecasts (C39:D42) | 2 / 1 / 0 | 2 | 2 of 7.5 |
| C4 correction mechanism (C44:D48) | 4 automatic and pre-determined; 2 automatic or pre-determined; 1 obliged to present measures; 0 none | 4 | 2.0 |
| C5 resilience (C50:D55) | sum of four 1/0 items: C5a escape clauses in line with the SGP, C5b budgetary or MTO safety margin, C5c cyclically adjusted target, C5d exclusions of items outside government control | 4 | 2.0 |

Observed score support in the rule table matches this (for example C2 takes values 0, 1, 3; C3b 0, 0.5, 1; C4 0, 1, 2, 4). Recomputing the FRSI from the components for the 158 scored rule versions reproduces the stated value (|diff| < 0.02) in 140 (88.6%); 18 differ (median |diff| 0.29, 90th percentile 1.53). The largest is FR rule 120131 (stated 0.67 in the rule table, 6.73 recomputed and 6.73 in the reconstruction sheet: apparently a decimal slip). Reconstruction-sheet FRSI values have no same-country, same-type in-force counterpart in the rule table (within 0.02) for 15 of 124 rows.

Country aggregation (reconstruction P11:P14, N20:O31, N16/P16):

1. Rule coverage = share of general-government expenditure of the covered sector (Eurostat) x share of the sector covered by the rule (H column, static: one value per rule, not per year).
2. Within each country and sector, rules are ranked by FRSI (dense ranking, tie example in Q12); the weight is 1/rank (F02 used 1, 1/2, 1/3).
3. Weighted FRSI = FRSI x coverage / ranking. Q13 states "(FRSI*10)*coverage/ranking", but column G is already on the 0-10 scale and the J column equals G x H / I (exactly for 117 of 124 rows; 7 rows deviate by up to 0.447, for example NL 200130 and 200220 have ranks 3 and 4 in column I but the J values imply 4 and 3). A dense rank by country and sector reproduces column I in 110 of 124 rows.
4. Country index = sum of weighted FRSI over all rules (K column). The 2024 C-FRSI equals this sum exactly for all 27 countries (max |diff| 3.6e-15).
5. The sums are not capped: 2024 values run from 8.47 (SI) to 22.26 (BG); over 1995-2023 the raw index runs from 0.067 (IE 2000) to 22.256 (BG), mean 9.06 over non-missing cells. The country index rises with the number of rules: Spearman correlation between the number of active rule-sector rows and the 2024 index is 0.831 (27 countries; 1 to 11 rules per country). A country with eleven weak rules (LT 22.02) scores above a country with one very strong rule (SI 8.47). Strength is therefore not separable from the number and coverage of rules.

Standardised sheet: Read-me B28 says it is "the standardised version"; reconstruction P16 says it is "standardized by dividing by the standard deviation" and refers to a sheet "Fiscal rules Index 1990-2021" (stale name). The data show a z-score (mean subtracted): regressing the standardised sheet on the raw sheet (with "." set to 0) gives slope 0.1634 and intercept -1.0831, implying mean 6.63 and SD 6.12 over all 945 cells (empirical mean 6.630, SD 6.113). The fit is not exact: R2 0.9972, residual SD 0.053 z, only 51.7% of cells within 0.002 z; 18 country-years deviate by more than 0.05 z (ES 2011-2014, LU 2004-2009 and 2013-14, PL 2021-22, RO 2020, LT 2018, NL 2021-22 by 1.11 z). Weights are fixed (0.2 each); F02 used 10,000 random weight sets whose mean approximates equal weights (F02 Explanation C57:C68). The z-score is panel-specific (all 27 x 35 cells, including 238 floor cells), so its level changes if a new vintage changes the panel.

## 4. Missing-value and zero coding

| Place | Code for "no rule / no data" | Meaning stated in the workbook |
|---|---|---|
| C-FRSI (raw) | string "." (237 cells, 1990-2024) and one empty cell (AT 1992) | "." = "Answer missing" (Abbreviations D50:E50); whether "." means "no rule in force" or "no survey answer" is not stated in the workbook |
| Fiscal Rule Index 1990-2024 (std) | constant -1.082949 (238 cells) | not stated in the workbook; equals (0 - mean)/SD, i.e. the raw value 0 |
| Fiscal Rule database (F01) | "n/a" for criteria and FRSI of 105 rule versions | "n/a means that the index for those rules has only been computed with the old methodology or ... will enter into force in the future" (F278) |
| Rule table text columns | "." and "No body"/"No pre-defined action" | "." = answer missing |

There are no numeric zeros in the raw sheet. Window 1995-2023: 149 of 783 country-years (19.0%) are "." / floor; the number of floor cells by year falls from 14 (1995) to 0 (2017 onwards). The same value therefore stands for at least four different situations, and the workbook gives evidence that the "no rule" reading is wrong for part of the missing cells:

- F02 (the same producer, 2016 update) shows rule-based index values for CZ, HU, SI and SE in 53 country-years of 1995-2015 where F01 shows the floor (CZ 16, HU 16, SI 20, SE 1; by year 1 to 3 countries every year). F01 dropped that history because the back-cast is a growth-rate chain anchored on a 2016 score (see section 5): a country with no active rule in 2016 cannot be back-cast.
- F01's own rule table lists rules in force for HU (16 country-years), SI (20) and SE (1) in the window while C-FRSI is "." in those years (37 country-years in total). The reverse also occurs: 39 window country-years with no rule in the table but a numeric C-FRSI (ES, LV and RO back-cast from old-methodology rules not in F01's table).
- Pre-independence or pre-accession years (HR 1990-2008 and others) are coded in the same way as years with no rule.

Correct count of defensible "true zero" (no national numerical rule) country-years: not determinable from F01; between 96 (149 minus the 53 contradicted by F02) and 149.

## 5. Methodological breaks: F01 versus F02

Differences in construction:

| Feature | F02 (old, 1990-2015) | F01 (current, 1990-2024) |
|---|---|---|
| Criteria | C1 statutory base (1-4), C2 adjustment margin (1-3), C3a monitoring (1-3, +1 alert), C3c enforcement body (1-3), C4a non-compliance actions (1-4), C4b escape clauses (+1), C5 media visibility (1-3) | C1 (0-3), C2 (0,1,3), C3a-d, C4 (0-4), C5 resilience (four 1/0 items); media visibility dropped; independent forecasting body (C3d), cyclically adjusted target, margins and exclusions added |
| Weights | mean of 10,000 random weight sets (about equal) | equal (0.2) |
| Rank weights | 1, 1/2, 1/3 | 1/rank (dense) |
| Countries | EU-27 + UK (28) | EU-27 |
| Years | 1990-2015 | 1990-2024 |
| Standardised file | z-score over 28 x 26 cells (floor -0.991109) | z-score over 27 x 35 cells (floor -1.082949) |

The splice (C-FRSI AB35, AB36): "scores awarded prior 2015 have been backtracked by multiplying the new 2016 score with the growth rate of the old FRSI scores. This was done to respect the trajectory of rule strengthening between both indices." F01 values before 2016 are therefore the old-methodology trajectory rescaled to the new 2016 level. Rules scored under the new criteria exist only from about 2012: the rule-level sheet gives at least one rule value for only 48.0% (154 of 321) of the numeric C-FRSI country-years in 1995-2011, 91.8% (90 of 98) in 2012-2015 and 98.6% (212 of 215) in 2016-2023. In the rule table, scored rule versions have 'until' dates only from 2013 on; the 105 "n/a" versions are old-methodology only (F278). Only three rules still in force after 2015 are unscored ("n/a"): DE 6012 (to 2020), PL 21022 (to 2020), FI 110151 (2020-2022).

Numerical comparison, overlap 1995-2015, 27 common countries (both z-scored on their own panel): pooled correlation of levels 0.923; correlation of country means 0.885; correlation of year-on-year changes 0.923. Country-years with a change (tol 0.0015 z) per year are almost identical in the two files (for example 2012: 15 versus 17; 2013: 13 versus 13; 2014: 19 versus 19; 2015: 16 versus 14), as expected from a growth-rate chain. At rule level, 82 rules scored in both files (matched on country, type and start year) have a mean FRSI of 6.24 (new) versus 7.20 (old), correlation 0.481, mean difference -0.95, SD of difference 1.70: the two rule-level scales do not rank rules alike.

F02 also records, for 2014 and 2015, that some rules' FRSI changed only because media visibility changed with no change in the rule (codes 1 and 3 in F02 'Fiscal Rule database' AC/AD; legend rows 264-266): 11 rules in 2014 (code 1: 10, code 3: 1) and 11 in 2015 (code 1: 11). F01 does not say whether the back-cast carries these non-rule changes.

Test for level shifts at survey/benchmark years versus rule-introduction years (raw C-FRSI, "." = 0, |change| above 0.05 points counts as a change; event = a rule starts in the year, or ends the year before; for 1996-2015 events come from F02's rule table, for 2016-2023 from F01's):

| Zone | Index changes | With a same-year rule event | Without |
|---|---|---|---|
| 1995-2015 (back-cast zone) | 132 | 130 (98.5%) | 2 (SE 1997 +3.44; FR 2010 -0.51) |
| 2016-2023 (current-method zone) | 42 | 27 (64.3%) | 15 (36%): EL 2016 +0.50, FI 2016 +0.40, EL 2017 +2.27, DE 2018 +0.53, ES 2018 +0.53, FR 2018 +0.21, HU 2018 +0.67, FI 2019 +0.33, LT 2019 +0.50, DE 2020 +0.07, ES 2021 +0.20, NL 2021 -6.70, PT 2021 +0.17, NL 2023 +6.85, SK 2023 +1.94 |

- Mean absolute change is 2.19 raw points in event country-years (n = 187) and 0.04 in non-event country-years (n = 596). In non-event country-years, mean |change| in benchmark/survey years (2012, 2014, 2015, 2016, 2017, 2019, 2022, 2024; n = 116) is 0.034 versus 0.046 in other years (n = 480); Mann-Whitney p = 0.287. There is no level shift at survey or benchmark years that is not tied to a rule event. The 2015 to 2016 splice itself shows no jump: mean change in the standardised index +0.019 z, mean |change| 0.021 z, 7 countries above tolerance.
- The big movement is the rule-introduction wave of 2012-2015: mean signed raw change +0.51 (2012), +2.45 (2013), +3.53 (2014), +0.93 (2015); all 59 index changes in 2012-2015 coincide with a rule entry or exit (13, 13, 19 and 14 in the four years); 54% of active rules have a start year in 2012-2015 (32 of them 2014, 21 2015; share of all rule-version starts in 2012-2015 is 39.4%). A pooled regression of |change| on a rule-event dummy and year dummies (clustered by country) gives an event coefficient of 1.87 points (SE 0.17) and positive extra for 2013 (+1.62, SE 0.57) and 2014 (+2.29, SE 0.88), none for 2012 or 2015: these years carry larger reforms, which is consistent with Fiscal Compact transposition but cannot be separated from a questionnaire-year effect with the workbook alone (the survey wave dates are not stated).
- Discontinuities inside F01 itself: (i) the standardised sheet is not a linear function of the raw sheet (R2 0.9972); in 2022-2024 it shows sub-tolerance noise where the raw sheet is constant (55 country-years, max 0.0049 z, by year 2015: 1, 2022: 18, 2023: 17, 2024: 19; for example AT 1.115278, 1.114756, 1.115278, 1.114761 in 2021-2024 versus a constant raw 13.4768); (ii) std moves above tolerance while raw is constant in 6 country-years (DK 2015, LV 2020, LV 2022, PL 2022, RO 2020, RO 2021, up to 0.080 z); (iii) raw moves while std does not in 5 (DE 2020, LT 2019, NL 2023, PL 2020, PL 2023); (iv) NL raw 19.62 (2017-2020), 12.92 (2021-2022), 19.76 (2023) while std is smooth (2.1165, 2.1394, 2.1394, 2.1394); (v) 14 cells are flagged by the producer as retroactive recalculation (C-FRSI AM1 legend; FR 2022-2024, LT 2015-2024, NL 2024) and 4 as "substantial change" (AM2 legend; HR, LV, PL, SK 2024). The rule-level and rule-table sheets also disagree about the start year of at least rule SK 26071 (rule table 2022, reconstruction 2023; the index jumps in 2023).

## 6. Escape clauses, flexibility, EU-level rules

- Scope (Read-me B10-B11): "national numerical fiscal rules" of all types (budget balance, debt, expenditure, revenue) at all levels of government. EU-level rules (SGP, Fiscal Compact) are not rows in the rule table. National rules that transpose or refer to EU requirements are included, and the EU institutions enter the scoring text: 5 rule rows mention the SGP (AT 1051, DK 7041, IE 14051, IE 14052, NL 20021), 3 the Fiscal Compact or TSCG (CY 4012, EL 9041, SK 26061), 22 rows mention the European Commission (or "EC") in the text columns (16 name it in the "body establishing a deviation" column L, 5 in the monitoring column K; for example CY 4031, EL 9041, FI 11091, IE 14052, LU 17052). The workbook does not state how the European Commission as deviation-monitoring body is scored in C3c ("independent authority" or "ministry/government body"), nor whether national rules whose enforcement lies mostly in EU law are scored as strong because of that enforcement. The national-versus-EU distinction is only recoverable from free text.
- Escape clauses and flexibility are criterion C5 (rule-level 20% of the FRSI): C5a "clearly defined escape clauses in line with the SGP", C5b margins, C5c cyclically adjusted targets, C5d exclusions. Among the 120 in-force scored rules: C5a = 1 for 38.3%, C5b 12.5%, C5c 36.7%, C5d 25.8%. Mean C5 contribution is about 9% of the mean FRSI. In F01 flexibility therefore raises the index, whereas in F02 only escape clauses added one point to the enforcement criterion (F02 Explanation C49).
- C2 also references escape clauses ("except in well-defined situations (i.e. escape clauses)", FRI D17).
- Not stated in the workbook: which events trigger the clauses, whether the 2020-2023 general escape clause activation changes any score, and whether scores are revised when clauses are activated. The word "escape" occurs in none of the rule-table text columns searched (description, additional information, non-compliance actions, monitoring and deviation bodies); C5a is a 1/0 flag. In 2020 five raw values move (BG +0.67, LU +0.50, FI +0.34, PL +0.17, DE +0.07); the workbook does not say whether any is related to the clause activation.

## 7. What the measure represents, per component

| Component | Represents | Evidence |
|---|---|---|
| C1 legal base | legal strength (de jure) | scale is the hierarchy of norms (D11:D14) |
| C2 room to revise | legal bindingness (de jure rigidity) | D17:D19 "can be changed ... by the Government" |
| C3a monitoring body | institutional monitoring set-up; partly practice ("no report systematically assessing compliance", D25) | D22:D25 |
| C3b real-time alert | enforcement design (ex-ante) | D28:D30 |
| C3c body for deviation / correction | enforcement institution (ex-ante) | D33:D37 |
| C3d independent forecasts | country-level institutional feature, repeated on every rule of the country | D40:D42 |
| C4 correction mechanism | enforcement design (ex-ante automatic or pre-defined consequences) | D45:D48 |
| C5 resilience | flexibility (de jure), scored as strength | D52:D55 |
| Coverage and rank weights | scope of the rule (share of GG spending) | P11, P12 |
| Compliance | not measured | no variable on actual compliance, sanctions imposed or deviations observed; "Non-compliance actions" (column M of the rule table) is the ex-ante consequence |

The index is a de jure design-strength index. It is not an enforcement-outcome or compliance measure. The country aggregate additionally rewards number and coverage of rules (section 3).

## 8. Variation for the design (EU-27, 1995-2023, N = 27, T = 29, 783 country-years)

Headline: standardised index. Tolerance for a "change": 0.0015 z, placed in the only clear gap in the sorted non-zero year-on-year changes (35 values below 0.001 and 41 below 0.005, then 0.00326 and 0.00489, then 0.00815 and above; the 35-41 small values are recalculation noise). The raw sheet has no clean gap (counts of non-zero |change| below 0.01 / 0.05 / 0.1 / 0.2: 7, 12, 17, 32 of 183), so 0.05 raw points is a judgement call; strict non-zero counts are given as well.

| Statistic | STD index (tol 0.0015 z) | STD, strict non-zero | RAW C-FRSI ("." = 0, tol 0.05) |
|---|---|---|---|
| Mean | 0.116 | 0.116 | 7.339 |
| Total SD | 0.978 | 0.978 | 5.973 |
| Between-country SD (of country means) | 0.452 | 0.452 | 2.748 |
| Cross-sectional SD (mean of 29 yearly SDs) | 0.609 | 0.609 | 3.731 |
| Within-country SD | 0.886 | 0.886 | 5.420 |
| SD after year means only removed | 0.614 | 0.614 | 3.764 |
| SD after two-way (country and year) demeaning | 0.424 | 0.424 | 2.617 |
| Two-way SD / total SD (variance share) | 0.433 (0.188) | 0.433 (0.188) | 0.438 (0.192) |
| Country-years with a change (of 756 transitions) | 179 | 214 | 171 (183 strict) |
| Countries with at least one change | 27 | 27 | 27 |
| Years with at least one change | 27 of 28 (none 1996) | | |
| Increases / decreases | 140 / 39 | | |

Distribution of the number of changes per country (std, tol 0.0015): 1 change: 3 countries (CZ, MT, SI); 2: 1 (CY); 4: 2; 5: 6; 6: 2; 7: 2; 8: 3; 9: 3; 10: 1; 11: 2; 12: 1 (PL); 15: 1 (FI). Median about 6; the raw sheet gives a similar shape (1 change: CZ, MT, SI; maximum 14, FI).

Sensitivity to the window (std):

| Window | Total SD | Within-country SD | Two-way SD | Two-way / total | Changes | Countries with a change | Years with a change |
|---|---|---|---|---|---|---|---|
| 1995-2023 | 0.978 | 0.886 | 0.423 | 0.433 | 179 | 27 | 27 |
| 2000-2023 | 0.966 | 0.857 | 0.417 | 0.432 | 163 | 27 | 23 |
| 2005-2023 | 0.951 | 0.833 | 0.414 | 0.436 | 148 | 27 | 18 |
| 2012-2023 | 0.783 | 0.596 | 0.387 | 0.495 | 93 | 27 | 11 |
| 2016-2023 | 0.612 | 0.235 | 0.214 | 0.349 | 38 | 22 | 7 |
| 1995-2011 | 0.595 | 0.326 | 0.280 | 0.470 | 71 | 20 | 15 |
| 1995-2015 | 0.750 | 0.587 | 0.375 | 0.500 | 134 | 26 | 19 |

Changes by year (std): 1997: 4, 1998: 3, 1999: 6, 2000: 3, 2001: 4, 2002: 3, 2003: 4, 2004: 2, 2005: 2, 2006: 5, 2007: 5, 2008: 6, 2009: 8, 2010: 6, 2011: 10, 2012: 15, 2013: 13, 2014: 19, 2015: 16, 2016: 7, 2017: 8, 2018: 5, 2019: 5, 2020: 7, 2021: 7, 2022: 3, 2023: 3. The pooled lag-1 autocorrelation of the level is 0.954.

Where the two-way residual variance sits: 42.4% of its sum of squares in 1995-2011 (the back-cast zone, largely from the old methodology), 24.0% in 2012-2015, 33.6% in 2016-2023. The five largest contributors (BG, SE, LT, DK, EE) hold 37.6%. 28.5% of changes occur in years in which at most 5 countries change (the rest are in common-reform years, which the year effects absorb in part; differential timing across countries is what remains).

Threshold (judgement, not a published standard): two-way SD at least 0.25 of the total SD (variance share at least 6.25%), and at least 30 changes in at least 15 countries. Justification: with country and year fixed effects the interaction coefficient's standard error scales inversely with the standard deviation of the demeaned moderator, so a ratio of 0.25 means the moderator contributes at most one quarter of the effective spread of a freely varying regressor; this is in the spirit of the fixed-effects inefficiency argument for slow-moving regressors (Plümper and Troeger, 2007, Political Analysis 15(2), 124-139; the exact cut-off here is mine). Result: full window 0.433 (pass), 2012-2023 0.495 (pass), 2016-2023 0.349 (pass, 38 changes in 22 countries). Reading note: if "modest" in the criterion is meant as an upper bound (variation small enough that reform endogeneity does not dominate), the full-window figure is not modest, because 18.8% of the variance survives two-way demeaning and most of it is the 2012-2015 reform wave (140 of the 179 changes are increases).

Fallback measure: a rule-presence dummy (raw C-FRSI numeric) has mean 0.810, 149 zero cells, only 14 switches (all 0 to 1) in 14 countries (1997: 2, 1999: 2, 2000: 1, 2002: 2, 2003: 1, 2009: 1, 2012: 1, 2013: 1, 2014: 1, 2015: 1, 2017: 1), and two-way SD 0.262 against total SD 0.393. It inherits the coding problem of section 4 and is far sparser than the level index in the restricted window.

## 9. Timing convention

- Not stated in the workbook: whether a year's value refers to 1 January or 31 December, the reference date of the survey, or the publication date by year. Read-me B10 and B33 say only that information is gathered annually and replies are reviewed every year; the vintage is "Last update: 03/03/2026" (B7) from the "18th Survey 2025" (C-FRSI W38).
- Dating is annual: rule 'since' and 'until' are integer calendar years (rule table N, O; "2024+" = still in force). Matching the 100 rule-level rows that can be linked to the rule table by code, the first year with a numeric rule-level FRSI equals the 'in force since' year in 71 of 100 rows, with 29 differing (mostly earlier than 'since', because rule-level rows merge versions). A rule therefore enters the index for the full calendar year of its start; mid-year starts are not distinguished.
- Revisions are retroactive (C-FRSI legend AM1: "scores adjusted for previous years as well to reflect a calculation update"; 14 flagged cells), and the 2016 splice rewrites history. The value for year t is the producer's ex-post knowledge as of March 2026, not what was known in year t.
- Lag: use the one-year lag (index at t-1) for the moderator. Reasons: (a) rule entry is dated to a whole calendar year although a rule adopted late in year t cannot have shaped the year-t budget and election-year behaviour; (b) reforms in year t can be a response to the year-t fiscal position and election timetable; (c) retroactive revisions mean the t value is unavailable to agents at t. A contemporaneous version is acceptable only as a robustness check.

## 10. Decision and exactly what to do

**Verdict: CONDITIONAL.**

1. Downgrade the full-window (1995-2023) version of S2 to exploratory. Reasons: 19.0% of country-years are "." in the raw sheet and are filled with an uninformative constant in the standardised sheet; 53 of those cells contradict F02 (CZ, HU, SI, SE); pre-2016 values are a growth-rate chain anchored on the 2016 score, and 52% of 1995-2011 numeric country-years have no new-methodology rule behind them (section 4, 5).
2. Keep S2 as a pre-specified secondary only in this restricted form, written into the analysis plan before estimation:
   - Window 2016-2023 (primary), with 2012-2023 as a pre-specified robustness window (11 of 324 missing, the back-cast zone 2012-2015 included).
   - Moderator = first lag (t-1) of the raw `C-FRSI` (or its z-score computed on the estimation sample), with "." kept as missing and the country-year dropped (never recoded to 0 or to the floor). Do not use the standardised sheet (panel-specific, not an exact transform of the raw sheet, 55 sub-tolerance noise cells in 2022-2024).
   - Resolve NL 2021-2022 before use (raw 12.92 versus 19.62 and 19.76 around it; the standardised sheet shows no dip): pre-specify either the standardised value for those two cells or exclusion with a sensitivity run.
   - Report a leave-one-country-out check, since the five largest contributors hold 37.6% of the two-way residual variation in the full window, and a version that drops the post-2015 changes not tied to a rule event if the producer cannot explain them.
   - State in the plan that identification in this window comes from 38 changes in 22 countries in 7 distinct years (two-way SD 0.214 z, 0.349 of total SD) and is therefore thin; state the minimum detectable moderation effect before looking at the outcome.
3. A rule-presence dummy is not recommended as a primary alternative: 14 switches, all 0 to 1, concentrated before 2004, and it carries the same coding problem. It can serve as an exploratory robustness check.
4. Interpret results as de jure design strength of national rules (and rule count/coverage), never as enforcement or compliance, and never use causal language from the interaction alone.

## 11. Open questions only the data producer can answer

1. Does "." in C-FRSI mean "no numerical rule in force", "no survey response", or "outside the survey (state not yet existing or not yet a member)"? Is the floor -1.082949 intended to mean "no rule"?
2. Why does F01 show no index for CZ before 2017, HU before 2013, SI before 2015, MT before 2014 and EL before 2012, when F02 (2016 update) shows rule-based values for CZ, HU, SI and EL earlier (CZ 16, HU 16, SI 20 country-years)? Were those rules abolished and dropped from the back-cast, or reclassified?
3. Exact back-cast algorithm for years before 2016: the old FRSI series used (with or without media visibility), the anchor year per country, treatment of countries whose rules in 2016 differ from earlier rules, and the treatment of rules abolished before 2012 (rows scored "n/a").
4. Why is the standardised sheet not an exact linear transform of the raw sheet (NL 2021-2022, 2022-2024 noise, ES/LU/PL differences), and which sheet is authoritative? What are the mean and SD used?
5. Is the NL raw dip of 2021-2022 (12.92) an error or a real change in a rule's coverage?
6. What are the survey reference date (1 January or 31 December) and the publication calendar by data year, and how are mid-year entries dated?
7. How is the European Commission scored as a deviation or monitoring body (C3a, C3c), and how are national rules whose binding force is EU law scored for C1 and C4?
8. What are the 15 post-2015 changes without a rule entry or exit (for example EL 2017 +2.27, SK 2023 +1.94, DE/ES 2018) and the 2018-2021 changes: re-scoring after survey updates, coverage-weight updates, or sector re-allocation? Is the coverage weight (H column) time-varying in the series although only one value per rule is shown?
9. Rank column I: why do 14 of 124 rows differ from a dense rank by country and sector, and why do NL 200130 and 200220 carry ranks that conflict with their weighted values? Which version of FR rule 120131 is correct (0.67 or 6.73)? Why do reconstruction FRSI values differ from rule-table values for 15 rows?
10. Was the 2020-2023 general escape clause ever reflected in C5a or any score, and is C5a revised when a clause is activated?
11. Is the country sum intended to be unbounded (maximum 22.26), and is the number-of-rules effect (Spearman 0.83 with rule count) intended?
12. Are there plans for a vintage archive, so the series can be tested for revisions between survey waves?

## Reproduction

`python scripts/probes/gate2_fgd_audit.py` from `C:\Users\andre\Desktop\Sandbox\Fiscal_Deficit` (offline; pandas, numpy, openpyxl, xlrd, scipy, statsmodels from the user site; reads data/raw read-only, writes nothing). The script's constants: `TOL_STD = 0.0015`, `TOL_RAW = 0.05`, `MIN_TWO_WAY_SD_RATIO = 0.25`.
