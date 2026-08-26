"""CPR land-sales catalogue: type / timing / geography of the odd-section half of
the checkerboard, and its relation to the homestead registers (SK only for the
join). Reads the geocoded point layer (one row per quarter section) for SK and
the flat catalogue CSV for prairie-wide totals. Writes
data/homesteads/analysis/cpr_sk.parquet and prints the tables used in
docs/analysis/register_to_freehold.html."""
from pathlib import Path
import json, re, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
pd.set_option("display.width", 220, "display.max_rows", 200, "display.max_columns", 30)

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "data" / "homesteads" / "analysis"; A.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- load points
pts = json.load(open(ROOT / "data" / "cpr_land_sales" / "cpr_land_sales_points.geojson"))
rows = []
for f in pts["features"]:
    p = f["properties"]; g = f["geometry"]
    rows.append(dict(contract=p.get("ContractNumber"), lld=p.get("LLD"), date=p.get("Date"), purchaser=p.get("Purchaser") or "",
                     mer=p.get("MER"), acres=p.get("Acres"), price=p.get("Price"), status=p.get("Status") or "",
                     twp=p.get("TWP"), rge=p.get("RGE"), sec=p.get("SEC"), qs=p.get("QS"), volume=p.get("Volume"), prov=p.get("Province"),
                     lon=g["coordinates"][0] if g else np.nan, lat=g["coordinates"][1] if g else np.nan))
c = pd.DataFrame(rows)
c["year"] = c.date.astype(str).str.extract(r"(\d{4})")[0].astype(float)
c["price"] = pd.to_numeric(c.price, errors="coerce"); c.loc[(c.price <= 0) | (c.price > 100), "price"] = np.nan
c["acres"] = pd.to_numeric(c.acres, errors="coerce")
for k in ("twp", "rge", "sec"): c[k] = pd.to_numeric(c[k], errors="coerce")
c["prov"] = c.prov.fillna(c.mer.map({"E1": "MB", "W1": "MB", "W2": "SK", "W3": "SK", "W4": "AB", "W5": "AB"}))
# SK W1 ranges 30+ are Saskatchewan (the point layer's Province field handles this where set)
print("points:", len(c), " by province:", c.prov.value_counts().to_dict())

# ---------------------------------------------------------------- classify
def status_class(s):
    s = s.upper()
    if re.search(r"CANCEL|NULL AND VOID|DEFAULT|FORFEIT|VOID", s): return "cancelled/defaulted"
    if "PAID IN FULL" in s: return "paid in full"
    if "ASSIGNED" in s or "TRANSFERRED" in s: return "assigned"
    if "UNCERTAIN" in s: return "uncertain"
    if not s.strip(): return "blank"
    return "other"
c["outcome"] = c.status.map(status_class)
c["assigned"] = c.status.str.upper().str.contains("ASSIGN")
c["joint"] = c.status.str.upper().str.contains("JOINT") | c.purchaser.str.contains(r"\|")

CORP = re.compile(r"\b(CO\.?|COMPANY|CORP|LTD|LIMITED|TRUST|BANK|SYNDICATE|SOCIETY|ASSOCIATION|COLONIZATION|LAND CO|INVESTMENT|MORTGAGE|LOAN|SOCIETE|ESTATE|CHURCH|MISSION|SCHOOL|MUNICIPALITY|RURAL MUNICIPALITY|VILLAGE|TOWN OF|CITY OF)\b", re.I)
RAIL = re.compile(r"RAILWAY|RAILROAD", re.I)
CROWN = re.compile(r"THE CROWN|HIS MAJESTY|HER MAJESTY|THE KING|DOMINION GOVERNMENT|GOVERNMENT OF|MINISTER OF|SOLDIER SETTLEMENT|DEPARTMENT OF", re.I)
US_STATES = r"IOWA|IA\.?|MINN\.?|MINNESOTA|N\.? ?DAK|NORTH DAKOTA|S\.? ?DAK|SOUTH DAKOTA|NEB\.?|NEBRASKA|ILL\.?|ILLINOIS|WIS\.?|WISCONSIN|MICH\.?|MICHIGAN|KAN\.?|KANSAS|MO\.?|MISSOURI|IND\.?|INDIANA|OHIO|N\.? ?Y\.?|MONT\.?|MONTANA|WASH\.?|WASHINGTON|ORE\.?|OREGON|CAL\.?|CALIFORNIA|COLO\.?|COLORADO|IDAHO|TEX\.?|TEXAS|OKLA\.?|U\.? ?S\.? ?A\.?|PENN\.?|PA\.?|MASS\.?|CONN\.?|VT\.?|MAINE|N\.? ?J\.?|MD\.?|VA\.?|KY\.?|TENN\.?|GA\.?|ARK\.?|WYO\.?|UTAH|NEVADA|ARIZ\.?|LA\.?|ALA\.?|MISS\.?|W\.? ?VA\.?|N\.? ?C\.?|S\.? ?C\.?|FLA\.?|DEL\.?|R\.? ?I\.?|N\.? ?H\.?|D\.? ?C\.?"
def residence(name):
    n = name.upper()
    if re.search(r",\s*(" + US_STATES + r")\s*$|,\s*(" + US_STATES + r")\s*\|", n): return "USA"
    if re.search(r",\s*(ONT\.?|ONTARIO|QUE\.?|QUEBEC|N\.? ?S\.?|NOVA SCOTIA|N\.? ?B\.?|NEW BRUNSWICK|P\.? ?E\.? ?I\.?|B\.? ?C\.?|BRITISH COLUMBIA)\s*($|\|)", n): return "Eastern Canada / BC"
    if re.search(r",\s*(MAN\.?|MANITOBA|SASK\.?|SASKATCHEWAN|ALTA\.?|ALBERTA|N\.? ?W\.? ?T\.?|ASSA\.?|ASSINIBOIA)\s*($|\|)", n): return "Prairie"
    if re.search(r",\s*(ENG\.?|ENGLAND|SCOT\.?|SCOTLAND|IRELAND|WALES|LONDON|GLASGOW|EDINBURGH|BELGIUM|HOLLAND|NETHERLANDS|FRANCE|GERMANY|BRUSSELS|PARIS|ANTWERP)\s*($|\|)", n): return "Britain / Europe"
    if re.search(r",\s*[A-Z][A-Z .'-]+,\s*[A-Z. ]{2,12}\s*($|\|)", n): return "other stated"
    return "not stated"
def ptype(name):
    if CROWN.search(name): return "Crown / government"
    if RAIL.search(name): return "railway company"
    if CORP.search(name): return "company / trust"
    return "individual(s)"
c["ptype"] = c.purchaser.map(ptype)
c["residence"] = c.purchaser.map(residence)
def norm_name(name):
    """First named person, as SURNAME, GIVEN with address and honorifics stripped."""
    first = name.split("|")[0].upper()
    first = re.sub(r"\b(MRS|MR|DR|REV|HON|ESQ|JR|SR)\.?\b", "", first)
    parts = [p.strip() for p in first.split(",") if p.strip()]
    if len(parts) >= 2: return f"{parts[0]}, {parts[1]}".strip()
    return parts[0] if parts else ""
c["nkey"] = c.purchaser.map(norm_name)
c["contract_acres"] = c.groupby("contract").acres.transform("first")
c.to_parquet(A / "cpr_sk.parquet")

sk = c[c.prov == "SK"].copy()
print("SK quarter-section sale points:", len(sk), " contracts:", sk.contract.nunique(), " dated:", sk.year.notna().sum(), " priced:", sk.price.notna().sum())
print("SK acres (sum of per-contract acres, deduped):", int(sk.drop_duplicates("contract").acres.sum()))

print("\n== A. WHEN AND FOR HOW MUCH (SK) ==")
sk["y"] = sk.year
t = sk.groupby("y").agg(quarters=("lld", "size"), contracts=("contract", "nunique"), med_price=("price", "median"), q1=("price", lambda s: s.quantile(.25)), q3=("price", lambda s: s.quantile(.75)))
print(t.round(2).to_string())
sk["period"] = pd.cut(sk.year, [1880, 1890, 1896, 1900, 1904, 1908, 1912, 1930], labels=["1881-90", "1891-96", "1897-1900", "1901-04", "1905-08", "1909-12", "1913-27"])
print("\nby period: quarters, median $/ac, acres/contract median, share block sales (contract >= 1,000 ac)")
print(sk.groupby("period").agg(quarters=("lld", "size"), med_price=("price", "median"), med_contract_ac=("contract_acres", "median"),
                                block=("contract_acres", lambda s: round((s >= 1000).mean() * 100, 1))).round(2))
print("\nmedian $/ac by meridian x period:"); print(sk.pivot_table(index="period", columns="mer", values="price", aggfunc="median").round(2))

print("\n== B. WHO BOUGHT (SK) ==")
print(pd.crosstab(sk.ptype, sk.period, margins=True))
print("\nshare of quarters by purchaser type per period (%):"); ct = pd.crosstab(sk.period, sk.ptype); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\nresidence (individuals only):"); ind = sk[sk.ptype == "individual(s)"]
ct = pd.crosstab(ind.period, ind.residence); print(ct); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\nresidence share among individuals with a stated residence, by period (%):")
st = ind[ind.residence != "not stated"]; ct = pd.crosstab(st.period, st.residence); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\nCrown / government purchases by year:"); print(sk[sk.ptype == "Crown / government"].year.dropna().astype(int).value_counts().sort_index().to_string())
print("Crown purchaser strings:"); print(sk[sk.ptype == "Crown / government"].purchaser.value_counts().head(8))
print("\ntop purchasers by quarters (SK):"); print(sk.nkey.value_counts().head(25))
acres = sk.groupby("nkey").agg(q=("lld", "size"), ac=("acres", "sum"), type=("ptype", "first")).sort_values("q", ascending=False)
print("distinct purchasers:", len(acres), " quarters held by top 1%:", round(acres.q.head(max(1, len(acres) // 100)).sum() / acres.q.sum() * 100, 1), "% ; top 10%:", round(acres.q.head(len(acres) // 10).sum() / acres.q.sum() * 100, 1), "%")
print("purchasers buying 1 quarter:", round((acres.q == 1).mean() * 100, 1), "% of purchasers, holding", round(acres.q[acres.q == 1].sum() / acres.q.sum() * 100, 1), "% of quarters; 2 quarters:", round(acres.q[acres.q == 2].sum() / acres.q.sum() * 100, 1), "%; 3-7:", round(acres.q[(acres.q >= 3) & (acres.q <= 7)].sum() / acres.q.sum() * 100, 1), "%; 8+:", round(acres.q[acres.q >= 8].sum() / acres.q.sum() * 100, 1), "%")
print("\nblock contracts >= 5,000 acres (SK):"); big = sk.drop_duplicates("contract"); big = big[big.contract_acres >= 5000][["year", "purchaser", "contract_acres", "price", "outcome"]].sort_values("contract_acres", ascending=False); print(big.head(20).to_string())

print("\n== C. OUTCOMES (SK) ==")
print(sk.outcome.value_counts()); print((sk.outcome.value_counts(normalize=True) * 100).round(1))
print("\noutcome by period (%):"); ct = pd.crosstab(sk.period, sk.outcome); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\noutcome by purchaser type (%):"); ct = pd.crosstab(sk.ptype, sk.outcome); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("\noutcome by residence, individuals (%):"); ct = pd.crosstab(ind.residence, ind.outcome); print((ct.div(ct.sum(1), axis=0) * 100).round(1))
print("assigned share:", round(sk.assigned.mean() * 100, 1), "% ; joint purchases:", round(sk.joint.mean() * 100, 1), "%")
print("cancelled/defaulted by year of sale (%):"); print(sk.groupby("y").outcome.apply(lambda s: round((s == "cancelled/defaulted").mean() * 100, 1)).to_string())

print("\n== D. GEOGRAPHY (SK) ==")
sk["band"] = pd.cut(sk.twp, [0, 10, 20, 30, 40, 50, 60], labels=["T1-10", "T11-20", "T21-30", "T31-40", "T41-50", "T51-56"])
print(sk.groupby("band").agg(quarters=("lld", "size"), med_year=("year", "median"), med_price=("price", "median"), cancelled=("outcome", lambda s: round((s == "cancelled/defaulted").mean() * 100, 1)), usa=("residence", lambda s: round((s == "USA").mean() * 100, 1))).round(2))
print("by meridian:"); print(sk.groupby("mer").agg(quarters=("lld", "size"), med_year=("year", "median"), med_price=("price", "median"), cancelled=("outcome", lambda s: round((s == "cancelled/defaulted").mean() * 100, 1))).round(2))

print("\n== E. LINK TO HOMESTEADS (SK townships) ==")
h = pd.read_parquet(A / "homesteads_flat3.parquet")
h["key"] = h.apply(lambda r: f"{int(r.twp)}-{int(r.rge)}-W{int(r.mer)}", axis=1)
sk["key"] = sk.apply(lambda r: f"{int(r.twp)}-{int(r.rge)}-{r.mer}" if pd.notna(r.twp) and pd.notna(r.rge) else None, axis=1)
hd = h[h.year.notna() & (~h.odd)]
ht = hd.groupby("key").agg(hs_n=("year", "size"), hs_first=("year", "min"), hs_med=("year", "median"),
                            hs_fail=("n_failed", lambda s: (s > 0).mean()), rail_yr=("rail_yr", "first"))
ct = sk[sk.year.notna()].groupby("key").agg(cpr_n=("lld", "size"), cpr_first=("year", "min"), cpr_med=("year", "median"), cpr_price=("price", "median"),
                                             cpr_cancel=("outcome", lambda s: (s == "cancelled/defaulted").mean()), usa=("residence", lambda s: (s == "USA").mean()))
j = ht.join(ct, how="inner"); j = j[(j.hs_n >= 10) & (j.cpr_n >= 5)]
print("townships with >=10 dated homesteads and >=5 dated CPR sales:", len(j))
j["gap"] = j.cpr_med - j.hs_med
print("CPR median sale year - homestead median entry year:"); print(j.gap.describe().round(1))
print("share townships where CPR median sale is >= 2 yrs after homestead median:", round((j.gap >= 2).mean() * 100, 1), "% ; <= -2:", round((j.gap <= -2).mean() * 100, 1), "%")
j["hs_dec"] = (j.hs_med // 10 * 10).astype(int)
print("\nby decade of homestead median: CPR price, CPR-homestead gap, CPR cancel rate, homestead fail rate")
print(j.groupby("hs_dec").agg(n=("gap", "size"), cpr_price=("cpr_price", "median"), gap=("gap", "median"), cpr_cancel=("cpr_cancel", "mean"), hs_fail=("hs_fail", "mean")).round(2))
print("\ncorrelations (township level):")
print(j[["cpr_price", "hs_med", "cpr_med", "gap", "hs_fail", "cpr_cancel", "usa"]].corr(method="spearman").round(2))
# price vs rail
j["rail_rel"] = j.cpr_med - j.rail_yr.where(j.rail_yr < 9999)
j["railband"] = pd.cut(j.rail_rel, [-99, -5, -1, 1, 5, 99], labels=["sold 5+ yrs before rail", "1-5 before", "around arrival", "1-5 after", "5+ after"])
print("\nCPR median price by timing of sale vs rail arrival (township):"); print(j.groupby("railband").cpr_price.agg(["median", "size"]).round(2))

# ---- name linkage: CPR purchasers who were also homestead claimants nearby
hn = h[(h.first_name != "") & (~h.inst)].copy()
hn["nkey"] = hn.first_name.str.upper().str.replace(r"\s+", " ", regex=True).str.strip()
hn["nkey"] = hn.nkey.str.replace(r"^([^,]+),\s*([^,]+).*$", r"\1, \2", regex=True)
hn = hn[hn.nkey.str.contains(",")]
def initials_key(k):
    m = re.match(r"^([^,]+),\s*(\S+)", k)
    return f"{m.group(1)}, {m.group(2)[0]}" if m else k
hn["ikey"] = hn.nkey.map(initials_key); sk["ikey"] = sk.nkey.map(initials_key)
ind_sk = sk[(sk.ptype == "individual(s)") & sk.nkey.str.contains(",")].copy()
# same township, exact name
hset = hn.groupby("key").nkey.apply(set).to_dict()
hset_i = hn.groupby("key").ikey.apply(set).to_dict()
def neighbours(key):
    m = re.match(r"(\d+)-(\d+)-(W\d)", key or "")
    if not m: return []
    t, r, w = int(m.group(1)), int(m.group(2)), m.group(3)
    return [f"{t+dt}-{r+dr}-{w}" for dt in (-1, 0, 1) for dr in (-1, 0, 1)]
ind_sk["match_same"] = [ (k in hset and n in hset[k]) for k, n in zip(ind_sk.key, ind_sk.nkey)]
ind_sk["match_nbr"] = [ any(n in hset.get(kk, ()) for kk in neighbours(k)) for k, n in zip(ind_sk.key, ind_sk.nkey)]
ind_sk["match_nbr_init"] = [ any(i in hset_i.get(kk, ()) for kk in neighbours(k)) for k, i in zip(ind_sk.key, ind_sk.ikey)]
print("\nNAME LINKAGE (SK individual purchasers, n=%d quarters):" % len(ind_sk))
print("  purchaser also a homestead claimant in the same township (exact 'SURNAME, GIVEN'):", round(ind_sk.match_same.mean() * 100, 1), "%")
print("  ... in same or 8 neighbouring townships:", round(ind_sk.match_nbr.mean() * 100, 1), "%")
print("  ... neighbouring, surname + first initial:", round(ind_sk.match_nbr_init.mean() * 100, 1), "%")
print("  (caveat: homestead registers only 58% transcribed, so these are floors)")
ind_sk["period"] = pd.cut(ind_sk.year, [1880, 1890, 1896, 1900, 1904, 1908, 1912, 1930], labels=["1881-90", "1891-96", "1897-1900", "1901-04", "1905-08", "1909-12", "1913-27"])
print("\nneighbour-match rate by period:"); print(ind_sk.groupby("period").match_nbr.agg(["mean", "size"]).round(3))
print("neighbour-match rate by residence:"); print(ind_sk.groupby("residence").match_nbr.agg(["mean", "size"]).round(3))
print("outcome by matched vs not:"); print(pd.crosstab(ind_sk.match_nbr, ind_sk.outcome, normalize="index").round(3) * 100)
# timing: matched purchasers — homestead entry year vs CPR purchase year
hm = hn[["key", "nkey", "year", "patent"]].dropna(subset=["year"])
mm = ind_sk[ind_sk.match_nbr & ind_sk.year.notna()].merge(hm, on="nkey", suffixes=("", "_hs"))
mm = mm[[k in neighbours(kk) for k, kk in zip(mm.key_hs, mm.key)]]
mm["d"] = mm.year - mm.year_hs
print("\nmatched pairs (n=%d): CPR purchase year - homestead entry year" % len(mm)); print(mm.d.describe().round(1))
print("  bought before entry:", round((mm.d < 0).mean() * 100, 1), "% ; same year:", round((mm.d == 0).mean() * 100, 1), "% ; 1-3 yrs after:", round(mm.d.between(1, 3).mean() * 100, 1), "% ; 4+ after:", round((mm.d >= 4).mean() * 100, 1), "%")
mm2 = mm[mm.patent.notna()]; mm2["dp"] = mm2.year - mm2.patent
print("  relative to patent (n=%d): before patent %.1f%%, same year %.1f%%, after %.1f%%" % (len(mm2), (mm2.dp < 0).mean() * 100, (mm2.dp == 0).mean() * 100, (mm2.dp > 0).mean() * 100))
sk.to_parquet(A / "cpr_sk.parquet")
# chart extract
out = {
  "price": {"year": t.index.astype(int).tolist(), "med": t.med_price.round(2).fillna(0).tolist(), "q1": t.q1.round(2).fillna(0).tolist(), "q3": t.q3.round(2).fillna(0).tolist(), "quarters": t.quarters.tolist()},
  "ptype": {"period": [str(p) for p in ct.index] if False else [str(p) for p in pd.crosstab(sk.period, sk.ptype).index], "series": list(pd.crosstab(sk.period, sk.ptype).columns), "counts": {col: pd.crosstab(sk.period, sk.ptype)[col].tolist() for col in pd.crosstab(sk.period, sk.ptype).columns}},
  "residence": {"period": [str(p) for p in pd.crosstab(st.period, st.residence).index], "series": list(pd.crosstab(st.period, st.residence).columns), "counts": {col: pd.crosstab(st.period, st.residence)[col].tolist() for col in pd.crosstab(st.period, st.residence).columns}},
  "outcome": {"period": [str(p) for p in pd.crosstab(sk.period, sk.outcome).index], "series": list(pd.crosstab(sk.period, sk.outcome).columns), "counts": {col: pd.crosstab(sk.period, sk.outcome)[col].tolist() for col in pd.crosstab(sk.period, sk.outcome).columns}},
  "match": {"period": [str(p) for p in ind_sk.groupby("period").match_nbr.mean().index], "rate": (ind_sk.groupby("period").match_nbr.mean() * 100).round(1).tolist(), "n": ind_sk.groupby("period").match_nbr.size().tolist()},
}
json.dump(out, open(Path(__file__).parent / "chart_data_cpr.json", "w"), ensure_ascii=False)
print("\nwrote chart_data_cpr.json")
