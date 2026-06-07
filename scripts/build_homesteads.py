#!/usr/bin/env python3
"""Extract Saskatchewan homestead records (W1/W2/W3 workbooks) and place them on
the calibrated open DLS grid (scripts/dls_grid.py).

This is WIP source data: ~485k quarter-section rows, ~256k populated, of which
~60k carry an entry date. Handles the known data issues:
  * date columns sometimes hold a name (misaligned) -> only true year values used
  * `Successful_Claims` may list several claimants (`;`) -> counted; when there is
    no date and >1 name the patentee is ambiguous (flagged)
  * institutional "claimants" (CPR, colonization railways, school districts) kept
    but not treated as homesteaders

Outputs (year axis = settlement year, see YEAR_MIN/MAX printed at end):
  docs/homesteads_qs.geojson      quarter-section polygons (-> tippecanoe pmtiles)
  docs/homesteads_townships.geojson  township centroids w/ cumulative-by-year counts
"""
import json
import re
import math
import datetime
import collections
from pathlib import Path

import pandas as pd

from dls_grid import GridModel, latt

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FILES = ["W1.xlsx", "W2.xlsx", "W3.xlsx"]
DATACOLS = ["Type", "FirstDate", "FirstDateSuccess", "Successful_Claims",
            "Failed_Claims", "Patent_Date", "Number_of_claims"]

YEAR_MIN, YEAR_MAX = 1870, 1935
NYEARS = YEAR_MAX - YEAR_MIN + 1

INSTITUTION = re.compile(r"railway|railroad|colonization|school district|church|"
                         r"hudson|pacific|government|crown|department", re.I)


def tenure_group(t):
    """Map a register `Type` to a tenure group for the map's blue ramp.
    H homestead · P pre-emption · S sale/grant · C Métis scrip · B Hudson's Bay
    · R railway (non-CPR) · K CPR (shown red) · O other/reserved · None unspecified."""
    if t is None:
        return None
    s = str(t).strip().lower()
    if not s or s == "nan":
        return None
    if "half" in s or "n.s.h.b" in s or "nshb" in s:
        return "C"
    if "hudson" in s:
        return "B"
    if "canadian pacific" in s or "cpr" in s or "c.p.r" in s:
        return "K"
    if "railway" in s or "railroad" in s or s in ("gnwory", "gtpry-r. of w"):
        return "R"
    if "pre-emption" in s or "preemption" in s:
        return "P"
    if any(w in s for w in ("homestead", "soldier", "military", "settlement",
                            "p.h", "pur. h", "p. h")):
        return "H"
    if any(w in s for w in ("forest", "reserve", "graz", "pasture", "past.", "lease",
                            "ranch", "vacant", "water", "easement", "permit",
                            "open for", "collateral", "cult")):
        return "O"
    if any(w in s for w in ("sale", "grant", "exchange", "assignment", "transfer",
                            "company", "quit claim")):
        return "S"
    return "O"


def year_of(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime.datetime, datetime.date)):
        y = v.year
    else:
        m = re.search(r"(18[6-9]\d|19[0-3]\d)", str(v))
        if not m:
            return None
        y = int(m.group(1))
    return y if YEAR_MIN <= y <= YEAR_MAX else None


def names(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return []
    return [p.strip() for p in re.split(r";", str(v)) if p.strip()]


def cumulative(counter):
    out, run = [], 0
    for i in range(NYEARS):
        run += counter.get(YEAR_MIN + i, 0)
        out.append(run)
    return out


def main():
    grid = GridModel()
    qs_features = []
    twp_count = collections.defaultdict(collections.Counter)
    twp_centroid = {}
    stats = collections.Counter()
    yhist = collections.Counter()

    for fn in FILES:
        xl = pd.ExcelFile(ROOT / fn)
        for sh in xl.sheet_names:
            df = pd.read_excel(ROOT / fn, sheet_name=sh)
            have = df[DATACOLS].notna().any(axis=1)
            for r in df[have].itertuples():
                qs = str(getattr(r, "QSECT", "")).strip().upper()
                if qs not in ("NE", "NW", "SE", "SW"):
                    stats["bad_qs"] += 1
                    continue
                try:
                    sec = int(r.PSECT); T = int(r.PTWP); R = int(r.PRGE); M = "W" + str(int(r.PMER))
                except (TypeError, ValueError):
                    stats["bad_key"] += 1
                    continue

                entry = year_of(r.FirstDate)
                success = year_of(r.FirstDateSuccess)
                patent = year_of(r.Patent_Date)
                my = entry or success or patent          # settlement year
                snames = names(r.Successful_Claims)
                fnames = names(r.Failed_Claims)
                nn = len(snames)

                if patent or success:
                    st = "P"   # patented / succeeded
                elif entry:
                    st = "E"   # entry filed, outcome/date unknown
                elif snames:
                    st = "U"   # claimed but undated
                else:
                    st = "F"   # only failed claims recorded
                stats[st] += 1

                claimant = snames[0] if snames else (fnames[0] if fnames else "")
                institutional = bool(snames and INSTITUTION.search(snames[0]))
                ambiguous = my is None and nn > 1        # unknown patentee

                # geometry from calibrated grid
                key = (T, R, M)
                if key not in grid.aff:
                    stats["affine_fallback"] += 1
                ring = grid.polygon(T, R, M, sec, qs)

                grp = tenure_group(r.Type)
                props = {"lld": f"{qs}-{sec:02d}-{T:03d}-{R:02d}-{M}", "st": st, "nn": nn}
                if grp:
                    props["grp"] = grp
                rawty = "" if (r.Type is None or (isinstance(r.Type, float) and math.isnan(r.Type))) else str(r.Type).strip()
                if rawty and rawty.lower() != "nan":
                    props["ty"] = rawty[:40]
                if my is not None:
                    props["y"] = my
                    yhist[my] += 1
                if patent:
                    props["py"] = patent
                if claimant:
                    props["nm"] = claimant[:60]
                if institutional:
                    props["inst"] = 1
                if ambiguous:
                    props["amb"] = 1
                qs_features.append({"type": "Feature",
                                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                                    "properties": props})

                # township aggregate (by settlement year)
                if my is not None:
                    twp_count[key][my] += 1
                if key not in twp_centroid:
                    c = grid.affine_for(T, R, M)
                    ctr = c["O"] + 6 * c["ex"] + 6 * c["ey"]   # township centre (u=v=6)
                    twp_centroid[key] = [round(float(ctr[0]), 5), round(float(ctr[1]), 5)]

    (DOCS / "homesteads_qs.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": qs_features}))
    print(f"Wrote homesteads_qs.geojson  ({len(qs_features):,} quarter sections)")

    twp_features = []
    for key, ctr in twp_centroid.items():
        cum = cumulative(twp_count[key])
        T, R, M = key
        twp_features.append({"type": "Feature",
                             "geometry": {"type": "Point", "coordinates": ctr},
                             "properties": {"twp": f"{T:03d}-{R:02d}-{M}",
                                            "total": cum[-1], "cum": cum}})
    (DOCS / "homesteads_townships.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": twp_features}))
    print(f"Wrote homesteads_townships.geojson  ({len(twp_features):,} townships)")

    ys = sorted(yhist)
    print("\nstatus:", dict(stats))
    print(f"settlement-year span: {ys[0]}–{ys[-1]}  (dated cells: {sum(yhist.values()):,})")
    print("by decade:", {d: sum(n for y, n in yhist.items() if y // 10 * 10 == d)
                         for d in range(1870, 1940, 10)})


if __name__ == "__main__":
    main()
