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
python3 scripts/build_settlement.py
echo "Tiling CPR quarter sections -> docs/cpr_qs.pmtiles ..."
tippecanoe -o docs/cpr_qs.pmtiles --layer=qs \
  --minimum-zoom=8 --maximum-zoom=14 --no-tile-size-limit --no-feature-limit \
  --force docs/cpr_qs_sales.geojson
rm -f docs/cpr_qs_sales.geojson   # gitignored intermediate

# ---- Homesteads (needs the calibrated open DLS grid) -----------------------
if [ ! -f data/cpr_land_sales/dls_anchors.csv ]; then
  echo "Fetching DLS calibration anchors (one-time, needs network) ..."
  python3 scripts/download_dls_anchors.py
fi
python3 scripts/build_homesteads.py
echo "Tiling homestead quarter sections -> docs/homesteads.pmtiles ..."
# maxzoom 13 keeps the file well under GitHub's 100 MB cap (quarter sections are
# still clearly visible/clickable; the map over-zooms cleanly to z15)
tippecanoe -o docs/homesteads.pmtiles --layer=homesteads \
  --minimum-zoom=8 --maximum-zoom=13 --no-tile-size-limit --no-feature-limit \
  --force docs/homesteads_qs.geojson
rm -f docs/homesteads_qs.geojson   # gitignored intermediate

echo "Done. Open docs/settlement.html via a range-capable server (GitHub Pages, or 'npx http-server docs')."
