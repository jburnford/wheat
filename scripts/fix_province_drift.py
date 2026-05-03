#!/usr/bin/env python3
"""Fix parser province-drift bugs.

When the OCR'd directories transition between railway-company sections,
the parser sometimes misses a `PROVINCE OF X` heading and carries the
previous province forward. We can detect this for geocoded rows by
checking the cgn_lat/lon against province bounding boxes, and for
ungrounded rows by trusting the corrected province of nearby geocoded
rows in the same volume + railway.

Reads/writes:
  /home/jic823/grain/tables/elevators_geocoded.csv
  /home/jic823/grain/tables/stations_geocoded.csv
"""
import csv
from collections import defaultdict
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"

# Loose bounding boxes for Canadian provinces (intentionally permissive
# at edges so we don't flip rows on the AB/SK or SK/MB borders).
PROV_BBOX = {
    "MANITOBA":          (48.9, -102.0, 60.0, -88.0),
    "SASKATCHEWAN":      (48.9, -110.0, 60.0, -101.3),
    "ALBERTA":           (48.9, -120.0, 60.0, -109.9),
    "BRITISH COLUMBIA":  (48.0, -139.5, 60.0, -114.0),
    "ONTARIO":           (41.6, -95.5, 56.9, -74.3),
    "QUEBEC":            (44.9, -79.9, 62.6, -57.0),
}


def find_prov(lat, lon):
    for prov, (la_min, lo_min, la_max, lo_max) in PROV_BBOX.items():
        if la_min <= lat <= la_max and lo_min <= lon <= lo_max:
            return prov
    return None


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())

    # Step 1: fix geocoded rows with clear coordinate-province mismatch
    n_geo_fixed = 0
    for r in rows:
        if r["coord_source"] == "parser_artifact":
            continue
        if not r["cgn_lat"] or r["cgn_lat"] == "0.0":
            continue
        try:
            lat = float(r["cgn_lat"]); lon = float(r["cgn_lon"])
        except ValueError:
            continue
        actual = find_prov(lat, lon)
        if actual and r["province"] != actual:
            r["province"] = actual
            n_geo_fixed += 1

    # Step 2: for ungrounded rows, use neighbor consensus.
    # Index rows by (volume, railway). Within each group, the parser walks
    # in directory order; if a contiguous run of rows is mislabeled, we
    # spread the corrected province to ungrounded rows in the same run.
    by_vol_rail = defaultdict(list)
    for i, r in enumerate(rows):
        if r["coord_source"] == "parser_artifact":
            continue
        by_vol_rail[(r["volume"], r["railway"])].append(i)

    n_ungr_fixed = 0
    for key, idxs in by_vol_rail.items():
        # walk through rows in this group in order
        for pos, ri in enumerate(idxs):
            r = rows[ri]
            if r["cgn_lat"] and r["cgn_lat"] != "0.0":
                continue  # already handled
            # look at nearest geocoded neighbor (before and after) within
            # this same volume+railway. If both neighbors agree on a
            # province different from this row's, override.
            prev_p = None
            for pp in range(pos - 1, max(-1, pos - 6), -1):
                rr = rows[idxs[pp]]
                if rr["cgn_lat"] and rr["cgn_lat"] != "0.0":
                    prev_p = rr["province"]
                    break
            next_p = None
            for pp in range(pos + 1, min(len(idxs), pos + 6)):
                rr = rows[idxs[pp]]
                if rr["cgn_lat"] and rr["cgn_lat"] != "0.0":
                    next_p = rr["province"]
                    break
            if prev_p and prev_p == next_p and prev_p != r["province"]:
                r["province"] = prev_p
                n_ungr_fixed += 1

    print(f"fixed by coord-bbox check (geocoded rows):   {n_geo_fixed:,}")
    print(f"fixed by neighbor consensus (ungrounded):    {n_ungr_fixed:,}")

    with ELEVATORS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {ELEVATORS}")

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
    print(f"wrote {STATIONS}")


if __name__ == "__main__":
    main()
