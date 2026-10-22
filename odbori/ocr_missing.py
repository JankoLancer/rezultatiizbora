#!/usr/bin/env python3
"""OCR any PDF that does not have a cached .txt (including uppercase .PDF)."""
import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "odbori"))
from scrape_odbori import ocr  # noqa: E402


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    slugs = []
    for d in sorted(glob.glob(os.path.join(ROOT, "odbori", "pdf", "*"))):
        if not os.path.isdir(d):
            continue
        pdfs = [p for p in glob.glob(os.path.join(d, "*")) if p.lower().endswith(".pdf")]
        outdir = os.path.join(ROOT, "odbori", "ocr", os.path.basename(d))
        missing = [p for p in pdfs if not os.path.exists(os.path.join(outdir, os.path.splitext(os.path.basename(p))[0] + ".txt"))]
        if missing:
            slugs.append((os.path.basename(d), len(missing)))
    print("cities with missing OCR:", len(slugs), "documents:", sum(n for _, n in slugs))
    for slug, n in slugs:
        print(slug, n)
    for slug, _ in slugs:
        ocr(slug, workers=workers)
    print("done")


if __name__ == "__main__":
    main()
