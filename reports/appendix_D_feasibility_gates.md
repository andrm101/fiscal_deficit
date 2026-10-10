# Appendix D -- Feasibility numbers and week-2 gate proposals

Status: indicative probe, 2026-10-10. Script: `scripts/feasibility_probe.py` (throw-away probe, NOT the production pipeline; seed 42; prints every number below; ~20 s; nothing written to disk).
Panel: EU-27 (Eurostat codes, EL = Greece), 1995-2023, 27 x 29 = 783 country-years.
**All election calendars in this appendix are random placeholders (random phase, strict 4-year spacing). Every MDE is indicative only.**

## Sources (queried in memory)

| Item | Endpoint | Notes |
|---|---|---|
| OLDDEP1, PC_Y65_MAX, MEDAGEPOP | Eurostat `demo_pjanind` (JSON-stat 2.0) | 777 of 783 cells; Croatia missing 1995-2000 for all three |
| CAPB | DBnomics `AMECO/UBLGBP` | "Net lending excluding interest of general government adjusted for the cyclical component, adjustment based on potential GDP"; unit: % of potential GDP at current prices. Verified from dataset label and unit. DBnomics indexed 2026-06-04 (Spring 2026 vintage, series run to 2027) |
| Check | DBnomics `AMECO/UBLGAP` | Total cyclically adjusted balance. UBLGAP - UBLGBP is <= 0 in 100% of cells (mean -2.42 pp), i.e. minus cyclically adjusted net interest -> UBLGBP is the primary-balance variant, as required |

**Forecast exclusion rule.** DBnomics/AMECO carries no observed/forecast flag. Rule used: vintage indexed June 2026 = Spring forecast, so forecast years are t and t+1 (2026-2027) and the latest outturn year is t-1 = 2025. The analysis window ends 2023 <= 2025, so no forecast year enters. Caveat: the 2021-2023 values are outturn but their cyclical adjustment rests on revised potential-output estimates.

## 1. Ageing variation (EU-27, 1995-2023)

Exact sum-of-squares decomposition on the 26-country balanced subset (Croatia excluded for lack of 1995-2000 data); two-way SD also given on all 27 (unbalanced).

| Statistic | OLDDEP1 (%) | 65+ share (%) | Median age (yrs) |
|---|---|---|---|
| Pooled mean / total SD | 25.09 / 5.01 | 16.67 / 2.95 | 39.80 / 3.14 |
| Variance share: between-country | 0.443 | 0.459 | 0.381 |
| Variance share: common year effects | 0.483 | 0.475 | 0.554 |
| Variance share: two-way residual | **0.074** | 0.066 | 0.065 |
| Within-country share (1 - between) | 0.557 | 0.541 | 0.619 |
| SD, country-demeaned (within) | 3.74 | 2.17 | 2.47 |
| SD, between component (country means) | 3.33 | 2.00 | 1.94 |
| **SD after country + year FE** | **1.36** (27 ctry: 1.35) | 0.75 | 0.80 |
| Year effects as share of within variance | 0.867 | 0.879 | 0.894 |
| Cross-country SD 1995 -> 2023 | 2.73 -> 4.19 | 1.84 -> 2.27 | 2.01 -> 2.33 |
| Mean change 1995-2023 | +11.1 pp | +6.6 pp | +7.5 yrs |
| Cross-country SD of the change | 3.70 | 2.03 | 2.22 |
| Common (mean-shift) share of squared change | 0.900 | 0.914 | 0.920 |
| Country-specific share | 0.100 | 0.086 | 0.080 |
| corr(country mean, EU-15 dummy) | +0.342 (R^2 0.117) | +0.291 | +0.188 |

- EU-15 (14 members in EU-27) mean OLDDEP1 26.3 vs 24.0 for post-2004 members (13, includes CY and MT, which are not CEE). Accession group explains only ~12% of the between-country variance, so a region/accession dummy does not absorb the between variation.
- At placeholder election dates (193 country-elections): SD of OLDDEP1 level 4.96; SD of its between-country component 3.31; SD of the within component 3.71.
- Standardised moderator z (pooled): SD of country means 0.67 z-units; two-way-demeaned SD 0.27 z-units.

**Implications.**
1. Main effect of OLDDEP1 with country + year FE: identified only from the two-way residual, 7.4% of variance, SD 1.35 pp (0.27 of the total SD). About 87% of within-country movement is a common upward trend that year FE absorb. Ageing is a slow, near-common trend, so a main effect is weakly identified.
2. Interaction ElectionWindow x OLDDEP1: the election dummy varies within country, so the interaction is estimable with country FE, but E x m mixes three sources: (a) cross-country heterogeneity in the election effect by average ageing level (between, SD 3.3 pp -- the largest usable source, 27 cross-sectional units); (b) election-effect drift over time along the common ageing trend (the trend is ~48% of variance and 87% of within variance), which is confounded with any period-specific change in election effects (SGP/fiscal-rule eras, crisis, COVID); (c) genuine within-country, trend-free variation (SD 1.35 pp). Year FE do NOT remove (b), because they absorb only the main effect of the year.
3. Within-between (Mundlak) design: use E x m-bar_i (between) and E x (m_it - m-bar_i) (within). Add E x period dummies (or E x linear trend) so the within term is not just a time-trend proxy. The clean within variation is small (1.35 pp; 0.27 SD), so expect the within interaction to be imprecise and the headline moderator result to rest mostly on between-country variation (a 27-cluster cross-section). Cross-country dispersion widens (SD 2.7 -> 4.2) while 90% of the squared 1995-2023 change is common, so divergence, not convergence, supplies the country-specific signal.

## 2. CAPB (AMECO UBLGBP) and indicative MDE

**Sample.** N = 27 countries; 22 balanced (29 years), 5 unbalanced; 770 of 783 country-years observed. Missing: HR 1995-2000 (6), CY 1995-96, CZ 1995-96, SI 1995-96, SK 1995 (13 in total).

**Variance.** Pooled mean -0.05, SD 3.06, min -27.62 (IE 2010), max 10.58 pp of potential GDP. Within-country SD 2.68; SD of country means 1.48; SD after two-way demeaning **2.37**. On the 22-country balanced subset: between 21.2%, year 17.9%, two-way residual 60.9% of variance. Robust residual SD (1.4826 x MAD) 1.98; largest residuals IE 2010 (-27.6), LT 1997 (-11.5), CY 2012, EL 2009, IE 2011. Pooled AR(1) of the two-way residual rho = 0.61 (country mean 0.59, range 0.14-0.91; FE-demeaning biases rho down by about 0.06). Effective clusters 27 (t critical, df 26 = 2.056).

**MDE design.** Estimation sample = the 770 cells with both CAPB and OLDDEP1. Per replication: random phase per country, 4-year election spacing; AR(1) noise with marginal SD 2.368 (observed two-way residual SD) and rho in {0, 0.61, 0.8}; OLS with country + year FE; country-clustered CR1 SEs (G/(G-1) x (N-1)/(N-K), K counts year FE); two-sided alpha 0.05 with t(26); 3,000 reps (3 x 3 scenarios, seed 42). SEs do not depend on the true effect (FWL), so power(beta) = P(|beta + b0|/se > t) is solved exactly from the null draws for 80% power. Interaction model: y = b1 E + b2 z + b3 E x z + FE, z standardised on the estimation sample; MDE is for b3 per +1 SD of the moderator, using real OLDDEP1. Wild-cluster bootstrap was not used.

| Residual autocorrelation | Election-year dummy (pp pot. GDP) | Pre-election-year dummy (pp) | Election x OLDDEP1, per +1 SD (pp) | Null rejection rate (election / pre / inter) |
|---|---|---|---|---|
| rho = 0 | 0.59 | 0.58 | 0.58 | 0.045 / 0.059 / 0.051 |
| rho = observed (0.61) | **0.37** | 0.37 | 0.38 | 0.053 / 0.055 / 0.058 |
| rho = 0.8 | 0.27 | 0.28 | 0.28 | 0.051 / 0.059 / 0.055 |

Median SEs: 0.199 / 0.125 / 0.091 (election dummy, by rho); analytic (2.056 + 0.842) x SE agrees within 3%. Monte Carlo error on a null rejection rate is about +/-0.004-0.008. MDE scales linearly with sigma: with the outlier-robust sigma = 1.98 all MDEs are x0.84 (e.g. 0.31 pp at observed rho).

Notes on direction: MDE falls as rho rises because a strict 4-year dummy is a high-frequency regressor, and persistent noise (at fixed marginal variance) has little power at that frequency. Real calendars (snap elections, irregular spacing) are less periodic, so the rho = 0 column is the safer planning number. The observed residual SD includes the Irish 2010 bank-recapitalisation outlier; the MDE would also shrink if one-offs are removed. Calibrating on the post-FE residual slightly understates the pre-FE noise (about 4% in SD).

**Comparison with the literature** (only what could be checked):
- Shi & Svensson (2006), *Journal of Public Economics* 90, 1367-1389: abstract-level finding that the fiscal deficit increases by close to 1% of GDP in election years on average, with larger cycles in developing countries. Verified from a search-result summary of the abstract; the headline deficit, not CAPB. An election-year dummy in our design would detect an effect of about 1 pp with power far above 80% (MDE 0.27-0.59 pp).
- Cyclically adjusted evidence: a search snippet attributes to Bednar (2019, system-GMM, EU-28, 1995-2016) a structural balance (% potential GDP) about 0.41 pp lower in the year before elections -- secondary source only, **not verified against the paper**. If true, an effect of that size is just above the MDE at observed rho (0.37, so power slightly over 80%) and well below it at rho = 0 (0.59, power roughly 50%; not computed exactly). Mink & de Haan (2006, euro area) was found only as a snippet (deficit, not CAPB). The claim that CAPB estimates are generally small or null: **not verified**.
- Reading: the design can detect headline-size cycles (about 1 pp) but is only marginally powered for structural-balance effects of about 0.4 pp, and a moderator interaction below about 0.4-0.6 pp per SD will not be detectable.

## 3. Effective estimation sample

- Country-years with OLDDEP1 and CAPB both observed, 1995-2023: **770 of 783 (98.3%)**, 27 countries. Croatia's OLDDEP1 gaps coincide with its missing CAPB years, so OLDDEP1 does not shrink the sample further.
- Earliest usable CAPB year: 1995 for 22 countries (AT BE BG DK EE FI FR DE EL HU IE IT LV LT LU MT NL PL PT RO ES SE); SK 1996; CY 1997; CZ 1997; SI 1997; HR 2001 (first both-observed year also 2001). Minimum observations per country 23.
- Cell count is not the binding constraint; the real limit is 27 clusters (use t(26), consider wild-cluster bootstrap) and a short election history per country.

## 4. Gate table (PROPOSALS for week-2; thresholds are judgement calls justified from the numbers above)

| Gate | Metric | Observed (probe) | Proposed GO | Amber / NO-GO | Rationale |
|---|---|---|---|---|---|
| G1 | Two-way-demeaned (country + year FE) SD of OLDDEP1 on the final sample | 1.35 pp (0.27 z-units); 7.4% of variance | >= 1.0 pp AND >= 0.20 z-units AND residual variance share >= 5% | Amber 0.7-1.0 pp (interaction via between-variation only, Mundlak mandatory); NO-GO < 0.7 pp for a main/within-effect claim | About 25% slack below observed so a defensible sample restriction (e.g. dropping HR or post-2019) does not fail the gate; below 0.7 pp the within term is almost pure trend |
| G2 | Election-dummy MDE (80% power, 5%, t(26), clustered) with real calendars, rho at observed value; also rho = 0 | 0.37 pp (rho obs.); 0.59 pp (rho = 0) | <= 0.50 pp at observed rho AND <= 0.75 pp at rho = 0 | Amber 0.5-1.0 pp; NO-GO > 1.0 pp (cannot detect even the Shi-Svensson headline effect) | Slack of about 35% over the placeholder result for real irregular calendars and the 2020 shock; 1.0 pp is the one effect size I could verify. Interaction (per +1 SD) required <= 0.75 pp |
| G3 | CAPB coverage (final sample, 1995-2023, outturn only) | 770/783 (98.3%); 22/27 start 1995; min 23 obs | >= 97% of cells (>= 760) AND all 27 countries >= 20 obs AND >= 22 countries from 1995 AND zero forecast-year cells | NO-GO if a vintage change drops coverage below 95% or any forecast year is included | Matches the observed coverage (missingness is 13 early-year cells in five accession countries); forecast rule from section "Sources" |

## Caveats

1. Placeholder calendars: strict 4-year cycles, random phase; real calendars are irregular and the dummy definition (election window) will change variance. Treat MDEs as order-of-magnitude.
2. MDEs scale with sigma (2.37 pp, includes IE 2010); robust sigma gives x0.84.
3. CAPB is ex-post revised AMECO data (potential-output revisions, COVID handling); real-time vintages are not used. AMECO has no forecast flag, so the cut-off is rule-based.
4. Gaussian AR(1) noise, no lagged dependent variable, no covariates (covariates would reduce sigma), no wild-cluster bootstrap; 27 clusters make CR1 inference fragile although null rejection is 4.5-5.9%.
5. Ageing decomposition excludes Croatia (balanced subset) for the exact shares; two-way SDs on all 27 are 1.35 / 0.75 / 0.79.
6. Literature figures: Shi-Svensson from an abstract-level search summary; Bednar (2019) second-hand and unverified; "CAPB estimates small or null" not verified.
