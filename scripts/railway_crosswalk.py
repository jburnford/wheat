#!/usr/bin/env python3
"""Crosswalk railway strings from elevators.csv to hr_codes.dbf CODE.

Strategy:
  1. Strip noise prefixes (NOT LICENSED, PRIVATE COUNTRY ELEVATOR, etc.)
     and capture them as 'class_hint' for elevator typing.
  2. Strip RAILWAY/RAILWAYS/RAILROAD suffix.
  3. Match cleaned name against normalized hr_codes CMPNY_NAME entries.

Outputs:
  /home/jic823/grain/tables/railway_crosswalk.csv  — raw -> code mapping
  /home/jic823/grain/tables/elevators_railway.csv  — elevators with rail_code,
                                                     class_hint columns added
"""
import csv
import re
from collections import Counter
from pathlib import Path

from dbfread import DBF

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators.csv"
HR_CODES = GRAIN / "dataverse/hr_codes.dbf/hr_codes.dbf"

# Noise prefixes that wrap a real railway name. Match longest first.
NOISE_PREFIXES = [
    r"BRACKETED FIGURES EXCLUDED FROM TOTALS?",
    r"BRACKETED ITEMS EXCLUDED FROM TOTALS?",
    r"BRACKETED ITEMS NOT INCLUDED IN TOTALS?",
    r"PUBLIC COUNTRY ELEVATORS ON THE",
    r"PUBLIC COUNTRY ELEVATORS",
    r"PRIVATE COUNTRY ELEVATORS?",
    r"PRIVATE COUNTRY",
    r"AND THESE ELEVATORS WERE RE-LICENSED AS MILL ELEVATORS",
    r"PUBLIC TERMINAL ELEVATORS\.?",
    r"NOT LICENSED",
]
# Build a single regex that strips any noise prefix + the dot/space joiner
NOISE_RE = re.compile(
    r"^\s*(?:" + "|".join(NOISE_PREFIXES) + r")[\s.]*", re.I
)
SUFFIX_RE = re.compile(r"\s*(RAILWAYS?|RAILROAD)\s*$", re.I)


def normalize_for_match(s: str) -> str:
    s = s.lower()
    # Common abbreviation expansions
    s = re.sub(r"\bb\.c\.\b", "british columbia", s)
    s = re.sub(r"\&", " and ", s)
    s = re.sub(r"[\.,'\-]", " ", s)
    s = re.sub(r"\s+(co|ry|rr|company|the)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_codes():
    """Return list of (code, raw_name, normalized_name)."""
    out = []
    for r in DBF(str(HR_CODES), encoding="latin-1"):
        code = r["CODE"]
        name = r["CMPNY_NAME"]
        # Replace y-umlaut artifacts in CMPNY_NAME (e.g. "RyÿCo" -> "Ry Co")
        clean = name.replace("ÿ", " ")
        out.append((code, name, normalize_for_match(clean)))
    return out


def best_match(query_norm: str, codes):
    """Find the single best CODE for a normalized query.

    Prefers: exact equality > query is suffix-or-equal of code-name > substring.
    Among equal-quality, prefer shorter code (corresponds to canonical ones).
    """
    if not query_norm:
        return None, None
    exact = [(c, raw) for c, raw, n in codes if n == query_norm]
    if exact:
        return min(exact, key=lambda x: len(x[0]))
    # query equals code-name with extra "railway" stripped — try with suffix
    q_with = query_norm + " railway"
    exact2 = [(c, raw) for c, raw, n in codes if n == q_with or n + " railway" == q_with]
    if exact2:
        return min(exact2, key=lambda x: len(x[0]))
    # Substring containment (code-name within query, both directions)
    contained = [(c, raw, n) for c, raw, n in codes
                 if (query_norm in n) or (n in query_norm)]
    if contained:
        # Prefer the longest matching n that doesn't blow up on common short tokens
        contained.sort(key=lambda x: -len(x[2]))
        c, raw, _ = contained[0]
        return c, raw
    return None, None


def strip_noise(rail_raw: str):
    """Return (clean_name, class_hint, was_noise)."""
    s = rail_raw.strip()
    m = NOISE_RE.match(s)
    if m:
        prefix = m.group(0).strip(" .").upper()
        s = s[m.end():].strip()
        return s, prefix, True
    return s, "", False


def main():
    codes = load_codes()
    print(f"loaded {len(codes)} hr_codes entries")

    # Aggregate raw railway strings
    rows = list(csv.DictReader(ELEVATORS.open()))
    rail_counts = Counter(r["railway"] for r in rows)
    print(f"distinct railway strings: {len(rail_counts)}")

    # Build crosswalk
    crosswalk = {}
    for raw, n in rail_counts.items():
        if not raw:
            crosswalk[raw] = {
                "raw": raw, "rows": n, "clean": "", "class_hint": "",
                "rail_code": "", "rail_canonical": "",
            }
            continue
        clean, class_hint, _ = strip_noise(raw)
        # Strip "RAILWAY" suffix for matching
        match_str = SUFFIX_RE.sub("", clean).strip()
        match_str = re.sub(r"^CINNADAN", "Canadian", match_str, flags=re.I)  # OCR error
        match_str = re.sub(r"^CANADIAN-PACIFIC", "Canadian Pacific", match_str, flags=re.I)
        q = normalize_for_match(match_str)
        code, canonical = best_match(q, codes)
        crosswalk[raw] = {
            "raw": raw,
            "rows": n,
            "clean": clean,
            "class_hint": class_hint,
            "rail_code": code or "",
            "rail_canonical": canonical or "",
        }

    # Sort by rows desc for output
    out_xw = GRAIN / "tables/railway_crosswalk.csv"
    with out_xw.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "raw", "rows", "clean", "class_hint", "rail_code", "rail_canonical",
        ])
        w.writeheader()
        for entry in sorted(crosswalk.values(), key=lambda x: -x["rows"]):
            w.writerow(entry)

    # Stats
    matched = sum(1 for e in crosswalk.values() if e["rail_code"])
    matched_rows = sum(e["rows"] for e in crosswalk.values() if e["rail_code"])
    total_rows = sum(e["rows"] for e in crosswalk.values())
    print(f"matched {matched}/{len(crosswalk)} distinct ({matched_rows}/{total_rows} rows)")
    print(f"\nwrote: {out_xw}")
    # Show unmatched
    print("\nunmatched railway strings (top 10 by rows):")
    for e in sorted(crosswalk.values(), key=lambda x: -x["rows"]):
        if e["rail_code"]:
            continue
        if not e["raw"]:
            continue
        print(f"  {e['rows']:6}  raw={e['raw'][:60]!r}  clean={e['clean'][:40]!r}")


if __name__ == "__main__":
    main()
