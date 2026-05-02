#!/usr/bin/env python3
"""Build GeoJSON of geocoded grain elevator stations.

Outputs:
  /home/jic823/grain/viz/stations.geojson           — all geocoded stations
  /home/jic823/grain/viz/stations_by_company.geojson — top-15 companies, color-styled
  /home/jic823/grain/viz/elevator_ops_summary.csv   — per-station summary
"""
import csv
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
VIZ = GRAIN / "viz"
VIZ.mkdir(exist_ok=True)


def hard_canon(s):
    if not s:
        return ""
    o = s.strip().lower()
    o = re.sub(r'^[\*†"\s]+', "", o)
    o = re.sub(r'[\*†"\s]+$', "", o)
    o = o.replace("&amp;", "&")
    o = re.sub(r"^the\s+", "", o)
    o = re.sub(r"\bsask\.?(?=\s|$)", "saskatchewan", o)
    o = re.sub(r"\balta\.?(?=\s|$)", "alberta", o)
    o = re.sub(r"\bman\.?(?=\s|$)", "manitoba", o)
    o = re.sub(r"\b(limited|ltd\.?)\b", "ltd", o)
    o = re.sub(r"\b(company|co\.?)\b", "co", o)
    o = re.sub(r"\b(corporation|corp\.?)\b", "corp", o)
    o = re.sub(r"\b(elev|el)\.?\b", "elevator", o)
    o = re.sub(r"'+", "", o)
    o = re.sub(r"[\.,]+", " ", o)
    return re.sub(r"\s+", " ", o).strip()


def title_case_owner(s):
    """Display-friendly capitalization."""
    return " ".join(w.capitalize() for w in s.split())


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    rows = [r for r in rows if r["coord_source"]
            and r["coord_source"] != "parser_artifact"
            and r["cgn_lat"] and r["cgn_lat"] != "0.0"]

    # Aggregate per (station, province): summarize all years/owners
    per_station = defaultdict(lambda: {
        "rows": 0, "owners": Counter(), "years": set(),
        "min_capacity": None, "max_capacity": None, "total_capacity": 0,
        "lat": None, "lon": None, "rail_canonical": Counter(),
        "coord_source": None,
    })
    for r in rows:
        key = (r["station"], r["province"])
        s = per_station[key]
        s["rows"] += 1
        owner = hard_canon(r["owner"])
        if owner:
            s["owners"][owner] += 1
        if r["season_start"]:
            try:
                s["years"].add(int(r["season_start"]))
            except ValueError:
                pass
        if r["capacity_bushels"]:
            try:
                cap = int(r["capacity_bushels"])
                s["total_capacity"] += cap
                s["min_capacity"] = (cap if s["min_capacity"] is None
                                     else min(s["min_capacity"], cap))
                s["max_capacity"] = (cap if s["max_capacity"] is None
                                     else max(s["max_capacity"], cap))
            except ValueError:
                pass
        if s["lat"] is None:
            try:
                s["lat"] = float(r["cgn_lat"])
                s["lon"] = float(r["cgn_lon"])
                s["coord_source"] = r["coord_source"]
            except ValueError:
                pass
        if r["rail_canonical"]:
            s["rail_canonical"][r["rail_canonical"]] += 1

    # Build GeoJSON
    features = []
    for (station, province), s in per_station.items():
        if s["lat"] is None:
            continue
        n_owners = len(s["owners"])
        top_owner = s["owners"].most_common(1)[0][0] if s["owners"] else ""
        top_rail = s["rail_canonical"].most_common(1)[0][0] if s["rail_canonical"] else ""
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(s["lon"], 5), round(s["lat"], 5)],
            },
            "properties": {
                "station": station,
                "province": province,
                "elevator_rows": s["rows"],
                "n_owners": n_owners,
                "n_years": len(s["years"]),
                "first_year": min(s["years"]) if s["years"] else None,
                "last_year": max(s["years"]) if s["years"] else None,
                "top_owner": title_case_owner(top_owner),
                "top_rail": top_rail,
                "max_capacity_bushels": s["max_capacity"],
                "coord_source": s["coord_source"],
            },
        }
        features.append(feat)

    geojson = {"type": "FeatureCollection", "features": features}
    out = VIZ / "stations.geojson"
    with out.open("w") as f:
        json.dump(geojson, f, separators=(",", ":"))
    print(f"wrote {out} ({len(features)} stations)")

    # Per-station summary CSV
    summary_csv = VIZ / "elevator_ops_summary.csv"
    with summary_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "lat", "lon", "elevator_rows",
                    "n_owners", "n_years", "first_year", "last_year",
                    "top_owner", "top_rail", "max_capacity_bushels",
                    "coord_source"])
        for (station, province), s in sorted(per_station.items(),
                                             key=lambda x: -x[1]["rows"]):
            if s["lat"] is None:
                continue
            top_owner = s["owners"].most_common(1)[0][0] if s["owners"] else ""
            top_rail = s["rail_canonical"].most_common(1)[0][0] if s["rail_canonical"] else ""
            w.writerow([station, province, round(s["lat"], 5), round(s["lon"], 5),
                        s["rows"], len(s["owners"]), len(s["years"]),
                        min(s["years"]) if s["years"] else "",
                        max(s["years"]) if s["years"] else "",
                        title_case_owner(top_owner), top_rail,
                        s["max_capacity"] or "",
                        s["coord_source"]])
    print(f"wrote {summary_csv}")


if __name__ == "__main__":
    main()
