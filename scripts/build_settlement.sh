#!/usr/bin/env bash
# Build all layers for docs/settlement.html (CPR sales + homestead checkerboard).
#
#   CPR:        build_settlement.py -> township + QS-sale GeoJSON -> cpr_qs.pmtiles
#   Homesteads: download_dls_anchors.py (once) -> build_homesteads.py
#               -> township + QS GeoJSON -> homesteads.pmtiles
#
# Requires: python3 (pandas, openpyxl, numpy), tippecanoe (brew install tippecanoe)
set -euo pipefail
cd "$(dirname "$0")/.."

# ---- CPR land sales --------------------------------------------------------
python3 scripts/build_settlement.py   # Saskatchewan only (Province==SK)
echo "Tiling CPR quarter sections -> docs/cpr_qs.pmtiles ..."
# minzoom 4 so quarter sections render at the SK overview too (no circles);
# --drop-densest-as-needed thins sub-pixel cells at low zoom into a density carpet
tippecanoe -o docs/cpr_qs.pmtiles --layer=qs \
  --minimum-zoom=4 --maximum-zoom=13 --drop-densest-as-needed --no-feature-limit \
  --force docs/cpr_qs_sales.geojson
rm -f docs/cpr_qs_sales.geojson   # gitignored intermediate

# ---- Homesteads (needs the calibrated open DLS grid) -----------------------
if [ ! -f data/cpr_land_sales/dls_anchors.csv ]; then
  echo "Fetching DLS calibration anchors (one-time, needs network) ..."
  python3 scripts/download_dls_anchors.py
fi
python3 scripts/build_homesteads.py
echo "Tiling homestead quarter sections -> docs/homesteads.pmtiles ..."
# minzoom 4 (render at overview) .. maxzoom 13 (under GitHub's 100 MB cap; the map
# over-zooms cleanly to z15); --drop-densest-as-needed thins low-zoom cells
tippecanoe -o docs/homesteads.pmtiles --layer=homesteads \
  --minimum-zoom=4 --maximum-zoom=13 --drop-densest-as-needed --no-feature-limit \
  --force docs/homesteads_qs.geojson
rm -f docs/homesteads_qs.geojson   # gitignored intermediate

# ---- incorporated towns (1921 urban knowledge graph) -----------------------
python3 scripts/build_townsites.py

echo "Done. Open docs/settlement.html via a range-capable server (GitHub Pages, or 'npx http-server docs')."
