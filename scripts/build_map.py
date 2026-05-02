#!/usr/bin/env python3
"""Build interactive Leaflet map with HR_rails lines + elevator points.

Outputs:
  /home/jic823/grain/viz/index.html         — interactive map (Folium/Leaflet)
  /home/jic823/grain/viz/rail_lines.geojson — reprojected HR_rails as GeoJSON
  /home/jic823/grain/viz/overview.png       — static PNG for README
"""
import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import folium
import shapefile
from pyproj import CRS, Transformer

GRAIN = Path("/home/jic823/grain")
HR_RAILS_SHP = GRAIN / "dataverse/HR_rails_new/HR_rails_NEW.shp"
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
VIZ = GRAIN / "viz"

# HR_rails projection
HR_CRS = CRS.from_proj4(
    "+proj=lcc +lat_1=49 +lat_2=77 +lat_0=49 +lon_0=-95 "
    "+x_0=0 +y_0=0 +datum=NAD27 +units=m +no_defs"
)
TO_WGS84 = Transformer.from_crs(HR_CRS, CRS.from_epsg(4326), always_xy=True)


def load_rails():
    """Yield reprojected polylines: (line_pts_latlon, props_dict)."""
    sf = shapefile.Reader(str(HR_RAILS_SHP), encoding="latin-1")
    fields = [f[0] for f in sf.fields[1:]]
    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        try:
            cnstrctd = int(rec.get("CNSTRCTD") or 0)
            abndnd = int(rec.get("ABNDND") or 0)
        except (TypeError, ValueError):
            cnstrctd = abndnd = 0
        # Only show lines built before 1944 and either still operating or
        # abandoned after 1911 (overlap with our directory window)
        if cnstrctd > 1944:
            continue
        if abndnd > 0 and abndnd < 1911:
            continue
        if rec.get("FCODE") in (5, 6):  # ferry / under construction
            continue
        pts = list(sr.shape.points)
        # Split into parts if multipart
        parts = list(sr.shape.parts) + [len(pts)]
        for i in range(len(parts) - 1):
            seg = pts[parts[i]:parts[i+1]]
            latlon = []
            for x, y in seg:
                lon, lat = TO_WGS84.transform(x, y)
                latlon.append((lat, lon))
            if len(latlon) >= 2:
                yield latlon, {
                    "bldr_code": rec.get("BLDR_CODE", ""),
                    "incrp_code": rec.get("INCRP_CODE", ""),
                    "cnstrctd": cnstrctd,
                    "abndnd": abndnd,
                }


def load_stations():
    rows = list(csv.DictReader(ELEVATORS.open()))
    rows = [r for r in rows if r["coord_source"]
            and r["coord_source"] != "parser_artifact"
            and r["cgn_lat"] and r["cgn_lat"] != "0.0"]
    # Aggregate per station
    per_station = {}
    for r in rows:
        key = (r["station"], r["province"])
        s = per_station.setdefault(key, {
            "rows": 0, "lat": None, "lon": None, "owners": Counter(),
            "years": set(), "rails": Counter(), "max_cap": 0,
            "coord_source": r["coord_source"],
        })
        s["rows"] += 1
        try:
            s["lat"] = float(r["cgn_lat"]); s["lon"] = float(r["cgn_lon"])
        except ValueError:
            pass
        if r["owner_canonical"]:
            s["owners"][r["owner_canonical"]] += 1
        if r["season_start"]:
            try: s["years"].add(int(r["season_start"]))
            except: pass
        if r["rail_canonical"]:
            s["rails"][r["rail_canonical"]] += 1
        try:
            cap = int(r["capacity_bushels"])
            if cap > s["max_cap"]:
                s["max_cap"] = cap
        except (ValueError, TypeError):
            pass
    return per_station


COORD_SOURCE_COLOR = {
    "cgn_direct": "#1f77b4",
    "agent_high": "#2ca02c",
    "agent_medium": "#9467bd",
    "hr_places": "#17becf",
    "manual_historical": "#ff7f0e",
    "lynch_map_interp": "#d62728",
    "wikipedia_ghost_sk": "#8c564b",
}


def build_folium(stations, rails):
    # Center on prairies
    m = folium.Map(
        location=[52.0, -106.0], zoom_start=5, tiles="cartodbpositron",
        prefer_canvas=True,
    )

    # Add rail lines
    rail_grp = folium.FeatureGroup(name="Historical railways (1836-1922)",
                                   show=True)
    for latlon, props in rails:
        folium.PolyLine(
            latlon, color="#888", weight=1, opacity=0.5,
        ).add_to(rail_grp)
    rail_grp.add_to(m)

    # Add stations grouped by coord_source for layer toggle
    groups = {}
    for src, color in COORD_SOURCE_COLOR.items():
        groups[src] = folium.FeatureGroup(name=f"Stations ({src})", show=True)

    for (station, prov), s in stations.items():
        if s["lat"] is None:
            continue
        src = s["coord_source"]
        col = COORD_SOURCE_COLOR.get(src, "#666")
        top_owner = s["owners"].most_common(1)[0][0] if s["owners"] else ""
        top_rail = s["rails"].most_common(1)[0][0] if s["rails"] else ""
        years = sorted(s["years"])
        years_str = (f"{years[0]}-{years[-1]}" if len(years) > 1
                     else str(years[0]) if years else "")
        popup_html = (
            f"<b>{station}</b>, {prov.title()}<br>"
            f"License years: {years_str} ({len(years)} appearances)<br>"
            f"Operators: {len(s['owners'])} ({s['rows']} elevator-row mentions)<br>"
            f"Top operator: {top_owner}<br>"
            f"Railway: {top_rail}<br>"
            f"Max capacity: {s['max_cap']:,} bu<br>"
            f"<i>coord_source: {src}</i>"
        )
        # Marker size scales with row count (log-ish)
        radius = max(2, min(8, 2 + s["rows"] // 25))
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=radius,
            color=col, weight=1, fill=True, fillColor=col, fillOpacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=station,
        ).add_to(groups.get(src, groups["cgn_direct"]))

    for g in groups.values():
        g.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # Legend
    legend_items = "".join(
        f'<div><span style="background:{c};display:inline-block;'
        f'width:10px;height:10px;border-radius:50%"></span> {n}</div>'
        for n, c in COORD_SOURCE_COLOR.items()
    )
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 10px; border: 1px solid #888;
                border-radius: 4px; font: 12px sans-serif; max-width: 220px;">
        <b>Coord source</b>{legend_items}
        <div style="margin-top:6px;font-size:11px;color:#555">
        Marker size ∝ number of license-year appearances.<br>
        Grey lines: historical railways (1836-1922).</div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def build_static_png(stations, rails):
    fig, ax = plt.subplots(figsize=(14, 10), dpi=110)
    # Rail lines
    for latlon, props in rails:
        lats = [p[0] for p in latlon]
        lons = [p[1] for p in latlon]
        ax.plot(lons, lats, color="#999", linewidth=0.4, alpha=0.6, zorder=1)

    # Elevators
    by_color = {}
    for (st, prov), s in stations.items():
        if s["lat"] is None:
            continue
        col = COORD_SOURCE_COLOR.get(s["coord_source"], "#666")
        by_color.setdefault(col, []).append((s["lon"], s["lat"], s["rows"]))
    for col, pts in by_color.items():
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        sizes = [max(2, min(20, p[2] / 4)) for p in pts]
        # Map color to source name for legend
        label = next((k for k, v in COORD_SOURCE_COLOR.items() if v == col), None)
        ax.scatter(lons, lats, s=sizes, c=col, alpha=0.7,
                   edgecolors="none", zorder=2, label=label)

    ax.set_xlim(-122, -88)
    ax.set_ylim(48.5, 56)
    ax.set_aspect(1.5)  # rough lat/lon aspect for prairies
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        "Canadian Prairie Grain Elevators 1911-1944\n"
        f"{sum(1 for s in stations.values() if s['lat'])} geocoded stations  ·  "
        f"historical railways shown in grey",
        fontsize=12,
    )
    ax.grid(alpha=0.2)
    ax.legend(loc="lower left", fontsize=8, markerscale=3, framealpha=0.9)
    plt.tight_layout()
    out = VIZ / "overview.png"
    plt.savefig(out, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"wrote {out}")


def write_rails_geojson(rails):
    feats = []
    for latlon, props in rails:
        feats.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(lon, 5), round(lat, 5)]
                                for lat, lon in latlon],
            },
            "properties": props,
        })
    geo = {"type": "FeatureCollection", "features": feats}
    out = VIZ / "rail_lines.geojson"
    with out.open("w") as f:
        json.dump(geo, f, separators=(",", ":"))
    print(f"wrote {out} ({len(feats)} segments)")


def main():
    print("loading rails...")
    rails = list(load_rails())
    print(f"  {len(rails)} segments")
    print("loading stations...")
    stations = load_stations()
    print(f"  {len(stations)} unique stations")

    write_rails_geojson(rails)
    print("building static PNG...")
    build_static_png(stations, rails)
    print("building interactive map...")
    m = build_folium(stations, rails)
    out = VIZ / "index.html"
    m.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
