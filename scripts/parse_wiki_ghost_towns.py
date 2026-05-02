#!/usr/bin/env python3
"""Parse Wikipedia's 'List of ghost towns in Saskatchewan' table into CSV."""
import csv
import re
from pathlib import Path

HTML = Path("/tmp/ghost_sk.html")
OUT = Path("/home/jic823/grain/tables/ghost_towns_sk.csv")

html = HTML.read_text()

# Extract first wikitable
m = re.search(r'<table[^>]*class="wikitable[^"]*"[^>]*>(.*?)</table>', html, re.DOTALL)
table = m.group(1)
rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)

records = []
for r in rows:
    cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.DOTALL)
    if len(cells) < 4:
        continue
    name_html, rm_html, land_html, latlon_html = cells[:4]
    # Skip header
    if "Name" in name_html and "Rural municipality" in rm_html:
        continue

    def strip(s):
        return re.sub(r"<[^>]+>", " ", s).strip()

    name = strip(name_html)
    name = re.sub(r"\s+", " ", name).strip()
    rm = re.sub(r"\s+", " ", strip(rm_html)).strip()
    land = re.sub(r"\s+", " ", strip(land_html)).strip()

    # geo class span has decimal lat;lon
    geo = re.search(r'class="geo"[^>]*>\s*([-\d.]+)\s*;\s*([-\d.]+)\s*<', latlon_html)
    if geo:
        lat = geo.group(1)
        lon = geo.group(2)
    else:
        lat = lon = ""

    if name:
        records.append({"name": name, "rm": rm, "land_address": land,
                        "lat": lat, "lon": lon})

with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["name", "rm", "land_address", "lat", "lon"])
    w.writeheader()
    w.writerows(records)

n_with_coords = sum(1 for r in records if r["lat"])
print(f"wrote {len(records)} ghost towns ({n_with_coords} with coords) to {OUT}")
