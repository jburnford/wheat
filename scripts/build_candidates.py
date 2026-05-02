#!/usr/bin/env python3
"""For each unmatched station, generate top-5 fuzzy CGN candidates.

Outputs /home/jic823/grain/tables/unmatched_candidates.csv with columns:
  station, province, rows, candidates_json
where candidates_json is a JSON array of {cgn_id, cgn_name, concise, lat, lon, score}.
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

GRAIN = Path("/home/jic823/grain")
CGN_DIR = GRAIN / "cgndb"
STATIONS = GRAIN / "tables/stations_geocoded.csv"
OUT = GRAIN / "tables/unmatched_candidates.csv"

PROV_FILE = {
    "MANITOBA": "cgn_mb_csv_eng.csv",
    "SASKATCHEWAN": "cgn_sk_csv_eng.csv",
    "ALBERTA": "cgn_ab_csv_eng.csv",
    "BRITISH COLUMBIA": "cgn_bc_csv_eng.csv",
    "ONTARIO": "cgn_on_csv_eng.csv",
    "QUEBEC": "cgn_qc_csv_eng.csv",
}


def norm_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r",.*", "", s)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_cgn_by_province():
    """Return dict[province] -> list[record].

    Includes all populated places, Indian Reserves, and (newly) Localities/
    Locations and other admin features that might be a station namesake.
    """
    out = defaultdict(list)
    for prov, fname in PROV_FILE.items():
        with (CGN_DIR / fname).open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                gc = r.get("Generic Category", "")
                concise = r.get("Concise Code", "")
                # Permissive: include any feature that could plausibly host
                # a station/elevator. Exclude pure water/terrain features.
                if gc in ("Water Feature", "Terrain Feature",
                          "Vegetation Feature", "Marine Feature",
                          "Underwater Feature"):
                    continue
                name = r.get("Geographical Name", "")
                if not name:
                    continue
                out[prov].append({
                    "cgn_id": r.get("CGNDB ID", ""),
                    "cgn_name": name,
                    "concise": concise,
                    "generic": r.get("Generic Term", ""),
                    "lat": r.get("Latitude", ""),
                    "lon": r.get("Longitude", ""),
                    "norm": norm_name(name),
                })
    return out


def main():
    cgn = load_cgn_by_province()
    print(f"loaded CGN: {sum(len(v) for v in cgn.values())} records "
          f"across {len(cgn)} provinces")

    stations = list(csv.DictReader(STATIONS.open()))
    unmatched = [
        s for s in stations
        if not s["cgn_lat"] and not (s["hr_lat"] and s["hr_lat"] != "0.0")
        and s["station"]  # skip empty
    ]
    print(f"unmatched stations: {len(unmatched)}")

    out_rows = []
    for s in sorted(unmatched, key=lambda x: -int(x["rows"])):
        prov = s["province"]
        prov_cgn = cgn.get(prov, [])
        if not prov_cgn:
            out_rows.append({
                "station": s["station"], "province": prov,
                "rows": s["rows"], "candidates_json": "[]",
            })
            continue
        choices = [c["norm"] for c in prov_cgn]
        target = norm_name(s["station"])
        # Use rapidfuzz to pick top 5 by token-set ratio
        hits = process.extract(target, choices, scorer=fuzz.WRatio, limit=5)
        cands = []
        for matched_norm, score, idx in hits:
            if score < 60:  # too noisy below this
                continue
            c = prov_cgn[idx]
            cands.append({
                "cgn_id": c["cgn_id"],
                "cgn_name": c["cgn_name"],
                "concise": c["concise"],
                "generic": c["generic"],
                "lat": c["lat"],
                "lon": c["lon"],
                "score": int(score),
            })
        out_rows.append({
            "station": s["station"], "province": prov,
            "rows": s["rows"], "candidates_json": json.dumps(cands),
        })

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "station", "province", "rows", "candidates_json",
        ])
        w.writeheader()
        w.writerows(out_rows)

    n_with = sum(1 for r in out_rows if r["candidates_json"] != "[]")
    print(f"wrote: {OUT}")
    print(f"  rows with at least 1 candidate: {n_with}/{len(out_rows)}")


if __name__ == "__main__":
    main()
