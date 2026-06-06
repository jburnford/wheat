#!/usr/bin/env python3
"""Download sparse authoritative DLS quarter-section anchor points.

We do NOT redistribute the proprietary IHS/Cenovus polygon geometry. Instead we
sample the centroids of the four *corner sections* (1, 6, 31, 36) of every
township from the public ArcGIS feature service, and use them only as
calibration anchors to fit our own regular DLS grid (see scripts/dls_grid.py).
The published grid is our computed reconstruction of the public survey fabric.

Source service (queryable, public):
  Grid_DLS_AGO / FeatureServer / 2  (Quarter Section)
  https://www.arcgis.com/home/item.html?id=013685e6e01d423b882bbf0b18f9c189

Output: data/cpr_land_sales/dls_anchors.csv  (gitignored intermediate)
        columns: QSC,SEC,TWP,RGE,MER,lon,lat   (lon/lat WGS84)

curl is used for the HTTPS GET because this machine's Python lacks CA certs.
"""
import csv
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cpr_land_sales" / "dls_anchors.csv"
BASE = ("https://services6.arcgis.com/fuL1oiT04UsHtQS8/arcgis/rest/services/"
        "Grid_DLS_AGO/FeatureServer/2/query")
PAGE = 2000


def webmerc_to_wgs84(x, y):
    lon = x / 20037508.34 * 180.0
    lat = y / 20037508.34 * 180.0
    lat = 180.0 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2)
    return lon, lat


def fetch(where, offset):
    args = [
        "curl", "-s", BASE,
        "--data-urlencode", f"where={where}",
        "--data-urlencode", "outFields=QSC,SEC,TWP,RGE,DIR,MER",
        "--data-urlencode", "returnCentroid=true",
        "--data-urlencode", "returnGeometry=false",
        "--data-urlencode", "orderByFields=OBJECTID",
        "--data-urlencode", f"resultOffset={offset}",
        "--data-urlencode", f"resultRecordCount={PAGE}",
        "--data-urlencode", "f=json",
    ]
    return json.loads(subprocess.run(args, capture_output=True, text=True, timeout=120).stdout)


def main():
    rows = []
    for mer in (1, 2, 3):
        where = f"MER={mer} AND DIR='W' AND SEC IN (1,6,31,36)"
        offset, got = 0, 0
        while True:
            d = fetch(where, offset)
            feats = d.get("features", [])
            if not feats:
                break
            for f in feats:
                a = f["attributes"]
                c = f.get("centroid")
                if not c:
                    continue
                lon, lat = webmerc_to_wgs84(c["x"], c["y"])
                rows.append([a["QSC"], a["SEC"], a["TWP"], a["RGE"], a["MER"],
                             round(lon, 6), round(lat, 6)])
            got += len(feats)
            offset += PAGE
            if not d.get("exceededTransferLimit") and len(feats) < PAGE:
                break
        print(f"MER {mer}: {got:,} corner-section centroids")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["QSC", "SEC", "TWP", "RGE", "MER", "lon", "lat"])
        w.writerows(rows)
    print(f"Wrote {OUT}  ({len(rows):,} anchors)")


if __name__ == "__main__":
    main()
