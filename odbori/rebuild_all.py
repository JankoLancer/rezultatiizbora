#!/usr/bin/env python3
"""Re-parse and/or rebuild all already downloaded municipalities.

Useful after changing list mappings or the parser: OCR is not repeated.

  python3 odbori/rebuild_all.py --parse --build --workers 4
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "odbori", "meta")
DATA = os.path.join(ROOT, "odbori", "data")


def slugs():
    out = []
    for p in sorted(glob.glob(os.path.join(META, "*.json"))):
        slug = os.path.basename(p)[:-5]
        if os.path.exists(os.path.join(DATA, slug + "_decisions.json")) or glob.glob(os.path.join(ROOT, "odbori", "ocr", slug, "*.txt")):
            out.append(slug)
    return out


def run_one(slug, do_parse, do_build):
    if do_parse:
        r = subprocess.run([sys.executable, "odbori/parse_odbori.py", slug], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return slug, "parse", r.stderr[-500:]
    if do_build:
        r = subprocess.run([sys.executable, "odbori/build_odbori.py", slug], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return slug, "build", r.stderr[-500:]
    return slug, "ok", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    if not args.parse and not args.build:
        ap.error("use --parse and/or --build")
    todo = args.only or slugs()
    print(f"{len(todo)} municipalities")
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, s, args.parse, args.build) for s in todo]
        for i, f in enumerate(as_completed(futs), 1):
            slug, what, err = f.result()
            if what != "ok":
                errors.append((slug, what, err))
                print("ERR", slug, what, err[:200])
            if i % 20 == 0:
                print(i, "/", len(todo))
    print("done, errors:", len(errors))


if __name__ == "__main__":
    main()
