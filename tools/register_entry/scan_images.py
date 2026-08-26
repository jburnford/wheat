#!/usr/bin/env python3
"""Build data/register/images.csv — the map from meridian / range / township to
page images on the shared drive.

    python tools/register_entry/scan_images.py "G:\\HGIS LAB\\Saskatchewan Archives\\Township General Register"
    python tools/register_entry/scan_images.py --from-list files.tsv     # from a "relative-path<TAB>size" listing

Expected layout (as on the HGIS Lab share):
    W3\\Range 14\\Township 35\\R14 - T35 - (6).jpg
    W1\\Range 30\\Township 38\\R30 - T38 - 6.JPG
    W2\\Range 21A\\...                       (ranges with a letter suffix are kept as e.g. 21A)
    W1\\Range 30\\Townships 57-76 (does not exist)\\Township 67\\...   (kept, flagged; not in the registers)

Columns: mer, rge, twp_from, twp_to, page, path, ext, viewable (0 for HEIC —
browsers cannot show HEIC; convert those folders to JPG). Standard library only.
"""
import argparse, csv, re, sys
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]; OUT = ROOT / "data" / "register" / "images.csv"
IMG = {".jpg": 1, ".jpeg": 1, ".png": 1, ".tif": 0, ".tiff": 0, ".heic": 0, ".pdf": 0}
RANGE = re.compile(r"^range\s*0*(\d+)([a-z]?)$", re.I)
TWP = re.compile(r"^township\s*0*(\d+)", re.I)
PAGE = re.compile(r"(\d+)\s*([A-Za-z])?\s*\)?\s*$")   # "6", "(6)", "12A" (supplementary page after 12)

def parse(rel):
    parts = PureWindowsPath(rel.replace("/", "\\")).parts
    if len(parts) < 4: return None
    mer = parts[0].upper()
    if mer not in ("W1", "W2", "W3", "E1", "W4"): return None
    m = RANGE.match(parts[1])
    if not m: return None
    rge = m.group(1) + m.group(2).upper()
    twp = None
    for p in parts[2:-1]:
        t = TWP.match(p)
        if t: twp = int(t.group(1))
    if twp is None: return None
    ext = Path(parts[-1]).suffix.lower()
    if ext not in IMG: return None
    stem = Path(parts[-1]).stem
    pm = PAGE.search(stem.replace("(", " ").replace(")", " "))
    page = (int(pm.group(1)) + (0.5 if pm.group(2) else 0)) if pm else 0
    return dict(mer=mer, rge=rge, twp_from=twp, twp_to=twp, page=page, path=rel.replace("/", "\\"), ext=ext, viewable=IMG[ext])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?"); ap.add_argument("--from-list"); a = ap.parse_args()
    rows = []
    if a.from_list:
        for line in open(a.from_list, encoding="utf-8", errors="replace"):
            rel = line.rstrip("\n").split("\t")[0].strip()
            if rel: r = parse(rel); rows.append(r) if r else None
    elif a.root:
        root = Path(a.root)
        for p in root.rglob("*"):
            if p.is_file():
                r = parse(str(p.relative_to(root))); rows.append(r) if r else None
    else:
        ap.error("give the image root or --from-list")
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: (r["mer"], int(re.sub(r"\D", "", r["rge"]) or 0), r["rge"], r["twp_from"], r["page"], r["path"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["mer", "rge", "twp_from", "twp_to", "page", "path", "ext", "viewable"]); w.writeheader(); w.writerows(rows)
    twps = {(r["mer"], r["rge"], r["twp_from"]) for r in rows}
    heic = sum(1 for r in rows if r["ext"] == ".heic")
    print(f"wrote {OUT}: {len(rows)} images, {len(twps)} townships, {heic} HEIC (not viewable in a browser)")
    bad = sorted({(r['mer'], r['rge'], r['twp_from']) for r in rows if not r['viewable']} - {(r['mer'], r['rge'], r['twp_from']) for r in rows if r['viewable']})
    if bad: print(f"townships with only non-viewable images: {len(bad)} — e.g. {bad[:8]}")

if __name__ == "__main__":
    main()
