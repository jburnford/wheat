#!/usr/bin/env python3
"""Spatially interpolate coordinates for unmatched stations using:
  1. Geocoded stations in the same (railway, province) — restricts to plausible region
  2. HR_rails_NEW line geometry for that railway code — projects onto the line
  3. Median of nearby geocoded stations as the interpolation seed

Approach:
  For each unmatched (station, province, rail_code):
    a) Find all geocoded stations sharing the same rail_code + province
    b) Compute the median lat/lon of those (the "rail-line centroid")
    c) Find HR_rails segments matching that rail_code + province bbox
    d) Project the centroid onto the nearest segment -> snapped point
    e) Use that snapped point as the station's interpolated location
    f) Confidence = 'low' (regional centroid on rail) / 'medium' (when only a few stations)

Outputs:
  /home/jic823/grain/tables/elevators_geocoded.csv (updated with interpolated coords)
  /home/jic823/grain/tables/stations_geocoded.csv (updated)
  /home/jic823/grain/tables/interpolation_report.csv (per-station explanation)
"""
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

import shapefile
from pyproj import CRS, Transformer

# HR_rails uses NAD27 Lambert Conformal Conic (projected meters).
HR_RAILS_CRS = CRS.from_proj4(
    "+proj=lcc +lat_1=49 +lat_2=77 +lat_0=49 +lon_0=-95 "
    "+x_0=0 +y_0=0 +datum=NAD27 +units=m +no_defs"
)
TO_WGS84 = Transformer.from_crs(HR_RAILS_CRS, CRS.from_epsg(4326), always_xy=True)

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"
HR_RAILS_SHP = GRAIN / "dataverse/HR_rails_new/HR_rails_NEW.shp"
REPORT = GRAIN / "tables/interpolation_report.csv"

# Rough province bboxes (lat_min, lon_min, lat_max, lon_max)
PROV_BBOX = {
    "MANITOBA":          (48.9, -102.0, 60.0, -88.0),
    "SASKATCHEWAN":      (48.9, -110.0, 60.0, -101.3),
    "ALBERTA":           (48.9, -120.0, 60.0, -109.9),
    "BRITISH COLUMBIA":  (48.0, -139.5, 60.0, -114.0),
    "ONTARIO":           (41.6, -95.5, 56.9, -74.3),
    "QUEBEC":            (44.9, -79.9, 62.6, -57.0),
}


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = p2 - p1; dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


def in_bbox(lat, lon, bbox):
    return bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]


def load_rails_by_code():
    """Load HR_rails segments grouped by BLDR_CODE.

    Returns dict[code] -> list of (lat, lon) coordinate sequences (line strings).
    The HR_rails shapefile uses NAD27 lat/lon coords.
    """
    sf = shapefile.Reader(str(HR_RAILS_SHP), encoding="latin-1")
    fields = [f[0] for f in sf.fields[1:]]
    out = defaultdict(list)
    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        code = str(rec.get("BLDR_CODE") or rec.get("INCRP_CODE") or "")
        if not code:
            continue
        # Get shape points (lon, lat ordering in shapefiles)
        pts = list(sr.shape.points)
        if not pts:
            continue
        # Heuristic: HR_rails coords look like (lon, lat) but for some files
        # may be projected. Detect: if abs(x)>180 or abs(y)>90, treat as projected and skip.
        latlon = []
        for x, y in pts:
            if -180 <= x <= 180 and -90 <= y <= 90:
                latlon.append((y, x))  # (lat, lon)
        if latlon:
            out[code].append(latlon)
    return out


def project_point_onto_line(plat, plon, line_pts):
    """Find closest point on a polyline (in lat/lon, treated as plane for short distances).
    Returns (lat, lon, distance_km) of the closest projection."""
    best = None
    for i in range(len(line_pts) - 1):
        ax, ay = line_pts[i]
        bx, by = line_pts[i+1]
        # Vector AB
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            cand = (ax, ay)
        else:
            t = ((plat - ax) * dx + (plon - ay) * dy) / (dx*dx + dy*dy)
            t = max(0.0, min(1.0, t))
            cand = (ax + t*dx, ay + t*dy)
        d = haversine(plat, plon, cand[0], cand[1])
        if best is None or d < best[2]:
            best = (cand[0], cand[1], d)
    return best


def closest_point_on_railway(plat, plon, segments, prov_bbox):
    """Return the closest projection across all segments (restricted to province bbox).
    Returns (lat, lon, dist_km) or None."""
    best = None
    for seg in segments:
        # Quick bbox filter: skip segments entirely outside province
        in_prov = any(in_bbox(la, lo, prov_bbox) for la, lo in seg)
        if not in_prov:
            continue
        # Filter to in-province points
        seg_in = [(la, lo) for la, lo in seg if in_bbox(la, lo, prov_bbox)]
        if len(seg_in) < 2:
            continue
        cand = project_point_onto_line(plat, plon, seg_in)
        if cand and (best is None or cand[2] < best[2]):
            best = cand
    return best


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())

    # Index existing geocoded coords by (rail_code, province)
    by_railprov = defaultdict(list)  # (code, prov) -> [(lat, lon, station)]
    for r in rows:
        if r["cgn_lat"] and r["rail_code"] and r["province"]:
            try:
                lat = float(r["cgn_lat"]); lon = float(r["cgn_lon"])
                if lat == 0.0:
                    continue
                by_railprov[(r["rail_code"], r["province"])].append(
                    (lat, lon, r["station"])
                )
            except (ValueError, TypeError):
                pass

    # Find unique unmatched stations + their volume/rail context
    unmatched_keys = {}
    for r in rows:
        if r["coord_source"]:
            continue
        if not r["station"]:
            continue
        key = (r["station"], r["province"])
        if key not in unmatched_keys:
            unmatched_keys[key] = {
                "rail_code": r["rail_code"],
                "rail_canonical": r["rail_canonical"],
                "rows": 0,
            }
        unmatched_keys[key]["rows"] += 1

    print(f"unmatched stations to interpolate: {len(unmatched_keys)}")

    # Load HR_rails segments
    rails = load_rails_by_code()
    print(f"HR_rails: {len(rails)} codes, "
          f"{sum(len(v) for v in rails.values())} segments")

    interpolated = {}
    report_rows = []
    for (station, prov), ctx in unmatched_keys.items():
        rail_code = ctx["rail_code"]
        bbox = PROV_BBOX.get(prov)
        if not bbox:
            report_rows.append({
                "station": station, "province": prov, "rows": ctx["rows"],
                "status": "no_province_bbox", "lat": "", "lon": "",
                "n_neighbors": 0, "neighbor_spread_km": "", "rail_dist_km": "",
            })
            continue

        # Find geocoded neighbors on the same rail line + province
        neighbors = by_railprov.get((rail_code, prov), [])
        if len(neighbors) < 3:
            report_rows.append({
                "station": station, "province": prov, "rows": ctx["rows"],
                "status": "too_few_neighbors", "lat": "", "lon": "",
                "n_neighbors": len(neighbors), "neighbor_spread_km": "",
                "rail_dist_km": "",
            })
            continue

        # Use median lat/lon as the rail-line centroid for this railway+province
        clat = median(n[0] for n in neighbors)
        clon = median(n[1] for n in neighbors)

        # Compute spread (median absolute deviation in km) for confidence
        dists = sorted(haversine(clat, clon, n[0], n[1]) for n in neighbors)
        spread = dists[len(dists)//2] if dists else 0  # median distance from centroid

        # Project centroid onto the nearest rail segment for that code
        rail_dist = ""
        snapped_lat, snapped_lon = clat, clon
        if rail_code in rails:
            cand = closest_point_on_railway(clat, clon, rails[rail_code], bbox)
            if cand:
                snapped_lat, snapped_lon, rail_dist = cand
                rail_dist = round(rail_dist, 2)

        interpolated[(station, prov)] = (snapped_lat, snapped_lon)
        report_rows.append({
            "station": station, "province": prov, "rows": ctx["rows"],
            "status": "interpolated",
            "lat": round(snapped_lat, 6), "lon": round(snapped_lon, 6),
            "n_neighbors": len(neighbors),
            "neighbor_spread_km": round(spread, 1),
            "rail_dist_km": rail_dist,
        })

    # Write interpolation report
    with REPORT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "station", "province", "rows", "status", "lat", "lon",
            "n_neighbors", "neighbor_spread_km", "rail_dist_km",
        ])
        w.writeheader()
        w.writerows(sorted(report_rows, key=lambda r: -r["rows"]))

    # Apply interpolations to elevators_geocoded.csv
    n_filled = 0
    for r in rows:
        if r["coord_source"]:
            continue
        coords = interpolated.get((r["station"], r["province"]))
        if coords:
            r["cgn_lat"] = str(round(coords[0], 6))
            r["cgn_lon"] = str(round(coords[1], 6))
            r["coord_source"] = "interpolated_rail"
            n_filled += 1

    with ELEVATORS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"interpolated rows: {n_filled}")

    # Stats
    n = len(rows)
    n_geo = sum(1 for r in rows if r["coord_source"]
                and r["coord_source"] not in ("parser_artifact",))
    n_real_unm = sum(1 for r in rows if not r["coord_source"])
    n_artifact = sum(1 for r in rows if r["coord_source"] == "parser_artifact")
    print(f"\ncoverage:")
    print(f"  geocoded:        {n_geo}/{n} ({n_geo*100//n}%)")
    print(f"  parser_artifact: {n_artifact}")
    print(f"  real unmatched:  {n_real_unm}")

    from collections import Counter
    print(f"\nby coord_source:")
    for k, v in Counter(r["coord_source"] for r in rows).most_common():
        print(f"  {k or '(none)':25} {v}")

    # Rebuild stations file
    pairs = {}
    for r in rows:
        k = (r["station"], r["province"])
        if k in pairs:
            pairs[k]["rows"] += 1
            continue
        pairs[k] = {
            "rows": 1, "cgn_id": r["cgn_id"], "cgn_name": r["cgn_name"],
            "cgn_concise": r["cgn_concise"], "cgn_lat": r["cgn_lat"],
            "cgn_lon": r["cgn_lon"], "hr_lat": r["hr_lat"],
            "hr_lon": r["hr_lon"], "csd_id": r["csd_id"],
            "wikidata_qid": r["wikidata_qid"], "coord_source": r["coord_source"],
        }
    with STATIONS.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "rows", "cgn_id", "cgn_name",
                    "cgn_concise", "cgn_lat", "cgn_lon", "hr_lat", "hr_lon",
                    "csd_id", "wikidata_qid", "coord_source"])
        for (st, prov), v in sorted(pairs.items(), key=lambda x: -x[1]["rows"]):
            w.writerow([st, prov, v["rows"], v["cgn_id"], v["cgn_name"],
                        v["cgn_concise"], v["cgn_lat"], v["cgn_lon"],
                        v["hr_lat"], v["hr_lon"], v["csd_id"],
                        v["wikidata_qid"], v["coord_source"]])

    print(f"\nwrote: {ELEVATORS}\n       {STATIONS}\n       {REPORT}")


if __name__ == "__main__":
    main()
