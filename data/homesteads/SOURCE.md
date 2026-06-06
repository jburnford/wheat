# Saskatchewan Homestead Records + Open DLS Grid

**Created by David Allan, Jim Clifford & Cheryl Troupe — Historical GIS (HGIS) Lab,
University of Saskatchewan.**

## Source records (work in progress)

`W1.xlsx`, `W2.xlsx`, `W3.xlsx` (repo root) — homestead claim transcriptions for
the 1st / 2nd / 3rd meridians west, one worksheet per range, one row per quarter
section. Columns: `QSECT, PSECT, PTWP, PRGE, PMER` (the Dominion Land Survey
description) plus `Type, FirstDate, FirstDateSuccess, Successful_Claims,
Failed_Claims, Patent_Date, Number_of_claims, Notes`.

| | |
|---|---|
| Total quarter-section rows | 484,876 |
| Rows with any data | ~256,000 |
| Rows with a settlement **date** | ~59,000 (span 1879–1935) |
| Meridians | W1 (ranges 30-34), W2, W3 |

### Known data-quality notes (it is a WIP transcription)
- `Successful_Claims` may list several claimants separated by `;`. **Where there
  is no date and more than one name, the patentee is unknown** (flagged `amb` in
  the output).
- Some sheets have **misaligned columns** — a name can appear in `Patent_Date`.
  The extractor only treats a value as a year if it actually parses as one.
- Institutional "claimants" (CPR, colonization railways, school districts, HBC)
  are kept but flagged `inst` — they are not homesteaders.

Settlement year used for the map = first available of FirstDate → FirstDateSuccess
→ Patent_Date. Rows with a name but no date are shown as **"claimed, undated."**

## Open DLS grid (how homesteads get geometry)

The spreadsheets carry no coordinates, and the CPR grid we already have only
covers the railway (odd) half of the checkerboard — homesteads sit on the
complementary **even** sections, so it joins to <3% of them. Saskatchewan's
authoritative quarter-section polygons are **proprietary**, so we reconstruct an
**open** grid instead:

1. `scripts/download_dls_anchors.py` samples the centroids of the four **corner
   sections** (1, 6, 31, 36) of every township from a public ArcGIS feature
   service (`Grid_DLS_AGO`, item `013685e6e01d423b882bbf0b18f9c189`). These
   sparse points are saved to `dls_anchors.csv` (**gitignored — not redistributed**).
2. `scripts/dls_grid.py` fits a per-township affine from those corner anchors and
   **generates** every quarter-section polygon as our own regular lattice.
3. We publish only that computed grid — a reconstruction of the public legal
   survey fabric — never the source polygons.

**Accuracy** (corner-anchored affine vs. held-out authoritative interior cells):
median **8 m**, mean 17 m, p90 32 m — well inside an 805 m quarter section. The
residual is the road-allowance non-linearity an affine can't capture.

## Rebuild

```sh
python3 scripts/download_dls_anchors.py   # one-time, needs network
scripts/build_settlement.sh               # builds CPR + homestead layers
```
