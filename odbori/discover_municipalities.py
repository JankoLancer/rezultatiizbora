#!/usr/bin/env python3
"""Discover all municipalities for the 2026 parliamentary election and
optionally fetch their committee-document metadata.

Output: odbori/municipalities_2026.json
  [{slug,name,region,region_name,id,data_id,stations,documents,fetched_at,...}]

Run:
  python3 odbori/discover_municipalities.py --metadata
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
sys.path.insert(0, ROOT)
from city_slugs import city_slug  # noqa: E402

BASE = "https://www.rik.parlament.gov.rs"
ELECTION_ROUND = "680072"
HEADERS = {
    "User-Agent": "rezultatiizbora.rs/1.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE + "/542645/rezultati/",
}
OUT = os.path.join(ROOT, "odbori", "municipalities_2026.json")
META = os.path.join(ROOT, "odbori", "meta")


def post(path, data, timeout=45):
    r = requests.post(BASE + path, data=data, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def get_municipalities():
    regions = post("/get-regions/", {"election_type": 2, "election_round": ELECTION_ROUND}).json()["regions"]
    out = []
    for rid, rname in regions.items():
        r = post(
            "/get-municipalities/",
            {"election_type": 2, "election_round": ELECTION_ROUND, "election_region": rid},
        )
        for data_id, mid, name in re.findall(
            r'<option data-id="(\d+)" value="(\d+)">([^<]+)</option>', r.text
        ):
            out.append(
                {
                    "region": rid,
                    "region_name": html.unescape(rname).strip(),
                    "data_id": data_id,
                    "id": mid,
                    "name": html.unescape(name).strip(),
                }
            )
    return out


def station_count(m):
    d = post(
        "/get-election-stations/",
        {
            "election_type": 2,
            "election_round": ELECTION_ROUND,
            "election_region": m["region"],
            "election_municipality": m["id"],
        },
    ).json()
    return len(d.get("election_stations") or {})


def fetch_metadata(m):
    records = []
    page = 1
    while True:
        r = requests.get(
            BASE + "/get-additional-documents",
            params={
                "page": page,
                "filters[document-type]": 4,
                "filters[election-round]": ELECTION_ROUND,
                "filters[municipality-id]": m["id"],
                "order": 1,
                "sort": 1,
                "election_type": 2,
            },
            headers=HEADERS,
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        records += d.get("records", [])
        pages = [int(x) for x in re.findall(r'data-page="(\d+)"', d.get("pagination", ""))]
        last = max(pages) if pages else page
        if page >= last:
            break
        page += 1
        time.sleep(0.1)
    for rec in records:
        mm = re.search(r'href="([^"]+)"', (rec.get("extfiles_link") or [""])[0])
        rec["_url"] = html.unescape(mm.group(1)) if mm else ""
    seen, uniq = set(), []
    for rec in records:
        if rec["_url"] and rec["_url"] not in seen:
            seen.add(rec["_url"])
            uniq.append(rec)
    return records, uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", action="store_true", help="fetch document metadata for every municipality")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", nargs="*", help="limit to slugs or names")
    args = ap.parse_args()

    municipalities = get_municipalities()
    print("municipalities:", len(municipalities))

    # slug uniqueness
    used = {}
    for m in municipalities:
        s = city_slug(m["name"])
        if s in used:
            s = f"{s}-{m['id']}"
        used[s] = m
        m["slug"] = s

    for i, m in enumerate(municipalities, 1):
        try:
            m["stations"] = station_count(m)
        except Exception as e:
            m["stations"] = None
            print("station count failed", m["name"], e)
        if i % 25 == 0:
            print("stations", i)

    if args.only:
        wanted = set(args.only)
        municipalities = [m for m in municipalities if m["slug"] in wanted or m["name"] in wanted]
        print("limited to", len(municipalities))

    if args.metadata:
        os.makedirs(META, exist_ok=True)

        def work(m):
            records, uniq = fetch_metadata(m)
            m["documents"] = len(uniq)
            m["document_records"] = len(records)
            m["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            json.dump(
                {
                    "municipality": {"id": m["id"], "data_id": m["data_id"], "name": m["name"], "slug": m["slug"]},
                    "region": m["region"],
                    "region_name": m["region_name"],
                    "election_round": ELECTION_ROUND,
                    "fetched_at": m["fetched_at"],
                    "documents": records,
                },
                open(os.path.join(META, m["slug"] + ".json"), "w", encoding="utf-8"),
                ensure_ascii=False,
            )
            return m["slug"], len(uniq)

        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(work, m): m for m in municipalities}
            for f in as_completed(futs):
                m = futs[f]
                try:
                    slug, n = f.result()
                    print(f"  {slug}: {n} docs")
                except Exception as e:
                    print("metadata failed", m["name"], repr(e))
                    m["documents"] = None
                done += 1
                if done % 10 == 0:
                    print("metadata", done, "/", len(municipalities))

    json.dump(municipalities, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", OUT)
    print("stations total:", sum(m.get("stations") or 0 for m in municipalities))
    print("documents total:", sum(m.get("documents") or 0 for m in municipalities))


if __name__ == "__main__":
    main()
