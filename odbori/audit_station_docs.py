#!/usr/bin/env python3
"""Read-only station-level audit of RIK committee documents.

The municipality-level /get-additional-documents listing is incomplete for some
stations; querying with filters[election_station] returns the missing documents.
This script compares those station-level results with the local metadata.

Usage:
  python3 odbori/audit_station_docs.py --slugs aleksandrovac --out /tmp/audit.json
"""
import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.rik.parlament.gov.rs"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "rezultatiizbora.rs/audit/1.0"}
MUNI = os.path.join(ROOT, "odbori", "municipalities_2026.json")


def doc_url(rec):
    m = re.search(r'href="([^"]+)"', (rec.get("extfiles_link") or [""])[0])
    return html.unescape(m.group(1)) if m else rec.get("_url") or ""


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    a = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
    s.mount("https://", a)
    s.mount("http://", a)
    return s


def fetch_station(s, mid, sid):
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
    r = s.get(BASE + "/get-additional-documents", params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])


def audit_city(m):
    slug = m["slug"]
    meta_path = os.path.join(ROOT, "odbori", "meta", slug + ".json")
    stations_path = os.path.join(ROOT, "odbori", "stations", slug + ".json")
    if not os.path.exists(meta_path) or not os.path.exists(stations_path):
        return {"slug": slug, "name": m.get("name", slug), "error": "missing local files"}
    meta = json.load(open(meta_path, encoding="utf-8"))
    mid = str(meta.get("municipality", {}).get("id") or m["id"])
    local = {doc_url(r) for r in meta.get("documents", []) if doc_url(r)}
    stations = json.load(open(stations_path, encoding="utf-8"))
    current = {}
    errors = []
    s = session()
    for sid, title in stations.items():
        for attempt in range(2):
            try:
                for rec in fetch_station(s, mid, sid):
                    u = doc_url(rec)
                    if u:
                        rec["_url"] = u
                        current[u] = rec
                break
            except Exception as e:
                if attempt == 1:
                    errors.append({"station_id": sid, "title": title, "error": repr(e)})
                else:
                    time.sleep(1 + attempt)
    new = [rec for u, rec in current.items() if u not in local]
    removed = [u for u in local if u not in current]
    return {
        "slug": slug,
        "name": m.get("name", slug),
        "stations_checked": len(stations),
        "current_unique": len(current),
        "local_unique": len(local),
        "new_docs": new,
        "removed": removed,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", nargs="*", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    partial = args.out + ".jsonl"
    done = set()
    if args.resume and os.path.exists(partial):
        for line in open(partial, encoding="utf-8"):
            try:
                done.add(json.loads(line)["slug"])
            except Exception:
                pass
    all_m = {m["slug"]: m for m in json.load(open(MUNI, encoding="utf-8"))}
    todo = [all_m[s] for s in args.slugs if s in all_m and s not in done]
    out = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_city, m): m for m in todo}
        for i, f in enumerate(as_completed(futs), 1):
            m = futs[f]
            try:
                row = f.result()
                out.append(row)
                with open(partial, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                n = len(row.get("new_docs", []))
                r = len(row.get("removed", []))
                if n or r or row.get("errors"):
                    print(f"{m['slug']}: +{n} -{r} errors={len(row.get('errors', []))}", flush=True)
            except Exception as e:
                out.append({"slug": m["slug"], "name": m.get("name"), "error": repr(e)})
                print("ERR", m["slug"], repr(e), flush=True)
            if i % 20 == 0:
                print(f"progress {i}/{len(todo)} elapsed {round(time.time()-t0)}s", flush=True)
    out.sort(key=lambda x: (-len(x.get("new_docs", [])), x["slug"]))
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cities": out}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE", len(out), "cities, elapsed", round(time.time()-t0), "s", flush=True)


if __name__ == "__main__":
    main()
