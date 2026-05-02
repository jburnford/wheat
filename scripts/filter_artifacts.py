#!/usr/bin/env python3
"""Mark parser artifacts (cross-refs, OCR garbage) so they're excluded from
the 'real unmatched stations' bucket. Updates coord_source to 'parser_artifact'
and produces a clean web-lookup queue.

Reads/writes:
  /home/jic823/grain/tables/elevators_geocoded.csv
  /home/jic823/grain/tables/stations_geocoded.csv
Writes:
  /home/jic823/grain/tables/web_lookup_queue.csv  (real unmatched stations)
"""
import csv
import re
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
STATIONS = GRAIN / "tables/stations_geocoded.csv"
QUEUE = GRAIN / "tables/web_lookup_queue.csv"

ARTIFACT_PATTERNS = [
    r"^\(.*\)$",                    # (also C.N.R.), (See page 172)
    r"^\d+$",                       # pure number like "0"
    r"^[\W_]+$",                    # punctuation only
    r"^.{1,2}$",                    # 1-2 char garbage like "C.P", "X"
    r"^Stations?$",                 # captured header
    r"^See\b",                      # "See above"
    r"\bC\.[NP]\b",                 # contains C.N or C.P (railway codes)
    r"^Total\b",                    # totals row
    r"\bdo\.?$",                    # ditto markers as station
    r"^Recapitulation",
]
ARTIFACT_RE = re.compile("|".join(ARTIFACT_PATTERNS), re.I)


def is_artifact(station: str) -> bool:
    s = station.strip()
    if not s:
        return True
    return bool(ARTIFACT_RE.search(s))


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    fieldnames = list(rows[0].keys())

    n_marked = 0
    for r in rows:
        if r["coord_source"]:
            continue
        if is_artifact(r["station"]):
            r["coord_source"] = "parser_artifact"
            n_marked += 1

    with ELEVATORS.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"marked as parser_artifact: {n_marked} rows")

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

    # Build web-lookup queue: real unmatched stations sorted by row count
    queue = [
        {"station": st, "province": prov, "rows": v["rows"]}
        for (st, prov), v in pairs.items()
        if not v["coord_source"] and not is_artifact(st)
    ]
    queue.sort(key=lambda x: -x["rows"])
    with QUEUE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["station", "province", "rows"])
        w.writeheader()
        w.writerows(queue)
    print(f"web-lookup queue: {len(queue)} stations / {sum(q['rows'] for q in queue)} rows")
    print(f"  wrote: {QUEUE}")

    # Final coverage stats
    n = len(rows)
    n_geo = sum(1 for r in rows if r["cgn_lat"] or (r["hr_lat"] and r["hr_lat"] != "0.0"))
    n_art = sum(1 for r in rows if r["coord_source"] == "parser_artifact")
    n_real_unm = n - n_geo - n_art
    print(f"\ncoverage:")
    print(f"  geocoded:        {n_geo}/{n} ({n_geo*100//n}%)")
    print(f"  parser_artifact: {n_art}/{n} ({n_art*100//n}%)")
    print(f"  real unmatched:  {n_real_unm}/{n} ({n_real_unm*100//n}%)")


if __name__ == "__main__":
    main()
