#!/usr/bin/env python3
"""Scrape RIK documents on polling-station committees (birački odbori).

Example:
    python3 odbori/scrape_odbori.py "Град Крагујевац" --slug kragujevac
    python3 odbori/scrape_odbori.py "Град Ниш" --slug nis

It downloads document metadata for document-type=4 (РЕШЕЊА О ИМЕНОВАЊУ
БИРАЧКИХ ОДБОРА) for the parliamentary 2026 election round (680072), then the
unique PDFs, and runs Tesseract OCR (Serbian Cyrillic) on the first two pages.

Raw files are written to odbori/pdf/<slug>/ and odbori/ocr/<slug>/ (gitignored);
metadata goes to odbori/meta/<slug>.json.
"""
import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.rik.parlament.gov.rs"
ELECTION_ROUND = "680072"
DOCUMENT_TYPE = "4"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "rezultatiizbora.rs/1.0"}


def municipality_id(name):
    r = requests.get(
        BASE + "/templates/election/getElectionStations.php",
        params={"q": name, "electionId": ELECTION_ROUND},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise SystemExit(f"Municipality not found: {name}")
    exact = [x for x in data if x["name"].strip().lower() == name.strip().lower()]
    return (exact or data)[0]


def fetch_metadata(mid):
    records = []
    page = 1
    while True:
        params = {
            "page": page,
            "filters[document-type]": DOCUMENT_TYPE,
            "filters[election-round]": ELECTION_ROUND,
            "filters[municipality-id]": mid,
            "order": 1,
            "sort": 1,
            "election_type": 2,
        }
        r = requests.get(BASE + "/get-additional-documents", params=params, headers=HEADERS, timeout=45)
        r.raise_for_status()
        d = r.json()
        records += d.get("records", [])
        pages = [int(x) for x in re.findall(r'data-page="(\d+)"', d.get("pagination", ""))]
        last = max(pages) if pages else page
        print(f"  metadata page {page}/{last}: {len(d.get('records', []))} records")
        if page >= last:
            break
        page += 1
        time.sleep(0.25)
    for rec in records:
        m = re.search(r'href="([^"]+)"', rec.get("extfiles_link", [""])[0])
        rec["_url"] = html.unescape(m.group(1)) if m else ""
    # de-duplicate by URL but keep the first record
    seen, uniq = set(), []
    for rec in records:
        if rec["_url"] and rec["_url"] not in seen:
            seen.add(rec["_url"])
            uniq.append(rec)
    return records, uniq


def pdf_key(url):
    parts = url.rstrip("/").split("/")
    return parts[-2] + "_" + parts[-1]


def download(urls, slug, workers=8):
    outdir = os.path.join(ROOT, "odbori", "pdf", slug)
    os.makedirs(outdir, exist_ok=True)

    def one(url):
        path = os.path.join(outdir, pdf_key(url))
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
        for attempt in range(3):
            try:
                r = requests.get(BASE + url, headers=HEADERS, timeout=90)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    open(path, "wb").write(r.content)
                    return path
            except Exception:
                time.sleep(1 + attempt)
        return None

    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, u): u for u in urls}
        for i, f in enumerate(as_completed(futs), 1):
            if f.result():
                ok += 1
            else:
                print("  FAILED:", futs[f])
            if i % 50 == 0:
                print(f"  downloaded {i}/{len(urls)}")
    print(f"PDFs: {ok}/{len(urls)} in {outdir}")


def ocr(slug, workers=4, dpi=150):
    srcdir = os.path.join(ROOT, "odbori", "pdf", slug)
    outdir = os.path.join(ROOT, "odbori", "ocr", slug)
    os.makedirs(outdir, exist_ok=True)
    pdfs = sorted(p for p in glob.glob(os.path.join(srcdir, "*")) if p.lower().endswith(".pdf"))
    todo = [p for p in pdfs if not (os.path.exists(os.path.join(outdir, os.path.splitext(os.path.basename(p))[0] + ".txt")))]
    print(f"OCR: {len(todo)} files to process ({len(pdfs)-len(todo)} cached)")

    def one(path):
        stem = os.path.splitext(os.path.basename(path))[0]
        dst = os.path.join(outdir, stem + ".txt")
        with tempfile.TemporaryDirectory(prefix="rikocr_") as td:
            base = os.path.join(td, "p")
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", path, base],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
            )
            chunks = []
            for img in sorted(glob.glob(base + "*.png")):
                r = subprocess.run(
                    ["tesseract", img, "stdout", "-l", "srp"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
                chunks.append(r.stdout)
            open(dst, "w", encoding="utf-8").write("\n\f\n".join(chunks))

    # OMP_THREAD_LIMIT=1 is important: several Tesseract processes otherwise
    # oversubscribe the CPU and slow down by an order of magnitude.
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, p): p for p in todo}
        for f in as_completed(futs):
            try:
                f.result()
                done += 1
            except Exception as e:
                print("  OCR FAILED:", futs[f], repr(e))
            if done % 25 == 0:
                print(f"  OCR {done}/{len(todo)}")
    print(f"OCR done: {done}/{len(todo)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("municipality", nargs="?", help="e.g. 'Град Крагујевац'")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--id", help="RIK document municipality id (skips autocomplete)")
    ap.add_argument("--name", help="municipality display name (with --id)")
    ap.add_argument("--region", default="", help="region id (optional metadata)")
    ap.add_argument("--region-name", default="", help="region name (optional metadata)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--download-workers", type=int, default=None)
    ap.add_argument("--ocr-workers", type=int, default=None)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-ocr", action="store_true")
    args = ap.parse_args()

    if args.id:
        m = {"id": str(args.id), "name": args.name or args.municipality or args.slug}
    else:
        if not args.municipality:
            raise SystemExit("municipality name or --id is required")
        m = municipality_id(args.municipality)
    print("municipality:", m)
    records, uniq = fetch_metadata(m["id"])
    print(f"records: {len(records)}, unique documents: {len(uniq)}")
    os.makedirs(os.path.join(ROOT, "odbori", "meta"), exist_ok=True)
    meta_path = os.path.join(ROOT, "odbori", "meta", args.slug + ".json")
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    m["slug"] = args.slug
    m["region"] = args.region
    m["region_name"] = args.region_name
    json.dump(
        {
            "municipality": m,
            "election_round": ELECTION_ROUND,
            "fetched_at": fetched_at,
            "documents": records,
        },
        open(meta_path, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print("metadata:", meta_path)
    dw = args.download_workers or args.workers
    ow = args.ocr_workers or args.workers
    if not args.skip_download:
        download([r["_url"] for r in uniq], args.slug, dw)
    if not args.skip_ocr:
        ocr(args.slug, ow, args.dpi)


if __name__ == "__main__":
    main()
