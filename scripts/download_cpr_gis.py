#!/usr/bin/env python3
"""Download the CPR Land Sales point layer from the UCalgary SANDS ArcGIS service.

Pages through the public MapServer feature layer (which caps each response at
~2000 records) and writes a single WGS84 GeoJSON FeatureCollection.

Source: https://sands.ucalgary.ca/app/CPRLandSales/
Service: App_CPRLandSales/CPRLandSales_v1_Map_Public/MapServer layer 1
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

SERVICE = (
    "https://sands.ucalgary.ca/arcgis/rest/services/"
    "App_CPRLandSales/CPRLandSales_v1_Map_Public/MapServer"
)
# Layer 1 = sale points; layer 2 = quarter-section grid polygons. (Layers 3/6/7/
# 10 are identical render-scale copies of the grid, so only layer 2 is needed.)


def count(session: requests.Session, layer: int) -> int:
    r = session.get(
        f"{SERVICE}/{layer}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["count"]


def fetch_page(session: requests.Session, layer: int, offset: int, page: int) -> list[dict]:
    params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": page,
        "orderByFields": "OBJECTID",
    }
    r = session.get(f"{SERVICE}/{layer}/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json().get("features", [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layer", type=int, default=1,
                    help="MapServer layer id: 1=sale points, 2=quarter-section grid")
    ap.add_argument("--out", type=Path,
                    default=Path("data/cpr_land_sales/cpr_land_sales_points.geojson"))
    ap.add_argument("--page", type=int, default=2000)
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    session = requests.Session()
    total = count(session, args.layer)
    print(f"Layer {args.layer} reports {total} features; paging by {args.page}", flush=True)

    features: list[dict] = []
    offset = 0
    while offset < total:
        page = fetch_page(session, args.layer, offset, args.page)
        if not page:
            print(f"  empty page at offset {offset}; stopping", flush=True)
            break
        features.extend(page)
        offset += len(page)
        print(f"  {offset}/{total}", flush=True)
        time.sleep(args.sleep)

    fc = {"type": "FeatureCollection", "features": features}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"Wrote {len(features)} features to {args.out}", flush=True)
    return 0 if len(features) == total else 2


if __name__ == "__main__":
    sys.exit(main())
