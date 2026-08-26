# Township General Register — entry app

A single-user, local data-entry tool for transcribing the Saskatchewan Township
General Registers into the W1/W2/W3 schema, with the page image beside the form,
the Archives-index names offered as click-to-choose chips, CPR catalogue values
offered as a pre-fill, and every save written to a plain CSV under git.

Runs on Windows or Linux with **plain Python 3.9+ — no packages to install** for
the app itself. `import_sheet.py`, `scan_images.py` and `export_xlsx.py` need
`pandas` and `openpyxl` (already on the lab machines that build the map).

## Setup (once per machine)

```bat
git clone https://github.com/jburnford/wheat.git
cd wheat
python tools\register_entry\import_sheet.py W3 R22      :: one CSV per range sheet you plan to work on
python tools\register_entry\scan_images.py "Q:\HGIS LAB\Saskatchewan Archives\Township General Register"
```

`import_sheet.py` writes `data/register/W3_R22.csv` — one row per quarter
section in register order (T1 → T55, section 1 → 36, NE NW SE SW) with the
Archives-index names and CPR-catalogue sale attached. Rows already typed in
the workbook come across as typed. Re-running it refreshes untouched rows from
the workbook and keeps rows entered in the app.

`scan_images.py` writes `data/register/images.csv`, the map from meridian /
range / township to page images on the shared drive (layout
`W3\Range 22\Township 04\R22 - T04 - (6).jpg`; about twelve pages a township).
Scanning the share takes ~10 minutes; a manifest is committed in the repo, so
only re-run it when new townships have been photographed.

The share also holds the raw iPhone `.HEIC` originals in a `HEIC files` folder
under each range; the township folders contain the JPG conversions, so the
manifest ignores the originals. Townships that have not been photographed yet
(for example W2 R13 T16–31, as of Aug 2026) have no images, and the plan CSV's
`pages` column shows 0 for them.

## Daily use

Double-click `tools\register_entry\run.bat`, or from a terminal in the repo:

```bat
python tools\register_entry\app.py
```

The app finds the register images on whichever drive the HGIS Lab share is
mapped to (Q: on the lab computers, G: elsewhere, or `\\datastore\HGISLab`);
pass `--images "<folder>"` only if it can't.

The browser opens at <http://127.0.0.1:8765>. Pick the sheet and township
(townships in this year's sampling plan are marked ★). The left pane shows the
page image (wheel = zoom, drag = pan, PageUp/PageDown = previous/next image,
F = fit, ⟳ = rotate); with **follow section** ticked it turns to the page that
should hold the current section (page ≈ section ÷ 3), and remembers your zoom
per page. Untick it, or use PageUp/PageDown, to browse freely. The right pane
is the form for the current quarter section.

For each quarter:

1. **Names** — the index names appear as chips. Click the one that proved up
   (it goes to *Successful*); shift-click any that failed. Add a name the index
   missed in the box below. *Number of claims* fills itself.
2. **Type** — pre-filled where predictable (CPR catalogue sale → Canadian Pacific
   Railway; sections 8/26 → HBC; 11/29 → School land; index file → Homestead).
   Keys 1–9 pick the nine common types, 0 = Other, or use the dropdown.
3. **Dates** — type `1903`, `1903-04-17`, `17 Apr 1903` or `Apr 17 1903`; they
   normalise on leaving the box. Patent-before-entry asks for confirmation.
   Register abbreviations: *Home* = Homestead, *Pre.* = Pre-emption, *P.H.* = Purchased Homestead (common in the pre-emption belt, W3 R20–30), *Ranche* = ranch lease; red *can.* = cancelled.
4. **Notes** — free text, as in the workbook (partial acreages, "Patented to …",
   half-section splits).
5. **Enter** saves and moves to the next quarter. **Ctrl+D** copies type, dates
   and (where the same person is on the file) the successful name from the
   previous quarter — useful for the homestead + pre-emption pairs and for
   runs of railway or HBC quarters. Ctrl+→ / Ctrl+← move without saving.

The section grid at the top of the form shows progress (light = untyped, mid
blue = typed in the workbook, dark = entered in the app, orange outline =
current).

**Commit** (top right) runs `git add data/register` + `git commit`, optionally
`git push`. Do it at the end of each session; every row also carries
`entered_at` and the image it was read from.

## Getting the data back into the workbooks / map

```bat
python tools\register_entry\export_xlsx.py           :: writes app rows into W1/W2/W3.xlsx (backs up first)
```

Then the usual `scripts/build_homesteads.py` + tippecanoe rebuild, or
`scripts/build_settlement.sh`.

## Files

| | |
|---|---|
| `app.py` | the server (standard library only) |
| `ui.html` | the page |
| `import_sheet.py` | workbook sheet → `data/register/<W>_<R>.csv` |
| `scan_images.py` | shared-drive images → `data/register/images.csv` |
| `export_xlsx.py` | `data/register/*.csv` → W1/W2/W3.xlsx |
| `data/register/*.csv` | the entered data, under version control |
