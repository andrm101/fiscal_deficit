# Gate 5: feasibility of a real-time CAPB comparison (S4, trigger T3)

Status 2026-10-10. Offline, descriptive only. Inputs: the 26 archived AMECO zips (`data/raw/ameco_archive/`, hashed in `manifest.jsonl`) and the pinned Spring 2026 snapshot (`data/raw/ameco/2026_spring/`). Code: `src/normalize/ameco_vintages.py` (tests: `tests/test_ameco_vintages.py`); long table: `data/interim/ameco_vintage_capb.csv` (gitignored; 135,594 rows, three items, 27 vintages). Project rule: Python only. **No election effect, and no regression of any outcome on election timing, was computed, printed or logged**; the election calendar is used only to date elections and to count availability.

## 0. Verdict

| Item | Result |
|---|---|
| Trigger T3 (`UBLGBP` for >= 20 EU-27 countries in every vintage Autumn 2014 to Autumn 2025) | **PASS**: 26 of 26 vintages carry `UBLGBP` for 27 countries (all of the EU-27; Romania is `ROM`, Greece `GRC`; minimum equals maximum) |
| Label and denominator | Identical in all 27 vintages (including the pinned Spring 2026): "Percentage of potential GDP at current prices"; title identical after whitespace normalisation |
| Sign convention | Surplus positive in every vintage (adjacent-vintage correlations 0.971 to 0.998; same-sign share 0.973 to 1.000) |
| "Autumn 2025" | A genuine, distinct Autumn vintage; the printed date (3 Jun 2025) is wrong (section 2) |
| Real-time panel coverage of the 715-row sample | 189 of 715 country-years (26.4 per cent): years 2015-2021 only; 216 (30.2 per cent) if 2014 is added for first-release revisions |
| Elections 2015-01-01 to 2021-12-31 with a pre-election vintage | 51 of 51 (scheduled 35, early 12, delayed 0, unclassified 4), in 47 distinct country-years |
| Recommendation for S4 | **DESCRIPTIVE-ONLY**: do not run a real-time election-effect replication; report CAPB revisions as a measurement-error appendix (section 7) |

## 1. Inventory of the 26 zips (step 1)

Every zip holds 18 chapter files `AMECO1.TXT ... AMECO18.TXT` (19 members in four zips, see below), semicolon-delimited, latin-1 (they also decode as UTF-8), `NA` for missing, one header row `CODE;COUNTRY;SUB-CHAPTER;TITLE;UNIT;1960;...;<last year>`, row code `AREA.1.0.319.0.UBLGBP`. Chapter 17 (cyclical adjustment) is `AMECO17.TXT` in every vintage; the unit text is `(Percentage of potential GDP at current prices) ` with a trailing space in the older files and without in the newest (handled by whitespace stripping). There is no explicit vintage stamp or header line inside the files; the only internal dates are the zip member timestamps.

Format variants handled: (i) three vintages (Autumn 2020, Autumn 2021, Spring 2022) wrap each chapter in a nested zip (`ameco17.zip` containing `AMECO17.TXT`; the outer zip also holds an `ameco0.zip`); (ii) the Autumn 2018 zip contains two chapter-17 files, `AMECO17.TXT` (stamp 2018-11-06) and `AMECO17_revised_semi_elasticities.TXT` (stamp 2019-02-22); the parser uses `AMECO17.TXT` (the file available at release). The revised file differs for every country-year (mean absolute difference 0.09 pp for `UBLGBP`, maximum 2.31 pp) and is closer to Spring 2019 than the original is (0.11 versus 0.17 pp, all years). Three elections fall between 22 Feb and 6 May 2019 (EE 2019-03-03, FI 2019-04-14, ES 2019-04-28) where the "available" Autumn 2018 data may be either variant; (iii) the Autumn 2025 chapter 17 holds 18 items (34 areas) against 25 items in Spring 2025 and Autumn 2024; `UBLGBP`, `UBLGAP` and `UBLGCP` are all present. `AVGDGP` (output gap) is a chapter 6 item and was not parsed (not needed for T3).

| vintage | printed | ch17 file stamp | container | members | countries | years | cells | first | last | sub-chapter tag |
|---|---|---|---|---|---|---|---|---|---|---|
| Autumn 2014 | 2014-11-06 | 2014-11-25 | flat txt | 18 | 27 | 39 | 527 | 1978 | 2016 | (ESA95) |
| Winter 2015 | 2015-02-04 | 2015-02-04 | flat txt | 18 | 27 | 39 | 543 | 1978 | 2016 | (ESA95) |
| Spring 2015 | 2015-05-07 | 2015-05-12 | flat txt | 18 | 27 | 42 | 578 | 1975 | 2016 | (ESA95) |
| Autumn 2015 | 2015-11-05 | 2015-11-05 | flat txt | 18 | 27 | 43 | 627 | 1975 | 2017 | (ESA 2010) |
| Winter 2016 | 2016-02-04 | 2016-01-28 | flat txt | 18 | 27 | 43 | 636 | 1975 | 2017 | (ESA 2010) |
| Spring 2016 | 2016-05-03 | 2016-04-28 | flat txt | 18 | 27 | 43 | 636 | 1975 | 2017 | (ESA 2010) |
| Autumn 2016 | 2016-11-09 | 2017-01-17 | flat txt | 18 | 27 | 44 | 662 | 1975 | 2018 | (ESA 2010) |
| Winter 2017 | 2017-02-13 | 2017-02-09 | flat txt | 18 | 27 | 44 | 663 | 1975 | 2018 | (ESA 2010) |
| Spring 2017 | 2017-05-11 | 2017-05-03 | flat txt | 18 | 27 | 44 | 663 | 1975 | 2018 | (ESA 2010) |
| Autumn 2017 | 2017-11-09 | 2018-02-22 | flat txt | 18 | 27 | 45 | 694 | 1975 | 2019 | (ESA 2010) |
| Spring 2018 | 2018-05-03 | 2018-05-07 | flat txt | 18 | 27 | 45 | 694 | 1975 | 2019 | (ESA 2010) |
| Autumn 2018 | 2018-11-08 | 2018-11-06 | flat txt | 19 | 27 | 46 | 724 | 1975 | 2020 | (ESA 2010) |
| Spring 2019 | 2019-05-07 | 2019-05-03 | flat txt | 18 | 27 | 46 | 724 | 1975 | 2020 | (ESA 2010) |
| Autumn 2019 | 2019-11-07 | 2019-11-21 | flat txt | 18 | 27 | 47 | 753 | 1975 | 2021 | (ESA 2010) |
| Spring 2020 | 2020-05-06 | 2020-05-12 | flat txt | 18 | 27 | 47 | 740 | 1975 | 2021 | (ESA 2010) |
| Autumn 2020 | 2020-11-05 | 2020-11-03 | nested zip | 19 | 27 | 48 | 767 | 1975 | 2022 | (ESA 2010) |
| Spring 2021 | 2021-05-12 | 2021-06-01 | flat txt | 18 | 27 | 48 | 786 | 1975 | 2022 | (ESA 2010) |
| Autumn 2021 | 2021-11-11 | 2021-11-04 | nested zip | 19 | 27 | 49 | 813 | 1975 | 2023 | (ESA 2010) |
| Spring 2022 | 2022-05-16 | 2022-05-30 | nested zip | 19 | 27 | 49 | 813 | 1975 | 2023 | (ESA 2010) |
| Autumn 2022 | 2022-11-17 | 2022-11-17 | flat txt | 18 | 27 | 50 | 840 | 1975 | 2024 | (ESA 2010) |
| Spring 2023 | 2023-05-15 | 2023-05-12 | flat txt | 18 | 27 | 50 | 840 | 1975 | 2024 | (ESA 2010) |
| Autumn 2023 | 2023-11-27 | 2023-11-27 | flat txt | 18 | 27 | 51 | 867 | 1975 | 2025 | (ESA 2010) |
| Spring 2024 | 2024-05-15 | 2024-05-15 | flat txt | 18 | 27 | 51 | 867 | 1975 | 2025 | (ESA 2010) |
| Autumn 2024 | 2024-11-15 | 2024-11-22 | flat txt | 18 | 27 | 52 | 894 | 1975 | 2026 | (ESA 2010) |
| Spring 2025 | 2025-05-19 | 2025-05-22 | flat txt | 18 | 27 | 52 | 894 | 1975 | 2026 | (ESA 2010) |
| Autumn 2025 | 2025-06-03 | 2025-12-11 | flat txt | 18 | 27 | 53 | 921 | 1975 | 2027 | (ESA 2010) |

Printed dates are from Appendix B section 1.3 and the acquisition TOML (cross-checked in a test). The chapter 17 file stamps differ from the printed dates in both directions: Winter and some Spring files are stamped up to 8 days earlier; many are 1 to 3 weeks later (Autumn 2014: printed 6 Nov, stamp 25 Nov; Spring 2021: 12 May versus 1 Jun; Spring 2022: 16 May versus 30 May), and two are months later (Autumn 2016: 9 Nov 2016 versus 17 Jan 2017; Autumn 2017: 9 Nov 2017 versus 22 Feb 2018), which suggests those chapter files were re-issued after the first release. The stamp is a file-build date, not a release date. Both dates are used in section 5.

## 2. The "Autumn 2025" date anomaly (step 1)

Printed 3 Jun 2025, 15 days after Spring 2025 (19 May 2025). Internal evidence:

- **Horizon.** Last column year is 2027, three years beyond 2024 (Spring 2025 ends 2026, two beyond). Under the AMECO rule (two forecast years in a Spring vintage, three in an Autumn vintage) this is an Autumn 2025 file, not a Spring 2025 file.
- **Not a duplicate.** Different SHA-256 for chapter 17; all 894 country-years it shares with Spring 2025 differ (mean absolute difference 0.098 pp); it is closest of any vintage pair to the pinned Spring 2026 (mean absolute difference 0.069 pp, the smallest of the 26 consecutive pairs).
- **Timestamps.** All 18 members are stamped 2025-12-11 12:24, six months after the printed date and about six and a half months after Spring 2025 (members stamped 2025-05-22 to 05-28).
- **Reading.** It is a real Autumn 2025 vintage whose printed date is a page error. The public release date is NOT VERIFIED: the file stamp (11 Dec 2025) is an upper bound on build, and Autumn vintages are normally released in the second half of November (inference from earlier vintages: 5 to 27 Nov). It does not affect any 2015-2023 election, because every one of them precedes any plausible release date.

## 3. Trigger T3 (step 3)

**PASS.** Per-vintage counts are in the table above. Summary: countries with `UBLGBP`: 27 in every vintage (no vintage below 20, none flagged); distinct years covered 39 (Autumn 2014) to 53; observed cells 527 to 921; first year 1978 (Autumn 2014, Winter 2015) then 1975; last year 2016 (Autumn 2014) up to 2027 (Autumn 2025). The label, the title and the denominator text are identical across vintages; no vintage has a different denominator or sign convention. One cosmetic difference: the sub-chapter tag reads "ESA95" in Autumn 2014, Winter 2015 and Spring 2015 and "ESA 2010" from Autumn 2015 (a data-basis switch, not a change in the CAPB definition, see section 4). The Spring 2020 vintage drops 13 pre-2000 back-cast cells (Baltic states, Malta, Slovakia, 1995-1999) present in Autumn 2019, which is why its cell count falls from 753 to 740.

Sign test (same country-years in adjacent vintages; sign agreement only where both values exceed 0.5 pp in absolute value):

| pair | n_overlap | pearson_r | slope_later_on_earlier | n_sign_testable | share_same_sign |
|---|---|---|---|---|---|
| Autumn 2014 -> Winter 2015 | 527 | 0.998 | 0.999 | 431 | 1.000 |
| Winter 2015 -> Spring 2015 | 533 | 0.992 | 0.987 | 434 | 0.998 |
| Spring 2015 -> Autumn 2015 | 578 | 0.994 | 0.987 | 466 | 0.998 |
| Autumn 2015 -> Winter 2016 | 625 | 0.998 | 0.996 | 505 | 1.000 |
| Winter 2016 -> Spring 2016 | 636 | 0.998 | 0.999 | 514 | 0.998 |
| Spring 2016 -> Autumn 2016 | 635 | 0.996 | 1.005 | 512 | 1.000 |
| Autumn 2016 -> Winter 2017 | 662 | 0.998 | 1.005 | 534 | 1.000 |
| Winter 2017 -> Spring 2017 | 663 | 0.997 | 1.000 | 544 | 1.000 |
| Spring 2017 -> Autumn 2017 | 663 | 0.998 | 0.992 | 549 | 1.000 |
| Autumn 2017 -> Spring 2018 | 694 | 0.996 | 1.007 | 571 | 1.000 |
| Spring 2018 -> Autumn 2018 | 694 | 0.997 | 0.994 | 574 | 1.000 |
| Autumn 2018 -> Spring 2019 | 724 | 0.991 | 0.998 | 585 | 0.998 |
| Spring 2019 -> Autumn 2019 | 724 | 0.997 | 1.005 | 580 | 1.000 |
| Autumn 2019 -> Spring 2020 | 740 | 0.971 | 0.993 | 590 | 0.973 |
| Spring 2020 -> Autumn 2020 | 740 | 0.979 | 1.011 | 598 | 0.993 |
| Autumn 2020 -> Spring 2021 | 767 | 0.979 | 0.974 | 624 | 0.997 |
| Spring 2021 -> Autumn 2021 | 786 | 0.994 | 0.997 | 648 | 1.000 |
| Autumn 2021 -> Spring 2022 | 813 | 0.992 | 0.981 | 672 | 0.999 |
| Spring 2022 -> Autumn 2022 | 813 | 0.993 | 1.001 | 675 | 0.997 |
| Autumn 2022 -> Spring 2023 | 840 | 0.993 | 0.988 | 691 | 0.996 |
| Spring 2023 -> Autumn 2023 | 840 | 0.997 | 0.998 | 679 | 1.000 |
| Autumn 2023 -> Spring 2024 | 867 | 0.997 | 0.999 | 707 | 1.000 |
| Spring 2024 -> Autumn 2024 | 867 | 0.989 | 0.996 | 698 | 0.999 |
| Autumn 2024 -> Spring 2025 | 894 | 0.998 | 1.004 | 741 | 0.999 |
| Spring 2025 -> Autumn 2025 | 894 | 0.997 | 0.996 | 746 | 0.999 |
| Autumn 2025 -> Spring 2026 | 921 | 0.998 | 1.001 | 774 | 1.000 |

Spot values stay surplus-positive in all vintages: EL 2016 is positive in all 26 and +10.58 in the final; DE 2009 +1.89; EL 2009 negative in every vintage. (EL 2016 moves from 2.5 in Spring 2015 to 10.6 in the final, a revision of about 8 pp, which illustrates section 6.)

## 4. Methodology homogeneity (step 4, descriptive)

Revision of the same country-year between consecutive vintages (later minus earlier, percentage points of potential GDP). Three views: all overlapping country-years; country-years that are non-forecast in the earlier vintage ("outturn years"; Spring/Autumn rule, Winter treated like Autumn, see section 8); and country-years from 2014 on. `mean_signed_t` is the t-statistic of the mean of country-average signed revisions across the countries (a level-shift screen). `outsized` = mean absolute revision at least 2 times the median across pairs.

**Outturn years only** (median mean-absolute revision 0.082 pp):

| pair | n | mean_signed | sd | mean_abs | max_abs | mean_signed_t | outsized |
|---|---|---|---|---|---|---|---|
| Autumn 2014 -> Winter 2015 | 446 | 0.001 | 0.087 | 0.051 | 0.485 | -0.004 |  |
| Winter 2015 -> Spring 2015 | 452 | 0.015 | 0.089 | 0.054 | 0.493 | 1.818 |  |
| Spring 2015 -> Autumn 2015 | 524 | 0.014 | 0.322 | 0.152 | 3.365 | 0.523 |  |
| Autumn 2015 -> Winter 2016 | 544 | 0.004 | 0.081 | 0.043 | 0.499 | 0.905 |  |
| Winter 2016 -> Spring 2016 | 555 | -0.000 | 0.111 | 0.061 | 0.704 | -0.356 |  |
| Spring 2016 -> Autumn 2016 | 581 | 0.014 | 0.201 | 0.114 | 1.356 | 1.305 |  |
| Autumn 2016 -> Winter 2017 | 581 | 0.010 | 0.160 | 0.070 | 1.120 | 0.120 |  |
| Winter 2017 -> Spring 2017 | 582 | -0.011 | 0.145 | 0.054 | 1.602 | -0.449 |  |
| Spring 2017 -> Autumn 2017 | 609 | 0.021 | 0.152 | 0.086 | 1.017 | 2.470 |  |
| Autumn 2017 -> Spring 2018 | 613 | 0.028 | 0.153 | 0.079 | 1.136 | 2.553 |  |
| Spring 2018 -> Autumn 2018 | 640 | 0.005 | 0.218 | 0.107 | 3.381 | 0.264 |  |
| Autumn 2018 -> Spring 2019 | 643 | 0.010 | 0.232 | 0.137 | 2.376 | 0.990 |  |
| Spring 2019 -> Autumn 2019 | 670 | 0.007 | 0.227 | 0.133 | 2.392 | 0.633 |  |
| Autumn 2019 -> Spring 2020 | 659 | -0.103 | 0.232 | 0.173 | 1.192 | -8.404 | YES |
| Spring 2020 -> Autumn 2020 | 686 | -0.020 | 0.300 | 0.192 | 2.028 | -1.317 | YES |
| Autumn 2020 -> Spring 2021 | 686 | 0.026 | 0.262 | 0.123 | 2.734 | 1.288 |  |
| Spring 2021 -> Autumn 2021 | 732 | 0.029 | 0.215 | 0.112 | 2.205 | 3.356 |  |
| Autumn 2021 -> Spring 2022 | 732 | 0.008 | 0.127 | 0.069 | 0.993 | 0.549 |  |
| Spring 2022 -> Autumn 2022 | 759 | 0.050 | 0.270 | 0.130 | 2.385 | 1.315 |  |
| Autumn 2022 -> Spring 2023 | 759 | -0.017 | 0.151 | 0.067 | 1.779 | -0.855 |  |
| Spring 2023 -> Autumn 2023 | 786 | 0.002 | 0.174 | 0.089 | 1.619 | -0.005 |  |
| Autumn 2023 -> Spring 2024 | 786 | -0.003 | 0.105 | 0.053 | 0.829 | 0.057 |  |
| Spring 2024 -> Autumn 2024 | 813 | 0.002 | 0.424 | 0.152 | 9.383 | 0.052 |  |
| Autumn 2024 -> Spring 2025 | 813 | 0.007 | 0.068 | 0.037 | 0.666 | 1.166 |  |
| Spring 2025 -> Autumn 2025 | 840 | -0.004 | 0.136 | 0.073 | 1.541 | -0.416 |  |
| Autumn 2025 -> Spring 2026 | 840 | -0.000 | 0.065 | 0.036 | 0.536 | -0.350 |  |

**All overlapping years:**

| pair | n | mean_signed | sd | mean_abs | max_abs | mean_signed_t | outsized |
|---|---|---|---|---|---|---|---|
| Autumn 2014 -> Winter 2015 | 527 | 0.005 | 0.209 | 0.087 | 2.805 | 0.083 |  |
| Winter 2015 -> Spring 2015 | 533 | -0.015 | 0.400 | 0.119 | 6.462 | -0.741 |  |
| Spring 2015 -> Autumn 2015 | 578 | 0.010 | 0.346 | 0.172 | 3.365 | 0.669 |  |
| Autumn 2015 -> Winter 2016 | 625 | 0.001 | 0.196 | 0.074 | 3.134 | 0.019 |  |
| Winter 2016 -> Spring 2016 | 636 | 0.017 | 0.192 | 0.097 | 1.325 | 1.783 |  |
| Spring 2016 -> Autumn 2016 | 635 | 0.030 | 0.268 | 0.141 | 2.608 | 1.961 |  |
| Autumn 2016 -> Winter 2017 | 662 | 0.014 | 0.195 | 0.094 | 1.132 | 0.572 |  |
| Winter 2017 -> Spring 2017 | 663 | 0.019 | 0.221 | 0.090 | 1.876 | 1.932 |  |
| Spring 2017 -> Autumn 2017 | 663 | 0.023 | 0.181 | 0.103 | 1.017 | 2.347 |  |
| Autumn 2017 -> Spring 2018 | 694 | 0.070 | 0.284 | 0.128 | 2.882 | 4.112 |  |
| Spring 2018 -> Autumn 2018 | 694 | 0.016 | 0.228 | 0.119 | 3.381 | 1.049 |  |
| Autumn 2018 -> Spring 2019 | 724 | -0.012 | 0.400 | 0.173 | 7.985 | -0.850 |  |
| Spring 2019 -> Autumn 2019 | 724 | 0.007 | 0.247 | 0.146 | 2.392 | 0.594 |  |
| Autumn 2019 -> Spring 2020 | 740 | -0.262 | 0.729 | 0.333 | 6.869 | -13.230 | YES |
| Spring 2020 -> Autumn 2020 | 740 | -0.123 | 0.644 | 0.303 | 5.160 | -5.600 | YES |
| Autumn 2020 -> Spring 2021 | 767 | 0.011 | 0.643 | 0.251 | 5.716 | 0.107 | YES |
| Spring 2021 -> Autumn 2021 | 786 | 0.026 | 0.356 | 0.163 | 2.996 | 1.877 |  |
| Autumn 2021 -> Spring 2022 | 813 | 0.055 | 0.384 | 0.154 | 3.136 | 2.597 |  |
| Spring 2022 -> Autumn 2022 | 813 | 0.033 | 0.365 | 0.172 | 2.969 | 0.880 |  |
| Autumn 2022 -> Spring 2023 | 840 | 0.030 | 0.370 | 0.142 | 2.871 | 1.327 |  |
| Spring 2023 -> Autumn 2023 | 840 | 0.001 | 0.252 | 0.118 | 2.238 | 0.021 |  |
| Autumn 2023 -> Spring 2024 | 867 | 0.003 | 0.241 | 0.101 | 2.132 | 0.492 |  |
| Spring 2024 -> Autumn 2024 | 867 | 0.012 | 0.455 | 0.174 | 9.383 | 0.693 |  |
| Autumn 2024 -> Spring 2025 | 894 | 0.008 | 0.215 | 0.081 | 2.300 | 0.781 |  |
| Spring 2025 -> Autumn 2025 | 894 | -0.008 | 0.226 | 0.098 | 2.768 | -0.700 |  |
| Autumn 2025 -> Spring 2026 | 921 | -0.006 | 0.169 | 0.069 | 1.246 | -0.924 |  |

**Years 2014 and later:**

| pair | n | mean_signed | sd | mean_abs | max_abs | mean_signed_t | outsized |
|---|---|---|---|---|---|---|---|
| Autumn 2014 -> Winter 2015 | 81 | 0.025 | 0.495 | 0.288 | 2.805 | 0.474 |  |
| Winter 2015 -> Spring 2015 | 81 | -0.179 | 0.994 | 0.485 | 6.462 | -1.448 |  |
| Spring 2015 -> Autumn 2015 | 81 | -0.082 | 0.669 | 0.409 | 3.365 | -1.022 |  |
| Autumn 2015 -> Winter 2016 | 108 | -0.010 | 0.445 | 0.243 | 3.134 | -0.202 |  |
| Winter 2016 -> Spring 2016 | 108 | 0.124 | 0.392 | 0.302 | 1.325 | 2.157 |  |
| Spring 2016 -> Autumn 2016 | 108 | 0.102 | 0.522 | 0.335 | 2.608 | 1.287 |  |
| Autumn 2016 -> Winter 2017 | 135 | 0.024 | 0.308 | 0.207 | 1.132 | 0.623 |  |
| Winter 2017 -> Spring 2017 | 135 | 0.156 | 0.391 | 0.255 | 1.876 | 2.917 |  |
| Spring 2017 -> Autumn 2017 | 135 | 0.047 | 0.307 | 0.232 | 0.944 | 1.252 |  |
| Autumn 2017 -> Spring 2018 | 162 | 0.228 | 0.511 | 0.337 | 2.882 | 4.469 |  |
| Spring 2018 -> Autumn 2018 | 162 | 0.019 | 0.256 | 0.187 | 0.906 | 0.669 |  |
| Autumn 2018 -> Spring 2019 | 189 | -0.080 | 0.678 | 0.284 | 7.985 | -1.226 |  |
| Spring 2019 -> Autumn 2019 | 189 | -0.023 | 0.303 | 0.207 | 1.181 | -0.755 |  |
| Autumn 2019 -> Spring 2020 | 216 | -0.699 | 1.194 | 0.746 | 6.869 | -11.033 | YES |
| Spring 2020 -> Autumn 2020 | 216 | -0.377 | 1.062 | 0.603 | 5.160 | -4.474 | YES |
| Autumn 2020 -> Spring 2021 | 243 | 0.033 | 1.076 | 0.568 | 5.716 | 0.326 |  |
| Spring 2021 -> Autumn 2021 | 243 | 0.073 | 0.595 | 0.343 | 2.996 | 1.469 |  |
| Autumn 2021 -> Spring 2022 | 270 | 0.156 | 0.644 | 0.356 | 3.136 | 3.332 |  |
| Spring 2022 -> Autumn 2022 | 270 | 0.028 | 0.518 | 0.301 | 2.969 | 0.603 |  |
| Autumn 2022 -> Spring 2023 | 297 | 0.131 | 0.588 | 0.304 | 2.871 | 2.919 |  |
| Spring 2023 -> Autumn 2023 | 297 | -0.015 | 0.400 | 0.225 | 2.238 | -0.581 |  |
| Autumn 2023 -> Spring 2024 | 324 | 0.007 | 0.380 | 0.203 | 2.132 | 0.226 |  |
| Spring 2024 -> Autumn 2024 | 324 | 0.037 | 0.412 | 0.244 | 3.717 | 1.295 |  |
| Autumn 2024 -> Spring 2025 | 351 | 0.011 | 0.340 | 0.166 | 2.300 | 0.407 |  |
| Spring 2025 -> Autumn 2025 | 351 | -0.024 | 0.349 | 0.175 | 2.768 | -1.140 |  |
| Autumn 2025 -> Spring 2026 | 378 | -0.007 | 0.258 | 0.132 | 1.246 | -0.329 |  |

Findings (no causal interpretation):

- **Typical size.** Mean absolute revision of outturn years between consecutive vintages is 0.04 to 0.19 pp (median 0.08). Up to Autumn 2017 the Spring-to-Autumn pairs are larger (0.09 to 0.15 pp) than the Autumn-to-Winter and Winter-to-Spring pairs (0.04 to 0.07 pp); for Autumn 2018 to Autumn 2020 the Autumn-to-Spring pairs are as large (0.12 to 0.17 pp), and from Autumn 2021 on they fall to 0.04 to 0.07 pp. Maximum single-cell revisions in outturn years range from 0.5 to 9.4 pp (the maximum is Cyprus 2012 in Spring to Autumn 2024).
- **COVID period.** Autumn 2019 to Spring 2020 and Spring 2020 to Autumn 2020 are flagged as outsized in the outturn view (0.173 and 0.192 pp), and Autumn 2019 to Spring 2020, Spring 2020 to Autumn 2020 and Autumn 2020 to Spring 2021 in the all-years view (0.333, 0.303, 0.251 pp). The largest cells are 2020 forecasts (PL -6.9, CY -5.4, EE -4.9 pp) and 2021 forecasts (SI -5.2, IE -4.5, AT -4.2 pp).
- **A level shift not explained by new outturn data.** Autumn 2019 to Spring 2020 shifts the outturn-year history downward: mean signed revision -0.103 pp (t = -8.4 across 27 countries), and the shift is present in every year 2014-2019 (mean -0.14 pp for 2014 growing to -0.35 pp for 2019), i.e. it is not confined to years where new data arrived. The cause (revision of the potential-output model, benchmark or COVID treatment) is NOT VERIFIED. A smaller positive shift appears at Autumn 2017 to Spring 2018 (+0.028 pp, t = 2.6) and Spring 2017 to Autumn 2017 (+0.021, t = 2.5).
- **ESA 95 to ESA 2010.** The vintages Autumn 2014 to Spring 2015 carry the ESA95 tag, Autumn 2015 onward ESA 2010. The pair Spring 2015 to Autumn 2015 has mean absolute outturn-year revision 0.152 pp and a maximum of 3.37 pp (PT 2014), about three times the neighbouring Autumn-to-Winter and Winter-to-Spring pairs, although it is not flagged as outsized. The "homogeneous from Autumn 2014" statement of Appendix B (about the cyclical-adjustment method) therefore holds for the method but not for the national-accounts basis of the first three vintages.
- **Other single revisions.** Autumn 2018 to Spring 2019 (maximum 7.99 pp in the all-years view, Cyprus 2018, a forecast-year in the earlier vintage), Spring 2024 to Autumn 2024 (9.38 pp, Cyprus 2012) and Winter 2015 to Spring 2015 (Cyprus 2014, -6.5 pp; Greece 2015 and 2016, -2.8 and -3.4 pp) are driven by single cells.

## 5. Real-time availability around elections (step 5, counts only)

Calendar: `data/interim/election_calendar_eu27.csv`, rows with `in_calendar` true (all 51 rows dated 2015-01-01 to 2021-12-31 are in the calendar). For each election the pre-election vintage is the latest vintage whose printed release date is strictly before the election date. "t" is the election year. The first vintage is Autumn 2014 (printed 6 Nov 2014), before the earliest election in the window (2015-01-25), so every election 2015-2021 has a pre-election vintage. Distribution of the pre-election vintage: Autumn 2014 (1), Winter 2015 (2), Spring 2015 (4), Autumn 2015 (2), Winter 2016 (2), Spring 2016 (4), Autumn 2016 (1), Winter 2017 (2), Spring 2017 (5), Autumn 2017 (2), Spring 2018 (4), Autumn 2018 (3), Spring 2019 (6), Autumn 2019 (3), Spring 2020 (2), Autumn 2020 (3), Spring 2021 (4), Autumn 2021 (1).

Counts of elections (printed-date rule), with the number whose pre-election vintage carries a value for t-1, a value for t-1 that is outturn (non-forecast), t, and t+1:

| class | n_elections | has_vintage | has_t_minus_1 | t_minus_1_is_outturn | has_t | has_t_plus_1 |
|---|---|---|---|---|---|---|
| scheduled | 35 | 35 | 35 | 23 | 35 | 35 |
| early | 12 | 12 | 12 | 8 | 12 | 12 |
| unclassified | 4 | 4 | 4 | 4 | 4 | 4 |
| total | 51 | 51 | 51 | 35 | 51 | 51 |

All 51 elections have t and t+1 (forecast or nowcast values: in the pre-election vintage the election year is always a forecast year) and t-1; t-1 is outturn only for the 35 elections held after the Spring release of year t (the remainder see t-1 as a forecast). The 51 elections occupy 47 distinct country-years (BG 2021 has three elections, EL 2015 two, ES 2019 two) out of 189 sample country-years in 2015-2021 (24.9 per cent); the remaining 142 carry a first-release CAPB but no election. Class counts at the country-year level overlap (one country-year can hold early and scheduled elections), so the table above counts elections.

**Sensitivity to the suspect dates.** Using the later of the printed date and the chapter 17 file stamp as the availability date changes the pre-election vintage for 3 of 51 elections (CY 2021-05-30, ES 2019-11-10, RO 2016-12-11) and reduces the outturn-t-1 count by one (unclassified: 4 to 3):

| class | n_elections | has_vintage | has_t_minus_1 | t_minus_1_is_outturn | has_t | has_t_plus_1 |
|---|---|---|---|---|---|---|
| scheduled | 35 | 35 | 35 | 23 | 35 | 35 |
| early | 12 | 12 | 12 | 8 | 12 | 12 |
| unclassified | 4 | 4 | 4 | 3 | 4 | 4 |
| total | 51 | 51 | 51 | 34 | 51 | 51 |

**Elections 2022-2023** (noted; outside the 2015-2021 window and the confirmatory sample, which reaches 2022 only as a sensitivity): 18 elections, all with a pre-election vintage:

| class | n_elections | has_vintage | has_t_minus_1 | t_minus_1_is_outturn | has_t | has_t_plus_1 |
|---|---|---|---|---|---|---|
| scheduled | 8 | 8 | 8 | 4 | 8 | 8 |
| early | 6 | 6 | 6 | 5 | 6 | 6 |
| unclassified | 4 | 4 | 4 | 2 | 4 | 4 |
| total | 18 | 18 | 18 | 11 | 18 | 18 |

**Coverage of the confirmatory sample.** The vintages' own window gives a real-time panel for 2015-2021 only: 189 of 715 sample country-years = 26.4 per cent (7 of 27 years = 25.9 per cent; the share differs slightly because 14 country-years are missing from the 715). A first-release panel (first outturn of year y appears in the Spring y+1 vintage) starts at y = 2014: 216 country-years = 30.2 per cent. The 1995-2013 part of the sample (70 per cent) has no first release in the archive.

## 6. Revisions: first release versus the pinned Spring 2026 value (step 6, descriptive)

Window: country-years 2014-2021 (27 countries x 8 years = 216 cells, none missing). Two definitions of first release:

- **First outturn**: earliest archived vintage in which the year is non-forecast (Spring y+1 in every case).
- **First appearance**: earliest vintage that contains the year (an Autumn forecast two to three years ahead: Autumn 2014 for 2014-2016; Autumn 2015 for 2017; ... Autumn 2019 for 2021).

Revision = final minus first release (pp of potential GDP).

| Definition | n | mean | SD | mean abs | share with sign change | correlation first/final (pooled) |
|---|---|---|---|---|---|---|
| First outturn | 216 | 0.140 | 0.975 | 0.639 | 0.097 | 0.933 |
| First appearance (forecast) | 216 | -0.413 | 2.282 | 1.677 | 0.343 | 0.541 |

By year, first outturn (the correlation is across the 27 countries within the year):

| year | n | mean_revision | sd_revision | mean_abs_revision | share_sign_change | corr_first_final |
|---|---|---|---|---|---|---|
| 2014 | 27 | 0.130 | 1.421 | 0.938 | 0.222 | 0.791 |
| 2015 | 27 | 0.347 | 1.296 | 0.718 | 0.111 | 0.710 |
| 2016 | 27 | 0.207 | 0.592 | 0.458 | 0.111 | 0.972 |
| 2017 | 27 | -0.177 | 0.818 | 0.577 | 0.148 | 0.938 |
| 2018 | 27 | 0.042 | 0.808 | 0.536 | 0.037 | 0.935 |
| 2019 | 27 | 0.434 | 0.918 | 0.672 | 0.074 | 0.923 |
| 2020 | 27 | 0.452 | 0.885 | 0.756 | 0.037 | 0.901 |
| 2021 | 27 | -0.314 | 0.543 | 0.455 | 0.037 | 0.975 |

By year, first appearance:

| year | n | mean_revision | sd_revision | mean_abs_revision | share_sign_change | corr_first_final |
|---|---|---|---|---|---|---|
| 2014 | 27 | -0.055 | 1.334 | 0.923 | 0.259 | 0.820 |
| 2015 | 27 | 0.344 | 1.328 | 1.009 | 0.222 | 0.735 |
| 2016 | 27 | 0.918 | 1.486 | 1.221 | 0.296 | 0.745 |
| 2017 | 27 | 0.992 | 1.947 | 1.602 | 0.407 | 0.545 |
| 2018 | 27 | 0.365 | 1.342 | 1.044 | 0.185 | 0.832 |
| 2019 | 27 | 0.331 | 1.459 | 1.065 | 0.185 | 0.806 |
| 2020 | 27 | -3.151 | 1.639 | 3.241 | 0.630 | 0.602 |
| 2021 | 27 | -3.048 | 2.465 | 3.309 | 0.556 | 0.319 |

By country, first outturn (8 years each; per-country correlations with n = 8 are unstable, e.g. PT 0.06, IE 0.57):

| eurostat_code | n | mean_revision | sd_revision | mean_abs_revision | share_sign_change | corr_first_final |
|---|---|---|---|---|---|---|
| BE | 8 | -0.077 | 0.197 | 0.171 | 0.000 | 0.995 |
| RO | 8 | 0.139 | 0.367 | 0.222 | 0.000 | 0.991 |
| SK | 8 | -0.114 | 0.414 | 0.305 | 0.375 | 0.977 |
| CZ | 8 | -0.121 | 0.364 | 0.306 | 0.125 | 0.991 |
| NL | 8 | 0.167 | 0.465 | 0.352 | 0.000 | 0.949 |
| DE | 8 | -0.362 | 0.328 | 0.376 | 0.000 | 0.989 |
| HU | 8 | -0.387 | 0.339 | 0.399 | 0.125 | 0.992 |
| SE | 8 | -0.382 | 0.478 | 0.412 | 0.250 | 0.850 |
| LV | 8 | 0.150 | 0.502 | 0.422 | 0.250 | 0.984 |
| AT | 8 | 0.083 | 0.507 | 0.425 | 0.000 | 0.977 |
| LT | 8 | -0.162 | 0.545 | 0.435 | 0.125 | 0.976 |
| FR | 8 | -0.352 | 0.494 | 0.435 | 0.000 | 0.948 |
| FI | 8 | -0.147 | 0.598 | 0.474 | 0.375 | 0.918 |
| HR | 8 | 0.327 | 0.638 | 0.479 | 0.125 | 0.970 |
| PL | 8 | 0.330 | 0.433 | 0.479 | 0.250 | 0.957 |
| DK | 8 | 0.297 | 0.600 | 0.544 | 0.000 | 0.919 |
| IT | 8 | 0.017 | 0.883 | 0.602 | 0.000 | 0.965 |
| EE | 8 | -0.134 | 0.727 | 0.618 | 0.125 | 0.883 |
| BG | 8 | 0.002 | 0.861 | 0.627 | 0.000 | 0.968 |
| LU | 8 | 0.312 | 0.849 | 0.657 | 0.000 | 0.853 |
| ES | 8 | 0.033 | 0.807 | 0.692 | 0.125 | 0.906 |
| PT | 8 | -0.575 | 1.375 | 0.774 | 0.125 | 0.059 |
| SI | 8 | 0.924 | 1.003 | 0.974 | 0.125 | 0.953 |
| MT | 8 | 0.024 | 1.566 | 1.163 | 0.000 | 0.937 |
| CY | 8 | 1.119 | 0.978 | 1.177 | 0.000 | 0.958 |
| IE | 8 | 0.575 | 2.066 | 1.629 | 0.000 | 0.569 |
| EL | 8 | 2.097 | 1.679 | 2.097 | 0.125 | 0.929 |

Stability of history for sample years before the archive window: Autumn 2014 against Spring 2026 for 1995-2013 (429 cells): mean revision 0.043, SD 0.741, mean absolute 0.452 pp, sign changes 4.4 per cent, correlation 0.975. This is the revision of a 2014 vintage's history, not a first release.

Reading: a first-outturn CAPB is on average 0.64 pp away from the final value (SD 0.97), above the 0.5 pp smallest effect size of interest proposed in Blueprint D-A; the forecast-based first appearance is off by 1.68 pp on average with 34 per cent sign changes, dominated by the 2020-2021 forecasts made in Autumn 2018 and Autumn 2019 (mean -3.1 pp). Greece (mean absolute 2.10 pp, always revised upward) and Ireland (1.63 pp) are the largest-revision countries.

## 7. Recommendation for S4 (step 7)

**Trigger T3: PASS** (S4 is not cancelled by T3). **S4 verdict: DESCRIPTIVE-ONLY** (not GO as an election-effect replication; not NO-GO either, because the data support a useful, cheap measurement-error appendix).

Reasons:

1. **Few elections.** Only 51 elections (35 scheduled, 12 early, 4 unclassified, 0 delayed) in 47 country-years have a pre-election vintage, and only 35 of them see the previous year as outturn. The delayed class is empty, so no class-specific real-time estimate exists for it, and the early (12) and unclassified (4) classes are far too small for any class contrast.
2. **Panel shrinks to a quarter.** The real-time panel is 189 country-years (26 per cent of 715), seven years, 27 clusters. Purely as arithmetic, not a power calculation: the registered design needs about 0.66 to 0.68 pp (wild-bootstrap MDE for the scheduled-election term, Gate 3b); if precision scaled with the square root of the number of observations, the MDE on 189 observations would be near 0.66 x sqrt(715/189) = 1.3 pp before adding first-release measurement error (SD 0.97 pp) and before the loss of between-year exposure variation. That is more than twice the 0.41 and 0.49 pp literature benchmarks and above the 1.0 pp demotion line of D-C. A proper simulation was not run and is not recommended.
3. **Measurement error is the interesting object.** The revision statistics above are informative for the thesis: the confirmatory outcome (Spring 2026 pinned values) differs from what a policymaker or an election-year analysis would have seen by 0.64 pp on average, with 9.7 per cent sign changes, and outturn revisions have been larger at vintage boundaries (COVID period, ESA basis switch).
4. **Methodology breaks.** The Spring 2020 level shift and the ESA95/ESA 2010 label switch (Autumn 2015) mean a pooled real-time series is not homogeneous; modelling it would need vintage fixed effects, which a 7-year panel cannot afford.

Recommended framing: a measurement-error appendix to the thesis, "How stable is CAPB across AMECO vintages?", with sections 3, 4 and 6 of this report (revision distribution, first-release versus final, country and year patterns, the 0.5 pp comparison). Optionally, report as a purely descriptive table how many elections would have had a real-time observation (section 5). Do not estimate an election association on real-time CAPB. Registry text for S4 should be amended from "Real-time CAPB comparison" to "CAPB revision and measurement-error appendix (descriptive)"; the fallback (headline primary balance and expenditure components) is not needed.

## 8. What could not be verified

- **True release dates** of every vintage. Printed dates (archive page) and zip member stamps disagree in both directions, by up to about 3.5 months (Autumn 2017); neither is a release timestamp. Autumn 2025 in particular: the printed date is wrong and the actual date is not known (stamp 2025-12-11).
- **Winter forecast horizon.** AMECO states the forecast-year rule only for Spring (2) and Autumn (3). Winter is treated here as 3 forecast years (assumption: Eurostat's first outturn for year t-1 arrives in April). Per-country exceptions to the rule (flagged in AMECO Reference Metadata) were not checked. If Winter were treated as 2, the "first outturn" vintage would be Winter y+1 instead of Spring y+1 for Winter-covered years.
- **Cause of level shifts** at Spring 2020 and at the ESA switch (ECP536 updates, output-gap model changes after 2014, COVID treatment, one-off classifications such as Cyprus).
- **Which Autumn 2018 variant** was publicly available between 22 Feb and 7 May 2019 (affects EE, FI, ES 2019 only).
- **Whether the archived chapter-17 files are the originally released versions.** Stamps up to 3.5 months after the printed date (Autumn 2016, Autumn 2017), a re-issued file inside the Autumn 2018 zip and a source file named "Autumn 2023 Revised" (Appendix B) suggest some were re-issued; if so, a real-time reconstruction is only approximately real-time. Provenance is the manifest (URL, size, hash) only.
- **`AVGDGP`** (chapter 6) was not parsed; the output-gap vintage history is not covered here.
- **Election dates and classes** come from the Gate 3a calendar (ETAD and ParlGov); whether each date is a first-round date was not re-checked here, and the class assignments inherit the calendar's caveats (29 unclassified elections among the in-calendar rows, 4 in 2015-2021).

## 9. Reproduction

`python src/normalize/ameco_vintages.py` rebuilds the long table; `python -m pytest tests/test_ameco_vintages.py -q -p no:cacheprovider` runs the tests (fixture tests plus real-file tests that skip if the archive is absent). All tables above are produced by the functions `t3_summary`, `adjacent_sign_check`, `revision_pairs`, `first_release_table`, `summarise_revisions`, `election_availability`, `availability_by_class`, `compare_to_final` and `realtime_window_coverage` in that module.
