#!/usr/bin/env python3
"""Geocode Belgrade-g1 stations (Novi Beograd, Zemun, Surčin, Barajevo) by address.

Adapted from geo/geocode_nis_addr.py.  Nominatim (countrycodes=rs, bounded
Belgrade viewbox), 4.5 s between uncached requests (shared IP), cache in
geo/beograd_g1_cache.json.  Output geo/beograd_g1_geo.json.
"""
import json
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "beograd_g1_locations.json")
OUT = os.path.join(BASE, "beograd_g1_geo.json")
CACHE = os.path.join(BASE, "beograd_g1_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "20.10,44.30,20.95,45.15"          # Belgrade city area
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place", "shop"}
SLEEP = 4.5

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

MAIN_CITY = {
    "Градска општина Нови Београд": "Нови Београд",
    "Градска општина Земун": "Земун",
    "Градска општина Сурчин": "Сурчин",
    "Градска општина Барајево": "Барајево",
}
# Settlement names that can begin an address (village prefix without comma).
SETTLEMENTS = {
    "Градска општина Нови Београд": ["НОВИ БЕОГРАД"],
    "Градска општина Земун": ["ЗЕМУН", "ЗЕМУН ПОЉЕ", "БАТАЈНИЦА", "АЛТИНА", "УГРИНОВЦИ"],
    "Градска општина Сурчин": ["ДОБАНОВЦИ", "СУРЧИН", "БЕЧМЕН", "ПЕТРОВЋИЋ",
                               "ЈАКОВО", "БОЉЕВЦИ", "ПРОГАР"],
    "Градска општина Барајево": ["БАРАЈЕВО", "АРНАЈЕВО", "БАЋЕВАЦ", "БЕЛАНОВИЦА",
                                 "БОЖДАРЕВАЦ", "ВРАНИЋ", "ГУНЦАТЕ", "ЛИПОВИЦА",
                                 "МАЛИ ПОЖАРЕВАЦ", "МЕЉАК", "РОЖАНЦИ", "СРЕМЧИЦА",
                                 "ШИЉАКОВАЦ", "ВЕЛИКИ БОРАК"],
}


def clean(a):
    # NB: consume the dot or a word boundary so street names like БРОДАРСКА survive
    a = re.sub(r"\bБР(?:\.|\b)\s*:?\s*", " ", a, flags=re.I)
    a = re.sub(r"\bББ\b", " ", a, flags=re.I)
    a = a.replace("–", "-").replace(":", " ")
    return re.sub(r"\s+", " ", a).strip(" ,")


def strip_num(rest):
    """Drop a trailing house number such as '19', '11/А', '1-А', '386 Д'."""
    return re.sub(r"\s*\d+(\s*[/\-]\s*[А-ЯЂЈЉЊЋЏA-Z0-9]+)?\s*$", "", rest).strip(" ,")


def split_addr(addr, muni):
    a = addr.strip()
    settlements = SETTLEMENTS[muni]
    up = a.upper()
    settlement, rest = None, a
    if "," in a:
        head, tail = a.split(",", 1)
        settlement, rest = head.strip(), tail.strip()
    else:
        for s in sorted(settlements, key=len, reverse=True):
            if up.startswith(s):
                settlement, rest = a[:len(s)].strip(), a[len(s):].strip()
                break
    if not settlement:
        settlement, rest = MAIN_CITY[muni], a
    return settlement, clean(rest)


def queries(addr, muni):
    settlement, rest = split_addr(addr, muni)
    qs = [f"{rest}, {settlement}, Београд, Србија"]
    street = strip_num(rest)
    if street and street != rest:
        qs.append(f"{street}, {settlement}, Београд, Србија")
    qs.append(f"{settlement}, Београд, Србија")
    qs.append(f"{settlement}, Србија")
    qs.append(f"{clean(addr)}, Србија")
    seen, out = set(), []
    for q in qs:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def search(q):
    if q in cache:
        return cache[q], False
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                 "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
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
    return res, True


def main():
    rows = json.load(open(IN, encoding="utf-8"))
    out, n_req = [], 0
    for r in rows:
        hit = used = None
        for q in queries(r["address"], r["municipality"]):
            hit, fresh = search(q)
            n_req += int(fresh)
            if hit:
                used = q
                break
        out.append({**r, "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
                    "display": hit["display"] if hit else None, "source": "address",
                    "geocoded_with": used})
        print(f"{r['municipality'][-12:]:<12} {r['no']:>3} {'OK ' if hit else 'X  '} "
              f"{r['address'][:40]:<40} -> "
              f"{'' if not hit else str(round(hit['lat'], 4))+','+str(round(hit['lon'], 4))}")
    miss = sum(1 for s in out if s["lat"] is None)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}; live requests {n_req}")


if __name__ == "__main__":
    main()
