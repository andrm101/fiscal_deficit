# Election dates and the ageing moderator

Downloaded 2026-10-10; SHA-256 per file in `manifest.jsonl`. Re-acquire with `config/acquisition/gate3_elections_and_ageing.toml`.

## ETAD v1.0.0 (`etad/`, **not committed**: dataset licence not stated)

- **Source:** Higashijima, Shimizu, Washida & Yanai (2025), *Electoral Studies* 96, 102964, https://doi.org/10.1016/j.electstud.2025.102964; data page https://yukiyanai.github.io/data_etad/ (page dated 2025-07-16; the files' server `Last-Modified` is 2026-10-08).
- **Files:** `ETAD_v_1_0_0.csv`, `ETAD_codebook_ver_1.pdf`. One row per election (not country-year), 1945–2023.
- **Key variables:** `held_date` (first polling day), `sche_date` (originally scheduled date; judgement-coded), `dif_days` (held minus scheduled; negative = early), `timing1` (1 on schedule, 2 moved, 3 unknown), `timing2` (-1 early, 0 on schedule, 1 delayed), `reason`, `termlength` (years).

## ParlGov 2024 stable release (`parlgov_2024_stable/`, CC0 1.0, committed)

- **Source:** Döring & Manow (2024), https://doi.org/10.7910/DVN/2VZ5ZC (released 2024-08-12). Elections and cabinets only until June 2023; the project is retired.
- **Files:** `view_election.tab` (Dataverse file 10437092), `codebook.pdf` (10437091).
- **Key variables:** `election_date` (last day of a multi-day election), `election_type` (parliament vs European Parliament), `previous_parliament_election_id`.

## Eurostat `demo_pjanind` (`eurostat_demo_pjanind/`, committed with acknowledgement)

- **Source:** Eurostat, Population structure indicators at national level, https://doi.org/10.2908/DEMO_PJANIND; SDMX-CSV extract, EU-27, 1994–2025, accessed 2026-10-10.
- **Variables:** `OLDDEP1` old-age dependency ratio, 1st variant (65+ per 100 aged 15–64; population at 1 January), `OLDDEP3` (65+ per 100 aged 20–64), `MEDAGEPOP` median age. Flags in `OBS_FLAG` (b, e, p). Greece is `EL`.
