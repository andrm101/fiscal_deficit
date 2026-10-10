# Acquisition manifest for Gates 1–3 (pending approval)

Prepared 2026-10-10. **Nothing in this manifest has been downloaded.** The probes used to build it were page reads, HTTP HEAD requests, Dataverse's file-listing API, and one-byte ranged requests (`Range: bytes=0-0`) on six static files to read their total size from `Content-Range`. No file contents were retrieved or saved.

Machine-readable versions (these drive the downloader): [gate 1](../config/acquisition/gate1_ameco_2026_spring.toml) · [gate 2](../config/acquisition/gate2_fiscal_governance.toml) · [gate 3](../config/acquisition/gate3_elections_and_ageing.toml). Downloader: [src/ingest/acquire.py](../src/ingest/acquire.py), 17 offline tests passing (localhost server only). It needs `--allow-network`, never overwrites, rejects content-type mismatches, writes only under `data/raw/`, records size, SHA-256, retrieval time and headers per file, and marks accepted files read-only.

## 1. What I need from you

Reply with one of: **approve all**, **approve gate N only**, or a list of IDs to drop. On approval I will run, in order:

```bash
python src/ingest/acquire.py --manifest config/acquisition/gate1_ameco_2026_spring.toml --allow-network
python src/ingest/acquire.py --manifest config/acquisition/gate2_fiscal_governance.toml --allow-network
python src/ingest/acquire.py --manifest config/acquisition/gate3_elections_and_ageing.toml --allow-network
```

Total expected: about **10.8 MB** (9.0 MB from measured or provider-stated sizes, about 1.75 MB from my estimates for the six API extracts, plus two files of unknown size, A03 and A04, unlikely to exceed a few MB). Optional file A10 (7.1 MB TXT zip) is excluded unless you ask for it.

## 2. Manifest

Size basis: **measured** = total size read from the server and enforced exactly; **page_stated** or **provider_api** = size printed by the provider, recorded but not enforced; **estimated** = my estimate from row counts, not measured; **unknown** = not available before download.

| ID | Gate | File / endpoint | Local path (under `data/raw/`) | Expected size (basis) | Content type | Chapter / series | Release / vintage | Licence status |
|---|---|---|---|---|---|---|---|---|
| A01 | 1 | `ameco_all_csv` (all zipped CSV files) | `ameco/2026_spring/ameco_all_csv.zip` | 6,181,987 B (measured) | application/zip | All chapters | Spring 2026; page date 3 Jun 2026; server Last-Modified 2026-06-02 14:51 UTC | None stated ("free of charge") |
| A02 | 1 | `Ameco help files (2026_05).zip` | `ameco/2026_spring/docs/ameco_help_files_2026_05.zip` | about 256,502 B (page: 250.49 KB) | application/zip | Explanatory texts by variable | Page date 21 May 2026 (before the 3 June release) | None stated |
| A03 | 1 | `Reference_Metadata_AMECO.pdf` | `ameco/2026_spring/docs/Reference_Metadata_AMECO.pdf` | unknown | application/pdf | Methodology: forecast-year rule, back-casting | Updated 26/11/2025 (per scout) | None stated |
| A04 | 1 | SDMX 2.1 `datastructure/ECFIN/DSD_AMECO/1.4?references=children` | `ameco/2026_spring/sdmx/DSD_AMECO_1.4.xml` | unknown | application/vnd.sdmx.structure+xml | Code lists: exact labels | DSD 1.4 | None stated |
| A05 | 1 | SDMX-CSV `AMECO_CHAPTER17-01/A......UBLGBP` | `ameco/2026_spring/sdmx/AMECO_CHAPTER17-01_UBLGBP.csv` | about 250 KB (estimated; scout counted 1,140 rows) | application/vnd.sdmx.data+csv | **UBLGBP** (CAPB, primary outcome) | Spring 2026 (chapter flow stamped 03/06/26 per scout) | None stated |
| A06 | 1 | SDMX-CSV `AMECO_CHAPTER17-01/A......UBLGAP` | `.../sdmx/AMECO_CHAPTER17-01_UBLGAP.csv` | about 250 KB (estimated) | same | UBLGAP (cyclically adjusted net lending) | same | None stated |
| A07 | 1 | SDMX-CSV `AMECO_CHAPTER17-01/A......UBLGCP` | `.../sdmx/AMECO_CHAPTER17-01_UBLGCP.csv` | about 250 KB (estimated) | same | UBLGCP (cyclical component, potential-GDP basis) | same | None stated |
| A08 | 1 | SDMX-CSV `AMECO_CHAPTER06-05/A......AVGDGP` | `.../sdmx/AMECO_CHAPTER06-05_AVGDGP.csv` | about 250 KB (estimated) | same | AVGDGP (output gap vs potential GDP) | same | None stated |
| A09 | 1 | SDMX-CSV `AMECO_CHAPTER16-04/A......UBLGIE` | `.../sdmx/AMECO_CHAPTER16-04_UBLGIE.csv` | about 250 KB (estimated) | same | UBLGIE (unadjusted EDP primary balance, for contrast) | same | None stated |
| A10 | 1, optional | `ameco_all_txt` | `ameco/2026_spring/ameco_all_txt.zip` | 7,134,059 B (measured) | application/zip | Cross-format parity only | Last-Modified 2026-06-02 14:51 UTC | None stated |
| F01 | 2 | `Numerical-Fiscal-Rules-database-2025.xlsx` | `fiscal_governance/nfr_2025_update/Numerical-Fiscal-Rules-database-2025.xlsx` | about 179,446 B (page: 175.24 KB) | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | Rule database and Fiscal Rule Strength Index 1990–2024 | 2025 update, page date 5 Mar 2026 | None stated; legal notice not read |
| F02 | 2 | `fiscal_rules_database_en_old_methodology.xls` | `fiscal_governance/nfr_2025_update/fiscal_rules_database_en_old_methodology.xls` | about 382,464 B (page: 373.5 KB) | application/vnd.ms-excel | Old-methodology database, break audit only | 2016 update, dated 6 Mar 2017 | None stated |
| E01 | 3 | `ETAD_v_1_0_0.csv` | `elections_ageing/etad/ETAD_v_1_0_0.csv` | 438,778 B (measured) | text/csv | ETAD v1.0.0 | Page 2025-07-16; **server Last-Modified 2026-10-08** | Dataset licence not stated; citation requested |
| E02 | 3 | `ETAD_codebook_ver_1.pdf` | `elections_ageing/etad/ETAD_codebook_ver_1.pdf` | 82,079 B (measured) | application/pdf | Codebook v1 | same | Not stated |
| E03 | 3 | ParlGov `view_election.tab` (Dataverse file 10437092) | `elections_ageing/parlgov_2024_stable/view_election.tab` | 1,243,626 B (provider API) | text/tab-separated-values | Election dates, previous-election links | 2024 stable, released 2024-08-12; data to June 2023 | CC0 1.0 |
| E04 | 3 | ParlGov `codebook.pdf` (Dataverse file 10437091) | `elections_ageing/parlgov_2024_stable/codebook.pdf` | 248,194 B (provider API) | application/pdf | Codebook | same | CC0 1.0 |
| P01 | 3 | Eurostat SDMX-CSV `demo_pjanind/A.OLDDEP1+OLDDEP3+MEDAGEPOP.<27 geos>`, 1994–2025 | `elections_ageing/eurostat_demo_pjanind/demo_pjanind_EU27_OLDDEP_1994_2025.csv` | about 500 KB (estimated, about 2,600 rows) | application/vnd.sdmx.data+csv | OLDDEP1, OLDDEP3, MEDAGEPOP | Accessed on download date | Reuse with acknowledgement |

### Official URLs

All full URLs are in the TOML files; they are listed here so you can check them before approving.

- **A01** https://economy-finance.ec.europa.eu/document/download/fd885a67-e390-46fb-a6d0-bbc67d946ebf_en
- **A02** https://economy-finance.ec.europa.eu/document/download/ee1f3fdc-bef6-498e-9de0-d57257186a66_en?filename=Ameco%20help%20files%20%282026_05%29.zip
- **A03** https://economy-finance.ec.europa.eu/document/download/ae8a3bbf-7a9c-446c-a91e-e4e4f721c21d_en?filename=Reference_Metadata_AMECO.pdf
- **A04** https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/sdmx/2.1/datastructure/ECFIN/DSD_AMECO/1.4?references=children
- **A05–A09** https://webgate.ec.europa.eu/ecfin/redisstat/api/dissemination/sdmx/2.1/data/{AMECO_CHAPTER17-01|AMECO_CHAPTER06-05|AMECO_CHAPTER16-04}/A......{item}?format=SDMX-CSV
- **A10** https://economy-finance.ec.europa.eu/document/download/03324a2c-995c-4163-a57d-62eb2d7e80df_en
- **F01** https://economy-finance.ec.europa.eu/document/download/57a58927-0240-4bc2-8686-f2c8cb50bf19_en?filename=Numerical-Fiscal-Rules-database-2025.xlsx
- **F02** https://economy-finance.ec.europa.eu/document/download/8a4717d6-0689-486a-8e60-cc45f06d5737_en?filename=fiscal_rules_database_en_old_methodology.xls
- **E01 / E02** https://yukiyanai.github.io/data_etad/ETAD_v_1_0_0.csv · …/ETAD_codebook_ver_1.pdf
- **E03 / E04** https://dataverse.harvard.edu/api/access/datafile/10437092 · …/10437091 (each 303-redirects to a signed S3 URL)
- **P01** https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/demo_pjanind/A.OLDDEP1+OLDDEP3+MEDAGEPOP.AT+BE+…+SK?startPeriod=1994&endPeriod=2025&format=SDMX-CSV&compressed=false

### Things the probing turned up (read before approving)

1. **AMECO has no static "bulk file" for the current vintage other than the zips on the download page.** The "Bulk Download Facility" is a query tool, so A01 (all CSV) is the immutable pin, and the SDMX-CSV extracts A05–A09 exist because only the SDMX response carries the `COMMENT` denominator string and `OBS_STATUS`. Whether the zip's CSVs carry an equivalent denominator field is **unknown until opened**; the metadata test therefore also checks zip-versus-SDMX parity.
2. **Vintage dates do not line up cleanly:** the page says "03 June 2026", the zip files report server `Last-Modified` 2026-06-02 14:51 UTC, the help zip is dated 21 May 2026, and the scout saw dataflow stamps of 21 May and 3 June. Each artefact is hashed separately and its own date is recorded; I will not claim they are one atomic snapshot until the content test confirms it.
3. **ETAD:** the page dates v1.0.0 to 2025-07-16 and says "available soon", yet both files were modified on 2026-10-08. The hash is recorded and the row count compared with the article's 3,127 elections. A silent re-upload would be reported, not hidden.
4. **Server quirks:** `Content-Length: 0` on HEAD for dynamic and several static EC endpoints, so sizes marked "unknown" or "estimated" are not measurable beforehand; Dataverse `.tab` sizes are the ingested tabular sizes.
5. The downloader sends an honest user agent (`fiscal-deficit-capstone/0.1`). If an EC server blocks it, I will report that and stop; I will not spoof a browser.
6. Multi-code SDMX filters (`A......UBLGBP+UBLGAP`) were not tested, so I use one request per item.

## 3. After download: what gets recorded (Gate 1)

Per file, in `data/raw/<source>/<vintage>/manifest.jsonl` (written by the downloader): `id`, requested and final URL, relative path, actual size, expected size and basis, size check result, **SHA-256**, **retrieval timestamp (UTC)**, HTTP status, content type, `Last-Modified`, `ETag`, licence status. The folder `data/raw/ameco/2026_spring/` is read-only and never overwritten.

Observed-versus-forecast status and last observed year are derived, not downloaded, so they are written by a separate step to `data/interim/ameco_2026_spring_snapshot.json`:

- `OBS_STATUS` distribution (the scout found `A` on every row, so the flag carries no information);
- the AMECO rule (last two years of a Spring vintage are forecasts) applied to each series to give the **last observed year used**, expected to be 2025 (forecast years 2026–27), with the sample end for the thesis separately fixed at the joint-coverage year (Gate 3);
- the vintage identifiers seen in the zip and in each SDMX `LAST UPDATE`.

## 4. Automated metadata test for UBLGBP (to be written once files exist: `tests/test_ameco_metadata.py`)

The test does not accept unit code 319 as evidence of the denominator. It must pass for `UBLGBP` to stay the provisional primary outcome.

| # | Assertion | Evidence source |
|---|---|---|
| 1 | **Exact official label** equals "Net lending (+) or net borrowing (-) excluding interest of general government adjusted for the cyclical component :- Adjustment based on potential GDP Excessive deficit procedure" | `DSD_AMECO_1.4.xml` (A04) |
| 2 | **Potential-GDP denominator**: the `COMMENT` field for every UBLGBP row contains "Percentage of potential GDP at current prices"; no row carries the "% of GDP (excessive deficit procedure)" text; UBLGIE's rows do carry the actual-GDP text (contrast) | A05, A09 |
| 3 | **Percentage scaling**: values are in percentage points, not fractions (e.g. DE 2009 ≈ +1.89 and EL 2009 ≈ −8.79 per the scout; plausible range check, 99th percentile of absolute values greater than 1); `UNIT_MULT` consistent with percent | A05 |
| 4 | **Surplus-positive sign**: label opens "Net lending (+)"; spot values from the scout (EL 2016 ≈ +10.58, EL 2009 ≈ −8.79) reproduced; **UBLGAP − UBLGBP ≤ 0 in every cell** (the difference is cyclically adjusted interest, scout mean −2.4 pp) | A05, A06 |
| 5 | **Release vintage**: `LAST UPDATE` of every UBLGBP row on or after the Spring 2026 stamp; same series in the A01 zip equals the SDMX series within rounding (chapter flows are rounded to 5 decimals); both vintage identifiers recorded | A01, A05 |
| 6 | **Observed versus estimated**: `OBS_STATUS` has no variation (documented non-informative); the last two years of each series are marked forecast by rule; no forecast year enters any estimation extract; last observed year reported | A03, A05 |
| 7 | **No silent country-code error**: Romania appears as `ROM`, Greece as `GRC`, and the crosswalk maps every code to the Eurostat code | A05 |
| 8 | **Series identity check (informational)**: UBLGIE − UBLGCP versus UBLGBP; the scout could not verify the identity, so this test **reports** the residual, it does not assert equality | A05, A07, A09 |

## 5. Gate 2: Fiscal Governance workbook audit (runs on F01, F02)

Written to `reports/gate2_fiscal_governance_audit.md`. The page provides no methodology note, user guide or escape-clause document (checked), so the workbook itself is the main evidence. The audit documents:

1. sheet names and structure; 2. annual coverage by country (1990–2024 claimed; country scope, EU-27 complete?); 3. how the index is built (components: coverage, legal strength, monitoring and corrective procedures, flexibility; weights if stated); 4. missing-value codes and how absence of a rule is coded (zero versus missing); 5. methodological breaks (comparison with F02; whether levels are comparable); 6. escape-clause and flexibility treatment (is an escape-clause year visible?); 7. whether the measure represents **legal strength, enforcement, or compliance**; 8. EU-level rules versus national rules (the page implies national only but does not say).

**Decision rule (yours):** if the workbook cannot support a time-varying, country-year, enforcement-or-strength-interpretable measure with documented breaks, **S2 is downgraded to exploratory** and removed from the secondary family.

## 6. Gate 3: real elections, joint coverage and power (runs on E01–E04, P01, A05)

Written to `reports/gate3_feasibility_update.md`, with code in `src/evaluate/power.py` and tests.

1. **Real calendar:** ETAD (`held_date`, `sche_date`, `dif_days`, `timing1/2`, `reason`, `termlength`) restricted to EU-27 national legislative elections, cross-checked against ParlGov dates; unclassified and unknown-scheduled-date elections listed in an exclusion table; ETAD file hash and row count compared with the article.
2. **Exposure** built exactly as frozen in the proposal (12-month fractional pre-election window, early-election and post-election terms), without any CAPB values merged.
3. **Final sample start year chosen from actual joint coverage** of CAPB (A05), the lagged moderator (P01), and the exposure, not imposed: the rule is the earliest year where at least 22 countries are jointly observed and every retained country has at least 20 observations; the end year follows ETAD and ParlGov (2023) unless the exclusion table says otherwise.
4. **Power by simulation**, three separate targets, each with the real calendar: the scheduled-election coefficient, the **between-country** ageing interaction, and the **within-country** ageing interaction. Calibration comes from the data: CAPB persistence (AR(1) on two-way residuals, with a Nickell-type correction because fixed-effects demeaning biases ρ downward), country-specific residual variances, and cross-country dependence preserved by resampling year-residual vectors across countries (block bootstrap by country-year). Inference matches the confirmatory plan (country-clustered with wild-cluster bootstrap-t, 27 clusters); minimum detectable effects reported at ρ = 0, observed, and high, with 80% power and α = 0.05, and compared with the G1 and G2 gate thresholds.
5. **Reporting** states plainly which assumptions come from the data and which are placeholders, and updates the 0.4–0.6 pp provisional range.

## 7. Items needing you (not downloads)

- **Literature gate:** I need full-text or author-manuscript versions of Carnazza, Liberati & Sacchi (2025) and Bednář (2019). ScienceDirect returned 403 and I will not bypass it. Please save the PDFs to `data/external/literature/` (Carnazza et al. is listed as open access, CC BY, via the publisher page), or tell me another route. (Update 2026-10-10: both have since been supplied and read in full.)
- **GitHub issues in the original repositories** (decision 9): the local `gh` login is `VonManstein142`, not `andrm101`. Confirm which account should post them before I open any issue.
