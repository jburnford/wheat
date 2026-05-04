# Wheat project — status as of 2026-05-03

## Headline

**97.8% of elevator-row mentions geocoded** (97,200 / 99,430). Live interactive map at <https://jimclifford.ca/wheat/> and <https://jburnford.github.io/wheat/>. Repo: `git@github.com:jburnford/wheat.git`.

## Coverage by source

| Source | Rows | Notes |
|---|---|---|
| CGNDB direct | 92,755 | Canadian Geographical Names Database (NRCan) — the spine |
| Agent high-confidence | 2,658 | LLM picked from rapidfuzz top-5 CGNDB candidates with OCR-error reasoning |
| Lynch 1933 map interpolation | 539 | Gemini extracted ordered rail-line station sequences; midpoint between two anchored neighbors |
| Agent medium-confidence | 427 | Same agent, lower confidence |
| Manual historical | 252 | Renamed places: Port Arthur → Thunder Bay, Hobbema → Maskwacis, Prussia → Leader, Saint John West, etc. |
| HR_places shapefile | 193 | NRCan Historical Railway Places (1:2M scale) |
| Manitoba Historical Society | 118 | mhs.mb.ca/docs/sites/* |
| Wikipedia | 80 | Hand-applied for known hamlets |
| Wikidata | 66 | Q-IDs supplied by user (Leslie, Jefferson, Glenwoodville→Glenwood, Wassewa→Wawanesa, etc.) |
| DLS-converted | 49 | Section-Township-Range conversions (Astum, Aikens, Alcester) |
| OCR variant | 31 | Gouvenour→Gouverneur etc. |
| gent.name/sask | 20 | Rainton |
| vantagepoints DLS | 17 | Alcester |
| Wikipedia ghost towns | 12 | Elswick + 11 others |
| **(ungrounded)** | **1,574** | Mostly tiny tail, median ~2 rows per station |
| Parser artifacts | 656 | Excluded — cross-refs, OCR garbage, "0" station names |

## What's still ungrounded

| Category | Stations | Rows |
|---|---|---|
| Real-looking prairie hamlets | 412 | 1,323 |
| Sidings/spurs (no townsite) | 50 | 160 |
| Short OCR fragments | 15 | 57 |
| Parser noise (parens, etc.) | 27 | 64 |

The real-looking tail is steeply diminishing — only ~3 stations have 15+ rows, ~80 stations have 2 rows, ~150 have 1 row. Most useful next-pass work is the 5-15 row stations (~83 stations / ~640 rows).

## Pipeline (`scripts/`)

12 reproducible stages from raw OCR markdown to interactive map:

1. `parse_elevators.py` — markdown → flat table (province/railway tracking)
2. `reconcile_stations.py` — match against hr_places + Canada-History csd_verified_matches
3. `railway_crosswalk.py` — directory railway names → hr_codes CODE
4. `normalize_owners.py` — canonicalize grain-company names
5. `match_cgndb.py` — Canadian Geographical Names Database direct + no-space + variant matching
6. `build_candidates.py` — rapidfuzz top-5 candidates per unmatched
7. `merge_resolutions.py` — apply LLM-agent CGNDB resolutions
8. `filter_artifacts.py` — mark parser noise
9. `apply_external_coords.py` — manual + Wikipedia ghost + MHS + DLS fixes
10. `interpolate_from_rail_lines.py` — auto-midpoint between anchored neighbors using Lynch map sequences in `rail_lines.jsonl`
11. `fix_province_drift.py` — re-assign province where geocoded coords clearly fall in another province's bbox
12. `build_geojson.py` / `build_map.py` / `build_timeseries.py` — final viz outputs

## Outputs

`/home/jic823/grain/tables/`
- `stations_geocoded.csv` — one row per (station, province) with coords + provenance
- `rail_lines.jsonl` — 198+ Lynch-map line sequences
- `ghost_towns_sk.csv` — Wikipedia ghost-towns parsed locally

`/home/jic823/grain/docs/` (deployed to GitHub Pages → jimclifford.ca/wheat/)
- `index.html` — interactive Leaflet map (3,200 markers + rail lines)
- `stations.geojson` — GitHub auto-rendered map
- `rail_lines.geojson` — historical Canadian railways 1836-1922 reprojected
- `overview.png` — static prairie overview
- `elevators_by_year_long.csv` — long format (station × year × n_elevators × total_capacity)
- `elevators_by_year_wide.csv` — paired YYYY_n + YYYY_cap columns per year
- `elevator_count_by_year.csv` — heatmap-friendly station × year matrix of counts
- `elevator_capacity_by_year.csv` — heatmap-friendly station × year matrix of capacities

## Two notable bugs fixed

1. **`Coderre\`` station name**: an unescaped backtick prematurely closed Folium's JS template literal, throwing `SyntaxError: Invalid regular expression: missing /` and aborting the entire map script (only the legend rendered). Sanitized backticks in `build_map.py`.

2. **Province parser drift**: some volumes had OCR-fused page numbers prefixing section headings, e.g. `"5.....# LIST OF LICENSED ELEVATORS AND WAREHOUSES IN THE PROVINCE OF SASKATCHEWAN"`. The strict heading regex anchored `#` to line start and missed these, so the parser kept the previous province (e.g. MB) for hundreds of rows actually in the next province (SK). Two-part fix: lenient `PROVINCE OF X` detection in `parse_elevators.py`, plus `fix_province_drift.py` post-process. Recovered ~2,500 rows (94% → 97% coverage).

## Counts

- **Distinct station locations**: 4,858
- **Distinct elevator-operations** (station × owner): ~26,340 — best estimate of "elevator buildings"
- **Distinct grain companies** (canonicalized): 3,752
- **License years covered**: 23 (1911-1912 through 1943-1944, with gaps 1922-23 and 1931-32 through 1938-39)

By province (peak distinct stations ever-licensed):
- Saskatchewan: 1,839
- Manitoba: 1,461
- Alberta: 1,137
- British Columbia: 203
- Ontario: 70
- Quebec: 15

## Next steps (if returned to)

1. Top-20 still-ungrounded list (~250 rows total) is the high-value remaining tail. 9 down already (Leslie, Saint John West, Smith Spur, Enterprise, Hope Farm, Jefferson, Prussia, Rainton, Wassewa, Aikens, Glenwoodville, Alcester, Bannerman, Desford, Fairburn, Astum, Gouvenour, Leach Siding, Hayter resolved earlier). 11 more to grind.
2. Owner canonicalization is shallow (~3,752 distinct companies) — fuzzy clustering could collapse to ~300-500 actual entities for cleaner top-operator analytics.
3. Knowledge-graph load: schema design + Cypher MERGE for `(:Station)`, `(:GrainCompany)`, `(:RailwayLine)` with `NEXT_ON_LINE` edges from `rail_lines.jsonl`.
4. Could improve the static `overview.png` (currently aspect-ratio thin); cartopy or geopandas would let it look proper.
