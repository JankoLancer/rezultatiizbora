#!/usr/bin/env python3
"""Apply a municipality-level station audit: add missing documents, download,
OCR, parse and rebuild the affected municipalities.

Input audit JSON is produced by audit_municipality_docs.py.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "odbori"))
import scrape_odbori as so  # noqa: E402

META = os.path.join(ROOT, "odbori", "meta")
MANUAL = os.path.join(ROOT, "odbori", "manual_docs")
DATA = os.path.join(ROOT, "odbori", "data")
PARSER = os.path.join(ROOT, "odbori", "parse_odbori.py")
BUILDER = os.path.join(ROOT, "odbori", "build_odbori.py")


def add_docs(slug, records):
    meta_path = os.path.join(META, slug + ".json")
    meta = json.load(open(meta_path, encoding="utf-8"))
    docs = meta.get("documents", [])
    seen = {r.get("_url") for r in docs if r.get("_url")}
    added = []
    for rec in records:
        url = rec.get("_url")
        if not url:
            m = so.re.search(r'href="([^"]+)"', (rec.get("extfiles_link") or [""])[0])
            url = m.group(1) if m else ""
        if not url or url in seen:
            continue
        rec = dict(rec); rec["_url"] = url
        docs.append(rec); added.append(rec); seen.add(url)
    if not added:
        return 0
    meta["documents"] = docs
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.makedirs(MANUAL, exist_ok=True)
    mp = os.path.join(MANUAL, slug + ".json")
    manual = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"documents": []}
    md = manual.setdefault("documents", [])
    mseen = {x.get("_url") for x in md if x.get("_url")}
    for rec in added:
        if rec["_url"] not in mseen:
            md.append(rec); mseen.add(rec["_url"])
    json.dump(manual, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(added)


def process(row, args):
    slug = row["slug"]
    records = row.get("new_docs") or []
    if not records:
        return slug, 0, "no new docs"
    try:
        n = add_docs(slug, records)
        if n == 0:
            return slug, 0, "already present"
        urls = [r["_url"] for r in records if r.get("_url")]
        so.download(urls, slug, args.download_workers)
        so.ocr(slug, args.ocr_workers, args.dpi)
        for cmd in ([sys.executable, PARSER, slug], [sys.executable, BUILDER, slug]):
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                return slug, n, "ERROR " + (r.stderr or r.stdout)[-300:]
        return slug, n, "ok"
    except Exception as e:
        return slug, 0, "ERROR " + repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--download-workers", type=int, default=3)
    ap.add_argument("--ocr-workers", type=int, default=2)
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    data = json.load(open(args.audit, encoding="utf-8"))
    rows = [c for c in data["cities"] if (not args.only or c["slug"] in set(args.only))]
    rows = [c for c in rows if c.get("new_docs")]
    print(f"applying {len(rows)} cities, {sum(len(c.get('new_docs',[])) for c in rows)} documents", flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, r, args): r for r in rows}
        for i, f in enumerate(as_completed(futs), 1):
            slug, n, status = f.result()
            print(f"{i}/{len(rows)} {slug}: {n} new, {status}", flush=True)
            if status == "ok": ok += 1
    print(f"done {ok}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
