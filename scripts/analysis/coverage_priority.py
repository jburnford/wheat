"""Compare transcribed townships against the full frame on province-wide strata,
and rank untranscribed sheet blocks by how much they would reduce the skew."""
from pathlib import Path
import json, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
pd.set_option("display.width", 220, "display.max_rows", 200, "display.max_columns", 30)
ROOT = Path(__file__).resolve().parents[2]; A = ROOT / "data" / "homesteads" / "analysis"
f = pd.read_parquet(A / "township_frame.parquet")
f["done"] = f.status == "done"
N, D = len(f), int(f.done.sum()); base = D / N
print(f"frame {N} townships; done {D} ({base*100:.1f}%)")

def cov(col):
    t = f.groupby(col).agg(frame=("done", "size"), done=("done", "sum"))
    t["frame_%"] = t.frame / N * 100; t["done_%"] = t.done / D * 100
    t["coverage_%"] = t.done / t.frame * 100
    t["ratio"] = t["done_%"] / t["frame_%"]
    t["deficit_twps"] = (t.frame * base - t.done).round(0)
    return t.round(2)
for col in ["era", "band", "merid", "cpr_belt", "near_reserve"]:
    print(f"\n== {col} ==  (ratio <1 under-represented; deficit = townships needed to reach proportional)"); print(cov(col))
print("\n== era x band ==  coverage % (done/frame)")
pv = f.pivot_table(index="band", columns="era", values="done", aggfunc=["size", "sum"])
print((pv["sum"] / pv["size"] * 100).round(0).fillna(-1).astype(int).to_string()); print("frame counts:"); print(pv["size"].fillna(0).astype(int).to_string())
print("\n== era x merid == coverage %")
pv = f.pivot_table(index="merid", columns="era", values="done", aggfunc=["size", "sum"])
print((pv["sum"] / pv["size"] * 100).round(0).fillna(-1).astype(int).to_string())

# ---- weight each township by under-representation of its cell (era x band x merid)
cell = ["era", "band", "merid"]
g = f.groupby(cell).agg(frame=("done", "size"), done=("done", "sum")).reset_index()
g["target"] = g.frame * base
g["need"] = (g.target - g.done).clip(lower=0)          # townships needed in this cell to be proportional
g["w"] = np.where(g.done > 0, (g.frame / N) / (g.done / D), 3.0).clip(0, 3.0)   # cells with no done townships get max weight
f = f.merge(g[cell + ["need", "w"]], on=cell, how="left")
f["priority_w"] = np.where(f.done, 0, f.w)

# ---- candidate blocks: sheet (mer, rge) x 12-township band, not-done townships only
f["tband"] = (f.twp - 1) // 12
cand = f[~f.done].groupby(["merid", "rge", "tband"]).agg(twps=("key", "size"), rows=("rows", "sum"), names_only=("status", lambda s: (s == "names-only").sum()),
                                                        score=("priority_w", "sum"), mean_w=("priority_w", "mean"),
                                                        t_min=("twp", "min"), t_max=("twp", "max"),
                                                        era=("era", lambda s: s.value_counts().index[0]), cpr=("cpr_belt", lambda s: (s == "CPR belt").mean()),
                                                        res=("near_reserve", "mean"), proxy=("settle_proxy", "median")).reset_index()
cand["score_per_row"] = cand.score / cand.rows * 1000
cand = cand[cand.twps >= 4].sort_values("mean_w", ascending=False)
print("\n== candidate blocks (sheet x 12-township band), ranked by mean under-representation weight ==")
print(cand.head(30).round(2).to_string())

# ---- greedy plan: pick blocks until each cell's need is met, prefer high mean_w, then large
need = g.set_index(cell)["need"].to_dict(); plan = []; picked = set()
fc = f[~f.done].copy()
for _ in range(40):
    best, bestgain = None, 0
    for (m, r, tb), blk in fc.groupby(["merid", "rge", "tband"]):
        if (m, r, tb) in picked or len(blk) < 4: continue
        gain = sum(min(need.get((e, b, mm), 0), n) for (e, b, mm), n in blk.groupby(cell).size().items())
        gain_per_row = gain / blk.rows.sum()
        if gain_per_row > bestgain: best, bestgain = (m, r, tb, blk), gain_per_row
    if best is None or bestgain <= 0: break
    m, r, tb, blk = best; picked.add((m, r, tb))
    for (e, b, mm), n in blk.groupby(cell).size().items():
        k = (e, b, mm); need[k] = max(0, need.get(k, 0) - n)
    plan.append(dict(merid=m, rge=r, t_min=int(blk.twp.min()), t_max=int(blk.twp.max()), twps=len(blk), rows=int(blk.rows.sum()),
                     names_only=int((blk.status == "names-only").sum()), era=blk.era.value_counts().index[0], band=blk.band.value_counts().index[0],
                     cpr_belt=round((blk.cpr_belt == "CPR belt").mean(), 2), near_res=round(blk.near_reserve.mean(), 2), gain=round(bestgain * blk.rows.sum(), 1)))
    if sum(need.values()) < 5: break
plan = pd.DataFrame(plan)
print("\n== greedy plan to reach proportional coverage (era x band x meridian) ==")
print(plan.to_string()); print("total rows in plan:", plan.rows.sum(), " townships:", plan.twps.sum())
print("remaining need after plan:", round(sum(need.values()), 1))

# ---- systematic spine alternative: every 3rd range x every 3rd township among not-done
spine = f[(~f.done) & (f.rge % 3 == 1) & (f.twp % 3 == 1)]
print("\n== systematic spine (rge%3==1, twp%3==1, not done):", len(spine), "townships,", int(spine.rows.sum()), "rows")
print(spine.groupby("era").size().to_dict()); print(spine.groupby("band").size().to_dict())

f.to_parquet(A / "township_frame_scored.parquet")
out = {"twps": [dict(k=r.key, m=int(r.mer), t=int(r.twp), r=int(r.rge), lon=round(r.lon, 4), lat=round(r.lat, 4), s=r.status, w=round(float(r.priority_w), 2), e=r.era, rows=int(r.rows)) for r in f.itertuples()],
       "plan": plan.to_dict(orient="records"), "cov": {c: cov(c).reset_index().to_dict(orient="records") for c in ["era", "band", "merid", "cpr_belt", "near_reserve"]},
       "base": base, "N": N, "D": D}
json.dump(out, open(Path(__file__).parent / "coverage_data.json", "w"), ensure_ascii=False, default=str)
print("wrote coverage_data.json")
