#!/usr/bin/env python3
"""Merge agent-resolved stations + manual historical-name fixes into the
geocoded elevators output.

Reads:
  /home/jic823/grain/tables/elevators_geocoded.csv
  /home/jic823/grain/tables/resolved_stations.csv

Writes:
  /home/jic823/grain/tables/elevators_geocoded.csv (overwrites with new coords)
  /home/jic823/grain/tables/stations_geocoded.csv (overwrites)
"""
import csv
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
RESOLVED = GRAIN / "tables/resolved_stations.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"

# Manual fixes for places the agent correctly identified but couldn't
# resolve from CGNDB (historical names, renamed, or merged places).
MANUAL = {
    # (station, province) -> (lat, lon, name, source)
    ("Port Arthur", "ONTARIO"):
        (48.4259, -89.2126, "Port Arthur (now Thunder Bay)", "manual_historical"),
    ("Fort William", "ONTARIO"):
        (48.3809, -89.2477, "Fort William (now Thunder Bay)", "manual_historical"),
    ("Hobbema", "ALBERTA"):
        (52.9536, -113.5742, "Hobbema (now Maskwacis)", "manual_historical"),
}


def main():
    # Load agent resolutions, accept high+medium confidence
    resolved = {}
    accept = {"high", "medium"}
    n_high = n_med = 0
    for r in csv.DictReader(RESOLVED.open()):
        if r["confidence"] in accept and r["cgn_lat"]:
            resolved[(r["station"], r["province"])] = {
                "lat": r["cgn_lat"], "lon": r["cgn_lon"],
                "name": r["cgn_name"], "id": r["cgn_id"],
                "source": f"agent_{r['confidence']}",
            }
            if r["confidence"] == "high":
                n_high += 1
            else:
                n_med += 1
    print(f"agent resolved: {n_high} high + {n_med} medium = {len(resolved)}")
    print(f"manual fixes: {len(MANUAL)}")

    # Augment with manual
    for k, (lat, lon, name, src) in MANUAL.items():
        resolved[k] = {"lat": str(lat), "lon": str(lon),
                       "name": name, "id": "", "source": src}

    # Load and rewrite elevators_geocoded
    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())
    if "coord_source" not in fieldnames:
        fieldnames.append("coord_source")

    n_filled = 0
    for r in rows:
        # Already has CGN coords from prior pass?
        if r["cgn_lat"]:
            r["coord_source"] = "cgn_direct"
            continue
        # Has HR coords (real, not 0.0)?
        if r["hr_lat"] and r["hr_lat"] != "0.0":
            r["coord_source"] = "hr_places"
            continue
        # Look up resolution
        m = resolved.get((r["station"], r["province"]))
        if m:
            r["cgn_lat"] = m["lat"]
            r["cgn_lon"] = m["lon"]
            r["cgn_name"] = m["name"]
            r["cgn_id"] = m["id"]
            r["coord_source"] = m["source"]
            n_filled += 1
        else:
            r["coord_source"] = ""

    with ELEVATORS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"newly geocoded rows: {n_filled}")

    # Stats + rewrite stations file
    n = len(rows)
    n_any = sum(1 for r in rows if r["cgn_lat"] or (r["hr_lat"] and r["hr_lat"] != "0.0"))

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

    n_st = len(pairs)
    n_st_geo = sum(1 for v in pairs.values()
                   if v["cgn_lat"] or (v["hr_lat"] and v["hr_lat"] != "0.0"))

    def pct(a, b): return f"{a}/{b} ({a*100//b}%)"
    print(f"\nFINAL coverage:")
    print(f"  rows:     {pct(n_any, n)}")
    print(f"  stations: {pct(n_st_geo, n_st)}")
    print(f"\nbreakdown by coord_source (rows):")
    from collections import Counter
    c = Counter(r["coord_source"] for r in rows)
    for k, v in c.most_common():
        print(f"  {k or '(none)':22} {v}")


if __name__ == "__main__":
    main()
