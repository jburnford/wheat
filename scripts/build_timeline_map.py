#!/usr/bin/env python3
"""Build interactive timeline map with year slider, where marker size scales
with total capacity at each station for the selected year.

Output:
  /home/jic823/grain/docs/timeline.html
  /home/jic823/grain/docs/timeline_data.json
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

GRAIN = Path("/home/jic823/grain")
ELEVATORS = GRAIN / "tables/elevators_geocoded.csv"
DOCS = GRAIN / "docs"
DOCS.mkdir(exist_ok=True)


def main():
    rows = list(csv.DictReader(ELEVATORS.open()))
    rows = [
        r for r in rows
        if r["coord_source"]
        and r["coord_source"] != "parser_artifact"
        and r["station"]
        and r["season_start"]
        and r["cgn_lat"]
        and r["cgn_lat"] != "0.0"
    ]

    # Aggregate per (station, year): n_elevators, total_capacity
    per = defaultdict(lambda: {"n": 0, "cap": 0, "lat": None, "lon": None,
                               "owners": set()})
    for r in rows:
        try:
            year = int(r["season_start"])
        except ValueError:
            continue
        key = (r["station"], r["province"], year)
        s = per[key]
        s["n"] += 1
        try:
            s["cap"] += int(r["capacity_bushels"])
        except (ValueError, TypeError):
            pass
        if s["lat"] is None:
            try:
                s["lat"] = float(r["cgn_lat"])
                s["lon"] = float(r["cgn_lon"])
            except ValueError:
                pass
        if r["owner_canonical"]:
            s["owners"].add(r["owner_canonical"])

    # Build a compact JSON: {station_id: {lat, lon, name, prov, years: {YYYY: [n, cap]}}}
    # station_id = "station|province"
    station_data = {}
    years_set = set()
    for (station, prov, year), s in per.items():
        if s["lat"] is None:
            continue
        sid = f"{station}|{prov}"
        if sid not in station_data:
            station_data[sid] = {
                "name": station,
                "prov": prov,
                "lat": round(s["lat"], 5),
                "lon": round(s["lon"], 5),
                "years": {},
            }
        station_data[sid]["years"][year] = [s["n"], s["cap"]]
        years_set.add(year)

    years = sorted(years_set)
    out_data = {
        "years": years,
        "stations": list(station_data.values()),
    }
    json_path = DOCS / "timeline_data.json"
    with json_path.open("w") as f:
        json.dump(out_data, f, separators=(",", ":"))
    print(f"wrote {json_path} ({len(station_data)} stations, "
          f"{len(years)} years)")

    # Cap distribution to choose marker scale
    all_caps = [v[1] for s in station_data.values()
                for v in s["years"].values() if v[1] > 0]
    if all_caps:
        all_caps.sort()
        p50 = all_caps[len(all_caps) // 2]
        p95 = all_caps[len(all_caps) * 95 // 100]
        cap_max = max(all_caps)
        print(f"capacity p50={p50:,}  p95={p95:,}  max={cap_max:,}")

    # Build the HTML
    html = HTML_TEMPLATE.replace("__MIN_YEAR__", str(years[0])) \
        .replace("__MAX_YEAR__", str(years[-1]))
    out_html = DOCS / "timeline.html"
    out_html.write_text(html)
    print(f"wrote {out_html}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Prairie Grain Elevators — Timeline (1911-1943)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css" />
  <script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
  <style>
    html, body { height: 100vh; width: 100vw; margin: 0; padding: 0;
                 font-family: system-ui, sans-serif; }
    #map { position: absolute; top: 0; left: 0; right: 0; bottom: 80px; }
    #controls { position: absolute; bottom: 0; left: 0; right: 0;
                height: 80px; background: white; padding: 8px 16px;
                box-shadow: 0 -2px 6px rgba(0,0,0,0.15);
                display: flex; align-items: center; gap: 12px; z-index: 1000; }
    #year-display { font-size: 24px; font-weight: bold; min-width: 100px;
                    color: #333; }
    #year-slider { flex: 1; }
    #stats { font-size: 13px; color: #555; min-width: 280px;
             text-align: right; line-height: 1.4; }
    #play-btn { padding: 6px 16px; background: #2c3e50; color: white;
                border: none; border-radius: 4px; cursor: pointer;
                font-size: 14px; }
    #play-btn:hover { background: #34495e; }
    #legend { position: absolute; top: 12px; right: 12px; z-index: 1000;
              background: white; padding: 10px; border: 1px solid #999;
              border-radius: 4px; font-size: 12px; max-width: 220px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
    .legend-circle { display: inline-block; border-radius: 50%;
                     background: rgba(46,134,193,0.6);
                     border: 1px solid #1a5276;
                     vertical-align: middle; margin-right: 4px; }
    .leaflet-popup-content { font-size: 13px; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="legend">
    <b>Total capacity at station</b><br/>
    <div style="margin-top: 6px;">
      <span class="legend-circle" style="width:6px;height:6px"></span> 25,000 bu<br/>
      <span class="legend-circle" style="width:10px;height:10px"></span> 100,000 bu<br/>
      <span class="legend-circle" style="width:16px;height:16px"></span> 500,000 bu<br/>
      <span class="legend-circle" style="width:24px;height:24px"></span> 1M+ bu (terminals)
    </div>
    <div style="margin-top: 6px; color: #666; font-size: 11px;">
      Drag the slider or hit Play to scrub through license years.
    </div>
    <div style="margin-top:8px;padding-top:8px;border-top:1px solid #ddd;">
      <a href="index.html" style="color:#1976d2;text-decoration:none;font-weight:bold;">
        ← Coord-source view</a>
    </div>
  </div>
  <div id="controls">
    <button id="play-btn">▶ Play</button>
    <input type="range" id="year-slider" min="__MIN_YEAR__" max="__MAX_YEAR__"
           step="1" value="__MIN_YEAR__" />
    <div id="year-display">__MIN_YEAR__</div>
    <div id="stats"></div>
  </div>

<script>
const map = L.map('map').setView([52.0, -103.0], 5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 18,
}).addTo(map);

let stationsData = [];
let layerGroup = L.layerGroup().addTo(map);

// Marker radius = a + b * sqrt(capacity) — area ∝ capacity
function radiusForCapacity(cap) {
  if (!cap || cap <= 0) return 3;
  // sqrt scale capped at ~25 px
  const r = 2 + Math.sqrt(cap / 5000);
  return Math.min(r, 30);
}

function colorForCapacity(cap) {
  if (cap >= 1000000) return '#7b1fa2';   // terminals
  if (cap >= 500000)  return '#c2185b';
  if (cap >= 200000)  return '#d84315';
  if (cap >= 100000)  return '#e65100';
  if (cap >= 50000)   return '#1976d2';
  return '#2e86c1';
}

function render(year) {
  layerGroup.clearLayers();
  let active = 0, totalCap = 0;
  for (const s of stationsData) {
    const yd = s.years[year];
    if (!yd) continue;
    const [n, cap] = yd;
    active++;
    totalCap += cap;
    const marker = L.circleMarker([s.lat, s.lon], {
      radius: radiusForCapacity(cap),
      color: colorForCapacity(cap),
      weight: 1,
      fillColor: colorForCapacity(cap),
      fillOpacity: 0.55,
    });
    marker.bindTooltip(s.name, { sticky: false });
    const capStr = cap ? cap.toLocaleString() + ' bu' : '(no capacity recorded)';
    marker.bindPopup(
      '<b>' + s.name.replace(/`/g, "'") + '</b>, ' +
      s.prov.replace(/`/g, "'") +
      '<br/>License year: ' + year +
      '<br/>Elevators: ' + n +
      '<br/>Total capacity: ' + capStr
    );
    layerGroup.addLayer(marker);
  }
  document.getElementById('year-display').textContent = year + '-' + ((year + 1) % 100).toString().padStart(2, '0');
  document.getElementById('stats').innerHTML =
    '<b>' + active.toLocaleString() + '</b> stations active<br/>' +
    'Total: <b>' + totalCap.toLocaleString() + '</b> bushels';
}

// Load data
fetch('timeline_data.json').then(r => r.json()).then(d => {
  stationsData = d.stations;
  render(parseInt(document.getElementById('year-slider').value));
}).catch(err => {
  document.getElementById('stats').textContent = 'Error loading data: ' + err;
});

document.getElementById('year-slider').addEventListener('input', e => {
  render(parseInt(e.target.value));
});

// Play button (auto-advance)
let playInterval = null;
document.getElementById('play-btn').addEventListener('click', () => {
  const btn = document.getElementById('play-btn');
  if (playInterval) {
    clearInterval(playInterval);
    playInterval = null;
    btn.textContent = '▶ Play';
    return;
  }
  btn.textContent = '⏸ Pause';
  const slider = document.getElementById('year-slider');
  playInterval = setInterval(() => {
    let v = parseInt(slider.value);
    const max = parseInt(slider.max);
    if (v >= max) v = parseInt(slider.min);
    else v++;
    slider.value = v;
    render(v);
  }, 600);
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
