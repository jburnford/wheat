"""Province-wide covariates from the scraped Provincial Archives homestead index.

In untranscribed sheets the index's names for a quarter section spill across the
register columns (Successful_Claims, Failed_Claims, Patent_Date, Number_of_claims,
Notes, Unnamed: 13...). Count name-like values per row, then per township:
  files       quarters with >=1 index name
  multi       quarters with >=2 names (a cancelled/abandoned entry before the last)
  n3          quarters with >=3 names
For transcribed (typed) rows, names = Successful_Claims + Failed_Claims entries.
Writes data/homesteads/analysis/index_township.parquet and index_rows.parquet
"""
from pathlib import Path
import re, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[2]; A = ROOT / "data" / "homesteads" / "analysis"
NAMECOLS = ["Successful_Claims", "Failed_Claims", "Patent_Date", "Number_of_claims", "Notes"]
YEAR = re.compile(r"^\s*(18|19)\d\d")
def namelike(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return 0
    if not isinstance(v, str): return 0
    s = v.strip()
    if not s or YEAR.match(s) or s.replace(".", "").isdigit(): return 0
    return len([p for p in s.split(";") if p.strip()])
rows = []
for fn in ["W1.xlsx", "W2.xlsx", "W3.xlsx"]:
    for sh, df in pd.read_excel(ROOT / fn, sheet_name=None).items():
        df = df.dropna(subset=["PTWP", "PRGE"])
        df["twp"] = pd.to_numeric(df.PTWP, errors="coerce"); df["rge"] = pd.to_numeric(df.PRGE, errors="coerce")
        df = df.dropna(subset=["twp", "rge"]); df["sec"] = pd.to_numeric(df.PSECT, errors="coerce")
        typed = df.Type.notna()
        cols = NAMECOLS + [c for c in df.columns if str(c).startswith("Unnamed")]
        cnt_index = df[cols].astype(object).applymap(namelike).sum(axis=1)                       # all name-like cells (index rows)
        cnt_reg = df[["Successful_Claims", "Failed_Claims"]].astype(object).applymap(namelike).sum(axis=1)  # curated columns (register rows)
        out = pd.DataFrame({"mer": int(fn[1]), "sheet": sh, "twp": df.twp.astype(int), "rge": df.rge.astype(int), "sec": df.sec,
                            "typed": typed.values, "names": np.where(typed, cnt_reg, cnt_index)})
        rows.append(out)
r = pd.concat(rows, ignore_index=True)
r["key"] = r.twp.astype(str) + "-" + r.rge.astype(str) + "-W" + r.mer.astype(str)
r["odd"] = r.sec % 2 == 1
r.to_parquet(A / "index_rows.parquet")
print("rows", len(r), " with >=1 name:", int((r.names >= 1).sum()), " >=2:", int((r.names >= 2).sum()), " >=3:", int((r.names >= 3).sum()))
print("names distribution (index rows):", r[~r.typed].names.clip(upper=5).value_counts().sort_index().to_dict())
print("names distribution (typed rows):", r[r.typed].names.clip(upper=5).value_counts().sort_index().to_dict())
t = r.groupby("key").agg(rows=("names", "size"), files=("names", lambda s: (s >= 1).sum()), multi=("names", lambda s: (s >= 2).sum()), n3=("names", lambda s: (s >= 3).sum()),
                         files_even=("names", lambda s: 0), typed=("typed", "mean")).reset_index()
ev = r[~r.odd].groupby("key").agg(files_even=("names", lambda s: (s >= 1).sum()), rows_even=("names", "size")).reset_index()
t = t.drop(columns="files_even").merge(ev, on="key", how="left")
t["file_share"] = t.files / t.rows; t["even_file_share"] = t.files_even / t.rows_even
t["multi_share"] = np.where(t.files > 0, t.multi / t.files, np.nan)
t["n3_share"] = np.where(t.files > 0, t.n3 / t.files, np.nan)
t.to_parquet(A / "index_township.parquet")
print(t.describe().round(3).T[["mean", "50%", "min", "max"]])
