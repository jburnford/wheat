#!/usr/bin/env python3
"""Match unmatched (and all) stations against CGNDB Populated Places.

Adds cgn_lat / cgn_lon / cgn_id / cgn_concise to elevators_final.csv.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
CGN_DIR = GRAIN / "cgndb"
ELEVATORS_FINAL = GRAIN / "tables/elevators_final.csv"
OUT = GRAIN / "tables/elevators_geocoded.csv"
STATIONS_OUT = GRAIN / "tables/stations_geocoded.csv"

PROV_TO_LABEL = {
    "MANITOBA": "Manitoba", "SASKATCHEWAN": "Saskatchewan",
    "ALBERTA": "Alberta", "BRITISH COLUMBIA": "British Columbia",
    "ONTARIO": "Ontario", "QUEBEC": "Quebec",
    "NEW BRUNSWICK": "New Brunswick", "NOVA SCOTIA": "Nova Scotia",
    "PRINCE EDWARD ISLAND": "Prince Edward Island",
}
PROV_TO_FILE = {
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


def load_cgn():
    """Return dict[(province_label, norm_name)] -> list[record]."""
    out = defaultdict(list)
    for prov, fname in PROV_TO_FILE.items():
        path = CGN_DIR / fname
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                # Populated places + Indian Reserves + First Nation admin
                # (catches Fort William and similar that aren't classified as
                # Populated Place but were grain-elevator locations)
                gc = r.get("Generic Category", "")
                concise = r.get("Concise Code", "")
                if gc != "Populated Place" and concise not in ("IR", "MUN1", "MUN2"):
                    continue
                name = r.get("Geographical Name", "")
                key = norm_name(name)
                if not key:
                    continue
                rec = {
                    "cgn_id": r.get("CGNDB ID", ""),
                    "cgn_name": name,
                    "cgn_concise": r.get("Concise Code", ""),
                    "cgn_generic": r.get("Generic Term", ""),
                    "cgn_lat": r.get("Latitude", ""),
                    "cgn_lon": r.get("Longitude", ""),
                    "cgn_relevance": r.get("Relevance at Scale", ""),
                }
                out[(prov, key)].append(rec)
    return out


def pick_best(hits):
    """If multiple CGN hits share a normalized name, prefer:
    1. CITY > TOWN > VILG > HAM > UNP > LOC (ranking)
    2. Higher relevance scale (smaller number = higher relevance)
    """
    rank = {"CITY": 0, "TOWN": 1, "VILG": 2, "HAM": 3, "UNP": 4, "LOC": 5}
    def key(h):
        r = rank.get(h["cgn_concise"], 9)
        try:
            rel = int(h["cgn_relevance"])
        except (TypeError, ValueError):
            rel = 99999999
        return (r, -rel)  # higher relevance scale (e.g. 2,000,000) wins first
    return sorted(hits, key=key)[0]


def main():
    cgn = load_cgn()
    print(f"loaded {len(cgn)} CGN populated-place keys")

    rows = list(csv.DictReader(ELEVATORS_FINAL.open()))
    extra_cols = ["cgn_id", "cgn_name", "cgn_concise", "cgn_lat", "cgn_lon"]
    fieldnames = [c for c in rows[0].keys()] + extra_cols

    # Variant generators for fallback matching: try common spelling/prefix
    # variants when the direct name doesn't hit.
    def variants(name: str):
        n = norm_name(name)
        out = [n]
        # 'Macleod' -> 'fort macleod' / 'fort macleod' -> 'macleod'
        if not n.startswith("fort "):
            out.append("fort " + n)
        else:
            out.append(n[5:])
        # 'Gainsboro' -> 'gainsborough'
        if n.endswith("boro"):
            out.append(n + "ugh")
        if n.endswith("burg"):
            out.append(n[:-4] + "bourg")
            out.append(n[:-4] + "burgh")
        # 'Strassburg' -> 'strasbourg' (specific common variant)
        if "strass" in n:
            out.append(n.replace("strass", "stras"))
        # 'Cutknife' -> 'cut knife', 'Southfork' -> 'south fork'
        for split in ("cut", "south", "north", "east", "west"):
            if n.startswith(split) and len(n) > len(split) + 1 and n[len(split)] != " ":
                out.append(split + " " + n[len(split):])
        # 'St.' / 'Ste.' handled in norm_name already
        return out

    # Build a no-spaces secondary index so "Cutknife" hits "Cut Knife" etc.
    nospace_idx = {}
    for (prov, key), hits in cgn.items():
        nokey = key.replace(" ", "")
        nospace_idx.setdefault((prov, nokey), []).extend(hits)

    # Per-station enrichment cache
    station_match = {}
    for r in rows:
        key = (r["province"], norm_name(r["station"]))
        if key not in station_match:
            hits = cgn.get(key, [])
            if not hits:
                # try the no-spaces secondary index (Cutknife -> Cut Knife, Rockglen -> Rock Glen)
                hits = nospace_idx.get(
                    (r["province"], norm_name(r["station"]).replace(" ", "")), []
                )
            if not hits:
                # try variants
                for v in variants(r["station"]):
                    hits = cgn.get((r["province"], v), [])
                    if hits:
                        break
                    hits = nospace_idx.get((r["province"], v.replace(" ", "")), [])
                    if hits:
                        break
            station_match[key] = pick_best(hits) if hits else None
        m = station_match[key]
        if m:
            for c in extra_cols:
                r[c] = m[c]
        else:
            for c in extra_cols:
                r[c] = ""

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Stations file
    pairs = {}
    for r in rows:
        k = (r["station"], r["province"])
        pairs.setdefault(k, {"rows": 0, **{c: r[c] for c in extra_cols}, "hr_lat": r["hr_lat"], "hr_lon": r["hr_lon"], "wikidata_qid": r["wikidata_qid"], "csd_id": r["csd_id"]})
        pairs[k]["rows"] += 1
    with STATIONS_OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "rows", "cgn_id", "cgn_name",
                    "cgn_concise", "cgn_lat", "cgn_lon", "hr_lat", "hr_lon",
                    "csd_id", "wikidata_qid"])
        for (st, prov), v in sorted(pairs.items(), key=lambda x: -x[1]["rows"]):
            w.writerow([st, prov, v["rows"], v["cgn_id"], v["cgn_name"],
                        v["cgn_concise"], v["cgn_lat"], v["cgn_lon"],
                        v["hr_lat"], v["hr_lon"], v["csd_id"], v["wikidata_qid"]])

    # Stats
    n = len(rows)
    n_cgn = sum(1 for r in rows if r["cgn_lat"])
    n_hr = sum(1 for r in rows if r["hr_lat"] and r["hr_lat"] != "0.0")
    n_any = sum(1 for r in rows if r["cgn_lat"] or (r["hr_lat"] and r["hr_lat"] != "0.0"))

    n_st = len(pairs)
    n_st_cgn = sum(1 for v in pairs.values() if v["cgn_lat"])
    n_st_hr = sum(1 for v in pairs.values() if v["hr_lat"] and v["hr_lat"] != "0.0")
    n_st_any = sum(1 for v in pairs.values()
                   if v["cgn_lat"] or (v["hr_lat"] and v["hr_lat"] != "0.0"))

    def pct(a, b): return f"{a}/{b} ({a*100//b}%)"
    print(f"\nrows:")
    print(f"  CGN coords:   {pct(n_cgn, n)}")
    print(f"  HR coords:    {pct(n_hr, n)}")
    print(f"  any coords:   {pct(n_any, n)}")
    print(f"\nunique (station, province):")
    print(f"  CGN coords:   {pct(n_st_cgn, n_st)}")
    print(f"  HR coords:    {pct(n_st_hr, n_st)}")
    print(f"  any coords:   {pct(n_st_any, n_st)}")
    print(f"\nwrote: {OUT}")
    print(f"       {STATIONS_OUT}")


if __name__ == "__main__":
    main()
