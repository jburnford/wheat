#!/usr/bin/env python3
"""Create (or refresh) the entry CSV for one range sheet from W1/W2/W3.xlsx.

    python3 tools/register_entry/import_sheet.py W3 R22 [--twp 1,4,7]

Writes data/register/W3_R22.csv — one row per quarter section in register
order — carrying:
  * the DLS key (QSECT PSECT PTWP PRGE PMER)
  * the register columns as they stand in the workbook (Type, dates, names,
    Number_of_claims, Notes) — blank for untranscribed rows
  * index_names: the scraped Archives-index names for the quarter (joined by
    "; "), gathered from wherever they spilled in untranscribed rows
  * cpr_hint: purchaser | date | $/ac | status from the CPR catalogue, if the
    quarter appears there
  * entered_at / image: filled by the app

Existing CSV rows that the app has already edited (entered_at set) are kept;
everything else is refreshed from the workbook. Needs pandas + openpyxl (the
app itself needs only the standard library).
"""
import sys, re, json, argparse, math
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "register"
REG = ["Type", "FirstDate", "FirstDateSuccess", "Successful_Claims", "Failed_Claims", "Patent_Date", "Number_of_claims", "Notes"]
KEY = ["QSECT", "PSECT", "PTWP", "PRGE", "PMER"]
YEAR = re.compile(r"^\s*(18|19)\d\d")
QS_ORDER = {"NE": 0, "NW": 1, "SE": 2, "SW": 3}

def namelike(v):
    if not isinstance(v, str): return []
    s = v.strip()
    if not s or YEAR.match(s) or s.replace(".", "").isdigit(): return []
    return [p.strip() for p in s.split(";") if p.strip()]

def fmt_date(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return ""
    if hasattr(v, "strftime"): return v.strftime("%Y-%m-%d")
    return str(v).strip()

def cpr_hints():
    p = ROOT / "data" / "cpr_land_sales" / "cpr_land_sales_points.geojson"
    if not p.exists(): return {}
    g = json.load(open(p)); out = {}
    for f in g["features"]:
        q = f["properties"]
        try: k = (str(q["QS"]).upper(), int(q["SEC"]), int(q["TWP"]), int(q["RGE"]), int(str(q["MER"]).lstrip("W")))
        except (TypeError, ValueError, KeyError): continue
        try: price = f"${float(q.get('Price')):.2f}/ac" if float(q.get("Price") or 0) > 0 else ""
        except (TypeError, ValueError): price = ""
        out[k] = " | ".join(x for x in [str(q.get("Purchaser") or ""), str(q.get("Date") or ""), price, str(q.get("Status") or "")] if x)
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("mer"); ap.add_argument("sheet"); ap.add_argument("--twp", default=""); ap.add_argument("--fresh", action="store_true", help="discard rows previously entered in the app")
    a = ap.parse_args()
    mer = a.mer.upper(); sheet = a.sheet.upper()
    df = pd.read_excel(ROOT / f"{mer}.xlsx", sheet_name=sheet)
    df = df.dropna(subset=["PTWP", "PRGE", "PSECT"])
    for c in ("PSECT", "PTWP", "PRGE", "PMER"): df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["QSECT"] = df.QSECT.astype(str).str.strip().str.upper()
    if a.twp:
        keep = {int(x) for x in a.twp.split(",")}; df = df[df.PTWP.isin(keep)]
    typed = df.Type.notna()
    spill = REG[3:] + [c for c in df.columns if str(c).startswith("Unnamed")]
    hints = cpr_hints()
    rows = []
    for _, r in df.iterrows():
        is_typed = bool(pd.notna(r.Type))
        if is_typed:
            index_names = namelike(r.Successful_Claims) + namelike(r.Failed_Claims)
        else:
            index_names = [n for c in spill for n in namelike(r.get(c))]
        k = (r.QSECT, int(r.PSECT), int(r.PTWP), int(r.PRGE), int(r.PMER))
        row = {"QSECT": r.QSECT, "PSECT": int(r.PSECT), "PTWP": int(r.PTWP), "PRGE": int(r.PRGE), "PMER": int(r.PMER)}
        if is_typed:
            row.update({"Type": str(r.Type).strip(), "FirstDate": fmt_date(r.FirstDate), "FirstDateSuccess": fmt_date(r.FirstDateSuccess),
                        "Successful_Claims": "" if pd.isna(r.Successful_Claims) else str(r.Successful_Claims).strip(),
                        "Failed_Claims": "" if pd.isna(r.Failed_Claims) else str(r.Failed_Claims).strip(),
                        "Patent_Date": fmt_date(r.Patent_Date),
                        "Number_of_claims": "" if pd.isna(r.Number_of_claims) else str(int(float(r.Number_of_claims))) if str(r.Number_of_claims).replace(".", "").isdigit() else str(r.Number_of_claims),
                        "Notes": "" if pd.isna(r.Notes) else str(r.Notes).strip()})
        else:
            row.update({c: "" for c in REG})
        row["index_names"] = "; ".join(index_names)
        row["cpr_hint"] = hints.get(k, "")
        row["entered_at"] = ""; row["image"] = ""
        rows.append(row)
    new = pd.DataFrame(rows)
    new["_o"] = new.QSECT.map(QS_ORDER); new = new.sort_values(["PTWP", "PSECT", "_o"]).drop(columns="_o")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{mer}_{sheet}.csv"
    if out.exists() and not a.fresh:
        old = pd.read_csv(out, dtype=str).fillna("")
        old = old[old.entered_at != ""]
        if len(old):
            kcols = KEY
            old["_k"] = old[kcols].astype(str).agg("|".join, axis=1); new["_k"] = new[kcols].astype(str).agg("|".join, axis=1)
            new = new[~new._k.isin(set(old._k))]
            new = pd.concat([new, old], ignore_index=True)
            new["_o"] = new.QSECT.map(QS_ORDER); new["PTWP"] = new.PTWP.astype(int); new["PSECT"] = new.PSECT.astype(int)
            new = new.sort_values(["PTWP", "PSECT", "_o"]).drop(columns=["_o", "_k"])
            print(f"kept {len(old)} rows already entered in the app")
    new.to_csv(out, index=False)
    print(f"wrote {out}  ({len(new)} quarters, {int((new.Type != '').sum())} already typed, {int((new.index_names != '').sum())} with index names, {int((new.cpr_hint != '').sum())} with CPR hints)")

if __name__ == "__main__":
    main()
