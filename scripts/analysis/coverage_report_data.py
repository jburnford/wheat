"""Zone definitions + SVG township maps for docs/analysis/transcription_priorities.html."""
from pathlib import Path
import json, math
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[2]; A = ROOT / "data" / "homesteads" / "analysis"
f = pd.read_parquet(A / "township_frame_scored.parquet")
f["done"] = f.status == "done"
N, D = len(f), int(f.done.sum()); base = D / N

# ---- spine: every 3rd range x every 3rd township (offset 1,1), not done
f["spine"] = (~f.done) & (f.rge % 3 == 1) & (f.twp % 3 == 1)

# ---- zones (meridian, range span, township span)
ZONES = [
  ("A", "Dry south-west", [(3, 1, 8, 1, 24), (3, 9, 19, 1, 14)], "Swift Current – Shaunavon – Maple Creek – Leader"),
  ("B", "Far south-west sheets", [(3, 20, 30, 1, 24)], "Cypress Hills – Maple Creek – Alsask; names-only sheets R20–R30"),
  ("C", "Forest fringe (north)", [(2, 1, 30, 49, 56), (3, 1, 30, 49, 56), (1, 30, 34, 49, 56)], "Hudson Bay Jct – Nipawin – Big River – Meadow Lake"),
  ("D", "East-central parkland", [(2, 1, 10, 25, 48)], "Kamsack – Pelly – Preeceville – Hudson Bay"),
  ("E", "South-east corner", [(2, 28, 30, 1, 36), (1, 30, 30, 1, 36)], "Estevan – Carnduff – Moosomin east strip"),
  ("F", "South-central plains", [(2, 14, 27, 1, 12)], "Big Muddy – Radville – Assiniboia"),
  ("G", "West-central (Kindersley–Kerrobert)", [(3, 20, 30, 25, 40)], "names-only sheets, 1908–12 belt"),
]
def in_zone(z):
    m = np.zeros(len(f), bool)
    for (mer, r0, r1, t0, t1) in z:
        m |= (f.mer == mer) & (f.rge.between(r0, r1)) & (f.twp.between(t0, t1))
    return m
zrows = []
f["zone"] = ""
for code, name, spec, desc in ZONES:
    m = in_zone(spec); f.loc[m & (f.zone == ""), "zone"] = code
    nd = f[m & ~f.done]
    zrows.append(dict(code=code, name=name, desc=desc, twps=int(m.sum()), done=int((m & f.done).sum()), coverage=round((m & f.done).sum() / max(m.sum(), 1) * 100, 1),
                      todo_twps=int(len(nd)), todo_rows=int(nd.rows.sum()), names_only=int((nd.status == "names-only").sum()),
                      mean_w=round(float(nd.priority_w.mean()), 2) if len(nd) else 0,
                      era=nd.era.value_counts(normalize=True).round(2).head(3).to_dict(), cpr_belt=round(float((nd.cpr_belt == "CPR belt").mean()) * 100, 0),
                      spine_twps=int((m & f.spine).sum()), spine_rows=int(f[m & f.spine].rows.sum())))
zones = pd.DataFrame(zrows).sort_values("mean_w", ascending=False)
print(zones.to_string())
print("spine total:", int(f.spine.sum()), "twps", int(f[f.spine].rows.sum()), "rows; in zones:", int((f.spine & (f.zone != "")).sum()))

# ---- what the sample would look like after the spine (era x band coverage)
after = f.copy(); after["done2"] = after.done | after.spine
def cov_tbl(col, dcol):
    t = after.groupby(col).agg(frame=(dcol, "size"), done=(dcol, "sum")); t["cov"] = (t.done / t.frame * 100).round(1); return t
print("\nera coverage now vs after spine:"); print(pd.concat([cov_tbl("era", "done")["cov"], cov_tbl("era", "done2")["cov"]], axis=1, keys=["now", "after"]))
print("band:"); print(pd.concat([cov_tbl("band", "done")["cov"], cov_tbl("band", "done2")["cov"]], axis=1, keys=["now", "after"]))
print("cpr:"); print(pd.concat([cov_tbl("cpr_belt", "done")["cov"], cov_tbl("cpr_belt", "done2")["cov"]], axis=1, keys=["now", "after"]))
pv = after.pivot_table(index="band", columns="era", values="done2", aggfunc=["size", "sum"])
print("era x band coverage after spine:"); print((pv["sum"] / pv["size"] * 100).round(0).fillna(-1).astype(int).to_string())
empty_cells_now = int((f.groupby(["era", "band"]).done.sum() == 0).sum()); empty_cells_after = int((after.groupby(["era", "band"]).done2.sum() == 0).sum())
print("era x band cells with zero coverage: now", empty_cells_now, "after spine", empty_cells_after)

# ---- SVG maps
W, H = 560, 600
lon0, lon1, lat0, lat1 = -110.2, -101.3, 48.9, 54.6
def xy(lon, lat):
    x = (lon - lon0) / (lon1 - lon0) * W
    y = (lat1 - lat) / (lat1 - lat0) * H
    return round(x, 1), round(y, 1)
# township ~ 9.66 km ~ 0.087 deg lat, lon width varies
def rect(r, fill, cls=""):
    dlat = 9.656 / 111.32; dlon = 9.656 / (111.32 * math.cos(math.radians(r.lat)))
    x, y = xy(r.lon - dlon / 2, r.lat + dlat / 2); x2, y2 = xy(r.lon + dlon / 2, r.lat - dlat / 2)
    return f'<rect x="{x}" y="{y}" width="{round(x2-x,2)}" height="{round(y2-y,2)}" fill="{fill}"{(" class=%s" % chr(34)+cls+chr(34)) if cls else ""}><title>{r.key} · {r.status} · {r.era} · {r.rows} rows</title></rect>'
STATUS_FILL = {"done": "var(--m-done)", "names-only": "var(--m-names)", "empty": "var(--m-empty)"}
ERA_FILL = {"pre-1890": "var(--e1)", "1890s": "var(--e2)", "1901-05": "var(--e3)", "1906-10": "var(--e4)", "1911+": "var(--e5)", "no proxy": "var(--e0)"}
svg_status = [rect(r, STATUS_FILL[r.status]) for r in f.itertuples()]
svg_spine = [rect(r, "none", "spine") for r in f[f.spine].itertuples()]
svg_era = [rect(r, ERA_FILL[r.era], "" if r.done else "nd") for r in f.itertuples()]
# zone outlines: bounding boxes of each rectangular spec
zone_boxes = []
for code, name, spec, desc in ZONES:
    for (mer, r0, r1, t0, t1) in spec:
        sub = f[(f.mer == mer) & f.rge.between(r0, r1) & f.twp.between(t0, t1)]
        if not len(sub): continue
        x, y = xy(sub.lon.min() - 0.06, sub.lat.max() + 0.05); x2, y2 = xy(sub.lon.max() + 0.06, sub.lat.min() - 0.05)
        zone_boxes.append(f'<rect x="{x}" y="{y}" width="{round(x2-x,1)}" height="{round(y2-y,1)}" class="zone"/><text x="{x+4}" y="{y+13}" class="zl">{code}</text>')
# city labels
CITIES = [("Saskatoon", -106.67, 52.13), ("Regina", -104.62, 50.45), ("Prince Albert", -105.75, 53.2), ("Battleford", -108.3, 52.73), ("Swift Current", -107.8, 50.29), ("Yorkton", -102.46, 51.21), ("Moose Jaw", -105.53, 50.39), ("Estevan", -102.98, 49.14), ("Maple Creek", -109.48, 49.91), ("Kindersley", -109.16, 51.47), ("Nipawin", -104.0, 53.36), ("Meadow Lake", -108.43, 54.13)]
cities = "".join(f'<circle cx="{xy(lo,la)[0]}" cy="{xy(lo,la)[1]}" r="2.2" class="city"/><text x="{xy(lo,la)[0]+4}" y="{xy(lo,la)[1]+3}" class="cl">{n}</text>' for n, lo, la in CITIES)
out = {"W": W, "H": H, "svg_status": "".join(svg_status), "svg_spine": "".join(svg_spine), "svg_era": "".join(svg_era), "zones_svg": "".join(zone_boxes), "cities": cities,
       "zones": zones.to_dict(orient="records"), "N": N, "D": D, "base": base,
       "spine": {"twps": int(f.spine.sum()), "rows": int(f[f.spine].rows.sum())},
       "cov_now_after": {c: pd.concat([cov_tbl(c, "done")[["frame", "done", "cov"]], cov_tbl(c, "done2")["cov"].rename("after")], axis=1).reset_index().to_dict(orient="records") for c in ["era", "band", "merid", "cpr_belt", "near_reserve"]},
       "cells": {"now": empty_cells_now, "after": empty_cells_after}}
json.dump(out, open(Path(__file__).parent / "coverage_report_data.json", "w"), ensure_ascii=False, default=str)
f.to_parquet(A / "township_frame_scored.parquet")
print("wrote coverage_report_data.json")
