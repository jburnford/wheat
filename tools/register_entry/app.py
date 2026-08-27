#!/usr/bin/env python3
"""Township General Register entry app — single user, standard library only.

    python tools/register_entry/app.py                # finds the register folder on Q:, G: or \\\\datastore\\HGISLab
    python tools/register_entry/app.py --images "Q:\\HGIS LAB\\Saskatchewan Archives\\Township General Register"

Then open http://127.0.0.1:8765 (it opens automatically). Data lives in
data/register/<W>_<R>.csv (one row per quarter section, created by
import_sheet.py); every save rewrites that CSV, so the work is plain text
under git. The "Commit" button runs `git add data/register && git commit`.

Images: the app looks for page images through data/register/images.csv (built
by scan_images.py) — columns: mer, rge, twp_from, twp_to, path (relative to
--images). If no manifest exists it falls back to listing the image root.
"""
import argparse, csv, io, json, os, re, subprocess, sys, threading, time, webbrowser, mimetypes
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from datetime import datetime

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data" / "register"
PLAN = ROOT / "data" / "homesteads" / "transcription_plan_2026.csv"
COLS = ["QSECT", "PSECT", "PTWP", "PRGE", "PMER", "Type", "FirstDate", "FirstDateSuccess", "Successful_Claims", "Failed_Claims",
        "Patent_Date", "Number_of_claims", "Notes", "index_names", "cpr_hint", "entered_at", "image"]
QS_ORDER = {"NE": 0, "NW": 1, "SE": 2, "SW": 3}
LOCK = threading.Lock()
IMAGE_ROOT = None
MANIFEST = []
CACHE = DATA / ".cache"
PREFETCHING = set()

FILE_LOCKS = {}
FILE_LOCKS_GUARD = threading.Lock()
def cached(rel):
    """Return a local copy of IMAGE_ROOT/rel, copying it into data/register/.cache first if needed."""
    src = (IMAGE_ROOT / rel).resolve()
    if not str(src).startswith(str(IMAGE_ROOT.resolve())) or not src.exists(): return None
    dst = CACHE / rel
    with FILE_LOCKS_GUARD: lock = FILE_LOCKS.setdefault(str(dst), threading.Lock())
    with lock:                                   # one copier per file; a concurrent request waits, then finds it cached
        if dst.exists() and dst.stat().st_size == src.stat().st_size: return dst
        dst.parent.mkdir(parents=True, exist_ok=True); tmp = dst.with_name(dst.name + f".{threading.get_ident()}.part")
        with open(src, "rb") as f, open(tmp, "wb") as g:
            while True:
                b = f.read(1 << 20)
                if not b: break
                g.write(b)
        os.replace(tmp, dst); return dst

def prefetch(paths):
    key = tuple(paths)
    if not IMAGE_ROOT or key in PREFETCHING: return
    PREFETCHING.add(key)
    def run():
        for rel in paths:
            try: cached(rel.replace("\\", "/"))
            except Exception: pass
        PREFETCHING.discard(key)
    threading.Thread(target=run, daemon=True).start()

# Type vocabulary: the values David has used, most frequent first (from the typed sheets, Aug 2026).
TYPES = ["Homestead", "Canadian Pacific Railway", "Sale", "Pre-emption", "School Land Sale", "Purchased Homestead", "Hudson Bay Company", "Canadian Northern Railway",
         "Qu’Appelle, Long Lake, and Saskatchewan Railroad and Steamboat Company", "Provincial Forest", "Indian Reserve", "Transferred",
         "North West Half-Breed Scrip", "Time Sale", "Settlement", "Soldier", "South African Volunteer Homestead", "Military Homestead",
         "Canadian Pacific Railway Souris Branch", "Manitoba South-Western Colonization Railway", "Manitoba and North Western Railway",
         "Manitoba and Southeastern Railway", "Great North-West Central Railway", "Canadian Pacific Railway Grant", "Special Grant", "Ranche",
         "Pasture Lease", "Grazing Permit", "Open for Grazing", "Cultivation Lease", "Exchange", "Northwest Colonization Company",
         "North West Half-Breed Grant", "Canadian Pacific Railway Sale", "Pasture Sale", "Provincial Land Sale", "Grand Trunk Pacific Railway Townsites",
         "Free Grant", "Drainage Sale", "Church + Cemetery site", "Blank (no entry)", "Other"]

def load_sheet(name):
    p = DATA / f"{name}.csv"
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in COLS: r.setdefault(c, "")
    return rows

def save_sheet(name, rows):
    p = DATA / f"{name}.csv"; tmp = p.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    os.replace(tmp, p)

def sheet_names():
    return sorted(p.stem for p in DATA.glob("W*_R*.csv"))

def plan_townships():
    out = {}
    if PLAN.exists():
        with open(PLAN, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.setdefault(f"{r['meridian']}_{r['sheet']}", set()).add(int(r["township"]))
    return out

def load_manifest():
    global MANIFEST
    m = DATA / "images.csv"; MANIFEST = []
    if m.exists():
        with open(m, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try: MANIFEST.append(dict(mer=r["mer"].upper(), rge=str(r["rge"]).upper().lstrip("0"), t0=int(r.get("twp_from") or 0), t1=int(r.get("twp_to") or 99), path=r["path"], page=float(r.get("page") or 0), viewable=str(r.get("viewable", "1")) != "0"))
                except (ValueError, KeyError): pass

def images_for(mer, rge, twp):
    rge = str(rge).upper().lstrip("0")
    hits = [x for x in MANIFEST if x["mer"] == mer and x["rge"] == rge and x["t0"] <= twp <= x["t1"]]
    hits.sort(key=lambda x: (x["page"], x["path"]))
    hits = [dict(path=x["path"], page=f"p{x['page']:g} · {x['path'].split(chr(92))[-1]}" if x["page"] else x["path"].split(chr(92))[-1], viewable=x["viewable"]) for x in hits]
    if not hits and IMAGE_ROOT:   # fallback: any file whose path mentions the range
        pat = re.compile(rf"(^|[^0-9]){rge}([^0-9]|$)")
        for p in sorted(IMAGE_ROOT.rglob("*")):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf") and mer.lower() in str(p).lower() and pat.search(p.stem):
                hits.append(dict(path=str(p.relative_to(IMAGE_ROOT)), page=""))
            if len(hits) > 400: break
    return hits

def git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)

KEY = ("QSECT", "PSECT", "PTWP", "PRGE", "PMER")
ENTRY_COLS = ("Type", "FirstDate", "FirstDateSuccess", "Successful_Claims", "Failed_Claims", "Patent_Date", "Number_of_claims", "Notes", "image", "entered_at")
PUSHED_CACHE = {}
def pushed_rows(name):
    """Rows of data/register/<name>.csv as they are on the upstream branch (origin/main after a push), keyed by quarter.
    Cached per upstream commit, so one `git show` per push rather than per township."""
    code, head = git("rev-parse", "@{upstream}")
    if code: return {}
    hit = PUSHED_CACHE.get(name)
    if hit and hit[0] == head: return hit[1]
    code, text = git("show", f"@{{upstream}}:data/register/{name}.csv")
    up = {}
    if not code:
        for r in csv.DictReader(io.StringIO(text)):
            up[tuple(r.get(k, "") for k in KEY)] = tuple(r.get(c, "") for c in ENTRY_COLS)
    PUSHED_CACHE[name] = (head, up); return up

class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); path = u.path
        if path == "/":
            b = (HERE / "ui.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path == "/api/sheets":
            plan = plan_townships(); out = []
            for n in sheet_names():
                rows = load_sheet(n); tw = {}
                for r in rows:
                    t = int(r["PTWP"]); d = tw.setdefault(t, {"twp": t, "n": 0, "typed": 0, "app": 0, "index": 0})
                    d["n"] += 1; d["typed"] += bool(r["Type"]); d["app"] += bool(r["entered_at"]); d["index"] += bool(r["index_names"])
                out.append({"name": n, "rows": len(rows), "typed": sum(bool(r["Type"]) for r in rows), "townships": sorted(tw.values(), key=lambda d: d["twp"]), "plan": sorted(plan.get(n, []))})
            self._json(out); return
        if path == "/api/sheet":
            n = q["name"][0]; twp = int(q["twp"][0])
            rows = [r for r in load_sheet(n) if int(r["PTWP"]) == twp]
            rows.sort(key=lambda r: (int(r["PSECT"]), QS_ORDER.get(r["QSECT"], 9)))
            up = pushed_rows(n)   # a quarter is "pushed" when it was saved in the app and GitHub holds exactly what is on disk
            for r in rows: r["pushed"] = bool(r["entered_at"]) and up.get(tuple(r[k] for k in KEY)) == tuple(r[c] for c in ENTRY_COLS)
            self._json({"rows": rows, "types": TYPES}); return
        if path == "/api/images":
            hits = images_for(q["mer"][0].upper(), q["rge"][0], int(q["twp"][0]))
            prefetch([h["path"] for h in hits if h.get("viewable", True)])   # warm the local cache for this township in the background
            self._json(hits); return
        if path.startswith("/img/"):
            if not IMAGE_ROOT: self.send_error(404); return
            rel = unquote(path[5:]); p = cached(rel)
            if p is None: self.send_error(404); return
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(p.stat().st_size)); self.send_header("Cache-Control", "max-age=3600"); self.end_headers()
            try:
                with open(p, "rb") as f:
                    while True:
                        chunk = f.read(1 << 20)
                        if not chunk: break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass   # browser moved on to another page mid-transfer
            return
        if path == "/api/status":
            code, out = git("status", "--porcelain", "data/register"); self._json({"changed": [l[3:] for l in out.splitlines()], "image_root": str(IMAGE_ROOT) if IMAGE_ROOT else None, "manifest": len(MANIFEST)}); return
        self.send_error(404)
    def do_POST(self):
        u = urlparse(self.path); n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/api/save":
            name = body["sheet"]; row = body["row"]
            with LOCK:
                rows = load_sheet(name); key = tuple(str(row[k]) for k in ("QSECT", "PSECT", "PTWP", "PRGE", "PMER")); hit = None
                for r in rows:
                    if tuple(str(r[k]) for k in ("QSECT", "PSECT", "PTWP", "PRGE", "PMER")) == key: hit = r; break
                if hit is None: self._json({"ok": False, "error": "row not found"}, 404); return
                for c in ("Type", "FirstDate", "FirstDateSuccess", "Successful_Claims", "Failed_Claims", "Patent_Date", "Number_of_claims", "Notes", "image"):
                    hit[c] = str(row.get(c, "")).strip()
                hit["entered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_sheet(name, rows)
            self._json({"ok": True, "entered_at": hit["entered_at"]}); return
        if u.path == "/api/commit":
            msg = body.get("message") or f"Register entry {datetime.now():%Y-%m-%d %H:%M}"
            c1, o1 = git("add", "data/register"); c2, o2 = git("commit", "-m", msg)
            pushed = ""
            if body.get("push"):
                c3, o3 = git("push"); pushed = o3
            self._json({"ok": c2 == 0, "output": (o1 + "\n" + o2 + "\n" + pushed).strip()}); return
        self.send_error(404)

def main():
    global IMAGE_ROOT
    ap = argparse.ArgumentParser(); ap.add_argument("--images", default=os.environ.get("REGISTER_IMAGES", "")); ap.add_argument("--port", type=int, default=8765); ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    SUB = "HGIS LAB/Saskatchewan Archives/Township General Register"
    candidates = [a.images] if a.images else [f"{d}:/{SUB}" for d in "QGHPRSTZ"] + [f"//datastore/HGISLab/{SUB}", f"/mnt/q/{SUB}", f"/mnt/g/{SUB}"]
    for c in candidates:                              # first mapped drive that has the register folder wins
        if c and Path(c).exists(): IMAGE_ROOT = Path(c); break
    if IMAGE_ROOT is None: print("warning: register image folder not found" + (f": {a.images}" if a.images else " on Q:, G: or \\\\datastore\\HGISLab — pass --images \"<path>\"")); 
    load_manifest()
    DATA.mkdir(parents=True, exist_ok=True)
    if not sheet_names():
        print("No sheets in data/register/. Create one first, e.g.:  python tools/register_entry/import_sheet.py W3 R22")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Register entry app: {url}   images: {IMAGE_ROOT or '(none)'}   manifest entries: {len(MANIFEST)}")
    if not a.no_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
