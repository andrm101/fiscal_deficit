# Eurostat extracts: controls and secondary outcomes

- **Provider:** Eurostat. Reuse allowed with acknowledgement of the source (https://ec.europa.eu/eurostat/web/main/help/copyright-notice). Committed.
- **Downloaded:** 2026-10-10 as SDMX-CSV (flags in a separate `OBS_FLAG` column; negative values preserved); SHA-256 and headers in `manifest.jsonl`. Re-acquire with `config/acquisition/gate4_controls_and_secondary.toml`.
- **Coverage:** EU-27, 1993–2025. Greece is `EL`.

| File | Dataset (DOI prefix 10.2908/) | Selection | Use |
|---|---|---|---|
| `gov_10a_main_pc_gdp_1993_2025.csv` | `GOV_10A_MAIN` | PC_GDP, S13: B9, D41PAY, TR, TE, D62PAY, D632PAY | Secondary outcomes (net lending, interest, revenue, expenditure, social benefits) |
| `gov_10a_main_d41pay_mio_eur_1993_2025.csv` | `GOV_10A_MAIN` | MIO_EUR, S13, D41PAY | Effective interest rate |
| `gov_10a_exp_cofog_pc_gdp_1993_2025.csv` | `GOV_10A_EXP` | PC_GDP, S13: TOTAL, GF10, GF1002, GF07 | Mechanism check (social protection, old age, health); shorter coverage |
| `gov_10dd_edpt1_gd_pc_gdp_1993_2025.csv` | `GOV_10DD_EDPT1` | PC_GDP, S13, GD | Lagged debt/GDP control |
| `gov_10dd_edpt1_gd_mio_eur_1993_2025.csv` | `GOV_10DD_EDPT1` | MIO_EUR, S13, GD | Interest-rate denominator |
| `nama_10_gdp_b1gq_cp_meur_1993_2025.csv` | `NAMA_10_GDP` | CP_MEUR, B1GQ | Nominal GDP growth |

## Definitions

`B9` net lending (+)/net borrowing (-); `D41PAY` interest paid (note the `PAY` suffix; plain `D41` returns nothing); `TR`/`TE` total revenue/expenditure; `D62PAY`/`D632PAY` social benefits in cash / social transfers in kind; `GD` government consolidated gross debt; `B1GQ` GDP at market prices; `PC_GDP` per cent of GDP; `MIO_EUR`/`CP_MEUR` million euro (current prices).
