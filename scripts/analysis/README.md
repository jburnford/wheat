# Homestead register analysis

Preliminary type / timing / geography analysis of the W1–W3 homestead registers,
written up in `docs/analysis/register_to_freehold.html` (Aug 2026).

Run in order from the repo root (needs pandas, pyarrow, shapely, openpyxl):

```sh
python3 scripts/analysis/build_table.py   # W1-W3 -> data/homesteads/analysis/homesteads_flat.parquet (~3 min)
python3 scripts/analysis/analyze.py       # type / timing / geography, rail proximity, CPR, reserve surrenders
python3 scripts/analysis/analyze2.py      # homestead-only lag, scrip, corporate holders, pre-emption, churn, fill speed
python3 scripts/analysis/analyze_cpr.py   # CPR land sales (SK): price, purchaser type/residence, outcomes, concentration, link to homesteads
```

- `build_table.py` reuses the parsers in `scripts/build_homesteads.py` (`year_of`,
  `names`, `tenure_group`) and the calibrated DLS grid for township centroids, so
  its row set matches the map exactly (281,850 rows at the Aug 2026 refresh).
- `analyze.py` writes `homesteads_flat2.parquet` (adds `rail_yr`, `churn`);
  `analyze2.py` writes `homesteads_flat3.parquet` (adds `holder`).
- `analyze_cpr.py` reads `data/cpr_land_sales/cpr_land_sales_points.geojson`
  (one point per quarter-section sale, with `Province`), classifies purchasers
  (Crown / railway / company / individual), parses stated residence from the
  purchaser string, classifies contract status, and name-matches individual
  purchasers against homestead claimants in the same or neighbouring township.
  Writes `cpr_sk.parquet`.
- `analysis_out.txt` / `analysis2_out.txt` / `analysis_cpr_out.txt` are the
  console output from the Aug 2026 runs; `chart_data.json` and
  `chart_data_cpr.json` are the extracts embedded in the report page.
- `data/homesteads/analysis/` is gitignored — rebuild it after each W1–W3 refresh.

Key definitions: settlement year = first of FirstDate → FirstDateSuccess →
Patent_Date; "churn" = `Number_of_claims > 1` or any name in `Failed_Claims`;
rail arrival = first line in `docs/rail_lines.geojson` built within 16 km of the
township centre.
