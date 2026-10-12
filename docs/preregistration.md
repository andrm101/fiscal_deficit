# Pre-registration: scheduled elections, population ageing and the cyclically adjusted primary balance in the EU-27

**Status: DRAFT, not frozen.** This document becomes binding when the git tag `preregistration-v1` is created on the commit that contains it and `docs/freeze_manifest.json`. Until then it may be edited. After the tag, every change is an amendment (section 14).

**Open items that block the tag:** none. The smallest effect size of interest (section 7) was confirmed by the researcher on 2026-10-12.

Language: results are described as associations. Scheduled elections are *predetermined*, not exogenous; the ageing interactions are never given a causal reading.

## 1. Question and hypotheses

*Are scheduled national elections associated with deterioration in the cyclically adjusted primary balance (CAPB) of EU member states, and does the association vary with population ageing?*

| ID | Statement | Status |
|---|---|---|
| **H1** | β_S: more pre-election exposure to a scheduled election is associated with a lower CAPB (expected sign negative; tested two-sided) | Confirmatory, Holm family of two |
| **H2B** | γ_B ≠ 0: the association differs with a country's average ageing level (cross-country heterogeneity; potentially confounded by other country traits). No direction is pre-registered | Confirmatory, Holm family of two |
| **H2W** | γ_W: whether the association changes as a country ages relative to its own mean | **Descriptive only**: estimate and interval, no test, no Holm adjustment. Decision D-C: not powered (minimum detectable effect 1.09 pp per SD) |

The confirmatory family is exactly {H1, H2B}, adjusted by Holm at a familywise level of 0.05.

## 2. Sample and data

- **Units:** 27 EU member states, annual, 1995–2021, **N = 715** country-years (unbalanced: 22 countries have all 27 years). Selection rule (decided before the outcome was merged to exposure): start year is the earliest year with at least 22 jointly observed countries and every retained country with at least 20 observations; end year is the last year with complete exposure for all 27 countries (the election sources end in 2023 and the 12-month pre-election window needs elections through the end of the following year). 14 country-years are excluded, all series starts: CY, CZ, SI 1995–96, SK 1995, HR 1995–2001.
- **Outcome `capb`:** AMECO `UBLGBP`, "net lending excluding interest of general government adjusted for the cyclical component, adjustment based on potential GDP, excessive deficit procedure", percentage points of potential GDP, surplus positive, **Spring 2026 vintage** (pinned; SHA-256 values in `data/raw/ameco/2026_spring/manifest.jsonl`). The last two years of that vintage (2026–27) are forecasts and are excluded. It is a model estimate, revised each vintage.
- **Election dates:** ETAD v1.0.0 (Higashijima et al., 2025) with ParlGov 2024 (Döring & Manow) as cross-check; both end in 2023. Cyprus and Malta come from ParlGov only and are unclassified.
- **Moderator:** Eurostat `demo_pjanind` `OLDDEP1` (persons aged 65+ per 100 aged 15–64, 1 January), accessed 2026-10-10, lagged one year.
- **Gold panel extract:** SHA-256 `2fcf20d4ca687f613d6743214b7be176ceb638b483f513eeed005bd1f73a5bb4` (715 confirmatory rows, sorted by country and year, fixed column order, comma-separated, LF line endings, booleans 1/0, missing as empty, floats with 10 decimals). Gold panel audit: `reports/gold_panel_audit.md`.

## 3. Exposure (frozen)

Built from election dates only, before any outcome was merged; module `src/normalize/elections.py`.
- **Windows:** pre-election window = the 12 months before the election day; `W_S`, `W_E`, `W_D`, `W_U` = the share of calendar year *t* inside the union of the pre-windows of scheduled, early, delayed and unclassified elections (0 to 1). `Post` = the share of year *t* inside the 12 months after any election.
- **Classification (ETAD, in this order):** unclassified if `timing1` is missing or 3, or `timing2` missing; delayed if `timing2` = 1 (unclassified when it contradicts `dif_days` or `reason` ∈ {7, 9}); early if `timing2` = −1 (unclassified when it contradicts `dif_days`); scheduled if `timing2` = 0, except `reason` ∈ {7, 9} gives early and `timing1` = 2 gives unclassified. ParlGov-only elections are unclassified. Counts over the 1990–2023 calendar: 143 scheduled, 75 early, 1 delayed, 29 unclassified.
- **Default treatment:** unclassified and delayed elections stay in the model as separate regressors (`W_U`; `W_D` is identically zero on the final sample and is dropped automatically).
- **Right-censoring:** no election after 2023 is hand-coded; the confirmatory sample therefore ends in 2021.

## 4. Model M1

For country *i*, year *t*, with country effects α_i and year effects λ_t:

`capb_it = α_i + λ_t + β_S·W_S + β_E·W_E + β_U·W_U + ρ·Post + γ_B·(W_S × abar_i) + γ_W·(W_S × adev_it) + η·a_it + Σ_e θ_e·(W_S × (era_e − m_e)) + ε_it`

- `a_it` = the lagged OLDDEP1 standardised to mean 0 and SD 1 on the estimation sample; `abar_i` = the country mean of `a` over that sample; `adev_it = a_it − abar_i`. The two interaction regressors are divided by the SD of their component, so γ_B and γ_W are effects **per +1 SD of the between and within component** (about 3.2 pp and 3.2 pp of OLDDEP1).
- **Era terms** for 2008–2015 and 2016–2021 (reference 1995–2007), each centred at its exposure-weighted mean `m_e = Σ(W_S·era_e)/Σ W_S`, so β_S is the association at the average era composition of scheduled-election exposure.
- **No controls.** Lagged output gap and euro membership are robustness controls only (703 rows).
- β_S is the effect of a full year of pre-election exposure (W_S = 1) at the sample-average moderator.

## 5. Estimator (V7, selected in Gate 3d)

Feasible weighted least squares with AR(1) feasible GLS and fixed effects, implemented by `GlsEstimator(design, wls=True, ar1=True)` in `src/evaluate/power_variants.py`. Steps, repeated unchanged in every bootstrap sample:
1. First stage: fixed-effects OLS of `capb` on the full M1 design; residuals `u1`.
2. Weights: `w_i = 1/σ_i²`, with σ_i² the mean squared first-stage residual of country *i*.
3. Persistence: pooled AR(1) coefficient of the country-standardised first-stage residuals over consecutive years, then the analytic Nickell correction (look-up inversion of the within-estimator bias at the mean number of observations per country).
4. Prais–Winsten transformation with that ρ, weighted by `w_i`; generalised least squares; coefficients and CR1 cluster-robust standard errors by country.

Selection record: the estimator was chosen by a pre-specified mechanical rule applied to power simulations (`reports/gate3c_specification_power.md`, `reports/gate3d_v7_candidate.md`).

## 6. Inference

- **P-values:** null-imposed wild-cluster bootstrap-t by country (27 clusters), Rademacher weights, **B = 9,999**, p = (1 + #{|t\*| ≥ |t|})/(B + 1), the whole feasible procedure re-estimated in every bootstrap sample; seed 42 through the project's seed scheme.
- **Intervals:** 95% bootstrap-t percentile intervals from the unrestricted wild bootstrap with the same weights and B. (Test-inversion intervals would be preferable in principle; they are computationally prohibitive here. Their absence is a limitation.)
- **Not valid for this estimator:** CR1 with t(26) (over-rejects by about 8–10% in simulation). It is shown for transparency only.
- **Multiplicity:** Holm over {H1, H2B}.
- **Known limitation:** under block-bootstrap noise, which carries real cross-country co-movement, wild-bootstrap size for β_S is about 11–12% (nominal 5%). The p-values may therefore be too small if cross-country dependence is real. Driscoll–Kraay and common-correlated-effects sensitivities accompany the headline.

## 7. Interpretation rule (smallest effect size of interest confirmed 2026-10-12)

Each interval is read three ways, with both flags reported: *excludes zero*; *equivalent*, if it lies inside ±SESOI; otherwise *inconclusive*. **Smallest effect size of interest (SESOI): 0.5 pp** of potential GDP (per SD for γ_B), between the two literature benchmarks (0.41 pp: Bednář 2019, WEO structural balance; 0.49 pp: Afonso, Alves & Leal 2026, primary expenditure). Because the typical first-outturn revision of the CAPB is 0.64 pp (`reports/gate5_realtime_feasibility.md`), measurement error is as large as the SESOI and must be stated beside every result.

## 8. Power and its limits (Gate 3d, wild bootstrap, 80% power, α = 0.05; pp of potential GDP)

| Target | At estimated persistence (ρ ≈ 0.69) | With no persistence | G2 |
|---|---|---|---|
| β_S | 0.513 | 0.807 | AMBER |
| γ_B (per SD) | 0.626 | 0.980 | AMBER |
| γ_W (per SD) | 1.091 | 1.647 | not powered |

Power for β_S against 0.41 pp is 63.5% (32.7% with no persistence) and against 0.49 pp 76.8% (42.5%). An inconclusive result is the most likely outcome and is a legitimate finding.

## 9. Diagnostics (reported, never used to select a specification)

Modified Wald (groupwise heteroskedasticity), Wooldridge serial correlation, Pesaran CD, CIPS unit-root tests on `capb` and the moderator, VIF (above 5 flagged), Hausman with the Mundlak terms, binned-kernel linearity and common support for the interaction (Hainmueller, Mummolo & Xu 2019), a lead placebo.

## 10. Pre-specified secondary analyses (Benjamini–Hochberg within the family)

Same model for: headline primary balance (AMECO `UBLGIE`, EDP, % of GDP), net lending, ΔCAPB, primary expenditure, revenue, social benefits (cash and in kind), COFOG social protection, old age, health; early-election term β_E with its own interval; robustness moderators (`OLDDEP3`, median age, 65+ share); sample variants (2022 extension, balanced 22, drop unclassified elections, gap-filled classes, leave-one-country-out, Ireland 2010 winsorised); robustness controls model; alternative windows (6 and 18 months, calendar-year dummies), crisis exclusions (2008–12, 2020–21), Driscoll–Kraay and CCE standard errors.

## 11. Exploratory and descriptive analyses

Fiscal-rule moderation (restricted to 2016–2021, lagged raw index; downgraded at Gate 2), triple interaction, nonlinear ageing, heterogeneity by debt level and EU-15 versus accession members, cabinet ideology and fragmentation, country typologies, at most one optional extension. Descriptive: S4 (CAPB revisions as a measurement-error appendix; a real-time election replication is not planned). Predictive module (rolling-origin, non-causal): persistence, regularised linear, gradient-boosted trees.

## 12. What was seen before this freeze (disclosure)

The outcome series was used for: sample coverage; unconditional descriptive statistics (`reports/tier1_descriptives.md`); and **residual-based noise calibration** for the power studies (persistence, country variance heterogeneity, the Ireland 2010 outlier). The choice of estimator was informed by that noise structure, never by any estimate of an election or ageing effect. **No statistic relating the outcome to any election variable has been computed.** During Gate 3a, file dimensions and coverage years of the CAPB file were printed before the exposure code was final; no CAPB value informed any classification or window. Literature figures used for benchmarks come from published abstracts and full texts (Appendix A and `reports/literature_fulltext_*.md`).

## 13. Reproducibility

Python 3.14.3 with the versions in `requirements.lock`; the confirmatory runner `src/models/py/m1.py` refuses to run on the real panel before the tag exists; raw file hashes are in the committed `manifest.jsonl` files; code and report hashes are in `docs/freeze_manifest.json`.

## 14. Deviations and amendments

After the tag, any change to sample, exposure, model, estimator, inference, hypotheses, family or interpretation rule is recorded in `docs/amendments.md` with date, reason and effect, and every affected result is labelled post hoc. Bug fixes that do not change any pre-registered quantity are logged but need no relabelling.
