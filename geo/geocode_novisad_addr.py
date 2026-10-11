#!/usr/bin/env python3
"""Geocode Novi Sad polling stations from the official 2022 referendum addresses.

Reads  geo/novisad_stations_locations.json  (built by align_novisad.py).
Writes geo/novisad_stations_geo.json and caches to geo/novisad_addr_cache.json.

Nominatim is rate limited (2.0s between uncached requests) per project rules.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "novisad_stations_locations.json")
OUT = os.path.join(BASE, "novisad_stations_geo.json")
CACHE = os.path.join(BASE, "novisad_addr_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "19.70,45.20,20.00,45.35"   # Novi Sad area
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place", "shop"}
SLEEP = 2.0

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def clean(a):
    a = re.sub(r"\bБР\.?\s*", " ", a, flags=re.I)
    a = re.sub(r"\bББ\b", " ", a, flags=re.I)
    a = a.replace("–", "-")
    return re.sub(r"\s+", " ", a).strip(" ,")


def _street(s):
    return re.sub(r"\s*\d+\s*[а-шa-z]?\s*$", "", s, flags=re.I).strip(" ,")


def queries(addr):
    a = addr.strip()
    c = clean(a)
    qs = []
    parts = [p.strip() for p in a.split(",")]
    if len(parts) >= 2:
        settlement = parts[0]
        rest = clean(",".join(parts[1:]))
        st = settlement.title()
        qs.append(f"{rest}, {st}, Србија" if rest else f"{st}, Нови Сад, Србија")
        street = _street(rest)
        if street and street != rest:
            qs.append(f"{street}, {st}, Србија")
        qs.append(f"{st}, Нови Сад, Србија")
    else:
        qs.append(f"{c}, Нови Сад, Србија")
    qs.append(f"{c}, Србија")
    # de-duplicate, keep order
    seen, out = set(), []
    for q in qs:
        if q not in seen and q.strip():
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
    out = []
    n_req = 0
    for r in rows:
        hit = used = None
        for q in queries(r["address"]):
            hit, fresh = search(q)
            n_req += int(fresh)
            if hit:
                used = q
                break
        out.append({**r, "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
                    "display": hit["display"] if hit else None, "source": "address",
                    "geocoded_with": used})
        print(f"{r['no']:>3} {'OK ' if hit else 'X  '} {r['name'][:34]:<34} {r['address'][:40]:<40} -> "
              f"{'' if not hit else str(round(hit['lat'], 4))+','+str(round(hit['lon'], 4))}")
    miss = sum(1 for s in out if s["lat"] is None)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}; live requests {n_req}")


if __name__ == "__main__":
    main()
