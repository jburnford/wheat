#!/usr/bin/env python3
"""Merge Jessica Jack's 1921 Saskatchewan urban-settlements knowledge graph into a
compact GeoJSON point layer for docs/settlement.html.

Inputs (from the Knowledge_Graph_Website repo, copied into data/townsites/):
  settlements.json       - 429 settlements: coords, population, railways, events
  tier_settlements.json  - commercial tier + top local industries per settlement

Output: docs/townsites.geojson  (429 points; founded-year for the time slider,
events + industries + tier for the popup).

Source: "Mapping Settler Colonialism in Saskatchewan", U Saskatchewan History
(Jessica Jack). 1921 federal census of incorporated municipalities.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "townsites"
DOCS = ROOT / "docs"


def main():
    settlements = json.loads((SRC / "settlements.json").read_text())
    tiers = json.loads((SRC / "tier_settlements.json").read_text())

    feats = []
    for name, s in settlements.items():
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None:
            continue
        events = sorted(((e.get("year"), e.get("event")) for e in s.get("events", [])
                         if e.get("year")), key=lambda x: x[0])
        founded = events[0][0] if events else None
        def ev_year(label):
            return next((y for y, e in events if e == label), None)

        t = tiers.get(name, {})
        inds = [f"{i['industry']} ({i['pct']}%)" for i in t.get("localIndustries", [])][:5]

        props = {
            "nm": name,
            "ty": s.get("typeLabel") or s.get("type") or "",
            "pop": s.get("population") or 0,
            "rw": s.get("primaryRailway") or "",
            "rws": ", ".join(s.get("railways", [])),
            "tier": t.get("tier") or "",
            "ct": t.get("commercialType") or "",
            "fy": founded,
            "iy": ev_year("Incorporated"),
            "ry": ev_year("Railway Arrives"),
            "ev": [[y, e] for y, e in events],
            "ind": inds,
        }
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {k: v for k, v in props.items() if v not in (None, "", [])}})

    (DOCS / "townsites.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}))
    withtier = sum(1 for f in feats if f["properties"].get("tier"))
    withfy = sum(1 for f in feats if f["properties"].get("fy"))
    print(f"Wrote townsites.geojson  ({len(feats)} settlements; "
          f"{withtier} with tier, {withfy} with a founding year)")


if __name__ == "__main__":
    main()
