#!/usr/bin/env python3
"""Download PDFs from Internet Archive for identifiers listed in search.csv.

Tries the `internetarchive` library first (handles auth, retries, file listing).
Falls back to a direct HTTP request to the standard download URL.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import requests

try:
    from internetarchive import get_item, download as ia_download
    HAS_IA = True
except ImportError:
    HAS_IA = False


def read_identifiers(csv_path: Path) -> list[str]:
    ids: list[str] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ident = (row.get("identifier") or "").strip()
            if ident:
                ids.append(ident)
    return ids


def download_via_ia(identifier: str, out_dir: Path) -> bool:
    """Download all PDF files for an item using the internetarchive library."""
    item = get_item(identifier)
    pdf_files = [f["name"] for f in item.files if f.get("name", "").lower().endswith(".pdf")]
    if not pdf_files:
        return False
    ia_download(
        identifier,
        files=pdf_files,
        destdir=str(out_dir),
        no_directory=False,
        ignore_existing=True,
        retries=3,
    )
    return True


def download_via_http(identifier: str, out_dir: Path) -> bool:
    """Fallback: try the conventional <identifier>.pdf download URL."""
    url = f"https://archive.org/download/{identifier}/{identifier}.pdf"
    target_dir = out_dir / identifier
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{identifier}.pdf"
    if target.exists() and target.stat().st_size > 0:
        return True
    with requests.get(url, stream=True, timeout=60) as r:
        if r.status_code != 200:
            return False
        with target.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
    return target.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="search.csv", type=Path)
    parser.add_argument("--out", default="pdfs", type=Path)
    parser.add_argument("--sleep", type=float, default=0.5,
                        help="Seconds to sleep between items (be polite to IA).")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    identifiers = read_identifiers(args.csv)
    print(f"Found {len(identifiers)} identifiers in {args.csv}")

    ok, failed = [], []
    for i, ident in enumerate(identifiers, 1):
        print(f"[{i}/{len(identifiers)}] {ident}", flush=True)
        try:
            success = False
            if HAS_IA:
                try:
                    success = download_via_ia(ident, args.out)
                except Exception as e:
                    print(f"  internetarchive failed: {e}; falling back to HTTP", flush=True)
            if not success:
                success = download_via_http(ident, args.out)
            (ok if success else failed).append(ident)
            if not success:
                print(f"  FAILED: no PDF found for {ident}", flush=True)
        except Exception as e:
            print(f"  ERROR {ident}: {e}", flush=True)
            failed.append(ident)
        time.sleep(args.sleep)

    print(f"\nDone. Success: {len(ok)}  Failed: {len(failed)}")
    if failed:
        failed_path = args.out / "failed.txt"
        failed_path.write_text("\n".join(failed) + "\n")
        print(f"Failed identifiers written to {failed_path}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
