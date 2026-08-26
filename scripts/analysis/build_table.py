"""Flatten W1/W2/W3 into one analysis table with township coordinates."""
import sys, re, math, warnings, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from build_homesteads import year_of, names, tenure_group, INSTITUTION, DATACOLS
from dls_grid import GridModel

ROOT = str(Path(__file__).resolve().parents[2])
grid = GridModel()
rows = []
for fn in ["W1.xlsx", "W2.xlsx", "W3.xlsx"]:
    xl = pd.ExcelFile(f"{ROOT}/{fn}")
    for sh in xl.sheet_names:
        df = pd.read_excel(f"{ROOT}/{fn}", sheet_name=sh)
        have = df[DATACOLS].notna().any(axis=1)
        for r in df[have].itertuples():
            qs = str(getattr(r, "QSECT", "")).strip().upper()
            try:
                sec = int(r.PSECT); T = int(r.PTWP); R = int(r.PRGE); M = int(r.PMER)
            except (TypeError, ValueError):
                continue
            snames = names(r.Successful_Claims); fnames = names(r.Failed_Claims)
            rawty = "" if (r.Type is None or (isinstance(r.Type, float) and math.isnan(r.Type))) else str(r.Type).strip()
            nclaims = pd.to_numeric(r.Number_of_claims, errors="coerce")
            rows.append(dict(mer=M, twp=T, rge=R, sec=sec, qs=qs, sheet=sh,
                             type_raw=rawty, grp=tenure_group(r.Type),
                             entry=year_of(r.FirstDate), success=year_of(r.FirstDateSuccess),
                             patent=year_of(r.Patent_Date),
                             n_success=len(snames), n_failed=len(fnames),
                             n_claims=nclaims if not pd.isna(nclaims) else np.nan,
                             inst=bool(snames and INSTITUTION.search(snames[0])),
                             first_name=(snames[0] if snames else ""),
                             notes=str(getattr(r, "Notes", "") or "")[:200]))
d = pd.DataFrame(rows)
d["year"] = d.entry.fillna(d.success).fillna(d.patent)
d["odd"] = d.sec % 2 == 1
# township centroid
cent = {}
for key, sub in d.groupby(["twp", "rge", "mer"]):
    T, R, M = key
    try:
        c = grid.affine_for(T, R, "W" + str(M))
        ctr = c["O"] + 6 * c["ex"] + 6 * c["ey"]
        cent[key] = (float(ctr[0]), float(ctr[1]))
    except Exception:
        cent[key] = (np.nan, np.nan)
d["lon"] = [cent[k][0] for k in zip(d.twp, d.rge, d.mer)]
d["lat"] = [cent[k][1] for k in zip(d.twp, d.rge, d.mer)]
OUT = Path(ROOT) / "data" / "homesteads" / "analysis"; OUT.mkdir(parents=True, exist_ok=True)
d.to_parquet(OUT / "homesteads_flat.parquet")
print(len(d), d.columns.tolist())
print(d.describe(include="all").T.head(30))
