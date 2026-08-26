"""Township-level transcription-status frame for prioritising data entry.

One row per township present in W1-W3 (the sampling frame), with:
  rows / populated / typed / dated counts, status (done / names-only / empty),
  centroid, and province-wide covariates that do not depend on transcription:
  rail arrival year (<=16 km), nearest 1921 town founding year (<=25 km),
  nearest elevator first year (<=15 km), CPR catalogue sales (n, median year,
  median $/ac), reserve within 10 km.
Writes data/homesteads/analysis/township_frame.parquet
"""
from pathlib import Path
import sys, json, math, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from shapely.ops import transform
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from dls_grid import GridModel
A = ROOT / "data" / "homesteads" / "analysis"; A.mkdir(parents=True, exist_ok=True)
DATACOLS = ["Type", "FirstDate", "FirstDateSuccess", "Successful_Claims", "Failed_Claims", "Patent_Date", "Number_of_claims"]

# ---------------------------------------------------------------- frame
rows = []
for fn in ["W1.xlsx", "W2.xlsx", "W3.xlsx"]:
    for sh, df in pd.read_excel(ROOT / fn, sheet_name=None).items():
        df = df.dropna(subset=["PTWP", "PRGE"])
        df["twp"] = pd.to_numeric(df.PTWP, errors="coerce"); df["rge"] = pd.to_numeric(df.PRGE, errors="coerce")
        df = df.dropna(subset=["twp", "rge"])
        df["pop"] = df[DATACOLS].notna().any(axis=1)
        df["typed"] = df.Type.notna()
        df["dated"] = df[["FirstDate", "FirstDateSuccess", "Patent_Date"]].notna().any(axis=1)
        g = df.groupby(["twp", "rge"]).agg(rows=("pop", "size"), populated=("pop", "sum"), typed=("typed", "sum"), dated=("dated", "sum")).reset_index()
        g["mer"] = int(fn[1]); g["sheet"] = sh
        rows.append(g)
f = pd.concat(rows); f["twp"] = f.twp.astype(int); f["rge"] = f.rge.astype(int)
f["key"] = f.apply(lambda r: f"{r.twp}-{r.rge}-W{r.mer}", axis=1)
f["typed_share"] = f.typed / f.rows
f["pop_share"] = f.populated / f.rows
f["status"] = np.select([f.typed_share >= 0.5, f.pop_share >= 0.3], ["done", "names-only"], "empty")
print("townships:", len(f)); print(f.status.value_counts())
print("typed_share histogram:", np.histogram(f.typed_share, bins=[0, .01, .1, .3, .5, .7, .9, 1.01])[0])

# ---------------------------------------------------------------- centroids
grid = GridModel()
MER_LON = {1: -97.4575, 2: -102.0, 3: -106.0}
def approx(t, r, m):
    lat = 49.0 + (t - 0.5) * 9.656 / 111.32
    lon = MER_LON[m] - (r - 0.5) * 9.656 / (111.32 * math.cos(math.radians(lat)))
    return lon, lat
lons, lats, src = [], [], []
for r in f.itertuples():
    try:
        c = grid.affine_for(r.twp, r.rge, f"W{r.mer}"); ctr = c["O"] + 6 * c["ex"] + 6 * c["ey"]
        lons.append(float(ctr[0])); lats.append(float(ctr[1])); src.append("grid")
    except Exception:
        lo, la = approx(r.twp, r.rge, r.mer); lons.append(lo); lats.append(la); src.append("approx")
f["lon"], f["lat"], f["ctr_src"] = lons, lats, src
print("centroid source:", f.ctr_src.value_counts().to_dict())

def proj(lon, lat):
    return ((np.asarray(lon) + 105) * 111.32 * math.cos(math.radians(52)), (np.asarray(lat) - 52) * 111.32)
px, py = proj(f.lon, f.lat); pts = [Point(x, y) for x, y in zip(px, py)]

# ---------------------------------------------------------------- rail
rail = json.load(open(ROOT / "docs" / "rail_lines.geojson"))
lines, yrs = [], []
for ft in rail["features"]:
    y = ft["properties"].get("cnstrctd") or 0
    if y <= 0: continue
    lines.append(transform(lambda x, yy, z=None: proj(x, yy), shape(ft["geometry"]))); yrs.append(int(y))
yrs = np.array(yrs); arr = np.full(len(f), 9999)
for y in sorted(set(yrs)):
    tree = STRtree([l for l, yy in zip(lines, yrs) if yy <= y])
    near = tree.query(pts, predicate="dwithin", distance=16.0)
    idx = np.unique(near[0]); arr[idx] = np.minimum(arr[idx], y)
f["rail_yr"] = arr

# ---------------------------------------------------------------- towns, elevators
def nearest_year(geo, yearkey, maxkm, filt=lambda p: True):
    g = json.load(open(geo)); P, Y = [], []
    for ft in g["features"]:
        p = ft["properties"]
        if not filt(p): continue
        try: y = int(p.get(yearkey))
        except (TypeError, ValueError): continue
        if y <= 0: continue
        x, yy = proj(*ft["geometry"]["coordinates"][:2]); P.append(Point(x, yy)); Y.append(y)
    tree = STRtree(P); out = np.full(len(f), np.nan)
    near = tree.query(pts, predicate="dwithin", distance=maxkm)
    for i, j in zip(near[0], near[1]):
        out[i] = np.nanmin([out[i], Y[j]])
    return out
f["town_fy"] = nearest_year(ROOT / "docs" / "townsites.geojson", "fy", 25)
f["elev_yr"] = nearest_year(ROOT / "docs" / "stations.geojson", "first_year", 15, lambda p: str(p.get("province", "")).upper().startswith("SASK"))
f["settle_proxy"] = f[["rail_yr", "town_fy", "elev_yr"]].replace(9999, np.nan).min(axis=1)

# ---------------------------------------------------------------- CPR catalogue
c = pd.read_parquet(A / "cpr_sk.parquet"); c = c[c.prov == "SK"]
c["key"] = c.apply(lambda r: f"{int(r.twp)}-{int(r.rge)}-{r.mer}" if pd.notna(r.twp) and pd.notna(r.rge) else None, axis=1)
cp = c.groupby("key").agg(cpr_n=("lld", "size"), cpr_yr=("year", "median"), cpr_price=("price", "median"))
f = f.merge(cp, left_on="key", right_index=True, how="left"); f["cpr_n"] = f.cpr_n.fillna(0).astype(int)

# ---------------------------------------------------------------- reserves
res = json.load(open(ROOT / "docs" / "reserves_initial.geojson"))
polys = [transform(lambda x, yy, z=None: proj(x, yy), shape(ft["geometry"])) for ft in res["features"]]
tree = STRtree(polys); near = tree.query(pts, predicate="dwithin", distance=10.0)
nr = np.zeros(len(f), dtype=bool); nr[np.unique(near[0])] = True; f["near_reserve"] = nr   # by position: index is not unique here

# ---------------------------------------------------------------- strata
f["era"] = pd.cut(f.settle_proxy, [0, 1890, 1900, 1905, 1910, 1950], labels=["pre-1890", "1890s", "1901-05", "1906-10", "1911+"]).astype(str).replace("nan", "no proxy")
f["band"] = pd.cut(f.twp, [0, 12, 24, 36, 48, 60], labels=["T1-12 (south)", "T13-24", "T25-36", "T37-48 (parkland)", "T49+ (forest fringe)"]).astype(str)
f["cpr_belt"] = np.where(f.cpr_n >= 20, "CPR belt", np.where(f.cpr_n > 0, "some CPR", "no CPR land"))
f["merid"] = "W" + f.mer.astype(str)
f = f.reset_index(drop=True)
f.to_parquet(A / "township_frame.parquet")
print(f.head()); print("saved", len(f))
