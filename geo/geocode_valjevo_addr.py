#!/usr/bin/env python3
"""Geocode Valjevo stations from the 2022 referendum addresses.

Query order per station: full address -> street/building only (number stripped)
-> settlement (no city) -> city. Nominatim, bounded to the Valjevo viewbox
(lon/lat: 19.186,44.821,20.586,43.721).

Nominatim is shared with other agents (same IP): 5.0 s between uncached requests,
HTTP 429 -> sleep 45 s and retry; failed/None results are never persisted to cache.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "valjevo_stations_locations.json")
OUT = os.path.join(BASE, "valjevo_stations_geo.json")
CACHE = os.path.join(BASE, "valjevo_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (valjevo geocoding)"}
VIEWBOX = "19.186,44.821,20.586,43.721"   # lon_min,lat_min,lon_max,lat_max
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}
CITY = "Ваљево"

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
cache = {k: v for k, v in cache.items() if v is not None}  # never keep failures/nulls
misses = set()  # in-run negative memo, not persisted


def clean(a):
    a = a.replace("–", "-").replace("—", "-")
    a = re.sub(r"\bБР\.\s*", " ", a)      # require the dot: never strips "БРАЋЕ"
    a = re.sub(r"\bББ\b", " ", a)
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def strip_number(a):
    a = re.sub(r"\s*\b\d+[A-Za-zА-Яа-я]?(?:[/-]\d+[A-Za-zА-Яа-я]?)?\s*$", "", a)
    return a.strip(" ,")


def queries(addr):
    a = clean(addr)
    m = re.search(r"ВАЉЕВ\w*", a, re.I)
    if "," in a:
        head, city = a.rsplit(",", 1)
        head, city = clean(head), clean(city)
    elif m:
        head, city = clean(a[:m.start()]), CITY
    else:
        head, city = a, CITY
    head = head.strip(" ,") or city
    qs = []
    qs.append(f"{head}, {city}, Србија")
    sn = strip_number(head)
    if sn and sn != head:
        qs.append(f"{sn}, {city}, Србија")
    if sn and sn != city:
        qs.append(f"{sn}, Србија")
    qs.append(f"{city}, Србија")
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def search(q):
    if q in cache:
        return cache[q]
    if q in misses:
        return None
    res, ok = None, False
    for attempt in range(5):
        if attempt:
            time.sleep(45)  # back off hard on 429
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
            if r.status_code == 429:
                print(f"    ~ 429 for {q!r} (attempt {attempt+1})")
                continue
            if r.status_code != 200:
                print(f"    ~ {r.status_code} for {q!r} (attempt {attempt+1})")
                continue
            data = r.json()
            ok = True
            if data:
                pick = next((d for d in data if d.get("class") in GOOD), data[0])
                res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                       "display": pick.get("display_name", ""), "type": pick.get("type")}
            break
        except Exception as exc:
            print(f"    ! {type(exc).__name__} for {q!r}: {exc}")
    if res is not None:
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        misses.add(q)
    time.sleep(5.0)
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
    print(f"{r['no']:>3} {'OK ' if hit else 'X  '} {r['address'][:40]:<40} -> "
          f"{'' if not hit else str(round(hit['lat'],4))+','+str(round(hit['lon'],4))}"
          f"  [{used}]")

miss = sum(1 for s in out if s["lat"] is None)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")
