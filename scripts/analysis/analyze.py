from pathlib import Path
import sys, json, warnings
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from shapely.geometry import shape, Point, LineString
from shapely.strtree import STRtree
from shapely.ops import transform
import shapely
pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_columns", 30)

S = str(Path(__file__).resolve().parents[2] / "data" / "homesteads" / "analysis")
d = pd.read_parquet(f"{S}/homesteads_flat.parquet")
d["decade"] = (d.year // 10 * 10)
dated = d[d.year.notna()].copy()
dated["year"] = dated.year.astype(int)
print("=" * 70); print("A. TYPE"); print("=" * 70)
print("rows:", len(d), " dated:", len(dated), " typed:", d.grp.notna().sum())
print("\nraw Type values (top 40):")
print(d.type_raw.replace("", "<blank>").value_counts().head(40))
print("\ntenure group counts (all / dated):")
print(pd.concat([d.grp.fillna("none").value_counts(), dated.grp.fillna("none").value_counts()], axis=1, keys=["all", "dated"]))
print("\ntenure group by decade (dated rows, % within decade):")
ct = pd.crosstab(dated.decade, dated.grp.fillna("none"))
print(ct); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\ntenure group by section parity (odd=railway half):")
print(pd.crosstab(d.grp.fillna("none"), d.odd))
print("\nHBC sections 8/26 and school sections 11/29 — tenure mix:")
d["secclass"] = np.select([d.sec.isin([8, 26]), d.sec.isin([11, 29]), d.odd], ["HBC(8,26)", "School(11,29)", "odd(rail)"], "even")
print(pd.crosstab(d.secclass, d.grp.fillna("none")))
print("\ninstitutional claimants:", d.inst.sum())
print(d[d.inst].first_name.str.upper().str.replace(r"[^A-Z ]", "", regex=True).value_counts().head(15))

print("\n" + "=" * 70); print("B. TIMING"); print("=" * 70)
print("\nsettlement year by year (all meridians):")
yy = pd.crosstab(dated.year, dated.mer); yy["all"] = yy.sum(1)
print(yy.to_string())
print("\npatent year histogram by 5-yr bin:")
p = d.patent.dropna().astype(int)
print((p // 5 * 5).value_counts().sort_index())
lag = d[d.entry.notna() & d.patent.notna()].copy()
lag["lag"] = lag.patent - lag.entry
print("\nentry->patent lag: n=", len(lag), " negative:", (lag.lag < 0).sum())
lag = lag[lag.lag >= 0]
print(lag.lag.describe())
print("lag distribution (years):"); print(lag.lag.clip(upper=15).value_counts().sort_index())
lag["cohort"] = lag.entry // 5 * 5
print("\nlag by entry cohort (median / mean / n / %<=3yr / %>=6yr):")
print(lag.groupby("cohort").lag.agg(median="median", mean="mean", n="size",
      le3=lambda s: (s <= 3).mean() * 100, ge6=lambda s: (s >= 6).mean() * 100).round(1))
print("\nlag by tenure group:")
print(lag.groupby(lag.grp.fillna("none")).lag.agg(["median", "mean", "size"]).round(1))

print("\nCHURN: Number_of_claims distribution (where recorded):")
print(d.n_claims.dropna().astype(int).clip(upper=6).value_counts().sort_index())
d["churn"] = (d.n_claims > 1) | (d.n_failed > 0)
print("share of populated quarters with >1 claim or any failed claim:", round(d.churn.mean() * 100, 1), "%")
print("  among dated:", round(dated.assign(churn=(dated.n_claims > 1) | (dated.n_failed > 0)).churn.mean() * 100, 1), "%")
print("\nchurn by decade of first entry (% of dated rows; mean claims where recorded):")
dd = dated.assign(churn=(dated.n_claims > 1) | (dated.n_failed > 0))
print(dd.groupby("decade").agg(n=("churn", "size"), churn_pct=("churn", lambda s: round(s.mean() * 100, 1)),
                               mean_claims=("n_claims", "mean"), failed_pct=("n_failed", lambda s: round((s > 0).mean() * 100, 1))).round(2))
print("\nchurn by tenure group:")
print(d.groupby(d.grp.fillna("none")).agg(n=("churn", "size"), churn_pct=("churn", lambda s: round(s.mean() * 100, 1)),
                                           failed_pct=("n_failed", lambda s: round((s > 0).mean() * 100, 1))))
print("\nfailed-only quarters (no successful claimant):", ((d.n_success == 0) & (d.n_failed > 0)).sum())
print("undated but named quarters:", ((d.year.isna()) & (d.n_success > 0)).sum())

# multi-quarter claimants
nm = d[(~d.inst) & (d.first_name != "")].first_name.str.strip().str.upper()
vc = nm.value_counts()
print("\nnames appearing on >1 quarter:", (vc > 1).sum(), "of", len(vc), " quarters held by such names:", vc[vc > 1].sum())
print("names on >=3 quarters:", (vc >= 3).sum(), " >=5:", (vc >= 5).sum())
print(vc.head(20))

print("\n" + "=" * 70); print("C. GEOGRAPHY"); print("=" * 70)
print("\nby meridian:")
print(d.groupby("mer").agg(rows=("year", "size"), dated=("year", "count"), med_year=("year", "median"),
                           q1=("year", lambda s: s.quantile(.25)), q3=("year", lambda s: s.quantile(.75)),
                           churn_pct=("churn", lambda s: round(s.mean() * 100, 1))))
print("\nby township band (lat), dated rows:")
dated["band"] = pd.cut(dated.twp, [0, 10, 20, 30, 40, 50, 60], labels=["T1-10", "T11-20", "T21-30", "T31-40", "T41-50", "T51-56"])
print(dated.groupby("band").agg(n=("year", "size"), med=("year", "median"), q1=("year", lambda s: s.quantile(.25)),
                                 q3=("year", lambda s: s.quantile(.75)), pre1900=("year", lambda s: round((s < 1900).mean() * 100, 1)),
                                 post1910=("year", lambda s: round((s >= 1910).mean() * 100, 1))))
print("\nmedian settlement year by band x meridian:")
print(dated.pivot_table(index="band", columns="mer", values="year", aggfunc="median"))
print("\ntenure mix by band (%):")
ct = pd.crosstab(dated.band, dated.grp.fillna("none")); print((ct.div(ct.sum(1), axis=0) * 100).round(1))

# --- railway proximity at time of entry ---
rail = json.load(open(str(Path(S).parents[2] / "docs") + "/rail_lines.geojson"))
def proj(lon, lat):  # equirectangular km around 52N
    return ((np.asarray(lon) + 105) * 111.32 * np.cos(np.radians(52)), (np.asarray(lat) - 52) * 111.32)
lines, yrs = [], []
for f in rail["features"]:
    y = f["properties"].get("cnstrctd") or 0
    if not y: continue
    g = shape(f["geometry"])
    g = transform(lambda x, yy, z=None: proj(x, yy), g)
    lines.append(g); yrs.append(int(y))
yrs = np.array(yrs)
tw = d.groupby(["twp", "rge", "mer"]).agg(lon=("lon", "first"), lat=("lat", "first")).reset_index()
px, py = proj(tw.lon, tw.lat)
pts = [Point(x, y) for x, y in zip(px, py)]
# year rail arrived within 16 km of township centre
arr = np.full(len(tw), 9999)
for y in sorted(set(yrs)):
    tree = STRtree([l for l, yy in zip(lines, yrs) if yy <= y])
    near = tree.query(pts, predicate="dwithin", distance=16.0)
    idx = np.unique(near[0])
    arr[idx] = np.minimum(arr[idx], y)
tw["rail_yr"] = arr
d = d.merge(tw[["twp", "rge", "mer", "rail_yr"]], on=["twp", "rge", "mer"])
dd = d[d.year.notna()].copy(); dd["year"] = dd.year.astype(int)
dd["rel"] = dd.year - dd.rail_yr.where(dd.rail_yr < 9999)
print("\nRAIL: townships with rail within 16 km by 1935:", (tw.rail_yr < 9999).sum(), "of", len(tw))
print("dated quarters: entry relative to rail arrival (<=16 km):")
print("  no rail by 1935:", dd.rel.isna().sum())
r = dd.rel.dropna()
print("  before rail (rel<0):", (r < 0).sum(), f"({(r<0).mean()*100:.1f}%)", " same year:", (r == 0).sum(), " after:", (r > 0).sum())
print("  rel distribution (years, clipped -15..15):"); print(r.clip(-15, 15).astype(int).value_counts().sort_index().to_string())
dd["relband"] = pd.cut(dd.rel, [-99, -6, -1, 0, 5, 99], labels=["rail 6+ yrs later", "rail 1-5 yrs later", "same year", "rail 1-5 yrs before", "rail 6+ yrs before"])
print("\nby decade of entry, % settled before rail reached 16 km:")
print(dd.groupby("decade").apply(lambda s: pd.Series({"n": len(s), "no_rail_ever": s.rel.isna().mean() * 100, "before_rail": (s.rel < 0).mean() * 100, "after_rail": (s.rel > 0).mean() * 100})).round(1))
lag2 = dd[dd.entry.notna() & dd.patent.notna() & (dd.patent >= dd.entry)].copy(); lag2["lag"] = lag2.patent - lag2.entry
print("\nentry->patent lag and churn by rail timing at entry:")
print(lag2.groupby("relband").lag.agg(["median", "mean", "size"]).round(1))
print(dd.groupby("relband").churn.mean().round(3) * 100)

# --- CPR odd-section sales vs even-section homesteads, same township ---
st = json.load(open(str(Path(S).parents[2] / "docs") + "/settlement_townships.geojson"))
cpr = pd.DataFrame([{"key": f["properties"]["twp"], "cpr_first": int(f["properties"]["first"]) if f["properties"].get("first") else np.nan,
                     "cpr_total": int(f["properties"]["total"])} for f in st["features"]])
dd["key"] = dd.apply(lambda r: f"{int(r.twp):03d}-{int(r.rge):02d}-W{int(r.mer)}", axis=1)
hs = dd[~dd.odd].groupby("key").year.agg(hs_med="median", hs_first="min", hs_n="size").reset_index()
j = hs.merge(cpr, on="key")
print("\nCPR: townships with both CPR sales and dated homesteads:", len(j))
print("homestead median entry − first CPR sale (years):"); print((j.hs_med - j.cpr_first).describe().round(1))
print("share where first homestead precedes first CPR sale:", round(((j.hs_first < j.cpr_first)).mean() * 100, 1), "%")
print("share where median homestead precedes first CPR sale:", round(((j.hs_med < j.cpr_first)).mean() * 100, 1), "%")

# --- reserve surrenders ---
sur = json.load(open(str(Path(S).parents[2] / "docs") + "/reserve_surrenders.geojson"))
from dls_grid import GridModel
grid = GridModel()
polys = [transform(lambda x, yy, z=None: proj(x, yy), shape(f["geometry"])) for f in sur["features"]]
props = [f["properties"] for f in sur["features"]]
tree = STRtree(polys)
# candidate townships: centre within 12 km of any surrender polygon
near = tree.query(pts, predicate="dwithin", distance=12.0)
cand = set(zip(tw.twp[near[0]], tw.rge[near[0]], tw.mer[near[0]]))
sub = d[[k in cand for k in zip(d.twp, d.rge, d.mer)]]
hits = []
for r in sub.itertuples():
    try:
        ring = grid.polygon(int(r.twp), int(r.rge), "W" + str(int(r.mer)), int(r.sec), r.qs)
    except Exception:
        continue
    c = np.mean(np.array(ring), axis=0)
    p = Point(*proj(c[0], c[1]))
    for i in tree.query(p, predicate="within"):
        hits.append(dict(idx=r.Index, reserve=props[i].get("RSRVE_NAME"), yr_sur=int(props[i].get("YR_SUR") or 0)))
h = pd.DataFrame(hits).drop_duplicates("idx").merge(d, left_on="idx", right_index=True)
print("\nRESERVE SURRENDERS: populated quarters inside surrendered reserve polygons:", len(h))
print(h.groupby(["reserve", "yr_sur"]).agg(n=("year", "size"), dated=("year", "count"), med_year=("year", "median"),
                                           min_year=("year", "min"), grp_mix=("grp", lambda s: s.fillna("-").value_counts().head(3).to_dict())).to_string())
hd = h[h.year.notna()]
print("dated entries relative to surrender year:", "before:", (hd.year < hd.yr_sur).sum(), " same/after:", (hd.year >= hd.yr_sur).sum())
print("lag surrender->entry (years):"); print((hd.year - hd.yr_sur).describe().round(1))
d.to_parquet(f"{S}/homesteads_flat2.parquet")
