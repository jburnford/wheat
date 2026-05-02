#!/usr/bin/env python3
"""Normalize grain-elevator owner names and produce final enriched table.

Inputs:
  /home/jic823/grain/tables/elevators_enriched.csv   (from reconcile_stations)
  /home/jic823/grain/tables/railway_crosswalk.csv    (from railway_crosswalk)

Output:
  /home/jic823/grain/tables/elevators_final.csv
  /home/jic823/grain/tables/owners.csv
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
EL_ENRICHED = GRAIN / "tables/elevators_enriched.csv"
RAIL_XW = GRAIN / "tables/railway_crosswalk.csv"


def canonicalize_owner(s: str) -> str:
    if not s:
        return ""
    o = s.strip()
    # Strip leading footnote markers and quotes
    o = re.sub(r'^[\*"\s]+', "", o)
    # Drop trailing dots and standalone footnote markers
    o = re.sub(r'[\.\s\*"]+$', "", o)
    # Replace HTML entities
    o = o.replace("&amp;", "&")
    # Drop leading "The "
    o = re.sub(r"^the\s+", "", o, flags=re.I)
    # Normalize legal suffixes
    o = re.sub(r"\b(limited|ltd\.?)\b", "Ltd", o, flags=re.I)
    o = re.sub(r"\b(company|co\.?)\b", "Co", o, flags=re.I)
    o = re.sub(r"\b(corporation|corp\.?)\b", "Corp", o, flags=re.I)
    o = re.sub(r"\b(incorporated|inc\.?)\b", "Inc", o, flags=re.I)
    # Drop trailing ", Ltd" formatting noise -> single space
    o = re.sub(r"[,]+", " ", o)
    o = re.sub(r"\s+", " ", o).strip()
    # Title case but preserve all-caps acronyms (very common in this corpus)
    return o


def main():
    # Load railway crosswalk
    xw = {}
    for r in csv.DictReader(RAIL_XW.open()):
        xw[r["raw"]] = r

    # Process elevators
    rows = list(csv.DictReader(EL_ENRICHED.open()))
    owner_counts = Counter()
    for r in rows:
        canon = canonicalize_owner(r["owner"])
        r["owner_canonical"] = canon
        owner_counts[canon] += 1
        # Add railway crosswalk fields
        x = xw.get(r["railway"], {})
        r["rail_code"] = x.get("rail_code", "")
        r["rail_canonical"] = x.get("rail_canonical", "")
        r["class_hint"] = x.get("class_hint", "")

    # Output enriched
    out_final = GRAIN / "tables/elevators_final.csv"
    fieldnames = list(rows[0].keys())
    with out_final.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Output owners summary
    out_owners = GRAIN / "tables/owners.csv"
    # For each canonical owner, collect the variants seen
    variants = defaultdict(list)
    for r in rows:
        if r["owner_canonical"]:
            variants[r["owner_canonical"]].append(r["owner"])
    with out_owners.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["owner_canonical", "rows", "n_variants", "sample_variants"])
        for owner, count in owner_counts.most_common():
            if not owner:
                continue
            uniq = sorted(set(variants[owner]))
            w.writerow([owner, count, len(uniq), " | ".join(uniq[:5])])

    print(f"raw distinct owners: {len({r['owner'] for r in rows})}")
    print(f"canonical distinct: {sum(1 for k in owner_counts if k)}")
    print(f"top 10 canonical:")
    for k, v in owner_counts.most_common(10):
        if k:
            print(f"  {v:6}  {k}")
    print(f"\nwrote: {out_final}")
    print(f"       {out_owners}")


if __name__ == "__main__":
    main()
