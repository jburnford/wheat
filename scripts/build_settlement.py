#!/usr/bin/env python3
"""Build data layers for the prairie land-settlement timeline map (docs/settlement.html).

Outputs:
  docs/settlement_townships.geojson  - one point per township (TWP-RGE-MER) with
                                        cumulative-by-year arrays of sale count and
                                        price/acre, for the zoomed-out layer
  docs/cpr_qs_sales.geojson          - quarter-section grid polygons that recorded a
                                        CPR land sale, tagged with sale year + price/acre
                                        (fed to tippecanoe -> docs/cpr_qs.pmtiles)

The map theme is **price per acre** over time (CPR land sold cheap early, dearer
later). The year axis spans the CPR land-sale catalogue, 1881-1927, padded to 1944.

Reserved for later: Saskatchewan homestead records drop in as a second layer
following the same per-year-array convention as the township layer.

(Grain elevators are a separate, related project -- see docs/timeline.html.)
"""
import json
import re
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPR = ROOT / "data" / "cpr_land_sales"
DOCS = ROOT / "docs"

YEAR_MIN = 1881
YEAR_MAX = 1944
NYEARS = YEAR_MAX - YEAR_MIN + 1  # 64


def sale_year(props):
    m = re.match(r"\s*(\d{4})", props.get("Date") or "")
    if not m:
        return None
    y = int(m.group(1))
    if y < YEAR_MIN or y > YEAR_MAX:
        return None
    return y


def price_per_acre(props):
    """Parse the Price field ($/acre). Return float, or None if unusable."""
    try:
        v = float(props.get("Price"))
    except (TypeError, ValueError):
        return None
    if v <= 0 or v > 1000:  # drop zeros and absurd outliers (max real ~$25-30/ac)
        return None
    return v


def qs_key(p):
    """Build the grid's LLD key (QS-SEC-TWP-RGE-MER) from a sale point's parts."""
    qs, sec, twp, rge, mer = (p.get(k) for k in ("QS", "SEC", "TWP", "RGE", "MER"))
    if not all([qs, sec, twp, rge, mer]):
        return None
    return f"{qs}-{sec}-{twp}-{rge}-{mer}"


def cumulative(counter):
    """Counter{year:val} -> list of cumulative values indexed by (year-YEAR_MIN)."""
    out, run = [], 0
    for i in range(NYEARS):
        run += counter.get(YEAR_MIN + i, 0)
        out.append(round(run, 1) if isinstance(run, float) else run)
    return out


def main():
    print("Loading CPR land-sale points ...")
    pts = json.loads((CPR / "cpr_land_sales_points.geojson").read_text())["features"]
    print(f"  {len(pts):,} points")

    # ---- 1. township aggregate -------------------------------------------------
    twp_count = collections.defaultdict(collections.Counter)   # key -> {year: n sales}
    twp_psum = collections.defaultdict(collections.Counter)    # key -> {year: sum $/ac}
    twp_pcnt = collections.defaultdict(collections.Counter)    # key -> {year: n priced}
    twp_coords = collections.defaultdict(lambda: [0.0, 0.0, 0])
    twp_prov = {}
    # earliest sale year + price per quarter-section, for joining onto grid polygons
    qs_year, qs_meta = {}, {}

    for f in pts:
        p = f["properties"]
        if p.get("Province") != "SK":     # Saskatchewan-only map
            continue
        y = sale_year(p)
        price = price_per_acre(p)
        lon, lat = f["geometry"]["coordinates"]
        mer, rge, twp = p.get("MER"), p.get("RGE"), p.get("TWP")
        if mer and rge and twp:
            tk = f"{twp}-{rge}-{mer}"
            if y is not None:
                twp_count[tk][y] += 1
                if price is not None:
                    twp_psum[tk][y] += price
                    twp_pcnt[tk][y] += 1
            c = twp_coords[tk]
            c[0] += lon; c[1] += lat; c[2] += 1
            twp_prov[tk] = p.get("Province")
        k = qs_key(p)
        if k is not None and y is not None:
            if k not in qs_year or y < qs_year[k]:
                qs_year[k] = y
                qs_meta[k] = {
                    "price": price,
                    "purchaser": (p.get("Purchaser") or "").replace("`", "'"),
                    "acres": p.get("Acres"),
                }

    twp_features = []
    for tk, coord in twp_coords.items():
        n = coord[2]
        cum = cumulative(twp_count[tk])
        if cum[-1] == 0:
            continue
        psum = cumulative(twp_psum[tk])
        pcnt = cumulative(twp_pcnt[tk])
        first = next((YEAR_MIN + i for i in range(NYEARS) if cum[i] > 0), None)
        twp_features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(coord[0] / n, 5), round(coord[1] / n, 5)]},
            "properties": {
                "twp": tk, "prov": twp_prov.get(tk),
                "total": cum[-1], "first": first,
                "cum": cum,      # cumulative sale count by year (drives circle size)
                "psum": psum,    # cumulative sum of $/ac by year
                "pcnt": pcnt,    # cumulative count of priced sales by year
            },
        })
    (DOCS / "settlement_townships.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": twp_features}))
    print(f"Wrote settlement_townships.geojson  ({len(twp_features):,} townships)")

    # ---- 2. quarter-section sale polygons (themed by $/acre) --------------------
    print("Loading QS grid polygons ...")
    grid = json.loads((CPR / "cpr_land_sales_grid.geojson").read_text())["features"]
    qs_features = []
    priced = 0
    for f in grid:
        lld = f["properties"].get("LLD")
        y = qs_year.get(lld)
        if y is None:
            continue  # unsold grid cell -> omit (sales-only layer)
        m = qs_meta[lld]
        props = {"year": y, "lld": lld, "prov": f["properties"].get("Province"),
                 "purchaser": m["purchaser"], "acres": m["acres"]}
        if m["price"] is not None:
            props["price"] = m["price"]
            priced += 1
        qs_features.append({"type": "Feature", "geometry": f["geometry"], "properties": props})
    (DOCS / "cpr_qs_sales.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": qs_features}))
    print(f"Wrote cpr_qs_sales.geojson  ({len(qs_features):,} sold quarter-sections, "
          f"{priced:,} with a usable $/acre)")

    print("\nNext: run scripts/build_settlement.sh to tile -> docs/cpr_qs.pmtiles")


if __name__ == "__main__":
    main()
