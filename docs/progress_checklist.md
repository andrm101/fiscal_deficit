# Progress checklist

Status on 2026-10-13. "Committed" means on `origin/main` (latest commit `6633485`); the pre-registration tag is `preregistration-v1`. This file is not part of the freeze manifest.

## Done and committed

| Stage | Item | Evidence |
|---|---|---|
| A/B | Proposal, literature matrix (full-text reads of Carnazza et al. and Bednář), source-to-variable map, feasibility gates | `reports/proposal.md`, `reports/appendix_A..D`, `reports/literature_fulltext_*.md` |
| Data | Acquisition manifest, offline-first acquisition tool (hash-checked, bounded retries), licences note | `reports/acquisition_manifest_2026-10-10.md`, `src/ingest/acquire.py`, `data/external/LICENSES.md` |
| Data | AMECO Spring 2026 normaliser (unit text, no reliance on code 319), vintages, Eurostat reader, ETAD/ParlGov calendar | `src/normalize/*`, `reports/gate3_*.md` |
| Gates | Gates 2, 3, 3c, 3d (calendar and sample, power, specification, V7 candidate), Gate 4 (controls), Gate 5 (real-time feasibility) | `reports/gate*.md`, `config/acquisition/` |
| Panel | Gold panel N = 715 (27 countries, 1995–2021), audit | `src/features/panel.py`, `reports/gold_panel_audit.md` |
| Descriptives | Tier-1 descriptives and nine figures | `reports/tier1_descriptives.md`, `reports/figures/t1_*.png` |
| Freeze | Pre-registration, registry, SESOI 0.5 pp, manifest, tag pushed before analysis | `docs/preregistration.md`, `docs/freeze_manifest.json`, tag `preregistration-v1` |
| Confirmatory | M1 under V7, run once, provenance verified | `reports/results/m1_confirmatory.{md,json}` |
| Specs | Robustness and secondary specifications fixed before any result | `docs/robustness_spec.md`, `docs/secondary_spec.md` |
| Secondary | Ten outcomes with BH/BY, S3 descriptives, forest plot, self-check | `reports/results/secondary.{md,json}`, `reports/figures/secondary_forest.png` |
| Robustness | Suite of 52 specifications (inference sensitivities with Driscoll–Kraay cross-checked against `linearmodels` and CCE, diagnostics, sample and definition variants, leave-one-out, lead placebo); sign of beta_S kept in all 52, interval excludes zero in 4 of 11 inference variants | commit `e362ba9`; `src/models/py/robustness.py`, `tests/test_robustness.py`, `reports/results/robustness.{md,json}` |
| Figures | Five results figures (headline estimates, election-window profile, exposure partial plot, inference ladder, CAPB country-year heatmap) and the robustness forest | commit `6633485`; `reports/figures/f1_*..f5_*.png`, `robustness_forest.png` |
| Thesis | First full draft as a Quarto book (Typst PDF): abstract, chapters 1–8, appendices A–D, `references.bib`; results chapters read the committed JSON at render time | `reports/thesis/` (render with `python scripts/quarto.py render reports/thesis --to typst`); not yet committed at the time of writing |
| Hygiene | Stale pre-freeze test made tag-aware; post-freeze log; pinned `.venv`; Quarto wrapper | `docs/post_freeze_log.md`, `tests/test_freeze.py` |

## Gaps (open, in priority order)

1. **Thesis draft review and completion**: supervisor, programme, submission date and official length limit for the title page; author-name confirmation; missing references (Holm, Benjamini–Yekutieli, Cameron–Gelbach–Miller 2011, equivalence testing, pre-registration; listed in the header of `reports/thesis/references.bib`); entries marked `note = {details to verify}`; consistent figure style and the 300 dpi / source-line check (issue 34).
2. **Exploratory models E1–E6** (issue 29) and the **CAPB revision appendix S4** (issue 30): both pre-specified as descriptive and not in the thesis draft.
3. **Predictive module** (issue 31) and the **single optional extension** decision (issue 32).
4. **Engineering and reproducibility**: CI workflow (issue 4), Makefile / `run_pipeline.py` (issue 6), static tests for absolute paths and network use (issue 5), `verify_manifest()` (issue 8), AMECO silver builder with forecast flag (issue 10), DuckDB writer (issue 12), contracts enforced in code (issue 14), README-claims check (issue 35), seed audit (issue 36), model card (issue 37), clean-clone reproduction (issue 38).
5. **Licence terms** for AMECO, EC Fiscal Governance Database and ETAD (issue 3).
6. **Issue hygiene**: the open decision issues 19 and 20 (SESOI, demotion rule) are resolved in the registry and can be closed with a link to the freeze commit; issues 21, 22, 23, 24, 26, 27, 28 and 33 can be closed or updated now.
7. **Administrative**: deadline and official length limit (plan assumes 16 weeks and 60–80 pages); issues for the original `andrm101` repositories (deferred).

## Interpretation to carry into the thesis

* The confirmatory beta_S (−0.379 pp, Holm p = 0.036) keeps its sign in all 52 robustness specifications, but its interval excludes zero in only four of eleven inference variants (and in 7 of 9 sample variants, 4 of 5 definition variants and 26 of 27 leave-one-out fits). It must be reported as fragile to the inference method, not to the sample.
* Of ten secondary outcomes, one survives BH (change in CAPB); no spending or revenue component clearly drives the CAPB association.
