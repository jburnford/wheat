#!/usr/bin/env python3
"""Auto-interpolate ungrounded stations from rail_lines.jsonl.

For each line: find ungrounded stations sandwiched between two geocoded
neighbors and place them at the midpoint. Updates elevators_geocoded.csv.

Repeated runs are idempotent — once a station is geocoded with
'lynch_map_interp' source, it stays.
"""
import csv
import json
import math
import re
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"
LINES = GRAIN / "tables/rail_lines.jsonl"


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())

    # Build geo + ungrounded indexes per (province, norm name) and a
    # province-agnostic lookup.
    geo = {}    # (prov, key) -> (lat, lon)
    geo_ns = {}  # (prov, no-space) -> (lat, lon)
    ungr = {}   # (prov, key) -> station_string
    ungr_ns = {}
    real_station = {}  # (prov, norm) -> original station name (for back-update)
    for r in rows:
        prov = r["province"]
        if prov not in ("SASKATCHEWAN", "MANITOBA", "ALBERTA"):
            continue
        nk = norm(r["station"])
        if not nk:
            continue
        real_station[(prov, nk)] = r["station"]
        if r["cgn_lat"] and r["cgn_lat"] != "0.0":
            try:
                lat = float(r["cgn_lat"]); lon = float(r["cgn_lon"])
                geo.setdefault((prov, nk), (lat, lon))
                geo_ns.setdefault((prov, nk.replace(" ", "")), (lat, lon))
            except ValueError:
                pass
        elif not r["coord_source"]:
            ungr.setdefault((prov, nk), r["station"])
            ungr_ns.setdefault((prov, nk.replace(" ", "")), r["station"])

    def lookup(name, prov_pref=None):
        nk = norm(name)
        nks = nk.replace(" ", "")
        # Priority order: same province first (geo or ungr), then others
        provs = (
            [prov_pref] + [p for p in ("SASKATCHEWAN", "MANITOBA", "ALBERTA")
                           if p != prov_pref]
            if prov_pref
            else ("SASKATCHEWAN", "MANITOBA", "ALBERTA")
        )
        # Within preferred province: try geo, then ungr (so ungrounded SK
        # beats geocoded-in-other-province)
        if prov_pref:
            if (prov_pref, nk) in geo:
                return ("geo", prov_pref, geo[(prov_pref, nk)],
                        real_station.get((prov_pref, nk)))
            if (prov_pref, nks) in geo_ns:
                return ("geo", prov_pref, geo_ns[(prov_pref, nks)], name)
            if (prov_pref, nk) in ungr:
                return ("ungr", prov_pref, None, ungr[(prov_pref, nk)])
            if (prov_pref, nks) in ungr_ns:
                return ("ungr", prov_pref, None, ungr_ns[(prov_pref, nks)])
        # Fall back to other provinces, geo first then ungr
        for prov in provs:
            if prov == prov_pref:
                continue
            if (prov, nk) in geo:
                return ("geo", prov, geo[(prov, nk)], real_station.get((prov, nk)))
            if (prov, nks) in geo_ns:
                return ("geo", prov, geo_ns[(prov, nks)], name)
        for prov in provs:
            if prov == prov_pref:
                continue
            if (prov, nk) in ungr:
                return ("ungr", prov, None, ungr[(prov, nk)])
            if (prov, nks) in ungr_ns:
                return ("ungr", prov, None, ungr_ns[(prov, nks)])
        return None

    # Process lines
    midpoints = {}  # (real_station_name, province) -> (lat, lon, source_desc)
    for line in LINES.open():
        d = json.loads(line)
        # First pass: determine dominant province by no-prefence lookup
        dom_count = {"SASKATCHEWAN": 0, "MANITOBA": 0, "ALBERTA": 0}
        for s in d["stations"]:
            r = lookup(s)
            if r and r[1] in dom_count:
                dom_count[r[1]] += 1
        prov_pref = max(dom_count, key=dom_count.get)
        if dom_count[prov_pref] == 0:
            prov_pref = None
        # Second pass: use dominant province as preference
        seq = [(s, lookup(s, prov_pref)) for s in d["stations"]]
        for i, (s, info) in enumerate(seq):
            if not info or info[0] != "ungr":
                continue
            ungr_real = info[3]
            ungr_prov = info[1]
            # find prev geocoded
            p = None
            for j in range(i - 1, -1, -1):
                if seq[j][1] and seq[j][1][0] == "geo":
                    p = seq[j]
                    break
            n = None
            for j in range(i + 1, len(seq)):
                if seq[j][1] and seq[j][1][0] == "geo":
                    n = seq[j]
                    break
            if not (p and n):
                continue
            plat, plon = p[1][2]
            nlat, nlon = n[1][2]
            mlat = round((plat + nlat) / 2, 6)
            mlon = round((plon + nlon) / 2, 6)
            key = (ungr_real, ungr_prov)
            # If multiple lines anchor the same station, keep first encountered
            midpoints.setdefault(key, (mlat, mlon, f"midpoint {p[0]}–{n[0]}"))

    print(f"interpolation candidates: {len(midpoints)}")

    n_filled = 0
    for r in rows:
        if r["coord_source"]:
            continue
        key = (r["station"], r["province"])
        if key in midpoints:
            mlat, mlon, src = midpoints[key]
            r["cgn_lat"] = str(mlat)
            r["cgn_lon"] = str(mlon)
            r["cgn_name"] = f"{r['station']} (interp: {src})"
            r["coord_source"] = "lynch_map_interp"
            n_filled += 1

    print(f"applied to {n_filled} elevator rows")
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
    print(f"\nstations newly geocoded by Lynch interpolation:")
    for (st, prov), (lat, lon, src) in sorted(midpoints.items()):
        print(f"  {st:25} ({prov[:3]})  ({lat:.4f},{lon:.4f})  via {src}")


if __name__ == "__main__":
    main()
