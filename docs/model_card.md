# Model card: rolling-origin forecasts of the next-year change in the cyclically adjusted primary balance (EU-27)

Date: 2026-10-14. Issue 37. Specification: `docs/predictive_spec.md` (2026-10-13, written before any result). Results: `reports/results/predictive.md` and `.json`; figures `reports/figures/predictive_errors.png` and `predictive_importance.png`. Code: `src/models/py/predictive.py`, `src/models/py/predictive_report.py`; tests `tests/test_predictive.py`. This card describes a **retrospective, non-causal comparison**. It is not an operational forecasting tool.

## 1. Intended use and non-use

* **Intended:** to ask, in a pre-specified way, whether lagged fiscal and macro variables, and in addition known-at-the-origin election and demographic variables, improve out-of-sample prediction of the next-year change in CAPB beyond persistence, for the 27 EU member states, 2009-2023.
* **Not intended:** real-time forecasting of fiscal positions (the data are final-vintage and the target is a model estimate); any statement about what produces fiscal outcomes; ranking countries; informing policy or investment decisions. Predictors that improve accuracy are predictors only. Scheduled elections are predetermined and the pre-registered association (beta_S, headline) is neither supported nor contradicted by a predictive result.

## 2. Target and data

* **Target:** `capb_{T+1} - capb_T`, pp of potential GDP (AMECO `UBLGBP`, Spring 2026 vintage), within country, consecutive years only; origin T is the end of year T. Optional secondary event: change below -0.5 pp (the project's smallest effect size of interest).
* **Rows:** 27 countries; primary evaluation block P: origins 2008-2020, forecast years 2009-2021, 351 forecasts (no missing cell); held-out block H: origins 2021-2022, forecast years 2022-2023, 54 forecasts, reported descriptively and never pooled with P. Training windows expand from forecast year 1997 (305 rows at the first origin, 683 at the last). No forecast year after 2023; the vintage forecast years 2026-2027 are never used.
* **Sources:** AMECO Spring 2026 (CAPB, output gap), Eurostat (debt, interest, GDP, demography), ETAD v1.0.0 and ParlGov 2024 (election dates). All local, static, hashed; extract SHA-256 `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4`.

## 3. Information set and leakage control

Features are dated on or before the origin and entered as within-country deviations from the training-window country mean plus that mean (country scheme CD); every transformation parameter, hyperparameter and boosting iteration count is fitted on the training window only and re-done at each origin. No function of the calendar year is used.

* **Feature sets:** B0 = lagged CAPB level and last change; B1 = B0 + debt, output gap, interest-growth differential, euro membership; B2 = B1 + four election columns + old-age dependency (two definitions) and median age.
* **Election columns** (new code, from the calendar): known pre-election exposure of the forecast year and of the origin year, and post-election exposure of both, built from elections already held plus the statutory next date (last election date + its term length). The frozen realised exposure columns are not predictors, because they use the class and date of elections after the origin. Early, delayed and unclassified elections are unforecastable by construction. The strict rule agrees with ETAD's recorded scheduled date within 31 days for 86.7% of 203 comparable elections (the specification's 71% figure counted missing comparisons as misses; see Deviations in the results file).
* **Leakage diagnostics (not forecasts):** feature sets that use ETAD's ex-post scheduled date, or the realised exposure of the forecast year, were fitted to measure how much look-ahead would help. No visible gain in RMSE (at most 0.7% in either direction), so the strict rule is not hiding accuracy that leaked information would reveal.
* **Tests:** a poisoned-future test replaces every value dated after the origin (CAPB, controls, demographics, election dates, term lengths, scheduled dates) with extreme values and asserts identical features and bit-identical forecasts for ridge/elastic net, boosting and the GAM, while a leaking feature does change.

## 4. Models

P0 persistence (forecast 0) and P0b (last change repeated); P1a ridge / elastic net (44 configurations); P1b histogram gradient boosting from scikit-learn (8 configurations, iteration count chosen by time-ordered inner validation); P1c GAM (statsmodels GLMGam), descriptive. Hyperparameters are chosen by inner time-series validation over the last five forecast years of each training window with the grids fixed in the specification. SHAP, LightGBM and XGBoost are not installed; **SHAP: not run: not installed**. Seed 42 through the project seed scheme (key 6000).

## 5. Results (block P; pp of potential GDP; all figures from `reports/results/predictive.md`)

| Model | RMSE | MAE | RMSE ratio to P0 (95% country-cluster interval) |
|---|---|---|---|
| P0 persistence | 2.639 | 1.603 | 1.000 |
| P1a-B1 | 2.588 | 1.636 | 0.981 [0.926, 1.025] |
| P1a-B2 | 2.586 | 1.635 | 0.980 [0.931, 1.016] |
| P1b-B1 | 2.611 | 1.651 | 0.989 [0.947, 1.034] |
| P1b-B2 | 2.640 | 1.659 | 1.000 [0.969, 1.037] |

* **Against persistence (Diebold-Mariano with the Harvey-Leybourne-Newbold correction on 13 yearly mean loss differentials, two-sided, t with 12 df, Holm over the six pre-listed comparisons):** raw p 0.50, 0.45, 0.39 and 0.97 for P1a-B1, P1b-B1, P1a-B2 and P1b-B2 against P0; all Holm-adjusted p equal 1.0. No model is distinguishable from persistence.
* **Incremental value of the political and demographic block (B2 versus B1, same model class):** P1a raw p 0.94, relative MSE reduction +0.2% [-2.4%, +3.4%]; P1b raw p 0.18, relative MSE change -2.2% [-5.4%, +0.2%]; Holm p 1.0. Reading R3: no evidence that the block improves out-of-sample prediction in 13 forecast years. The test can only detect a mean loss differential of about 0.6 SD (50% power) to 0.85 SD (80% power) of the yearly differential, and a calendar signal of the pre-registered size could lower MSE by at most about 0.02 pp^2, so this null is expected and says nothing about the pre-registered association.
* **Calibration (realised on forecast):** slopes 0.78 [0.33, 1.39] (P1a-B1), 0.82 (P1a-B2), 0.68 (P1b-B1), 0.51 [0.00, 1.18] (P1b-B2): compatible with calibration but with wide intervals and a negative intercept; forecasts are noisy.
* **Error structure:** errors are dominated by crisis years (2010-2011, 2020) and by country-specific one-offs; RMSE by era is 2.97-3.07 in 2009-2015 and 2.01-2.06 in 2016-2021 for the learned models against 3.08 and 2.00 for persistence.
* **Block H (2022-2023, descriptive):** RMSE 1.58 for persistence; 1.49 (P1a-B1 and B2), 1.41 (P1b-B1) and 1.44 (P1b-B2); ratios 0.89-0.95. Two forecast years support no inference and the 2022 values of CAPB were used in an earlier robustness analysis.
* **Leave-one-country-out:** pooled RMSE ratio to the main run 0.996 (P1a-B1), 0.992 (P1a-B2), 1.019 (P1b-B1), 1.006 (P1b-B2); per-country ratios 0.94-1.31. Transfer to an unseen country is about as accurate as the main run, which itself is close to persistence.
* **Interpretation tools (predictive only):** out-of-sample permutation importance attributes the usable signal to the lagged fiscal-macro group (a 10.9% [3.0, 23.5] rise in squared error for P1a, 6.3% [1.1, 13.7] for P1b); permuting the political group changes squared error by -0.25% and -0.05% (intervals contain zero) and the demographic group by -0.39% and -0.30%. Accumulated local effects show mean reversion in the CAPB level and a mildly positive slope in debt; the known pre-election exposure has a flat curve.
* **Optional binary event** (change below -0.5 pp; prevalence 38.2% in P, 11.1% in H): Brier skill against the training-window rate 0.04 (P1a-B1) and 0.02 or less for the other sets in P; AUC 0.57-0.60. Descriptive only.

## 6. Limitations

1. **Ex-post revised target and features.** All values are the Spring 2026 vintage; CAPB, the output gap and potential GDP are model estimates revised with later data, so the vintage values of the lagged CAPB and output gap embed information from years after the origin. Comparisons across models share this contamination, but the accuracy levels are not operational forecast skill. A real-time replication is feasible for 2015-2021 only and is not planned.
2. **Measurement error of the target.** The CAPB revision SD is 0.97 pp and the mean absolute revision 0.64 pp (S4); the sign of the one-year change differs between first outturn and final in 14.8% of country-years, which also limits the binary event.
3. **AMECO forecast years.** The last two years of the vintage (2026-2027) are forecasts and are never used; the last forecast year used is 2023, because the election calendar is incomplete after mid-2023 and end-of-vintage potential-output revisions are largest; block H is closest to that edge.
4. **Small T.** 13 forecast years in P and 2 in H; 27 countries; the DM test has 12 degrees of freedom and the cluster bootstrap 27 clusters.
5. **Regime shifts and one-offs** (euro entry, fiscal rules, 2008-12, 2020-21 escape clause, 2022-23 energy support, Ireland 2010) change the data-generating process; no year effects are allowed by design.
6. **Political features measure the statutory schedule with error** and cannot see early or unscheduled elections; Cyprus and Malta use an assumed 5-year term.
7. **Demographic features are slow-moving and close to country identity.**
8. **No common-factor information** (no year effects, no cross-sectional means).
9. **Software:** no SHAP, LightGBM or XGBoost; scikit-learn boosting and statsmodels GAM are used.
10. **Associations only.** Nothing here supports a causal reading.

## 7. Ethical and misuse notes

The data are public macro-fiscal statistics on states; no personal data. Risks are over-reading a retrospective accuracy comparison as a forecasting service, and over-reading a null for the political block as evidence that elections do not matter for fiscal policy. Both readings are excluded by the specification.

## 8. Reproducibility

`.venv/Scripts/python.exe -m pytest tests/test_predictive.py` runs the synthetic and election-date tests; `.venv/Scripts/python.exe src/models/py/predictive_report.py --stage all` runs and caches every fit (requires the `preregistration-v1` tag) and rewrites the results and figures. Fits are cached in `data/interim/predictive_cache` (not committed). The frozen files listed in `docs/freeze_manifest.json` are verified unchanged by the run and by a test.
