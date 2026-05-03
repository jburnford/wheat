#!/usr/bin/env python3
"""Apply coordinates from external sources (Wikipedia ghost towns, etc.) to
ungrounded stations in elevators_geocoded.csv.

Edit MANUAL_FIXES + EXTERNAL_FILES below to add more sources.
"""
import csv
import re
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"

# (station, province) -> (lat, lon, name, source)
MANUAL_FIXES = {
    # Lynch-map interpolations: midpoint between two anchored neighbors on
    # the same rail line.
    ("Lovat", "SASKATCHEWAN"): (
        50.176, -103.043, "Lovat (interpolated Glenavon-Peebles)",
        "lynch_map_interp",
    ),
    ("Adair", "SASKATCHEWAN"): (
        50.331, -103.169, "Adair (interpolated Wolseley-Baring)",
        "lynch_map_interp",
    ),
    ("Varcoe", "MANITOBA"): (
        50.057, -99.672, "Varcoe (interpolated Moorepark-Brookdale)",
        "lynch_map_interp",
    ),
    # Real prairie hamlets not in CGNDB (Wikipedia coords)
    ("Leslie", "SASKATCHEWAN"): (
        51.691, -103.712, "Leslie (Wikipedia)",
        "wikipedia",
    ),
    # OCR variants of Mecheche AB (Munson-Watts midpoint)
    ("Mechesche", "ALBERTA"): (
        51.6126, -112.4142, "Mecheche (OCR variant)",
        "lynch_map_interp",
    ),
    ("Mecheché", "ALBERTA"): (
        51.6126, -112.4142, "Mecheche (OCR variant)",
        "lynch_map_interp",
    ),
}

# External CSV sources: each entry is (path, name_col, lat_col, lon_col, source_label, province)
EXTERNAL_FILES = [
    (GRAIN / "tables/ghost_towns_sk.csv", "name", "lat", "lon",
     "wikipedia_ghost_sk", "SASKATCHEWAN"),
]


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def main():
    # Build (province, norm_name) -> (lat, lon, src_name, source)
    fixes = {}
    for k, v in MANUAL_FIXES.items():
        fixes[(k[1], norm(k[0]))] = v
    for path, ncol, latcol, loncol, source, prov in EXTERNAL_FILES:
        if not path.exists():
            continue
        for r in csv.DictReader(path.open()):
            if not r.get(latcol) or not r.get(loncol):
                continue
            try:
                lat = float(r[latcol]); lon = float(r[loncol])
            except ValueError:
                continue
            key = (prov, norm(r[ncol]))
            if key not in fixes:  # don't override earlier sources
                fixes[key] = (lat, lon, r[ncol], source)

    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())
    n_filled = 0
    for r in rows:
        if r["coord_source"]:
            continue
        key = (r["province"], norm(r["station"]))
        if key in fixes:
            lat, lon, name, src = fixes[key]
            r["cgn_lat"] = str(round(lat, 6))
            r["cgn_lon"] = str(round(lon, 6))
            r["cgn_name"] = name
            r["coord_source"] = src
            n_filled += 1
    print(f"applied {n_filled} new geocodings")

    with ELEVATORS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

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

    n = len(rows)
    n_geo = sum(1 for r in rows if r["coord_source"]
                and r["coord_source"] != "parser_artifact")
    print(f"\ncoverage: {n_geo}/{n} ({n_geo*100//n}%)")


if __name__ == "__main__":
    main()
