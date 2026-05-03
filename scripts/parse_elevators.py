#!/usr/bin/env python3
"""Parse Chandra OCR markdown of CGC elevator directories into a flat table.

Usage: parse_elevators.py <input.md> [<input.md> ...]
Writes combined CSV to /home/jic823/grain/tables/elevators.csv (overwrites).
"""
import csv
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

OUT_DIR = Path("/home/jic823/grain/tables")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROVINCES = {
    "MANITOBA", "SASKATCHEWAN", "ALBERTA", "BRITISH COLUMBIA",
    "ONTARIO", "QUEBEC", "NEW BRUNSWICK", "NOVA SCOTIA",
    "PRINCE EDWARD ISLAND",
}
PROVINCE_RE = re.compile(
    r"(?:PROVINCE OF\s+)?(" + "|".join(PROVINCES) + r")\b", re.I
)
# Railway heading: text ending in RAILWAY/RAILWAYS, may have qualifiers like
# "PUBLIC COUNTRY ELEVATORS ON THE CANADIAN PACIFIC RAILWAY"
RAILWAY_RE = re.compile(
    r"\b((?:[A-Z][A-Z .,&'\-]*?)?(?:RAILWAY|RAILWAYS|RAILROAD))\b\.?", re.I
)
RECAP_RE = re.compile(r"\bRECAPITULATION\b", re.I)
# Running header like "CANADIAN PACIFIC RAILWAY—MANITOBA—Con."
RUNHEAD_RE = re.compile(
    r"([A-Z][A-Z .,&'\-]*?(?:RAILWAY|RAILWAYS|RAILROAD))[\s.]*[—–\-][\s.]*("
    + "|".join(PROVINCES) + r")[\s.]*[—–\-][\s.]*(?:Con|Continued)\.?",
    re.I,
)
YEAR_RE = re.compile(
    r"(?:SEASON|LICEN[CS]E YEAR)[\s,]+([0-9]{4})\s*[-–]\s*([0-9]{2,4})",
    re.I,
)
CAPACITY_RE = re.compile(
    r"^\s*([A-Z](?:\.[A-Z])*\.?)?\s*([\d,]+)\s*\.?\s*([A-Z](?:\.[A-Z])*\.?)?\s*$"
)
DITTO_RE = re.compile(r'^["“”\s.]+$')


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".").strip(" .")


def extract_season(md: str) -> tuple[str | None, str | None]:
    m = YEAR_RE.search(md)
    if not m:
        return None, None
    y1, y2 = m.group(1), m.group(2)
    if len(y2) == 2:
        y2 = y1[:2] + y2
    return y1, y2


def iter_blocks(md: str):
    """Yield (kind, text) in document order. kind is 'table' or 'heading'.

    'heading' covers:
      - markdown headings (# / ## / ### / ####)
      - **bold** runs (which may appear after </table> with no newline)
    """
    table_pat = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL)
    # Allow heading after start-of-line OR after `>` (for </table>## X cases)
    head_pat = re.compile(r"(?:^|(?<=>))(#{1,5})\s+(.+?)\s*$", re.MULTILINE)
    bold_pat = re.compile(r"\*\*([^*]+?)\*\*")
    # OCR fused a page-number prefix onto some province headings, e.g.
    #   "5.....# LIST OF LICENSED ELEVATORS AND WAREHOUSES IN THE PROVINCE OF SASKATCHEWAN"
    # Detect "PROVINCE OF X" in any line as a fallback heading.
    inline_prov_pat = re.compile(
        r"PROVINCE OF\s+(" + "|".join(PROVINCES) + r")\b", re.I,
    )

    table_spans = [(m.start(), m.end()) for m in table_pat.finditer(md)]

    def in_table(pos):
        for s, e in table_spans:
            if s <= pos < e:
                return True
        return False

    events = []
    for m in table_pat.finditer(md):
        events.append((m.start(), "table", m.group(0)))
    for m in head_pat.finditer(md):
        events.append((m.start(), "heading", m.group(2)))
    for m in bold_pat.finditer(md):
        if not in_table(m.start()):
            events.append((m.start(), "heading", m.group(1)))
    for m in RUNHEAD_RE.finditer(md):
        if not in_table(m.start()):
            events.append((m.start(), "runhead", (m.group(1), m.group(2))))
    # Inline "PROVINCE OF X" fallback for OCR-mangled headings
    for m in inline_prov_pat.finditer(md):
        if not in_table(m.start()):
            events.append((m.start(), "heading",
                           f"PROVINCE OF {m.group(1).upper()}"))

    events.sort()
    for _, kind, text in events:
        yield kind, text


def parse_table(html: str):
    soup = BeautifulSoup(html, "html.parser")
    headers = [normalize(th.get_text(" ")) for th in soup.find_all("th")]
    if not headers or "STATION" not in {h.upper() for h in headers}:
        return None
    # Detect 4-column "STATION | RLY | OWNER | CAPACITY" tables (Public Terminal style)
    has_rly_col = any(
        h.upper().startswith(("RLY", "RAILWAY")) for h in headers
    )
    rows = []
    pending_station = None
    pending_station_remaining = 0
    last_owner = None
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells = [(td, normalize(td.get_text(" "))) for td in tds]
        owner = capacity = None
        if has_rly_col:
            # 4-col: STATION | RLY | OWNER | CAPACITY
            # When station rowspan continues, only 3 cells appear: RLY | OWNER | CAPACITY
            if len(cells) >= 4:
                station_td, station_txt = cells[0]
                try:
                    rs = int(station_td.get("rowspan", "1"))
                except ValueError:
                    rs = 1
                if station_txt:
                    pending_station = station_txt
                    pending_station_remaining = rs - 1
                # cells[1] is railway code (skip — comes from section heading)
                owner = cells[2][1]
                capacity = cells[3][1]
            elif len(cells) == 3 and pending_station and pending_station_remaining > 0:
                # cells[0] is railway code (skip), cells[1] owner, cells[2] capacity
                owner = cells[1][1]
                capacity = cells[2][1]
                pending_station_remaining -= 1
            else:
                continue
        else:
            # 3-col: STATION | OWNER | CAPACITY
            if len(cells) >= 3:
                station_td, station_txt = cells[0]
                try:
                    rs = int(station_td.get("rowspan", "1"))
                except ValueError:
                    rs = 1
                if station_txt:
                    pending_station = station_txt
                    pending_station_remaining = rs - 1
                owner = cells[1][1]
                capacity = cells[2][1]
            elif len(cells) == 2 and pending_station and pending_station_remaining > 0:
                owner = cells[0][1]
                capacity = cells[1][1]
                pending_station_remaining -= 1
            else:
                continue
        if DITTO_RE.match(owner) and last_owner:
            owner = last_owner
        else:
            last_owner = owner
        rows.append((pending_station, owner, capacity))
    return rows


def split_capacity(cap: str):
    if not cap:
        return None, None
    m = CAPACITY_RE.match(cap)
    if not m:
        return None, None
    prefix, num, suffix = m.group(1), m.group(2), m.group(3)
    try:
        bushels = int(num.replace(",", ""))
    except ValueError:
        bushels = None
    code = (prefix or suffix or "").rstrip(".").replace(".", "")
    return (code or None), bushels


def classify_heading(text: str):
    """Return (key, value) for a heading text, or (None, None)."""
    t = normalize(text)
    if not t:
        return None, None
    if RECAP_RE.search(t):
        return "recap", True
    # Must be uppercase-ish to be a section header (avoid catching prose)
    letters = [c for c in t if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) < 0.6:
        return None, None
    # Province takes priority if both match (e.g. "MANITOBA" alone)
    pmatch = PROVINCE_RE.search(t)
    rmatch = RAILWAY_RE.search(t)
    # Don't grab a province out of a railway-name heading
    if rmatch and not (pmatch and pmatch.group(0).upper() == t.upper()):
        rail = normalize(rmatch.group(1))
        # Prepend any qualifier prefix that ends in the railway name
        return "railway", rail.upper()
    if pmatch:
        return "province", pmatch.group(1).upper()
    return None, None


def parse_file(md_path: Path):
    md = md_path.read_text()
    season_y1, season_y2 = extract_season(md)
    province = None
    railway = None
    skip_next_table = False
    out = []
    for kind, payload in iter_blocks(md):
        if kind == "heading":
            key, val = classify_heading(payload)
            if key == "recap":
                skip_next_table = True
            elif key == "province":
                province = val
            elif key == "railway":
                railway = val
        elif kind == "runhead":
            rail, prov = payload
            railway = normalize(rail).upper()
            province = prov.upper()
        elif kind == "table":
            if skip_next_table:
                skip_next_table = False
                continue
            rows = parse_table(payload)
            if not rows:
                continue
            for station, owner, cap in rows:
                etype, bushels = split_capacity(cap)
                out.append({
                    "volume": md_path.stem,
                    "season_start": season_y1,
                    "season_end": season_y2,
                    "province": province,
                    "railway": railway,
                    "station": station,
                    "owner": owner,
                    "elevator_type": etype,
                    "capacity_bushels": bushels,
                    "capacity_raw": cap,
                })
    return out


def main(paths):
    all_rows = []
    for p in paths:
        rows = parse_file(Path(p))
        with_prov = sum(1 for r in rows if r["province"])
        with_rail = sum(1 for r in rows if r["railway"])
        print(f"  {Path(p).name}: {len(rows)} rows  prov={with_prov}  rail={with_rail}")
        all_rows.extend(rows)
    out_csv = OUT_DIR / "elevators.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "volume", "season_start", "season_end", "province", "railway",
                "station", "owner", "elevator_type", "capacity_bushels",
                "capacity_raw",
            ],
        )
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_csv}")


if __name__ == "__main__":
    main(sys.argv[1:])
