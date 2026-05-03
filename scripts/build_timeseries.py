#!/usr/bin/env python3
"""Build per-station per-year timeseries of elevator count and total capacity.

Outputs:
  /home/jic823/grain/docs/elevators_by_year_long.csv  — long format (station, year, n, cap)
  /home/jic823/grain/docs/elevators_by_year_wide.csv  — wide: station + year_n + year_cap columns
  /home/jic823/grain/docs/elevator_count_by_year.csv  — station × year matrix of counts
  /home/jic823/grain/docs/elevator_capacity_by_year.csv — station × year matrix of capacities
"""
import csv
from collections import defaultdict
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
OUT_DIR = GRAIN / "docs"
OUT_DIR.mkdir(exist_ok=True)


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    rows = [r for r in rows
            if r["coord_source"] != "parser_artifact"
            and r["station"] and r["season_start"]
            and r["owner_canonical"]]  # require owner so we count real elevators

    # Aggregate
    counts = defaultdict(int)   # (station, prov, year) -> n elevators
    caps = defaultdict(int)     # (station, prov, year) -> total capacity
    coords = {}                 # (station, prov) -> (lat, lon, coord_source)

    for r in rows:
        try:
            year = int(r["season_start"])
        except ValueError:
            continue
        key = (r["station"], r["province"], year)
        counts[key] += 1
        try:
            caps[key] += int(r["capacity_bushels"])
        except (ValueError, TypeError):
            pass
        sk = (r["station"], r["province"])
        if sk not in coords and r["cgn_lat"] and r["cgn_lat"] != "0.0":
            try:
                coords[sk] = (
                    float(r["cgn_lat"]), float(r["cgn_lon"]),
                    r["coord_source"],
                )
            except ValueError:
                pass

    # All years actually present
    years = sorted({k[2] for k in counts})
    stations = sorted({(k[0], k[1]) for k in counts})

    # Long format
    long_csv = OUT_DIR / "elevators_by_year_long.csv"
    with long_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "lat", "lon", "coord_source",
                    "year", "n_elevators", "total_capacity_bushels"])
        for (st, prov), in [(s,) for s in stations]:
            lat, lon, src = coords.get((st, prov), (None, None, ""))
            for year in years:
                key = (st, prov, year)
                if key in counts:
                    w.writerow([st, prov,
                                round(lat, 5) if lat else "",
                                round(lon, 5) if lon else "",
                                src, year, counts[key], caps[key]])
    print(f"wrote {long_csv}  ({len(rows)} elevator-row mentions, {len(stations)} stations, {len(years)} years)")

    # Wide format with paired columns: station + year_n + year_cap for each year
    wide_csv = OUT_DIR / "elevators_by_year_wide.csv"
    with wide_csv.open("w", newline="") as f:
        w = csv.writer(f)
        header = ["station", "province", "lat", "lon", "coord_source"]
        for y in years:
            header.append(f"{y}_n")
            header.append(f"{y}_cap")
        w.writerow(header)
        for (st, prov) in stations:
            lat, lon, src = coords.get((st, prov), (None, None, ""))
            row = [st, prov,
                   round(lat, 5) if lat else "",
                   round(lon, 5) if lon else "", src]
            for y in years:
                key = (st, prov, y)
                if key in counts:
                    row.append(counts[key])
                    row.append(caps[key] or "")
                else:
                    row.append("")
                    row.append("")
            w.writerow(row)
    print(f"wrote {wide_csv}")

    # Count-only matrix
    count_csv = OUT_DIR / "elevator_count_by_year.csv"
    with count_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "lat", "lon"] + [str(y) for y in years])
        for (st, prov) in stations:
            lat, lon, src = coords.get((st, prov), (None, None, ""))
            row = [st, prov,
                   round(lat, 5) if lat else "",
                   round(lon, 5) if lon else ""]
            for y in years:
                row.append(counts.get((st, prov, y), ""))
            w.writerow(row)
    print(f"wrote {count_csv}")

    # Capacity-only matrix
    cap_csv = OUT_DIR / "elevator_capacity_by_year.csv"
    with cap_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "province", "lat", "lon"] + [str(y) for y in years])
        for (st, prov) in stations:
            lat, lon, src = coords.get((st, prov), (None, None, ""))
            row = [st, prov,
                   round(lat, 5) if lat else "",
                   round(lon, 5) if lon else ""]
            for y in years:
                row.append(caps.get((st, prov, y), ""))
            w.writerow(row)
    print(f"wrote {cap_csv}")

    # Summary
    print(f"\nyears covered: {years[0]}-{years[-1]} ({len(years)} license years)")
    print(f"distinct stations: {len(stations)}")
    print(f"\nProvincial summary (peak counts):")
    from collections import Counter
    prov_counts = Counter()
    for (st, prov), in [(s,) for s in stations]:
        prov_counts[prov] += 1
    for prov, n in prov_counts.most_common():
        print(f"  {prov:18}  {n:>4} stations ever-licensed")


if __name__ == "__main__":
    main()
