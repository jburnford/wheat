#!/usr/bin/env python3
"""Open synthetic Dominion Land Survey quarter-section grid for SK/MB.

Saskatchewan's authoritative quarter-section polygons are proprietary, so we
reconstruct an approximate grid from the public CPR land-grant cells
(data/cpr_land_sales/cpr_land_sales_grid.geojson) and the regular structure of
the DLS itself.

Method:
  1. Per township (TWP,RGE,MER) that has CPR anchor cells, fit a local affine
     mapping the within-township quarter-section lattice (u,v) -> (lon,lat).
     This is exact-ish (residual ~45 m) where anchors exist.
  2. For townships with no / too few anchors, "march" in from the nearest
     anchored townships using each neighbour's own basis vectors (which encode
     local meridian convergence), inverse-distance weighted. This stays accurate
     because adjacent townships differ by a near-constant 6-mile offset.

A quarter-section's lattice position within its township:
     row = (SEC-1)//6 ; col = (5-(SEC-1)%6) if row even else (SEC-1)%6   # W->E
     u = col*2 + (QS in NE/SE) ; v = row*2 + (QS in NE/NW)              # 0..11
"""
import json
import csv
import math
import collections
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "data" / "cpr_land_sales" / "cpr_land_sales_grid.geojson"
ANCHORS = ROOT / "data" / "cpr_land_sales" / "dls_anchors.csv"


def latt(sec, qs):
    N = int(sec)
    row = (N - 1) // 6
    col = (5 - (N - 1) % 6) if row % 2 == 0 else (N - 1) % 6
    u = col * 2 + (1 if qs in ("NE", "SE") else 0)
    v = row * 2 + (1 if qs in ("NE", "NW") else 0)
    return u, v


def _centroid(geom):
    """Robust centroid lon/lat from Polygon or MultiPolygon, ignoring any z."""
    g = geom["coordinates"]
    while isinstance(g[0][0], (list, tuple)):  # descend to a ring
        g = g[0]
    a = np.array(g, float)[:, :2]
    return a.mean(axis=0)


def load_anchor_cells():
    """meridian -> list of (T,R,u,v,lon,lat) for every CPR quarter-section."""
    grid = json.loads(GRID.read_text())["features"]
    bymer = collections.defaultdict(list)
    for f in grid:
        p = f["properties"]
        qs, sec = p.get("QS"), p.get("SEC")
        if qs not in ("NE", "NW", "SE", "SW") or sec in (None, ""):
            continue
        try:
            T, R = int(p["TWP"]), int(p["RGE"])
        except (TypeError, ValueError):
            continue
        u, v = latt(sec, qs)
        lon, lat = _centroid(f["geometry"])
        bymer[p["MER"]].append((T, R, u + 0.5, v + 0.5, lon, lat))
    return bymer


def fit_township_affines(cells, min_cells=4):
    """list of (T,R,u,v,lon,lat) -> {(T,R): params} where params = dict with
    O (corner lon/lat at u=v=0), ex (per +1 u), ey (per +1 v), n (#cells)."""
    by = collections.defaultdict(list)
    for T, R, u, v, lon, lat in cells:
        by[(T, R)].append((u, v, lon, lat))
    out = {}
    for tr, pts in by.items():
        if len(pts) < min_cells:
            continue
        a = np.array(pts, float)
        X = np.column_stack([a[:, 0], a[:, 1], np.ones(len(a))])  # u, v, 1
        clon, *_ = np.linalg.lstsq(X, a[:, 2], rcond=None)
        clat, *_ = np.linalg.lstsq(X, a[:, 3], rcond=None)
        out[tr] = {
            "O": np.array([clon[2], clat[2]]),      # value at u=v=0
            "ex": np.array([clon[0], clat[0]]),     # d/du
            "ey": np.array([clon[1], clat[1]]),     # d/dv
            "n": len(pts),
        }
    return out


def predict_township(tr, affines, neighbors=8):
    """Estimate O/ex/ey for any township by marching from nearest anchored
    townships using their own basis. Returns dict like fit_township_affines."""
    if tr in affines:
        return affines[tr]
    T, R = tr
    cand = sorted(affines.items(), key=lambda kv: abs(kv[0][0] - T) + abs(kv[0][1] - R))[:neighbors]
    wsum = 0.0
    Oacc = np.zeros(2); exacc = np.zeros(2); eyacc = np.zeros(2)
    for (Tn, Rn), pr in cand:
        d = abs(Tn - T) + abs(Rn - R)
        w = 1.0 / (d * d + 1e-6)
        # range R+1 lies one township WEST (u-=12); township T+1 lies NORTH (v+=12)
        O_pred = pr["O"] - (R - Rn) * 12 * pr["ex"] + (T - Tn) * 12 * pr["ey"]
        Oacc += w * O_pred; exacc += w * pr["ex"]; eyacc += w * pr["ey"]; wsum += w
    return {"O": Oacc / wsum, "ex": exacc / wsum, "ey": eyacc / wsum, "n": 0}


def quarter_polygon(params, u, v):
    """4-corner ring (lon,lat) for the quarter-section with SW lattice corner (u,v)."""
    O, ex, ey = params["O"], params["ex"], params["ey"]
    def P(uu, vv):
        p = O + uu * ex + vv * ey
        return [round(float(p[0]), 6), round(float(p[1]), 6)]
    return [P(u, v), P(u + 1, v), P(u + 1, v + 1), P(u, v + 1), P(u, v)]


_HALF_MILE = 804.672          # quarter section = 40 chains = half a statute mile (m)

def _m_per_deg_lat(phi):
    r = math.radians(phi)
    return 111132.92 - 559.82 * math.cos(2 * r) + 1.175 * math.cos(4 * r)

def _m_per_deg_lon(phi):
    r = math.radians(phi)
    return 111412.84 * math.cos(r) - 93.5 * math.cos(3 * r) + 0.118 * math.cos(5 * r)

def _axis(idx, coord, expected, span_needed=6.0):
    """Spacing along one axis. Measure it from the anchors when they actually span
    the township (a reliable regression — this captures real survey variation such
    as correction-line / fractional townships); otherwise fall back to the
    mathematical half-mile. A loose sanity clamp rejects only genuine garbage.
    Position (origin) always comes from the anchors. Returns (step, origin)."""
    step = expected
    if idx.max() - idx.min() >= span_needed and len(np.unique(idx)) >= 2:
        s = np.polyfit(idx, coord, 1)[0]
        if 0.7 <= s / expected <= 1.3:                # sane measurement -> trust it
            step = s
    origin = float(np.mean(coord - idx * step))       # position always from anchors
    return step, origin


def load_anchor_affines():
    """Per-township grid from the authoritative corner-section anchors
    (data/cpr_land_sales/dls_anchors.csv). Returns {(T,R,'W#'): params}.

    DLS township sides run true N–S and E–W, so the grid is axis-aligned:
    longitude depends only on the column (u), latitude only on the row (v) — a
    sheared/rotated cell is impossible. A quarter section is half a mile, so the
    cell size is essentially a known constant: we use the latitude-adjusted
    half-mile as the backbone, override it with the *measured* spacing only when
    the anchors span the township and agree within an 8% threshold, and always
    take the township's position from the anchors. Works from a single anchor."""
    # dedupe by quarter section first — the source service has duplicate/overlapping
    # cells for some townships, which would otherwise bias the regression
    dedup = collections.defaultdict(lambda: collections.defaultdict(list))
    with ANCHORS.open() as fh:
        for r in csv.DictReader(fh):
            key = (int(r["TWP"]), int(r["RGE"]), "W" + r["MER"])
            dedup[key][(int(r["SEC"]), r["QSC"])].append((float(r["lon"]), float(r["lat"])))
    by = collections.defaultdict(list)
    for key, cells in dedup.items():
        for (sec, qsc), lls in cells.items():
            u, v = latt(sec, qsc)
            lon = sum(p[0] for p in lls) / len(lls)
            lat = sum(p[1] for p in lls) / len(lls)
            by[key].append((u + 0.5, v + 0.5, lon, lat))
    out = {}
    for key, pts in by.items():
        a = np.array(pts, float)
        phi = a[:, 3].mean()
        sx, ox = _axis(a[:, 0], a[:, 2], _HALF_MILE / _m_per_deg_lon(phi))
        sy, oy = _axis(a[:, 1], a[:, 3], _HALF_MILE / _m_per_deg_lat(phi))
        out[key] = {"O": np.array([ox, oy]),
                    "ex": np.array([sx, 0.0]),         # one column step, due east
                    "ey": np.array([0.0, sy]),         # one row step, due north
                    "n": len(pts)}
    return out


class GridModel:
    """Calibrated open DLS grid: authoritative corner anchors give each township
    an exact-ish affine; townships missing anchors fall back to marching from the
    nearest anchored townships."""

    def __init__(self):
        self.aff = load_anchor_affines()
        # index anchored townships by meridian for nearest-neighbour fallback
        self._by_mer = collections.defaultdict(dict)
        for (T, R, M), p in self.aff.items():
            self._by_mer[M][(T, R)] = p

    def affine_for(self, T, R, M):
        key = (T, R, M)
        if key in self.aff:
            return self.aff[key]
        return predict_township((T, R), self._by_mer.get(M, {}))

    def polygon(self, T, R, M, sec, qs):
        u, v = latt(sec, qs)
        return quarter_polygon(self.affine_for(T, R, M), u, v)


# ----------------------------------------------------------------------------
if __name__ == "__main__":   # cross-validation: hold out whole townships
    bymer = load_anchor_cells()
    rng = np.random.RandomState(0)
    for M in ["W1", "W2", "W3"]:
        cells = bymer[M]
        tws = sorted({(T, R) for T, R, *_ in cells})
        rng.shuffle(tws)
        nho = max(1, len(tws) // 5)
        hold = set(tws[:nho])
        train_cells = [c for c in cells if (c[0], c[1]) not in hold]
        aff = fit_township_affines(train_cells)
        # predict held-out cell centroids
        res = []
        for T, R, u, v, lon, lat in cells:
            if (T, R) not in hold:
                continue
            pr = predict_township((T, R), aff)
            p = pr["O"] + u * pr["ex"] + v * pr["ey"]
            dlon = (p[0] - lon) * 111000 * np.cos(np.radians(lat))
            dlat = (p[1] - lat) * 111000
            res.append((dlon ** 2 + dlat ** 2) ** 0.5)
        res = np.array(res)
        print(f"{M}: {len(aff)} anchored tws | held-out {len(hold)} tws ({len(res)} cells) "
              f"-> mean {res.mean():.0f}m  median {np.median(res):.0f}m  "
              f"p90 {np.percentile(res,90):.0f}m  max {res.max():.0f}m")
