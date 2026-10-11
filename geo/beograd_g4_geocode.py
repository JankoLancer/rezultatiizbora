#!/usr/bin/env python3
"""Geocode the g4 Belgrade-municipality stations by address.

Adapted from geo/geocode_nis_addr.py / geocode_subotica_addr.py.
Nominatim, Belgrade-area viewbox, 4.5 s between uncached requests (shared IP,
other agents run in parallel), cache in geo/beograd_g4_cache.json.

Input : geo/beograd_g4_locations.json
Output: geo/beograd_g4_geo.json
"""
import json
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "beograd_g4_locations.json")
OUT = os.path.join(BASE, "beograd_g4_geo.json")
CACHE = os.path.join(BASE, "beograd_g4_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "20.10,44.30,20.95,45.15"          # Belgrade + outer municipalities
SLEEP = 4.5
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}


def clean(a):
    a = re.sub(r"\([^)]*\)", " ", a)          # drop parenthetical notes
    a = re.sub(r"\bБР\.?(?=\s*\d)", " ", a)    # strip "БР." only before a number
    a = re.sub(r"\bББ\b", " ", a)
    return re.sub(r"\s+", " ", a).strip(" ,")


def strip_num(rest):
    """Drop a trailing house number such as '19', '11/А', '1-А'."""
    return re.sub(r"\s*\d+\s*([/\-]\s*[А-ЯЂЈЉЊЋЏA-Z0-9]+)?\s*$", "", rest).strip(" ,")


def queries(addr):
    a = addr.strip()
    c = clean(a)
    qs = []
    if "," in a:
        sett, rest_raw = a.split(",", 1)
        sett = sett.strip()
        rest = clean(rest_raw)
        qs.append(f"{rest}, {sett}, Београд, Србија")
        st = strip_num(rest)
        if st and st != rest:
            qs.append(f"{st}, {sett}, Београд, Србија")
        qs.append(f"{sett}, Београд, Србија")
        qs.append(f"{sett}, Србија")
    else:
        qs.append(f"{c}, Београд, Србија")
        st = strip_num(c)
        if st and st != c:
            qs.append(f"{st}, Београд, Србија")
        qs.append(f"{c}, Србија")
    qs.append(f"{c}, Србија")
    seen, uniq = set(), []
    for q in qs:
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def search(q):
    if q in cache:
        return cache[q]
    res = None
    for attempt in range(1, 4):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5,
                                     "countrycodes": "rs", "viewbox": VIEWBOX,
                                     "bounded": 1}, headers=H, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data:
                    pick = next((d for d in data if d.get("class") in GOOD), data[0])
                    res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                           "display": pick.get("display_name", ""), "type": pick.get("type")}
                break
        except Exception:
            time.sleep(3 * attempt)
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


rows = json.load(open(IN, encoding="utf-8"))
out = []
for r in rows:
    hit = used = None
    for q in queries(r["address"]):
        hit = search(q)
        if hit:
            used = q
            break
    out.append({**r, "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
                "display": hit["display"] if hit else None, "source": "address",
                "geocoded_with": used})
    print(f"{r['municipality'].split()[-1][:10]:<10} {r['no']:>3} {'OK ' if hit else 'X  '} "
          f"{r['address'][:44]:<44} -> "
          f"{'' if not hit else str(round(hit['lat'],4))+','+str(round(hit['lon'],4))}")

miss = sum(1 for s in out if s["lat"] is None)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")
