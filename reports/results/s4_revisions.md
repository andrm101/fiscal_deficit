# S4: CAPB revisions and measurement error (descriptive appendix)

Specification: `docs/s4_spec.md` (dated 2026-10-13, SHA-256 `333a6d483ad918db...`). Code: `src/evaluate/revisions.py`; figure: `reports/figures/s4_revisions.png`. Units: percentage points (pp) of potential GDP (AMECO `UBLGBP`, surplus positive). Descriptive only: no election effect is estimated, the pre-registered headline is unchanged (beta_S = -0.379 pp, 95% interval [-0.691, -0.069]), and all statements are associations.

Why this appendix exists: trigger T3 passed (the vintage archive carries CAPB for all 27 countries), but a real-time panel covers 2015-2021 only (189 of 715 confirmatory country-years; 51 elections), so an election-effect replication on first-release data is not feasible (Gate 5, `reports/gate5_realtime_feasibility.md`). What the archive supports is a description of how far the first-outturn CAPB lies from the final value used in the confirmatory analysis.

## 0. Summary

- Sample: 216 country-years (27 countries, 2014-2021); first-outturn vintages: Spring 2015 (27); Spring 2016 (27); Spring 2017 (27); Spring 2018 (27); Spring 2019 (27); Spring 2020 (27); Spring 2021 (27); Spring 2022 (27).
- Revision (final - first outturn): mean 0.14 pp [-0.04, 0.36]; mean absolute 0.64 pp [0.49, 0.81]; SD 0.97 pp [0.70, 1.22]; median absolute 0.42 pp [0.34, 0.50].
- Level sign change in 9.7% [5.6%, 14.4%] of country-years; correlation of first outturn and final 0.93 [0.90, 0.96].
- |Revision| above the 0.5 pp SESOI in 42.1% [34.7%, 50.0%] of country-years; mean absolute revision 0.64 pp and median absolute revision 0.42 pp against 0.5 pp (pre-specified reading in section 3).
- The SD of the revision is 2.6 times |beta_S| and the mean absolute revision 1.7 times |beta_S|; the revision SD is 0.36 of the within-country SD of CAPB in the confirmatory sample.

## 1. Definitions and sample

- **First outturn.** The value of CAPB for year y in the earliest archived vintage in which y is no longer a forecast. AMECO has no forecast flag, so the rule is structural: the last 2 year columns of a Spring vintage and the last 3 of an Autumn vintage are forecasts; Winter is treated like Autumn (3 forecast years; an assumption, since the previous year's outturn reaches AMECO only from Spring). The rule is applied by the frozen `ameco_vintages.first_release_table`.
- **Final.** Spring 2026 (the pinned vintage of the confirmatory analysis). Check: 216 of 216 sample rows match the gold-panel CAPB; largest absolute difference between the panel CAPB and the final value 0.000000 pp.
- **Revision** = final - first outturn (positive: the first outturn understated the surplus relative to the final).
- **Primary sample**: country-years 2014-2021 with both values (216). Extension: 2014-2024 (297); 2022-2024 lie outside the confirmatory sample. The 2014 first outturn is Spring 2015 (Autumn 2014 holds 2014 as a forecast).

First-outturn vintages (primary sample): Spring 2015: 27; Spring 2016: 27; Spring 2017: 27; Spring 2018: 27; Spring 2019: 27; Spring 2020: 27; Spring 2021: 27; Spring 2022: 27.

## 2. Revision statistics

Primary sample, N = 216. Intervals are 95% country-cluster percentile bootstrap intervals (9999 draws, seed 42, 27 clusters; approximate with so few clusters).

| Statistic | Estimate | 95% interval |
|---|---|---|
| Mean revision (final - first), pp | 0.140 | [-0.043, 0.361] |
| Mean absolute revision, pp | 0.639 | [0.494, 0.814] |
| SD of the revision, pp | 0.975 | [0.700, 1.217] |
| Median revision, pp | 0.047 | [-0.055, 0.180] |
| Median absolute revision, pp | 0.421 | [0.341, 0.497] |
| Share with |revision| above the SESOI | 42.1% | [34.7%, 50.0%] |
| Share with a sign change of the CAPB level | 9.7% | [5.6%, 14.4%] |
| Share with a sign change of the one-year change in CAPB | 14.8% | [10.2%, 19.9%] |
| Correlation, first outturn and final | 0.933 | [0.903, 0.955] |
| Slope of final on first | 1.010 | [0.910, 1.090] |
| Intercept of final on first, pp | 0.139 | [-0.048, 0.339] |
| Slope of first on final | 0.862 | [0.804, 0.953] |
| Reliability ratio var(final) / var(first) | 1.172 | [0.966, 1.346] |
| Correlation of the revision with the first outturn | 0.025 | [-0.234, 0.231] |
| Correlation of the revision with the final | 0.383 | [0.136, 0.542] |

Mean revision with a CR1 t(26) interval: 0.140 pp [-0.076, 0.356].
The sign-of-change share uses the 216 country-years with the one-year change defined in both vintages. Exact zeros never count as sign changes.

Quantiles (pp):

| Quantity | 1% | 5% | 10% | 25% | 50% | 75% | 90% | 95% | 99% |
|---|---|---|---|---|---|---|---|---|---|
| Revision | -2.05 | -0.93 | -0.77 | -0.36 | 0.05 | 0.49 | 1.15 | 1.91 | 3.64 |
| Absolute revision | 0.00 | 0.03 | 0.07 | 0.19 | 0.42 | 0.78 | 1.48 | 2.17 | 3.85 |

Largest absolute revisions (pp):

| Country | Year | First outturn | Final | Revision |
|---|---|---|---|---|
| EL | 2015 | 0.30 | 5.58 | 5.27 |
| PT | 2014 | 3.07 | -0.79 | -3.85 |
| IE | 2019 | 0.56 | 4.41 | 3.85 |
| EL | 2014 | 4.87 | 8.68 | 3.81 |
| SI | 2015 | 0.23 | 2.90 | 2.67 |
| CY | 2014 | -3.25 | -0.66 | 2.59 |
| IE | 2020 | -3.60 | -1.09 | 2.51 |
| MT | 2017 | 5.21 | 2.73 | -2.48 |

## 3. Revisions against the 0.5 pp smallest effect size of interest

The mean absolute revision is 0.64 pp [0.49, 0.81], the median absolute revision 0.42 pp [0.34, 0.50], and 42.1% [34.7%, 50.0%] of country-years have |revision| above 0.5 pp.

Reading (pre-specified rule, spec section 2 item 7): neither the mean nor the median absolute revision has an interval entirely above 0.5 pp, so this sample does not support the statement that the typical revision exceeds the SESOI. Mean absolute revision: point estimate 0.64 pp (above 0.5 pp), interval [0.49, 0.81] contains 0.5 pp. Median absolute revision: point estimate 0.42 pp (below 0.5 pp), interval [0.34, 0.50] excludes 0.5 pp. The mean is pulled up by a right tail (the largest revisions are listed above) while 58% of country-years lie within 0.5 pp of the final. What can be said: revisions of the size of the SESOI are common (42% of country-years exceed it) and the revision SD (0.97 pp) is a multiple of it.

## 4. Noise-to-signal comparison

Headline beta_S = -0.379 pp (95% bootstrap-t interval [-0.691, -0.069]; pre-registered V7, unchanged). Plain quotients; no inference.

| Quantity | Value |
|---|---|
| SD of the revision / |beta_S| | 2.57 |
| Mean absolute revision / |beta_S| | 1.68 |
| SD of final CAPB, revision sample (pp) | 2.71 |
| SD of the revision / SD of final CAPB, revision sample | 0.36 |
| SD of CAPB, confirmatory sample (N = 715) (pp) | 3.10 |
| SD of the revision / SD of CAPB, confirmatory sample | 0.31 |
| Within-country SD of CAPB, confirmatory sample (pp) | 2.70 |
| SD of the revision / within-country SD | 0.36 |
| Two-way (country and year) demeaned SD of CAPB, confirmatory sample (pp) | 2.39 |
| SD of the revision / two-way demeaned SD | 0.41 |

Reading: the revision SD (0.97 pp) is 2.6 times the size of the estimated beta_S. The variation a fixed-effects design uses (within-country, or net of country and year effects) has an SD of 2.70 and 2.39 pp, so the revision SD is 0.36 and 0.41 times those scales. This describes how noisy a first-outturn CAPB would have been as a measure of the final value; it does not say that the final value is free of error, and it does not by itself bias or invalidate the pre-registered estimate.

## 5. Reliability and attenuation (illustration, no correction applied)

Reliability ratio var(final) / var(first outturn) = 1.172 [0.966, 1.346]; SD of the first outturn 2.50 pp, of the final 2.71 pp. Slope of final on first 1.010 [0.910, 1.090]; slope of first on final 0.862 [0.804, 0.953].

Classical-measurement-error reasoning, in words. Suppose the first outturn equalled the final value plus noise that is independent of the final value. Then var(first) = var(final) + var(noise), so the reliability ratio would be below one, and it would equal the factor by which an OLS slope on the first outturn *used as a regressor* shrinks towards zero (a true slope of 1 would be estimated near the reliability). Under that model the revision would also be uncorrelated with the final value. The opposite polar case treats the revision as news that is independent of the first outturn (final = first + news); then var(final) is at least var(first), the reliability is at least one, and there is no attenuation. In this sample, the reliability is at or above one (1.17), the direction of the news model and not of added noise; the revision is correlated 0.03 [-0.23, 0.23] with the first outturn and 0.38 [0.14, 0.54] with the final, the correlation with the first outturn being closer to zero. The gap between the reliability and the slope of final on first (0.162) equals cov(revision, final) / var(first) and is zero in the pure classical-noise case. The real process is probably a mixture (new outturn data are news; re-estimation of potential output and benchmark changes behave more like systematic shifts), and the sample cannot separate the two.

What this means for the headline. In the pre-registered model CAPB is the *outcome* and the exposure `W_S` is calendar-based. Classical noise in an outcome does not bias the coefficient on an error-free regressor; it widens the interval. The attenuation reasoning therefore applies to analyses that use CAPB (or its lags) as a regressor and to any real-time re-analysis. Non-classical error, i.e. revisions associated with election exposure, is the case that could matter for the headline; section 7 describes it. No correction is applied: the headline stays as pre-registered.

## 6. Revision size by year and by country

By year (27 country-years each; `n_exposed` = country-years with `W_S > 0`, available for the confirmatory sample only). Rows marked * lie outside the confirmatory sample (2022-2024) and are not part of the primary sample.

| Year | n | n_exposed | Mean revision | SD | Mean abs | |rev| > 0.5 | Sign change |
|---|---|---|---|---|---|---|---|
| 2014 | 27 | 10 | 0.13 | 1.42 | 0.94 | 48% | 22% |
| 2015 | 27 | 11 | 0.35 | 1.30 | 0.72 | 37% | 11% |
| 2016 | 27 | 9 | 0.21 | 0.59 | 0.46 | 41% | 11% |
| 2017 | 27 | 10 | -0.18 | 0.82 | 0.58 | 41% | 15% |
| 2018 | 27 | 12 | 0.04 | 0.81 | 0.54 | 33% | 4% |
| 2019 | 27 | 10 | 0.43 | 0.92 | 0.67 | 41% | 7% |
| 2020 | 27 | 7 | 0.45 | 0.89 | 0.76 | 63% | 4% |
| 2021 | 27 | 9 | -0.31 | 0.54 | 0.46 | 33% | 4% |
| 2022* | 27 | - | -0.15 | 0.74 | 0.62 | 56% | 11% |
| 2023* | 27 | - | -0.10 | 0.70 | 0.45 | 30% | 0% |
| 2024* | 27 | - | -0.02 | 0.30 | 0.21 | 4% | 0% |

By country (primary sample, 8 years each, sorted by mean absolute revision; country-level statistics from 8 observations are unstable):

| Country | n | Mean revision | SD | Mean abs | Median abs | |rev| > 0.5 | Sign change |
|---|---|---|---|---|---|---|---|
| EL | 8 | 2.10 | 1.68 | 2.10 | 1.71 | 88% | 12% |
| IE | 8 | 0.58 | 2.07 | 1.63 | 1.59 | 75% | 0% |
| CY | 8 | 1.12 | 0.98 | 1.18 | 1.18 | 62% | 0% |
| MT | 8 | 0.02 | 1.57 | 1.16 | 1.14 | 62% | 0% |
| SI | 8 | 0.92 | 1.00 | 0.97 | 0.58 | 62% | 12% |
| PT | 8 | -0.58 | 1.37 | 0.77 | 0.44 | 38% | 12% |
| ES | 8 | 0.03 | 0.81 | 0.69 | 0.63 | 75% | 12% |
| LU | 8 | 0.31 | 0.85 | 0.66 | 0.42 | 38% | 0% |
| BG | 8 | 0.00 | 0.86 | 0.63 | 0.48 | 50% | 0% |
| EE | 8 | -0.13 | 0.73 | 0.62 | 0.63 | 62% | 12% |
| IT | 8 | 0.02 | 0.88 | 0.60 | 0.39 | 25% | 0% |
| DK | 8 | 0.30 | 0.60 | 0.54 | 0.57 | 50% | 0% |
| PL | 8 | 0.33 | 0.43 | 0.48 | 0.54 | 50% | 25% |
| HR | 8 | 0.33 | 0.64 | 0.48 | 0.26 | 25% | 12% |
| FI | 8 | -0.15 | 0.60 | 0.47 | 0.43 | 38% | 38% |
| FR | 8 | -0.35 | 0.49 | 0.44 | 0.30 | 38% | 0% |
| LT | 8 | -0.16 | 0.54 | 0.43 | 0.53 | 50% | 12% |
| AT | 8 | 0.08 | 0.51 | 0.42 | 0.38 | 38% | 0% |
| LV | 8 | 0.15 | 0.50 | 0.42 | 0.43 | 38% | 25% |
| SE | 8 | -0.38 | 0.48 | 0.41 | 0.17 | 38% | 25% |
| HU | 8 | -0.39 | 0.34 | 0.40 | 0.33 | 25% | 12% |
| DE | 8 | -0.36 | 0.33 | 0.38 | 0.31 | 25% | 0% |
| NL | 8 | 0.17 | 0.47 | 0.35 | 0.20 | 12% | 0% |
| CZ | 8 | -0.12 | 0.36 | 0.31 | 0.20 | 25% | 12% |
| SK | 8 | -0.11 | 0.41 | 0.30 | 0.29 | 38% | 38% |
| RO | 8 | 0.14 | 0.37 | 0.22 | 0.11 | 12% | 0% |
| BE | 8 | -0.08 | 0.20 | 0.17 | 0.17 | 0% | 0% |

## 7. Revisions and election-exposure years (descriptive, unadjusted)

| Stratum | n | Countries | Mean revision, pp [95% CI, country-clustered t] | Mean abs revision, pp [95% CI] | SD | Sign change |
|---|---|---|---|---|---|---|
| Exposure year (`W_S > 0`) | 78 | 24 | -0.074 [-0.278, 0.131] | 0.486 [0.375, 0.598] | 0.73 | 11.5% |
| Not an exposure year (`W_S = 0`) | 138 | 27 | 0.261 [-0.044, 0.566] | 0.725 [0.488, 0.962] | 1.07 | 8.7% |

Difference in the mean revision (exposure year minus other years): -0.334 pp, CR1 t(26) interval [-0.719, 0.050], country-cluster bootstrap interval [-0.695, 0.016]. Difference in the mean absolute revision: -0.239 pp, CR1 interval [-0.490, 0.012], bootstrap interval [-0.475, -0.014].

Descriptive and unadjusted: no controls, no country or year effects, no test of the election effect is reported or implied. An exposure-year difference in revisions could indicate that first-outturn CAPB is biased around elections (a real-time bias), but it could equally reflect which countries and years are exposed (the exposure-year count by year is in section 6), so it is not a replication of the election effect and it does not enter the confirmatory family.

## 8. Comparison with Gate 5

| Statistic | Gate 5 table (3 d) | Quoted in issue / decision log | S4 (unrounded) | Agrees with table at 3 d | Agrees with quoted figure |
|---|---|---|---|---|---|
| Mean absolute revision, pp | 0.639 | 0.64 | 0.63881 | yes | yes |
| SD of the revision, pp | 0.975 | 0.98 | 0.97499 | yes | NO |
| Level sign-change share | 0.097 | 0.097 | 0.09722 | yes | yes |
| Correlation first/final | 0.933 | 0.93 | 0.93302 | yes | yes |

All four statistics reproduce the Gate 5 table at its three-decimal rounding. Same definition (first outturn = earliest archived vintage with the year non-forecast under the Spring 2 / Autumn 3 rule, the frozen `first_release_table`), same window (2014-2021), same final (pinned Spring 2026) and the same country-years: S4 restates the Gate 5 computation and adds intervals; it is not a new estimate.

The rounded figure quoted in the issue and the decision log for the sd of the revision (0.98) differs from the S4 value rounded to two decimals (0.97): the unrounded S4 value is 0.97499, which Gate 5 printed as 0.975; rounding that three-decimal figure a second time gives 0.98. This is a double-rounding difference of one unit in the second decimal, not a difference of sample or definition.

## 9. Sensitivity: extended window 2014-2024

N = 297 (27 countries); 2022-2024 are outside the confirmatory sample, and their final values are only 1 to 3 years after the first outturn, so late revisions are not yet in.

| Statistic | Primary | Extended | Extended 95% interval |
|---|---|---|---|
| N | 216 | 297 |  |
| Mean revision, pp | 0.140 | 0.078 | [-0.057, 0.232] |
| Mean absolute revision, pp | 0.639 | 0.581 | [0.461, 0.722] |
| SD of the revision, pp | 0.975 | 0.895 | [0.664, 1.103] |
| Median absolute revision, pp | 0.421 | 0.375 | [0.301, 0.449] |
| Share |revision| > 0.5 pp | 42.1% | 38.7% | [32.0%, 45.8%] |
| Level sign-change share | 9.7% | 8.1% | [4.7%, 11.8%] |
| Correlation first/final | 0.933 | 0.945 | [0.924, 0.963] |
| Reliability var(final)/var(first) | 1.172 | 1.171 | [0.998, 1.321] |

## 10. Limitations

- CAPB is a model-based estimate (potential output, budget semi-elasticities). A revision mixes new outturn data with re-estimation of the model; the decomposition is not identified here.
- AMECO methodology changes between vintages (ESA 95 to ESA 2010 in Autumn 2015, a level shift at Spring 2020, COVID treatment; Gate 5 section 4), so a revision is not pure data noise and the vintage series is not homogeneous.
- The archived chapter 17 files are not guaranteed to be the originally released versions (Gate 5 section 8), so 'first outturn' means first outturn in the archive.
- The real-time panel covers 2015-2021 for elections (189 of 715 country-years; 51 elections), so it cannot support a replication of the election effect, and this appendix does not attempt one.
- The forecast / outturn cut-off is structural (no AMECO flag); country-specific exceptions were not checked. If Winter were treated as two forecast years the first outturn of some years could be a Winter vintage (Gate 5 section 8).
- Eight years per country and 27 countries: country-level statistics are unstable and the percentile bootstrap with 27 clusters is approximate. The intervals describe the sampling variation of the country panel, not the model uncertainty of AMECO.
- The reliability ratio, the sign-change shares and the exposure comparison are descriptive features of this panel, not estimates of a structural measurement-error parameter or of a real-time bias.

## 11. Provenance

- seed 42, 9999 country-cluster bootstrap draws, level 0.95; numpy 2.4.4, pandas 3.0.2, scipy 1.17.1.
- vintage long table `data/interim/ameco_vintage_capb.csv` SHA-256 `8d2540cac56bdcb1cefde4999486065197c6603ec8b97fa0d8e36c95ea31b9f5`.
- confirmatory panel read through `m1.load_real_panel` (tag `preregistration-v1`, hash-checked); used for `W_S` and for the SD of CAPB only.
- reproduce: `python src/evaluate/revisions.py`; tests: `python -m pytest tests/test_revisions.py -q -p no:cacheprovider`.
