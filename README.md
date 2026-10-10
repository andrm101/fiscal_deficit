# Scheduled elections, population ageing and the cyclically adjusted primary balance in the EU-27

MSc Data Science capstone (SDU Kolding). **Status: design and data-audit stage. There are no estimation results yet**, and no outcome model will be run before the pre-registration freeze (`preregistration-v1`).

## Question

Are scheduled national elections associated with deterioration in the cyclically adjusted primary balance (AMECO `UBLGBP`, % of potential GDP) of EU member states, and does the association vary with population ageing? Annual EU-27 panel, 1995–2021 (N = 715 country-years). Scheduled elections are treated as *predetermined*, not exogenous; the ageing interaction is never given a causal reading. The confirmatory model is a two-way fixed-effects regression with fractional 12-month pre-election exposure and a within/between split of the old-age dependency ratio.

**Known limitation.** A simulation on the real election calendar finds minimum detectable effects of roughly 0.7 pp (election term) and 0.9 pp per SD (ageing interactions), above the 0.4–0.5 pp effects reported in the literature. The thesis is therefore framed around interval estimates, and an inconclusive result is the most likely outcome. See `reports/gate3_power_update.md`.

## Where things are

| Path | Content |
|---|---|
| `reports/proposal.md` | Stage B proposal (supervisor-facing) and appendices A–D (literature, sources, repository reuse, feasibility) |
| `reports/gate*.md`, `reports/literature_fulltext_*.md` | Gate 1–4 audits and the full-text literature extractions |
| `docs/decision_log.md`, `docs/stage_c_blueprint.md` | Decisions, repository tree, data contracts, pipeline graph, tests plan, milestones, 16-week plan with scope-cut triggers |
| `config/` | Acquisition manifests, data contracts, model registries (confirmatory / secondary / exploratory / predictive), country crosswalk |
| `src/`, `tests/`, `scripts/` | Python code and tests (stdlib + pandas/numpy/scipy/statsmodels/pyarrow); R code arrives with the modelling milestone |
| `data/raw/` | Hashed, read-only source files with a `manifest.jsonl` and `README.md` per source |

## Reproducing

The pipeline is **offline-first** (ADR-001). Only `src/ingest/acquire.py` may use the network, and only with `--allow-network`:

```bash
python src/ingest/acquire.py --manifest config/acquisition/gate1_ameco_2026_spring.toml --dry-run
python src/ingest/acquire.py --manifest config/acquisition/gate1_ameco_2026_spring.toml --allow-network
python -m pytest tests -q
```

Raw files whose redistribution terms are unverified (AMECO, the EC Fiscal Governance workbooks, ETAD) are not in version control; the committed `manifest.jsonl` files carry their SHA-256 values so a re-download can be verified. Tests that read those files need them restored first. See `data/external/LICENSES.md`.

## Data sources and attribution

AMECO (European Commission, DG ECFIN), EC Fiscal Governance Database, Eurostat (reuse with acknowledgement), ParlGov 2024 (Döring & Manow, CC0), ETAD (Higashijima et al., 2025). Full citations and terms: `data/external/LICENSES.md`.

## Licence

Code and original text: MIT (`LICENSE`). Third-party data keep their providers' terms.
