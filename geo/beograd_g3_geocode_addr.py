#!/usr/bin/env python3
"""Geocode Belgrade g3 polling stations from the official 2022-referendum
addresses (Vozdovac, Zvezdara, Vracar, Stari Grad).

Adapted from geo/geocode_nis_addr.py.  Input : geo/beograd_g3_locations.json
Output: geo/beograd_g3_geo.json    Cache: geo/beograd_g3_cache.json

Fallback chain per station:
   1. full address   "<street no>, <opstina>, Београд, Србија"
   2. street-only    "<street>, <opstina>, Београд, Србија"
   3. address w/o municipality
   4. settlement/opstina ("<opstina>, Београд, Србија")
"""
import json
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "beograd_g3_locations.json")
OUT = os.path.join(BASE, "beograd_g3_geo.json")
CACHE = os.path.join(BASE, "beograd_g3_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "20.10,44.30,20.95,45.15"   # Belgrade area (left,top,right,bottom)
SLEEP = 4.5
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}

SHORT = {
    "Градска општина Вождовац": "Вождовац",
    "Градска општина Звездара": "Звездара",
    "Градска општина Врачар": "Врачар",
    "Градска општина Стари Град": "Стари Град",
}


def clean(a):
    a = re.sub(r"\bБРОЈ\b", " ", a, flags=re.I)
    a = re.sub(r"\bБР\.?", " ", a, flags=re.I)
    a = a.replace("ББ", " ")
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def queries(addr, muni):
    a = addr.strip()
    c = clean(a)
    short = SHORT.get(muni, muni)
    qs = []
    qs.append(f"{c}, {short}, Београд, Србија")
    street = re.sub(r"\s*\d+[A-Za-zА-Ша-ш]?\s*$", "", c).strip(" ,")
    if street and street != c:
        qs.append(f"{street}, {short}, Београд, Србија")
    qs.append(f"{c}, Београд, Србија")
    if street:
        qs.append(f"{street}, Београд, Србија")
    qs.append(f"{short}, Београд, Србија")
    # de-dup, keep order
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def search(q):
    if q in cache:
        return cache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 5,
                                 "countrycodes": "rs", "viewbox": VIEWBOX,
                                 "bounded": 1}, headers=H, timeout=30)
        data = r.json()
        if data:
            pick = next((d for d in data if d.get("class") in GOOD), data[0])
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", ""), "type": pick.get("type")}
    except Exception:
        res = None
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    rows = json.load(open(IN, encoding="utf-8"))
    out = []
    for r in rows:
        hit = used = None
        if r["address"].strip():
            for q in queries(r["address"], r["municipality"]):
                hit = search(q)
                if hit:
                    used = q
                    break
        out.append({**r, "lat": hit["lat"] if hit else None,
                    "lon": hit["lon"] if hit else None,
                    "display": hit["display"] if hit else None,
                    "source": "address", "geocoded_with": used})
        print(f"{SHORT.get(r['municipality'], r['municipality'])[:11]:<11} {r['no']:>3} "
              f"{'OK ' if hit else 'X  '} {r['address'][:40]:<40} -> "
              f"{'' if not hit else str(round(hit['lat'], 5)) + ',' + str(round(hit['lon'], 5))}")
    miss = sum(1 for s in out if s["lat"] is None)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nGeocoded {len(out) - miss}/{len(out)}; missing {miss} -> {OUT}")


if __name__ == "__main__":
    main()
