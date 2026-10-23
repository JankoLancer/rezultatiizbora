#!/usr/bin/env python3
"""Fast read-only audit: municipality-level RIK queries by document subtype.

The plain municipality listing is incomplete. Querying with
filters[election_station]=-1 and filters[additional-data]=1/2/0 returns the
permanent, expanded and all/change documents, including documents the plain
listing omits.

Usage:
  python3 odbori/audit_municipality_docs.py --out /tmp/audit.json
"""
import argparse
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.rik.parlament.gov.rs"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "rezultatiizbora.rs/audit/1.0"}
MUNI = os.path.join(ROOT, "odbori", "municipalities_2026.json")
_tls = threading.local()


def session():
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        a = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=2)
        s.mount("https://", a)
        s.mount("http://", a)
        _tls.s = s
    return s


def doc_url(rec):
    m = re.search(r'href="([^"]+)"', (rec.get("extfiles_link") or [""])[0])
    return html.unescape(m.group(1)) if m else rec.get("_url") or ""


def get_page(mid, ad, page):
    p = {
        "page": page,
        "filters[document-type]": "4",
        "filters[election-round]": "680072",
        "filters[municipality-id]": mid,
        "filters[election_station]": "-1",
        "filters[additional-data]": ad,
        "order": 2,
        "sort": 2,
        "election_type": 2,
    }
    s = session()
    for attempt in range(3):
        try:
            r = s.get(BASE + "/get-additional-documents", params=p, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def fetch_filter(mid, ad):
    d = get_page(mid, ad, 1)
    first = d.get("records", [])
    pages = [int(x) for x in re.findall(r"data-page=\"(\d+)\"", d.get("pagination", ""))]
    last = max(pages) if pages else 1
    rest = []
    if last > 1:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(get_page, mid, ad, p) for p in range(2, last + 1)]
            for f in as_completed(futs):
                try:
                    rest += f.result().get("records", [])
                except Exception:
                    pass
    return first + rest


def audit_city(m):
    meta_path = os.path.join(ROOT, "odbori", "meta", m["slug"] + ".json")
    if not os.path.exists(meta_path):
        return {"slug": m["slug"], "name": m.get("name", m["slug"]), "error": "missing local meta"}
    meta = json.load(open(meta_path, encoding="utf-8"))
    mid = str(meta.get("municipality", {}).get("id") or m["id"])
    local = {doc_url(r) for r in meta.get("documents", []) if doc_url(r)}
    current = {}
    errors = []
    for ad in ("1", "2", "0"):
        try:
            for rec in fetch_filter(mid, ad):
                u = doc_url(rec)
                if u:
                    rec["_url"] = u
                    current[u] = rec
        except Exception as e:
            errors.append({"additional_data": ad, "error": repr(e)})
    new = [rec for u, rec in current.items() if u not in local]
    removed = [u for u in local if u not in current]
    return {
        "slug": m["slug"],
        "name": m.get("name", m["slug"]),
        "current_unique": len(current),
        "local_unique": len(local),
        "new_docs": new,
        "removed": removed,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", nargs="*", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
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
    munis = json.load(open(MUNI, encoding="utf-8"))
    if args.slugs:
        wanted = set(args.slugs)
        munis = [m for m in munis if m["slug"] in wanted]
    munis = [m for m in munis if m["slug"] not in done]
    print(f"todo {len(munis)} cities", flush=True)
    out = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_city, m): m for m in munis}
        for i, f in enumerate(as_completed(futs), 1):
            m = futs[f]
            try:
                row = f.result()
                out.append(row)
                with open(partial, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"{m['slug']}: +{len(row.get('new_docs', []))} -{len(row.get('removed', []))} errors={len(row.get('errors', []))}", flush=True)
            except Exception as e:
                print("ERR", m["slug"], repr(e), flush=True)
            if i % 10 == 0:
                print(f"progress {i}/{len(munis)} elapsed {round(time.time()-t0)}s", flush=True)
    out.sort(key=lambda x: (-len(x.get("new_docs", [])), x["slug"]))
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cities": out}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE", len(out), "cities, elapsed", round(time.time()-t0), "s", flush=True)


if __name__ == "__main__":
    main()
