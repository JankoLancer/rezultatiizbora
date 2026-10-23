#!/usr/bin/env python3
"""Targeted RIK re-audit for polling stations where the Student list is absent.

The target set is supplied as JSON (slug/no). The script first checks the
station-level RIK endpoint, optionally applies newly found documents, and can
force a fresh OCR pass for every document belonging to those stations.

Usage:
  python3 odbori/reaudit_student_gaps.py --targets /tmp/opencode/student_gap_stations.json --out /tmp/opencode/student_rik.json
  python3 odbori/reaudit_student_gaps.py --targets ... --out ... --apply --force-ocr --rebuild
"""
import argparse
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
sys.path.insert(0, os.path.join(ROOT, "odbori"))
import scrape_odbori as so  # noqa: E402

BASE = "https://www.rik.parlament.gov.rs"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "rezultatiizbora.rs/audit/1.0"}


def doc_url(rec):
    m = re.search(r'href="([^"]+)"', (rec.get("extfiles_link") or [""])[0])
    return html.unescape(m.group(1)) if m else rec.get("_url") or ""


def get_station_docs(s, mid, sid):
    params = {
        "page": 1,
        "filters[document-type]": "4",
        "filters[election-round]": "680072",
        "filters[municipality-id]": mid,
        "filters[election_station]": sid,
        "order": 2,
        "sort": 2,
        "election_type": 2,
    }
    for attempt in range(3):
        try:
            r = s.get(BASE + "/get-additional-documents", params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("records", [])
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def audit_city(slug, targets):
    meta_path = os.path.join(ROOT, "odbori", "meta", slug + ".json")
    stations_path = os.path.join(ROOT, "odbori", "stations", slug + ".json")
    meta = json.load(open(meta_path, encoding="utf-8"))
    stations = json.load(open(stations_path, encoding="utf-8"))
    mid = str(meta.get("municipality", {}).get("id"))
    local = {doc_url(r) for r in meta.get("documents", []) if doc_url(r)}
    no_to_sid = {}
    for sid, title in stations.items():
        m = re.match(r"\s*(\d+)", str(title))
        if m:
            no_to_sid.setdefault(int(m.group(1)), sid)
    s = requests.Session()
    s.headers.update(HEADERS)
    a = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
    s.mount("https://", a)
    rows = []
    for no in sorted(targets):
        sid = no_to_sid.get(no)
        if not sid:
            rows.append({"no": no, "error": "no station id"})
            continue
        try:
            recs = get_station_docs(s, mid, sid)
        except Exception as e:
            rows.append({"no": no, "sid": sid, "error": repr(e)})
            continue
        current = []
        for rec in recs:
            u = doc_url(rec)
            if u:
                rec["_url"] = u
                current.append(rec)
        new = [r for r in current if r["_url"] not in local]
        rows.append({
            "no": no,
            "sid": sid,
            "station_title": next((t for t in stations.values() if re.match(rf"\s*{no}\b", str(t))), ""),
            "rik_records": len(current),
            "new_docs": new,
        })
    return {"slug": slug, "municipality_id": mid, "stations": rows}


def add_docs(slug, docs):
    if not docs:
        return 0
    meta_path = os.path.join(ROOT, "odbori", "meta", slug + ".json")
    meta = json.load(open(meta_path, encoding="utf-8"))
    existing = {doc_url(r) for r in meta.get("documents", []) if doc_url(r)}
    added = []
    for rec in docs:
        if rec.get("_url") and rec["_url"] not in existing:
            meta["documents"].append(rec)
            existing.add(rec["_url"])
            added.append(rec)
    if not added:
        return 0
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    manual_path = os.path.join(ROOT, "odbori", "manual_docs", slug + ".json")
    manual = json.load(open(manual_path, encoding="utf-8")) if os.path.exists(manual_path) else {"documents": []}
    seen = {r.get("_url") for r in manual.get("documents", []) if r.get("_url")}
    for rec in added:
        if rec["_url"] not in seen:
            manual["documents"].append(rec)
            seen.add(rec["_url"])
    os.makedirs(os.path.dirname(manual_path), exist_ok=True)
    json.dump(manual, open(manual_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(added)


def force_ocr(slug, docs, dpi, psm):
    pdfdir = os.path.join(ROOT, "odbori", "pdf", slug)
    ocrdir = os.path.join(ROOT, "odbori", "ocr", slug)
    os.makedirs(ocrdir, exist_ok=True)
    todo = []
    for rec in docs:
        u = rec.get("_url") or ""
        if not u:
            continue
        key = so.pdf_key(u)
        pdf = os.path.join(pdfdir, key)
        if not os.path.exists(pdf) or os.path.getsize(pdf) < 1000:
            so.download([u], slug, 1)
        if not os.path.exists(pdf):
            continue
        todo.append((pdf, os.path.join(ocrdir, os.path.splitext(key)[0] + ".txt")))
    def one(pair):
        pdf, dst = pair
        if os.path.exists(dst) and not os.path.exists(dst + ".pre_reocr"):
            os.replace(dst, dst + ".pre_reocr")
        with tempfile.TemporaryDirectory(prefix="rikreocr_") as td:
            base = os.path.join(td, "p")
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", pdf, base],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
            )
            chunks = []
            for img in sorted(
                os.path.join(td, f) for f in os.listdir(td) if f.startswith("p") and f.endswith(".png")
            ):
                r = subprocess.run(
                    ["tesseract", img, "stdout", "-l", "srp", "--psm", str(psm)],
                    capture_output=True, text=True, timeout=120,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
                chunks.append(r.stdout)
            open(dst, "w", encoding="utf-8").write("\n\f\n".join(chunks))
            return dst

    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, p) for p in todo]
        for f in as_completed(futs):
            try:
                f.result()
                done += 1
            except Exception as e:
                print("OCR FAILED", e, flush=True)
    return len(todo), done


def rebuild(slug):
    for cmd in ([sys.executable, "odbori/parse_odbori.py", slug],
                [sys.executable, "odbori/build_odbori.py", slug]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return "ERROR " + (r.stderr or r.stdout)[-300:]
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--psm", type=int, default=6)
    args = ap.parse_args()
    data = json.load(open(args.targets, encoding="utf-8"))
    grouped = {}
    for row in data["stations"]:
        grouped.setdefault(row["slug"], []).append(row["no"])
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_city, slug, nos): slug for slug, nos in grouped.items()}
        for f in as_completed(futs):
            slug = futs[f]
            try:
                row = f.result()
                results.append(row)
                n = sum(len(x.get("new_docs", [])) for x in row["stations"])
                print(f"{slug}: stations={len(row['stations'])} new_docs={n}", flush=True)
            except Exception as e:
                print("ERR", slug, repr(e), flush=True)
                results.append({"slug": slug, "error": repr(e)})
    results.sort(key=lambda x: x["slug"])
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cities": results},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    new_total = sum(len(x.get("new_docs", [])) for c in results for x in c.get("stations", []))
    print(f"DONE cities={len(results)} new_docs={new_total}", flush=True)

    if args.apply:
        for city in results:
            docs = [r for st in city.get("stations", []) for r in st.get("new_docs", [])]
            if docs:
                n = add_docs(city["slug"], docs)
                so.download([r["_url"] for r in docs], city["slug"], 4)
                print(f"APPLIED {city['slug']}: {n} docs", flush=True)
    if args.force_ocr:
        for city in results:
            docs = []
            for st in city.get("stations", []):
                no = st["no"]
                for rec in st.get("new_docs", []):
                    docs.append(rec)
                # Also include local documents for this station.
                meta = json.load(open(os.path.join(ROOT, "odbori", "meta", city["slug"] + ".json"), encoding="utf-8"))
                for rec in meta.get("documents", []):
                    if re.match(rf"\s*{no}\b", rec.get("election_station_title", "") or ""):
                        docs.append(rec)
            # de-duplicate by URL
            uniq = {r.get("_url"): r for r in docs if r.get("_url")}
            if uniq:
                total, done = force_ocr(city["slug"], list(uniq.values()), args.dpi, args.psm)
                print(f"REOCR {city['slug']}: {done}/{total}", flush=True)
    if args.rebuild:
        for city in results:
            print(f"REBUILD {city['slug']}: {rebuild(city['slug'])}", flush=True)


if __name__ == "__main__":
    main()
