# Full-text literature check: Bednář (2019)

Date of check: 2026-10-10. Reader: literature-gate subagent.

## 0. What was read and how

- File: `data/external/literature/POLITICAL BUDGET CYCLES IN THE EUROPEAN UNION_ NEW EVIDENCE -- Milan Bednař ... .pdf` (25 PDF pages).
- The Read tool's PDF mode failed (poppler's `pdftoppm` is not installed), so the text layer was extracted with pypdfium2. The text layer is clean on all 25 pages: body, footnotes, Tables 1-5, references and appendix.
- Equations M.1 and M.2 were garbled in the text layer, so PDF page 10 was rendered to an image and read. Table 5 (PDF pages 19-20) was also rendered to check significance stars. Figure 3 (PDF page 22) was read as an image.
- Not readable as text: Figure 1 (schematic), Figure 2 (country shares). Neither carries a number needed here. Figure 3 bar values match Tables 4-5.
- Page numbers below are printed journal pages. PDF page k = journal page 522 + k (PDF 1 = p. 523).
- Everything is paraphrased; no table is reproduced; only the coefficients needed are reported.
- Labels: FULL-TEXT VERIFIED (page) or UNRESOLVED.

## 1. Citation check

| Field | Value in PDF | Status |
|---|---|---|
| Author | Milan Bednář (PhD student, University of Economics, Prague) | FULL-TEXT VERIFIED (p. 523) |
| Title | Political Budget Cycles in the European Union: New Evidence of Fragmentation | FULL-TEXT VERIFIED (p. 523) |
| Journal | Acta Oeconomica, Akadémiai Kiadó | FULL-TEXT VERIFIED (p. 523) |
| Volume / issue / pages / year | Vol. 69 (4), pp. 523-547, 2019 | FULL-TEXT VERIFIED (p. 523; running headers) |
| DOI | 10.1556/032.2019.69.4.3 | FULL-TEXT VERIFIED (p. 523) |
| History | Received 16 Apr 2018; revised 16 Jul 2018; accepted 27 Oct 2018 | FULL-TEXT VERIFIED (p. 523) |

All project citations (Appendix A B8, proposal bibliography) match. The proposal's use of "Bednář" with diacritics is correct.

## 2. Sample

- Countries: "all 28 countries of the EU" (p. 533). The paper never prints the full list. UK is confirmed in the panel because it appears in the turnout group (Table 2, p. 535). France, Germany and Sweden are named in the text (p. 539). By inference the 28 are the EU-28 of 2016 (the 27 of our design plus the UK). Labelled UNRESOLVED as an explicit list; FULL-TEXT VERIFIED that it is 28 incl. UK.
- Years: 1995-2016, annual (p. 533). Frequency annual; the author says quarterly would be better but data are insufficient (pp. 531, 544).
- Panel is unbalanced (p. 533). The appendix (p. 547) gives 616 observations for the election dummy and decade dummies, which equals 28 x 22, so the panel is laid out for every country from 1995 regardless of accession date (inference: pre-accession years of the CEE countries are in the frame; whether they enter estimation is UNRESOLVED).
- Observations in the estimation: 513 (headline balance) and 464 (structural balance), 28 countries (Table 3, p. 537). The structural series has 552 observations before lags (appendix, p. 547).
- Data sources (Table 1, p. 534; intro p. 524): Eurostat (headline balance, household income); IMF World Economic Outlook (structural balance, GDP growth); World Bank Open Data (age ratio, internet use); Comparative Political Data Set (government changes); election dummy "own" (no source named); Transparency International CPI, Freedom of the Press index, Heritage Tax Burden index, International IDEA (legislature size, turnout) for the grouping variables.
- The reference list gives the CPDS as 1960-2014 (p. 545) while the sample runs to 2016 and the text cites "Armingeon et al. (2017)", which is not in the reference list. Minor internal inconsistency. gov_chan has 582 of 616 observations (p. 547).

## 3. Dependent variable

- Main outcome: "general government structural budget balance to potential GDP", variable `str_budget_exp_pt_gdp`, source IMF World Economic Outlook database (Table 1, p. 534). FULL-TEXT VERIFIED. It is the total structural balance (interest included), not a primary balance and not a CAPB. It is a level, in per cent of potential GDP.
- Secondary outcome: general government balance / GDP (`budget_exp_gdp`), Eurostat (Table 1, p. 534). FULL-TEXT VERIFIED.
- Source is the IMF WEO, not AMECO, EC, OECD or national sources. FULL-TEXT VERIFIED (p. 534).
- Vintage / download date: not stated anywhere. UNRESOLVED. (Inference only: sample ends 2016 and the paper was received April 2018, so a 2017-2018 WEO vintage is plausible; do not cite.)
- Ex-post versus real-time: not stated; no real-time or forecast data are mentioned. UNRESOLVED (the WEO historical series is by construction a single revised vintage, but the paper does not say so).
- Cyclical adjustment method: not described; the adjustment is wholly delegated to the IMF series. UNRESOLVED. The author's rationale for structural balance is that it captures policy motivation better and weakens the correlation with GDP growth (pp. 533, 523).
- Descriptives (appendix, p. 547): structural balance mean -2.51, SD 3.01, min -18.7, max 5.9 (n = 552).

## 4. Election variables

- The only election regressor in the main models is `L1.ELEC_effect`: the first lag of a dummy "capturing election year depending on a political system" (Table 1, p. 534). For semi-presidential systems both parliamentary and presidential elections are used (Table 1; footnote 10, p. 536). Source: "Own"; no election-date source is named. FULL-TEXT VERIFIED.
- Timing interpretation. The author says the lag means the effect "a year before the election year" (t-1), and the abstract and conclusions say the deficit occurs "in the year before elections" (pp. 523, 536, 538, 543). A first lag of an election-year dummy equals 1 in the year AFTER the election year, not the year before. Figure 1 (p. 526) and footnote 13 (p. 538) do not resolve this. The coding that would make the text correct (a lead of the election dummy, or a dummy defined as the pre-election year) is never stated. UNRESOLVED; this is an internal inconsistency that matters for how the 0.41 pp is cited. The appendix shows the dummy has a full 616 observations with mean 0.279 (about 172 flagged country-years), which cannot discriminate lead from lag.
- No election-year (t) coefficient, no year-after (t+1) coefficient and no lead coefficient is reported for the baseline. Only L1 appears in Tables 3-5. FULL-TEXT VERIFIED (pp. 537-542). The author states that the literature usually studies the election year and chose the lag instead (footnote 13, p. 538). EU Parliament elections and referenda were tried and gave inconsistent, insignificant results; not shown (p. 538).
- Scheduled versus early/snap: NOT distinguished. One pooled dummy; the only differentiation is by electoral system (parliamentary versus presidential). FULL-TEXT VERIFIED (pp. 534, 536).
- Endogeneity of election timing: explicitly NOT treated as endogenous (p. 531). Four reasons given: (1) Brender-Drazen (2005) and Ademmer-Dreher (2016) find neither theory nor evidence that it matters much; (2) Persson-Tabellini's concern about election dates and the cycle is handled by controlling for GDP growth and real disposable income growth; (3) crises and unrest are covered by decade effects, and EU members did not suffer substantial unrest; (4) Efthyvoulou (2012) is cited as finding PBCs not driven by strategically timed elections and, if anything, stronger when the date is fixed by law. No test, instrument or sample split on timing is run by the author. Reason (4) is second-hand and is the only statement about scheduled elections in the paper.

## 5. Other political variables, especially "fragmentation"

- The title's "fragmentation" is NOT party-system or legislative fragmentation. It means heterogeneity of the EU: splitting member states into sub-groups to see where cycles appear (pp. 523, 532, 538). FULL-TEXT VERIFIED. There is no party-fragmentation index in any regression.
- The only other political regressor is `gov_chan`, the number of changes in government per year (CPDS), entered as a level, treated as exogenous (pp. 531, 534). Coefficient: -0.445 (SE 0.134) for the headline balance and -0.277 (SE 0.109) for the structural balance (Table 3, p. 537); negative and significant in all models, interpreted as party competition or instability of ruling parties. Not interacted with elections.
- The literature review cites Bayar and Smeets (2009) for the finding that political fragmentation matters little for deficits (p. 527); that is second-hand.
- Political ideology and electoral-system characteristics were among the more than 30 associations screened, but no results are shown (p. 538).

## 6. Demographic / ageing variable

- `pop_15_64 / 65`: ratio of population aged 15-64 to population aged 65 and over, World Bank (Table 1, p. 534; text p. 532). It is a control in levels; a higher value means a younger population. FULL-TEXT VERIFIED.
- Coefficient: -0.943 (SE 0.822) headline; -0.982 (SE 0.585) structural (Table 3, p. 537). Neither is significant at 5 per cent. In the sub-sample models it is significant only in model (6) at -1.235 (SE 0.710, 10 per cent level; Table 5, p. 542).
- Not interacted with the election dummy anywhere. The author reads the negative sign as more potential voters raising incentives or lobby strength (p. 539), which is a loose reading of an insignificant control. No ageing-by-election result exists in the paper. FULL-TEXT VERIFIED.
- Descriptives: mean 4.38, SD 0.83 (p. 547).

## 7. Institutional and fiscal-rule variables

- None enters any regression as a regressor. FULL-TEXT VERIFIED (variable list, p. 534).
- Fiscal rules, euro membership, geography, electoral systems, ideology, trade openness, indebtedness, government expenditure, economic freedom and education were among the more than 30 characteristics screened for sub-group effects (p. 538), but only eight are reported. The fiscal-rule result is not reported. UNRESOLVED (not in the paper).
- Reported grouping variables with institutional content: legislature size (International IDEA, directly elected members), parliamentary turnout (International IDEA), tax burden (Heritage), corruption (CPI), media freedom times non-internet use (Freedom of the Press; World Bank). All are time-invariant country classifications based on whole-period averages (pp. 534-535).
- Euro-area and Southern/most-indebted sub-samples: no significant electoral effect, which the author notes contradicts Efthyvoulou (2012); results not shown (p. 540).

## 8. Estimator and specification

- Model M.1 (p. 532): outcome on two own lags, controls X, GDP growth, L1 election dummy, country effect, error. M.2 (p. 532): the same with the election dummy interacted with a group dummy and its complement, plus the group dummy and a growth-difference control (`gdp_var`). Structural balance only in M.2. FULL-TEXT VERIFIED (page 10 rendered).
- Estimator: two-step system GMM (Blundell-Bond), Windmeijer-corrected standard errors; software xtabond2 (pp. 529, 530). Whether errors are clustered by country is not said ("robust"). The table notes say t-statistics were used (p. 537).
- Instruments: lagged levels (two and more periods) of the dependent variable, gdp_growth and real disposable income change for the difference equation; one-period lagged differences for the level equation. Election dummy, gov_chan, age ratio and decade dummies are treated as exogenous, instrumented by themselves in the difference equation (pp. 533, 537).
- Proliferation controls: decade dummies in place of year effects; collapsed GMM matrix; PCA on the GMM-type instruments (Mehrhoff 2009); the author rejects limiting to second lags only (pp. 529-530). Number of retained components is not stated; KMO 0.872 / 0.864 and variance explained 0.740 / 0.747 are reported.
- Instrument count: 20 in Table 3, 22 in Tables 4-5, against 28 countries, so below the rule of thumb (pp. 529, 536, 537, 541).
- Tests, structural balance (Table 3 col 2): AR(2) test statistic 0.855, p = 0.393; Hansen 11.31, p = 0.334. Headline (col 1): AR(2) 0.964, p = 0.335; Hansen 12.08, p = 0.280. Tables 4-5: Hansen p from 0.128 to 0.518; AR(2) p from 0.21 to 0.83. AR(1) is not reported anywhere. FULL-TEXT VERIFIED.
- Time effects: three decade dummies (1990s, 2000s, 2010s), not year effects (pp. 529-530). These cannot absorb the 2008-2012 crisis or EU-wide shocks, which are correlated with the election calendar.
- Controls: GDP growth (endogenous), real adjusted disposable income per capita change (endogenous), government changes, working-age to elderly ratio (exogenous). The author avoids log GDP per capita because of near collinearity with growth (footnote 8, p. 532).
- Lagged dependent variable: structural 0.862 (SE 0.074) and second lag -0.113 (SE 0.076); headline 0.630 (SE 0.125) and -0.0872 (SE 0.098) (Table 3). Own derived calculation (not in the paper): the two structural lags sum to 0.749, so a permanent shift of -0.414 would cumulate to roughly -1.65 pp; the coefficient is a short-run impact conditional on this dynamics.

## 9. Main results

- Headline balance, L1.ELEC_effect: -0.496, SE 0.221, p < 0.05 (Table 3 col 1, p. 537).
- Structural balance, L1.ELEC_effect: -0.414, SE 0.174, p < 0.05, N = 464, 28 countries (Table 3 col 2, p. 537). This is the 0.41 pp figure quoted in the abstract and used in our project. By my own normal-approximation arithmetic the 95 per cent interval is about -0.76 to -0.07 pp.
- The author describes the range as -0.41 to -0.50 pp and says the structural effect is weaker, as expected (p. 536).
- Other timing coefficients (election year, year after, leads): none reported. Other election types: not shown.
- Other controls (structural): gdp_growth 0.126 (SE 0.083, ns); income change -0.122 (SE 0.093, ns); gov_chan -0.277 (SE 0.109, **) (Table 3).
- Heterogeneity (Tables 4-5, pp. 540-542; Figure 3, p. 544): interaction of L1 election dummy with group, structural balance:

| Group | Coefficient (pp) | SE | Stars |
|---|---|---|---|
| GDP per capita below 100% of EU-28 (17 countries) | -0.551 | 0.173 | *** |
| GDP per capita below 80% of EU-28 (11 countries) | -0.720 | 0.225 | *** |
| Post-communist (11) | -0.641 | 0.187 | *** |
| Low tax burden (10) | -0.613 | 0.225 | ** |
| High perceived corruption (11) | -0.758 | 0.242 | *** |
| Low media freedom / low internet use (10) | -0.740 | 0.174 | *** |
| Low number of directly elected legislators (20) | -0.485 | 0.189 | ** |
| Parliamentary turnout below 40% (13) | -0.733 | 0.197 | ** |

- Complement groups are all insignificant and of mixed sign (from -0.243 to +0.136; Tables 4-5). The paper reports no formal test that the group and complement coefficients differ. FULL-TEXT VERIFIED.
- The strongest cycles are in corruption, media/internet, GDP-per-capita (<80%) and low-turnout groups; the weakest is legislature size (p. 543). Country representation: Slovakia, Romania, Croatia and Bulgaria are in every group; Lithuania, Hungary, Poland, Latvia, Estonia and the Czech Republic in at least 75 per cent of groups; France, Germany, Sweden and ten others appear in 25 per cent or fewer (pp. 539-540). Cycles are therefore attributed to Central and Eastern Europe.
- The author states that group characteristics are not individually significant as regressors in the full sample, so no causal reading of them is possible (p. 539).
- Heterogeneity coefficients are the within-group impact of the lagged dummy; magnitudes range -0.49 to -0.76 pp (pp. 539, 544).

## 10. Robustness and stated limitations

- Authors' checks: headline versus structural outcome; EU Parliament elections and referenda (insignificant, not shown); euro-area and Southern sub-samples (insignificant, not shown).
- Stated limitations: annual data likely understate cycles, quarterly data not available (pp. 531, 544); group characteristics are associations, not causes; legislative-size result holds only in a larger group, so it is less robust (pp. 535-536); cut-off points set individually because of gaps in the distributions (pp. 534-535); suggests a threshold may exist (p. 539); recommends considering more characteristics (p. 544).
- Not done or not reported: leave-one-country-out; alternative instrument sets or year effects; one-step or difference GMM; pooled OLS/FE comparison; placebo timing; any test that sub-group effects differ; scheduled/early split; real-time data.
- Selection concern: eight groups are reported out of more than 30 candidate characteristics screened (p. 538), and cut-offs were chosen after seeing results, so the heterogeneity findings carry a multiple-testing and garden-of-forking-paths risk. This is my assessment, not the author's.

## 11. Implications for our design (EU-27, CAPB level, scheduled-election exposure, ageing interaction)

- Direct comparator for H1? Partial. Same literature strand (EU panel, election timing, structural balance), but: overall WEO structural balance (interest included) rather than CAPB; EU-28 incl. UK; pooled election dummy; ambiguous timing coding; dynamic GMM impact coefficient. The 0.41 pp is a defensible order-of-magnitude benchmark, not a like-for-like target.
- Separates scheduled from early elections? No. The paper treats timing as exogenous by assertion and cites Efthyvoulou second-hand.
- Ageing interaction? No. An uninteracted age-ratio control only; insignificant. Our novelty claim (ageing x election) is not contradicted.
- Replicate: structural/cyclically adjusted outcome rather than headline; control for GDP growth and income; government-change control (gov_chan) as a candidate political control; reporting of AR(2) and Hansen p-values and instrument count if we run any GMM robustness; instrument count below number of clusters.
- Avoid: decade dummies instead of year effects (keep two-way FE or year effects, because crisis years and election calendars correlate); instrument proliferation (if system GMM is run, collapse, cap lags, report count below 27 clusters; PCA step is optional and its component count should be reported); undocumented vintage and cyclical-adjustment method (we must record the AMECO/EC vintage and download date); lagged-dummy timing ambiguity (define in a codebook whether exposure is year before, election year or after); unreported significance conventions; post hoc sub-group selection (pre-specify the ageing moderator).
- Power note: with SE 0.174 the paper's own interval reaches roughly 0.76 pp, so the 0.41 benchmark is imprecise. Our MDE (about 0.66-0.68 pp, blueprint 7.1) sits inside that interval; the benchmark comparison should say so.
- Early elections: since the paper pools scheduled and early elections, its effect may be a blend. Efthyvoulou-based remark (stronger when date fixed by law) is the only support for scheduled-only cycles and should be cited as second-hand.

## 12. Statements in project files confirmed, contradicted or qualified; corrections needed (files not edited)

### 12.1 `reports/appendix_A_literature_matrix.md`, row B8 (line 110)

| Statement | Status | Correction |
|---|---|---|
| 28 EU countries, 1995-2016 | Confirmed (p. 523, 533) | Add: annual, unbalanced, includes UK; N = 464 (structural), 513 (headline) |
| Structural budget balance to potential GDP | Confirmed (p. 534) | Add: IMF WEO general government structural balance (total, interest included; not primary, not CAPB); vintage not stated; cyclical adjustment method not described |
| Election timing (year before election) | Qualified | Regressor is L1 of an election-year dummy (parliamentary plus presidential in semi-presidential systems); authors read it as year before, notation implies year after; no scheduled/early split; no other timing coefficients |
| System GMM with PCA to limit instruments | Confirmed (pp. 529-530, 537) | Add: two-step, collapsed, Windmeijer SEs, 20 (22) instruments vs 28 countries, Hansen p 0.334, AR(2) p 0.393, decade dummies instead of year effects |
| "structural balance lower by 0.41 pp" | Confirmed and sharpened (Table 3 col 2) | -0.414, SE 0.174, p < 0.05; headline -0.496, SE 0.221 |
| Heterogeneity: lower GDP per capita, post-communist, low media freedom etc. | Confirmed (pp. 538-543) | Add magnitudes -0.49 to -0.76 pp, complements insignificant, no difference test, post hoc cut-offs from more than 30 screened characteristics; euro area and Southern groups insignificant; fiscal rules screened but not reported |
| "No ageing moderator in abstract" | Confirmed in substance, qualified | Full text: no ageing interaction, but a working-age/elderly ratio control is included (coefficient -0.98, SE 0.585, ns) |
| Verification "PASS via Crossref + OpenAlex abstract" | Superseded | Relabel FULL-TEXT VERIFIED, 2026-10-10 |
| Title "fragmentation" (implicit) | Add note | Means cross-country heterogeneity, not party-system fragmentation |

### 12.2 Appendix A section 3, item 2 (line 278)

- "Structural balance lower in the year before elections" must be qualified as in 12.1 (lagged election-year dummy; timing interpretation unresolved).
- "28 EU countries, 1995-2016, system GMM": confirmed.
- "Ageing is not in the abstract" should become "ageing enters only as an uninteracted control (age ratio, insignificant)". Add that the paper does not distinguish scheduled from early elections and treats timing as exogenous.
- "Closest prior work using a structural balance and election timing in the EU": still fair, but add the outcome is the IMF WEO total structural balance, not CAPB.

### 12.3 `reports/proposal.md`

- Section 6 table row (line 125): replace "About 0.41 pp lower in the year before elections; no ageing moderator in abstract" with the full-text values (0.41 pp, SE 0.17, WEO total structural balance, lag of election-year dummy, age ratio as uninteracted control). The column header says "abstract-level"; this row is now full-text.
- Gap paragraph (line 141): the statement that Bednář is the closest structural-balance prior is confirmed; add that it does not separate scheduled from early elections and has no CAPB or ageing interaction. This reinforces rather than weakens the gap.
- Open items (line 430, item 4) and deliverables table (line 370): "Bednář is still abstract-only; no file in data/external/literature" is now false. The two questions it names are answered: no scheduled/early split; structural-balance source is IMF WEO with vintage not stated.
- Lines 359 and 423 (0.41-0.49 pp benchmarks): 0.41 is full-text verified; add that the benchmark outcome differs and the paper's interval is wide (about -0.76 to -0.07 by my arithmetic).
- Line 423 "one structural-balance study (Bednář 2019)": acceptable; specify "total structural balance, IMF WEO".

### 12.4 `docs/stage_c_blueprint.md`

- Section 7.1 bullet (line 161): "Bednář 0.41 pp, abstract-level" should read full text (Table 3, structural balance, SE 0.17); keep "indicative only", add different outcome and timing definition.
- Risk row T5 (line 183) and milestone row (line 197, "Bednář check (T5)"): resolved; the review need not carry the "abstract verified" label for Bednář.

### 12.5 Other places the 0.41 figure or Bednář status appears (found by search)

- `reports/appendix_D_feasibility_gates.md` lines 68 and 92 ("secondary source only, not verified"; "second-hand and unverified").
- `reports/gate3_power_update.md` lines 153 and 164 ("abstract-level, Appendix A row B8").
- `src/evaluate/power.py` line 911 label "abstract-level"; `scripts/feasibility_probe.py` line 418.
- `docs/decision_log.md` entry 7; `reports/acquisition_manifest_2026-10-10.md` line 113; `reports/literature_fulltext_carnazza.md` lines 9 and 107 ("no Bednar file present").

### 12.6 Inconsistencies inside the paper

1. Timing: the regressor is a lag of an election-year dummy, but the text and abstract call it the year before elections.
2. Table 1 and Table 2 swap the group sizes: Table 1 gives 11 countries for the under-100 group and 17 for the under-80 group, whereas Table 2 lists 17 and 11. Table 2 and the appendix means (0.182 vs 0.125) support the Table 2 version.
3. Stars: Table 5 model (6) gdp_var -0.340 (SE 0.102) has no star though t is about 3.3; parl_turn_40 -0.733 (SE 0.197, t about 3.7) carries only two stars while smaller t-ratios carry three.
4. Table 5 labels GDP growth `gdp_change` rather than `gdp_growth`.
5. Section 2.4 calls the balance measures "independent variables" (they are the dependent variable).
6. Conclusions write the deficit "rises by -0.41 pp", mixing sign conventions.
7. The CPDS citation (Armingeon et al. 2017 in text, University of Berne 2017 covering 1960-2014 in references) does not match the 2016 sample end.
8. Tables 4-5 report identical N, KMO and explained variance to Table 3 col 2 despite added regressors; plausible if the new controls are exogenous, but unexplained.
9. The author claims robustness from the Hansen tests, yet the AR(1) test is never reported (only AR(2) and Hansen), so the standard GMM diagnostic set is incomplete.
