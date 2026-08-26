"""Write data/homesteads/transcription_plan_2026.csv: the 1-in-9 systematic spine
(range % 3 == 1 and township % 3 == 1) minus townships already transcribed,
ordered by meridian -> range sheet -> township. Re-run after each W1-W3
refresh (coverage_frame.py + coverage_priority.py + index_names.py first)."""
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[2]; A = ROOT / "data" / "homesteads" / "analysis"
f = pd.read_parquet(A / "township_frame_scored.parquet")
t = pd.read_parquet(A / "index_township.parquet")[["key", "files", "multi", "multi_share", "even_file_share"]]
f = f.drop(columns=[c for c in ["files", "multi", "multi_share", "even_file_share"] if c in f.columns]).merge(t, on="key", how="left")
sp = f[(f.status != "done") & (f.rge % 3 == 1) & (f.twp % 3 == 1)].copy()
sp["meridian"] = "W" + sp.mer.astype(str)
sp["index_files"] = sp.files.fillna(0).astype(int)
sp["index_multi_name_pct"] = (sp.multi_share * 100).round(0)
sp["even_quarters_with_file_pct"] = (sp.even_file_share * 100).round(0)
sp["rail_arrival"] = sp.rail_yr.replace(9999, np.nan)
sp["settlement_era_proxy"] = sp.era
sp["infill_zone"] = sp.zone.replace("", "")
sp["note"] = np.where(sp.index_files == 0, "no homestead files in index — likely reserve/forest/lease; low yield, keep for completeness",
             np.where(sp.index_files < 20, "few homestead files — quick township", ""))
sp = sp.sort_values(["mer", "rge", "twp"]); sp["sequence"] = range(1, len(sp) + 1)
sp = sp.rename(columns={"rge": "range", "twp": "township"})
cols = ["sequence", "meridian", "range", "township", "sheet", "status", "rows", "index_files", "index_multi_name_pct", "even_quarters_with_file_pct",
        "settlement_era_proxy", "rail_arrival", "cpr_belt", "near_reserve", "band", "infill_zone", "lon", "lat", "note"]
out = sp[cols].copy(); out["lon"] = out.lon.round(4); out["lat"] = out.lat.round(4)
out.to_csv(ROOT / "data" / "homesteads" / "transcription_plan_2026.csv", index=False)
print("townships:", len(out), "rows:", int(out.rows.sum()))
