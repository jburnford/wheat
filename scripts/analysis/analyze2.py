import warnings, re
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_columns", 30)
from pathlib import Path
S = str(Path(__file__).resolve().parents[2] / "data" / "homesteads" / "analysis")
d = pd.read_parquet(f"{S}/homesteads_flat2.parquet")
d["decade"] = d.year // 10 * 10
H = d[d.grp == "H"]
print("== a. HOMESTEAD (H) entry->patent lag ==")
l = H[H.entry.notna() & H.patent.notna()].copy(); l["lag"] = l.patent - l.entry; l = l[l.lag >= 0]
print("n", len(l), " lag==0:", (l.lag == 0).sum(), f"({(l.lag==0).mean()*100:.1f}%)", " entry==success==patent:",
      ((l.entry == l.success) & (l.success == l.patent)).sum())
l["cohort"] = l.entry // 5 * 5
print(l.groupby("cohort").lag.agg(n="size", median="median", mean="mean", p0=lambda s: (s == 0).mean() * 100,
                                  p3_5=lambda s: s.between(3, 5).mean() * 100, ge6=lambda s: (s >= 6).mean() * 100, ge10=lambda s: (s >= 10).mean() * 100).round(1))
lz = l[l.lag > 0]
print("excluding lag 0:"); print(lz.groupby("cohort").lag.agg(n="size", median="median", mean="mean").round(1))
print("H lag by meridian (lag>0):"); print(lz.groupby("mer").lag.agg(["size", "median", "mean"]).round(1))

print("\n== b. METIS SCRIP (C) ==")
C = d[d.grp == "C"]
print(C.type_raw.value_counts())
print("by meridian:", C.mer.value_counts().to_dict())
print("by year:"); print(C.year.dropna().astype(int).value_counts().sort_index().to_string())
C2 = C.assign(key=C.twp.astype(str) + "-" + C.rge.astype(str) + "-W" + C.mer.astype(str))
print("top townships:"); print(C2.key.value_counts().head(15))
print("townships with any scrip:", C2.key.nunique())
print("scrip: lag entry->patent"); cl = C[C.entry.notna() & C.patent.notna()]; print((cl.patent - cl.entry).describe().round(1))
print("scrip names sample:"); print(C.first_name.value_counts().head(10))
print("scrip churn:", round(C.churn.mean() * 100, 1), "% ; n_success>1:", (C.n_success > 1).sum())

print("\n== c. CORPORATE / FINANCIER / STATE HOLDINGS ==")
nm = d.first_name.str.strip().str.upper()
corp = nm.str.contains(r"COMPANY|CORPORATION|TRUST|LIMITED|\bLTD\b|\bCO\b|SYNDICATE|BANK|INVESTMENT|MORTGAGE|LOAN|COLONIZATION|SOCIETY|BOARD", regex=True)
state = nm.str.contains(r"FOREST|PARK|RESERVE|DEPARTMENT|GOVERNMENT|PROVINCE|DOMINION|CROWN|MINISTER|CHIEF ", regex=True)
rail = nm.str.contains(r"RAILWAY|RAILROAD", regex=True)
hbc = nm.str.contains(r"HUDSON", regex=True)
d["holder"] = np.select([rail, hbc, corp & ~rail, state], ["railway", "HBC", "company/trust", "state/forest/reserve"], "individual")
d.loc[d.first_name == "", "holder"] = "(unnamed)"
print(d.holder.value_counts())
print("quarters by holder class, dated share and median year:")
print(d.groupby("holder").agg(n=("year", "size"), dated=("year", "count"), med_year=("year", "median")))
cc = d[d.holder == "company/trust"]
print("\ncompanies/trusts: distinct names", cc.first_name.nunique(), " quarters", len(cc), " acres ~", len(cc) * 160)
print(cc.first_name.str.upper().value_counts().head(25))
print("company/trust acquisitions by year:"); print(cc.year.dropna().astype(int).value_counts().sort_index().to_string())
print("company by meridian:", cc.mer.value_counts().to_dict())
print("company rows by grp:", cc.grp.fillna("-").value_counts().to_dict())
# individuals with many quarters
ind = d[d.holder == "individual"]
vc = ind.first_name.str.upper().str.strip().value_counts()
print("\nindividual names on >=4 quarters:", (vc >= 4).sum(), " on >=10:", (vc >= 10).sum())
print(vc.head(25))
print("individuals: share of quarters held by names on 1 quarter:", round(vc[vc == 1].sum() / vc.sum() * 100, 1), "%; on 2:", round(vc[vc == 2].sum() / vc.sum() * 100, 1), "%; 3+:", round(vc[vc >= 3].sum() / vc.sum() * 100, 1), "%")

print("\n== d. PRE-EMPTION / PURCHASED HOMESTEAD ==")
P = d[d.grp == "P"]
print("by meridian:", P.mer.value_counts().to_dict())
print("by year:"); print(P.year.dropna().astype(int).value_counts().sort_index().to_string())
print("P by township band:"); print(pd.cut(P.twp, [0, 10, 20, 30, 40, 60]).value_counts().sort_index())
print("purchased homestead raw types:"); print(d[d.type_raw.str.contains("Pur|P\\.H|P\\. H", regex=True)].type_raw.value_counts())

print("\n== e. FAILED CLAIMANTS ==")
print("total failed-claim name entries:", int(d.n_failed.sum()), " quarters with >=1 failed:", (d.n_failed > 0).sum(),
      " successful-name entries:", int(d.n_success.sum()))
print("failed per quarter distribution:"); print(d.n_failed.clip(upper=5).value_counts().sort_index())
print("H quarters: failed>=1", round((H.n_failed > 0).mean() * 100, 1), "% ; failed>=2", round((H.n_failed >= 2).mean() * 100, 1), "%")
print("failed rate by meridian (H):"); print(H.groupby("mer").n_failed.apply(lambda s: round((s > 0).mean() * 100, 1)))
print("failed rate by band (H):"); print(H.groupby(pd.cut(H.twp, [0, 10, 20, 30, 40, 50, 60])).n_failed.apply(lambda s: round((s > 0).mean() * 100, 1)))
print("failed rate (H) by decade of first entry:"); print(H.groupby("decade").n_failed.apply(lambda s: round((s > 0).mean() * 100, 1)))

print("\n== f. SOLDIER / MILITARY ==")
sol = d[d.type_raw.str.contains("Soldier|Military|South African|Volunteer", regex=True) | d.first_name.str.upper().str.contains("SOLDIER SETTLEMENT")]
print(sol.type_raw.value_counts()); print("by year:"); print(sol.year.dropna().astype(int).value_counts().sort_index().to_string())
print("by meridian:", sol.mer.value_counts().to_dict())

print("\n== g. TOWNSHIP FILL SPEED (even sections, >=40 dated) ==")
ev = d[(~d.odd) & d.year.notna()]
g = ev.groupby(["twp", "rge", "mer"]).year.agg(n="size", first="min", p10=lambda s: s.quantile(.1), p50="median", p90=lambda s: s.quantile(.9))
g = g[g.n >= 40]; g["span"] = g.p90 - g.p10
print("townships:", len(g)); print(g.span.describe().round(1))
g["first_dec"] = (g.p10 // 10 * 10).astype(int)
print(g.groupby("first_dec").span.agg(["size", "median", "mean"]).round(1))
print("share filled (p10->p90) within 2 yrs:", round((g.span <= 2).mean() * 100, 1), "% ; within 5:", round((g.span <= 5).mean() * 100, 1), "%")

print("\n== h. NOTES sample ==")
n = d[d.notes.str.strip().ne("") & d.notes.str.lower().ne("nan")]
print("rows with notes:", len(n))
print(n.notes.str.lower().str.extract(r"(cancel|abandon|forfeit|homestead|patent|scrip|reserve|surrender|transfer|assign|sold|sale|lease|death|died|widow|minor|company)")[0].value_counts())
for s in n.notes.sample(25, random_state=1): print("  -", s[:120])
d.to_parquet(f"{S}/homesteads_flat3.parquet")
