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
    # Real prairie hamlets not in CGNDB (Wikidata coords)
    ("Leslie", "SASKATCHEWAN"): (
        51.691, -103.712, "Leslie [Q6530572]",
        "wikidata",
    ),
    # OCR captured "West St. John, N.B" as a station; this is actually
    # Saint John West, New Brunswick (a port elevator location). The
    # parser had it under QUEBEC because the directory was in the QC
    # section when it ran into this NB reference.
    ("West St. John, N.B", "QUEBEC"): (
        45.259374, -66.077759, "Saint John West [Q112548740]",
        "wikidata",
    ),
    # Smith Spur MB (railway siding; coords from Manitoba Historical Society)
    # https://www.mhs.mb.ca/docs/sites/smithspurelevator.shtml
    ("Smith Spur", "MANITOBA"): (
        49.35424, -97.50230, "Smith's Spur (MHS)",
        "manitoba_historical_society",
    ),
    # Enterprise MB (railway siding; coords from Manitoba Historical Society)
    # https://www.mhs.mb.ca/docs/sites/enterpriseelevator.shtml
    ("Enterprise", "MANITOBA"): (
        49.08651, -99.55038, "Enterprise (MHS)",
        "manitoba_historical_society",
    ),
    # Hope Farm MB (railway siding; coords from Manitoba Historical Society)
    # https://www.mhs.mb.ca/docs/sites/hopefarmelevator.shtml
    ("Hope Farm", "MANITOBA"): (
        49.22100, -97.38578, "Hope Farm (MHS)",
        "manitoba_historical_society",
    ),
    # Jefferson AB [Q6175334]
    ("Jefferson", "ALBERTA"): (
        49.085278, -113.091111, "Jefferson [Q6175334]",
        "wikidata",
    ),
    # Prussia SK was renamed to Leader during WWI [Q1915145]
    ("Prussia", "SASKATCHEWAN"): (
        50.8876, -109.5466, "Prussia → Leader [Q1915145]",
        "manual_historical",
    ),
    # Rainton SK — coords from gent.name/sask:towns:rainton
    ("Rainton", "SASKATCHEWAN"): (
        49.816667, -103.750556, "Rainton (gent.name)",
        "gent_name_sask",
    ),
    # Alcester MB — DLS midpoint of school sites SE 18-5-19-W1 + NE 15-5-19-W1
    # Source: https://vantagepoints.ca/stories/alcester/
    ("Alcester", "MANITOBA"): (
        49.3830, -99.8062, "Alcester (DLS school sites)",
        "vantagepoints_dls",
    ),
    # Bannerman MB — coords from MHS Virtual Manitoba
    # https://www.mhs.mb.ca/docs/virtualmanitoba/Places/B/bannerman.html
    ("Bannerman", "MANITOBA"): (
        49.039567, -99.803920, "Bannerman (MHS Virtual MB)",
        "manitoba_historical_society",
    ),
    # Desford MB — coords from MHS
    # https://www.mhs.mb.ca/docs/sites/desford.shtml
    ("Desford", "MANITOBA"): (
        49.12555, -99.92930, "Desford (MHS)",
        "manitoba_historical_society",
    ),
    # Fairburn MB
    ("Fairburn", "MANITOBA"): (
        49.17727, -99.99619, "Fairburn (MHS)",
        "manitoba_historical_society",
    ),
    # Astum SK — DLS Section 9-33-21-W3
    ("Astum", "SASKATCHEWAN"): (
        51.7968, -108.7474, "Astum (DLS 9-33-21-W3)",
        "dls_converted",
    ),
    # Glenwoodville AB → Glenwood [Q5569424]
    ("Glenwoodville", "ALBERTA"): (
        49.3636, -113.511, "Glenwoodville → Glenwood [Q5569424]",
        "wikidata",
    ),
    # Leach Siding SK — on CN Elrose Sub between Wiseton and Dinsmore
    # (per Sask Pool map). Wiseton 51.3129,-107.6491; Dinsmore 51.3309,-107.4453
    ("Leach Siding", "SASKATCHEWAN"): (
        51.3219, -107.5472, "Leach Siding (mid Wiseton-Dinsmore)",
        "lynch_map_interp",
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
