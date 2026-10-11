#!/usr/bin/env python3
"""Geocode Jagodina stations from the 2022 referendum addresses.

Query order per station: full address -> street/building only (number stripped)
-> settlement (no city) -> city. Nominatim, bounded to the Jagodina viewbox.

Nominatim is shared with other agents (same IP) and often returns HTTP 429;
failures are retried with backoff and are never written to the cache.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "jagodina_stations_locations.json")
OUT = os.path.join(BASE, "jagodina_stations_geo.json")
CACHE = os.path.join(BASE, "jagodina_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (jagodina geocoding)"}
VIEWBOX = "21.05,43.85,21.55,44.15"   # lon_min,lat_min,lon_max,lat_max around Jagodina
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
# drop any previously cached error/None results so they get retried
cache = {k: v for k, v in cache.items() if v is not None}


def clean(a):
    a = a.replace("–", "-")
    a = re.sub(r"\bБР\.\s*", " ", a)      # require the dot: never strips "БРАЋЕ"
    a = re.sub(r"\bББ\b", " ", a)
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def strip_number(a):
    a = re.sub(r"\s*\b\d+[A-Za-zА-Яа-я]?(?:[/-]\d+[A-Za-zА-Яа-я]?)?\s*$", "", a)
    return a.strip(" ,")


def queries(addr):
    a = clean(addr)
    m = re.search(r"ЈАГОДИН\w*", a, re.I)
    if "," in a:
        head, city = a.rsplit(",", 1)
        head, city = clean(head), clean(city)
        if m and m.start() > a.rfind(","):
            head = clean(a[:m.start()])
            city = "Јагодина"
    elif m:
        head, city = clean(a[:m.start()]), "Јагодина"
    else:
        head, city = a, "Јагодина"
    head = head.strip(" ,")
    qs = []
    if head:
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
    res = None
    ok = False
    waits = [0, 8, 20, 40, 70]
    for attempt, wait in enumerate(waits):
        if wait:
            time.sleep(wait)
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
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
    if ok:
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(4.0)
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
    print(f"{r['no']:>2} {'OK ' if hit else 'X  '} {r['address'][:40]:<40} -> "
          f"{'' if not hit else str(round(hit['lat'],4))+','+str(round(hit['lon'],4))}"
          f"  [{used}]")

miss = sum(1 for s in out if s["lat"] is None)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")
