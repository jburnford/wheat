#!/usr/bin/env python3
"""Reconcile elevator station names against hr_places_all + csd_verified_matches.

Inputs:
  /home/jic823/grain/tables/elevators.csv
  /home/jic823/grain/dataverse/hr_places_all-1/hr_places_all.shp
  /home/jic823/Canada-History-Knowledge-Graph/wikidata_grounding/csd_verified_matches.jsonl

Outputs:
  /home/jic823/grain/tables/stations.csv         — unique stations + matches
  /home/jic823/grain/tables/elevators_enriched.csv — elevators joined to stations
  /home/jic823/grain/tables/unmatched_stations.csv — stations with no match
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import shapefile

GRAIN = Path("/home/jic823/grain")
ELEVATORS_CSV = GRAIN / "tables/elevators.csv"
HR_PLACES_SHP = GRAIN / "dataverse/hr_places_all-1/hr_places_all.shp"
CSD_JSONL = Path(
    "/home/jic823/Canada-History-Knowledge-Graph/wikidata_grounding/"
    "csd_verified_matches.jsonl"
)

PROV_ABBREV = {
    "MANITOBA": "MB", "SASKATCHEWAN": "SK", "ALBERTA": "AB",
    "BRITISH COLUMBIA": "BC", "ONTARIO": "ON", "QUEBEC": "QC",
    "NEW BRUNSWICK": "NB", "NOVA SCOTIA": "NS",
    "PRINCE EDWARD ISLAND": "PE",
}
# REG_CODE in hr_places_all: 1=NL, 2=Maritimes, 3=QC, 4=ON, 5=Prairies, 6=BC, etc.
# We'll use province-aware matching so REG_CODE isn't strictly needed.


def norm_name(s: str) -> str:
    """Lowercase, strip punctuation/diacritics-light, collapse spaces."""
    s = s.lower()
    s = re.sub(r"[éèê]", "e", s)
    s = re.sub(r"[àâ]", "a", s)
    s = re.sub(r"[ôö]", "o", s)
    s = re.sub(r"[îï]", "i", s)
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parenthesized qualifiers
    s = re.sub(r",.*", "", s)  # drop ", VL" / ", T-V" suffixes
    s = re.sub(r"^\d+\.\s*", "", s)  # drop "128. " number prefix from csd_name
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_hr_places():
    """Return dict[norm_name] -> list[record]."""
    sf = shapefile.Reader(str(HR_PLACES_SHP), encoding="latin-1")
    fields = [f[0] for f in sf.fields[1:]]
    out = defaultdict(list)
    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        name = rec.get("NAME_NOM") or ""
        key = norm_name(name)
        if key:
            out[key].append(rec)
    return out


def load_csd_matches():
    """Return dict[norm_name] -> list[record]."""
    out = defaultdict(list)
    with CSD_JSONL.open() as f:
        for line in f:
            d = json.loads(line)
            for nm in (d.get("csd_name"), d.get("wikidata_label")):
                if nm:
                    out[norm_name(nm)].append(d)
    return out


def main():
    hr_idx = load_hr_places()
    csd_idx = load_csd_matches()
    print(f"loaded hr_places: {sum(len(v) for v in hr_idx.values())} recs / "
          f"{len(hr_idx)} keys")
    print(f"loaded csd_matches: {sum(len(v) for v in csd_idx.values())} recs / "
          f"{len(csd_idx)} keys")

    # Collect unique (station, province) pairs from elevators
    pairs = Counter()
    rows = []
    with ELEVATORS_CSV.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
            pairs[(r["station"], r["province"])] += 1

    stations_out = []
    unmatched = []
    for (station, province), count in sorted(pairs.items()):
        key = norm_name(station)
        prov_abbr = PROV_ABBREV.get(province, "")

        hr_hits = hr_idx.get(key, [])
        # Filter HR hits — hr_places has no province field directly, but
        # REG_CODE 5 = Prairies (MB/SK/AB), 6 = BC.
        # Without finer filtering, just take the first hit; if multiple,
        # mark ambiguous.
        hr_hit = None
        if hr_hits:
            hr_hit = hr_hits[0]

        csd_hits = csd_idx.get(key, [])
        csd_hit = None
        if csd_hits:
            if prov_abbr:
                p_hits = [h for h in csd_hits
                          if h.get("csd_id", "").startswith(prov_abbr)]
                if p_hits:
                    csd_hit = p_hits[0]
            if not csd_hit:
                csd_hit = csd_hits[0]

        rec = {
            "station": station,
            "province": province,
            "rows": count,
            "hr_name": hr_hit["NAME_NOM"] if hr_hit else "",
            "hr_lat": hr_hit["LATITUDE"] if hr_hit else "",
            "hr_lon": hr_hit["LONGITUDE"] if hr_hit else "",
            "hr_concs": hr_hit["CONCS_CODE"] if hr_hit else "",
            "hr_ambiguous": "Y" if len(hr_hits) > 1 else "",
            "csd_id": csd_hit["csd_id"] if csd_hit else "",
            "csd_name": csd_hit["csd_name"] if csd_hit else "",
            "wikidata_qid": csd_hit["wikidata_qid"] if csd_hit else "",
            "csd_ambiguous": "Y" if len(csd_hits) > 1 else "",
        }
        stations_out.append(rec)
        if not hr_hit and not csd_hit:
            unmatched.append({"station": station, "province": province,
                              "rows": count})

    out_st = GRAIN / "tables/stations.csv"
    with out_st.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stations_out[0].keys()))
        w.writeheader()
        w.writerows(stations_out)

    out_un = GRAIN / "tables/unmatched_stations.csv"
    with out_un.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["station", "province", "rows"])
        w.writeheader()
        w.writerows(sorted(unmatched, key=lambda r: -r["rows"]))

    # Elevators joined
    by_pair = {(s["station"], s["province"]): s for s in stations_out}
    out_e = GRAIN / "tables/elevators_enriched.csv"
    with out_e.open("w", newline="") as f:
        fieldnames = list(rows[0].keys()) + [
            "hr_name", "hr_lat", "hr_lon", "csd_id", "wikidata_qid",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            s = by_pair[(r["station"], r["province"])]
            r2 = dict(r)
            r2["hr_name"] = s["hr_name"]
            r2["hr_lat"] = s["hr_lat"]
            r2["hr_lon"] = s["hr_lon"]
            r2["csd_id"] = s["csd_id"]
            r2["wikidata_qid"] = s["wikidata_qid"]
            w.writerow(r2)

    # Stats
    n_st = len(stations_out)
    n_hr = sum(1 for s in stations_out if s["hr_name"])
    n_csd = sum(1 for s in stations_out if s["csd_id"])
    n_either = sum(1 for s in stations_out if s["hr_name"] or s["csd_id"])
    n_both = sum(1 for s in stations_out if s["hr_name"] and s["csd_id"])
    n_un = len(unmatched)
    rows_un = sum(u["rows"] for u in unmatched)
    print(f"\nunique (station, province): {n_st}")
    print(f"  hr_places match:   {n_hr} ({n_hr/n_st:.0%})")
    print(f"  csd_qid match:     {n_csd} ({n_csd/n_st:.0%})")
    print(f"  either:            {n_either} ({n_either/n_st:.0%})")
    print(f"  both:              {n_both} ({n_both/n_st:.0%})")
    print(f"  unmatched:         {n_un} stations / {rows_un} elevator rows")
    print(f"\nwrote: {out_st}\n       {out_e}\n       {out_un}")


if __name__ == "__main__":
    main()
