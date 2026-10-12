# Robustness and diagnostics specification (written and committed before the suite was run)

Date: 2026-10-12, after the confirmatory result (`reports/results/m1_confirmatory.md`) and before any robustness result. This note fixes the exact definitions of the sensitivities that `docs/preregistration.md` (sections 6, 9, 10) names without defining them. It does not change any pre-registered quantity. Nothing here may be altered after the suite has run except by a dated entry in `docs/amendments.md`; every result is reported whatever it shows, with no selection among specifications and no "specification curve" pick.

Code lives in new files only (`src/models/py/robustness.py`, `tests/test_robustness.py`). The frozen files (everything listed in `docs/freeze_manifest.json` under `src/`, `config/`, `docs/preregistration.md`, `scripts/freeze.py`, `requirements.lock`) must stay byte-identical; a test checks that.

The headline is the pre-registered V7 result. Targets: β_S (a full year of pre-election exposure to a scheduled election), γ_B (per +1 SD between-country ageing), and γ_W (descriptive). Every row below reports estimate, 95% interval, p-value where defined, and the pre-registered reading (excludes zero / equivalent within ±0.5 pp / inconclusive). A summary reports how many specifications keep the sign of β_S and how many have an interval that excludes zero, without ranking them.

## A. Inference sensitivities (cross-country dependence)

All use the M1 regressors exactly as in the headline (centred era terms, no controls, N = 715).
1. **OLS-FE baseline (V0)** with CR1 t(26) and with the null-imposed wild-cluster bootstrap-t (Rademacher, B = 9,999, seed key 42). Bridges from the headline estimator to the standard one.
2. **Driscoll–Kraay** standard errors on the OLS-FE baseline: Bartlett kernel, bandwidth m = floor(4·(T/100)^(2/9)) = 2 (T = 27 years), and a second run with m = 4. Critical values from t(26). Cross-checked against `linearmodels.PanelOLS(..., cov_type="kernel")` on the same data.
3. **Two-way clustering** (country and year; Cameron–Gelbach–Miller 2011) on the OLS-FE baseline, t(26).
4. **CCE (Pesaran 2006 pooled, CCEP)**: add to the OLS-FE model country-specific coefficients on the cross-sectional averages (CSAs, computed each year over countries in the sample) of the outcome and of every regressor; year effects are kept. Two versions fixed in advance: **CCE-full** (CSAs of `capb` and of all M1 regressors) and **CCE-lite** (CSAs of `capb` and of `W_S` only). Inference: CR1 t(26) and null-imposed wild-cluster bootstrap-t (B = 9,999). Report the number of added parameters against N and flag degrees-of-freedom exhaustion.
5. **V7 + CCE**: the headline estimator V7 applied to the CCE-lite and CCE-full designs (extra columns in the design), wild-cluster bootstrap-t as in the headline.
6. **Residual dependence diagnostics** on the V7 and OLS-FE residuals: Pesaran (2015) CD test and the average absolute pairwise correlation, before and after CCE augmentation.

## B. Pre-registered diagnostics (reported, never used to choose a specification)

Modified Wald groupwise heteroskedasticity; Wooldridge serial-correlation test; CIPS (Pesaran 2007) panel unit-root tests on `capb` and on the lagged moderator (constant and trend variants, lag order chosen by a fixed rule: 1); VIF of the M1 regressors (above 5 flagged); Hausman FE-vs-RE comparison alongside the Mundlak terms already in M1; binned-kernel linearity and common-support check for the two interactions (Hainmueller, Mummolo & Xu 2019; three equal-count bins); **lead placebo**: add `W_S_lead`, the share of year *t* inside months 13–24 before a scheduled election, to M1 and report its coefficient (the pre-window itself is months 1–12).

## C. Sample variants (V7, B = 9,999 unless stated)

Balanced-22 (the 22 countries observed in all 27 years); drop country-years that touch unclassified or delayed elections (`touches_unclassified_or_delayed`); gap-filled election classes (the `*_gf` exposure columns); **leave-one-country-out** (27 fits, B = 999, report the range of β_S and γ_B and the country whose removal moves β_S most); Ireland 2010 winsorised at the existing residual-tail rule (V2w); crisis exclusions: drop 2008–2012, drop 2020–2021, drop both; the **2022 extension** (N = 737, exposure complete on trust in ETAD for 22 countries) if it can be built without modifying frozen code, otherwise reported as not built; the robustness-controls model (add the lagged output gap and euro membership, N = 703).

## D. Definition variants (V7)

Pre-election window of 6 and of 18 months (all exposure classes rebuilt from `data/interim/election_calendar_eu27.csv` with the same share-of-year construction, in new code, not by editing the frozen module); a calendar-year election dummy (1 in the year of a scheduled election) in place of the fractional exposure; the moderator replaced by `OLDDEP3` lag and by median age lag (re-standardised, same Mundlak split).

## E. Outputs

`reports/results/robustness.md` and `.json`; a forest plot of β_S and γ_B across all specifications (300 dpi, units, source line); synthetic-data tests showing each new estimator recovers a known effect and that the Driscoll–Kraay result equals `linearmodels`.
