# Saskatchewan Urban Settlements, 1921

**Created by Jessica Jack**, as part of the *Mapping Settler Colonialism in
Saskatchewan* project (Jim Clifford & Cheryl Troupe), University of Saskatchewan
History Department.

429 incorporated municipalities profiled in the 1921 federal census, with
coordinates, population, railway companies, commercial tier, top industries, and
dated event timelines (founding, incorporation, railway arrival, post office,
church, school, etc.).

Source repo: <https://github.com/jjax07/Knowledge_Graph_Website>
Project story map: <https://storymaps.arcgis.com/stories/8288eb9615484e708922e81411e63936>

## Files

- `settlements.json` — 429 settlements: coords, population, railways, dated events.
- `tier_settlements.json` — commercial tier + top local industries per settlement.

## Use here

`scripts/build_townsites.py` merges the two into `docs/townsites.geojson` (one
point per town). On the settlement map each town **appears at its founding year**
as the slider advances, is sized by commercial tier (kept small so the rural
land data stays the focus), and its popup shows the timeline, tier, railways and
top industries.
