# CPR Land Sales Catalogue

Downloaded from Borealis (Canadian Dataverse repository).

| | |
|---|---|
| Title | CPR Land Sales Catalogue |
| Persistent ID | `doi:10.5683/SP3/JVTACU` |
| Landing page | <https://borealisdata.ca/dataset.xhtml?persistentId=doi:10.5683/SP3/JVTACU> |
| Version | 1 (RELEASED) |
| License | CC0 1.0 (public domain dedication) |
| File | `CPR Land Sales Catalogue.csv` (6,439,448 bytes, 53,088 data rows) |
| MD5 | `b88f69385de01313c2e507cb7a644226` |

## Columns

`Volume`, `Contract number`, `Date`, `Purchaser`, `Quarter`, `Section`,
`Township`, `Range`, `Meridian`, `Acres`, `Price`, `Status`

Records of Canadian Pacific Railway land sales, keyed by Dominion Land Survey
location (quarter / section / township / range / meridian).

## Re-download

```sh
curl -sL "https://borealisdata.ca/api/access/datafile/654288?format=original" \
  -o "CPR Land Sales Catalogue.csv"
```

## GIS / geocoded point layer

The flat CSV above has only Dominion Land Survey text (quarter/section/township/
range/meridian) — no coordinates. The **geocoded** version is published by the
University of Calgary SANDS group as an ArcGIS web app:

- App: <https://sands.ucalgary.ca/app/CPRLandSales/>
- Service: `https://sands.ucalgary.ca/arcgis/rest/services/App_CPRLandSales/CPRLandSales_v1_Map_Public/MapServer`

`cpr_land_sales_points.geojson` is the point layer (MapServer layer 1) downloaded
from that service in WGS84.

| | |
|---|---|
| Features | 117,232 points (one per quarter-section sale) |
| CRS | EPSG:4326 (WGS84) |
| Extent | lon -116.07 .. -96.59, lat 49.00 .. 54.24 (MB/SK/AB) |
| By province | AB 53,160 · SK 41,082 · MB 22,990 |
| Attributes | `OBJECTID, ContractNumber, LLD, Date, Purchaser, MER, Acres, Price, Status, TWP, RGE, Volume, UID, Barcode, SEC, QS, Extent, Province` |

The point count (117k) exceeds the CSV row count (53k) because a catalogue row
covering multiple quarter-sections (e.g. `NE\|SE\|NW\|SW`) is exploded into one
point per quarter-section.

Re-download with `scripts/download_cpr_gis.py` (pages the service in 2,000-record
batches).
