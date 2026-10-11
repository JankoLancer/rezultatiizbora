#!/usr/bin/env python3
"""Geocode Grad Čačak stations from the official 2022 referendum addresses.

Adapted from geo/geocode_nis_addr.py.  Nominatim with the Čačak viewbox,
4.0 s between uncached requests, cache in geo/cacak_cache.json.
Output: geo/cacak_stations_geo.json
"""
import json
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "cacak_stations_locations.json")
OUT = os.path.join(BASE, "cacak_stations_geo.json")
CACHE = os.path.join(BASE, "cacak_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0"}
VIEWBOX = "20.10,43.70,20.60,44.05"          # Grad Čačak municipality
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}


def clean(a):
    a = re.sub(r"БР\.\s*", " ", a)   # require the dot so "БРАЋЕ" is not touched
    a = a.replace("ББ", " ")
    return re.sub(r"\s+", " ", a).strip(" ,")


def strip_num(rest):
    """Drop a trailing house number such as '19', '11/А', '1-А'."""
    return re.sub(r"\s*\d+(\s*[/\-]\s*[А-ЯЂЈЉЊЋЏA-Z0-9]+)?\s*$", "", rest).strip(" ,")


def queries(addr):
    a = addr.strip()
    c = clean(a)
    qs = []
    m = re.match(r"ЧАЧАК\s*,\s*(.+)", a, re.I)
    if m:
        rest = clean(m.group(1))
        qs.append(f"{rest}, Чачак, Србија")
        street = strip_num(rest)
        if street and street != rest:
            qs.append(f"{street}, Чачак, Србија")
    else:
        parts = [p.strip() for p in a.split(",")]
        if len(parts) > 1:
            loc, rest = clean(parts[0]), clean(",".join(parts[1:]))
            qs.append(f"{rest}, {loc}, Србија")
            street = strip_num(rest)
            if street and street != rest:
                qs.append(f"{street}, {loc}, Србија")
            qs.append(f"{loc}, Чачак, Србија")
        else:
            qs.append(f"{clean(a)}, Чачак, Србија")
    qs.append(f"{c}, Србија")
    return qs


def search(q):
    # cache holds a hit dict, or {} for a genuine "no result"; errors are not cached
    if q in cache:
        return cache[q] or None
    res = None
    for attempt in range(1, 4):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
            if r.status_code == 429:
                time.sleep(20 * attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if data:
                pick = next((d for d in data if d.get("class") in GOOD), data[0])
                res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                       "display": pick.get("display_name", ""), "type": pick.get("type")}
            else:
                res = {}
            break
        except Exception:
            time.sleep(5 * attempt)
            res = None
    if res is not None:  # cache hits and genuine empty results ({}), not errors
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(4.0)
    return res or None


def main():
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
        print(f"{r['no']:>3} {'OK ' if hit else 'X  '} {r['address'][:52]:<52} -> "
              f"{'' if not hit else str(round(hit['lat'], 4))+','+str(round(hit['lon'], 4))}")

    miss = sum(1 for s in out if s["lat"] is None)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")


if __name__ == "__main__":
    main()
