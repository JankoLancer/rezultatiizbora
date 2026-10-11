#!/usr/bin/env python3
"""Geocode Šabac stations from the 2022 referendum addresses.

Query order per station: full address -> street/building only -> settlement ->
city.  Nominatim, bounded to the Šabac viewbox.

Nominatim is shared with other agents (same IP) and often returns HTTP 429;
429s are retried after a 45 s sleep, other failures with backoff, and failed /
None results are never written to the cache.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "sabac_stations_locations.json")
OUT = os.path.join(BASE, "sabac_stations_geo.json")
CACHE = os.path.join(BASE, "sabac_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (sabac geocoding)"}
VIEWBOX = "18.995,45.307,20.395,44.207"   # lon_min,lat_max,lon_max,lat_min (Nominatim order)
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
# drop any previously cached error/None results so they get retried
cache = {k: v for k, v in cache.items() if v is not None}


# OSM spells these settlements differently from the RIK document.
ALIASES = {"ЋОСИЋ МАЛА": "Ћосића Мала"}


def clean(a):
    a = a.replace("–", "-").replace("—", "-")
    a = re.sub(r"\bБР\.\s*", " ", a)      # require the dot: never strips "БРАЋЕ"
    a = re.sub(r"\bББ\b", " ", a)
    a = re.sub(r"\bб\.?\s*б\.?", " ", a)  # "б.б." / "б б"
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def strip_number(a):
    a = re.sub(r"\s*\b\d+[A-Za-zА-Яа-я]?(?:[/-]\d+[A-Za-zА-Яа-я]?)?\s*$", "", a)
    return a.strip(" ,")


def queries(addr):
    a = clean(addr)
    m = re.search(r"ШАБ(?:АЦ|ЦА)\w*", a, re.I)
    if m:
        if a[:m.start()].strip(" ,"):
            head = clean(a[:m.start()].strip(" ,"))      # "STREET N, ШАБАЦ"
        else:
            head = clean(a[m.end():].strip(" ,"))         # "ШАБАЦ, STREET N"
        city = "Шабац"
    else:
        head, city = a, "Шабац"
    head = ALIASES.get(head.strip(" ,").upper(), head.strip(" ,"))
    qs = []
    if head:
        qs.append(f"{head}, {city}, Србија")
        sn = strip_number(head)
        if sn and sn != head:
            qs.append(f"{sn}, {city}, Србија")
        seg = head.split(",")[0].strip()
        if seg and seg != head and seg != sn:
            qs.append(f"{seg}, {city}, Србија")
            qs.append(f"{seg}, Србија")
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
            if r.status_code == 429:
                print(f"    ~ 429 for {q!r}; sleeping 45s (attempt {attempt+1})")
                time.sleep(45)
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
    if ok:
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
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
    print(f"{r['no']:>3} {'OK ' if hit else 'X  '} {str(r['address'])[:42]:<42} -> "
          f"{'' if not hit else str(round(hit['lat'],4))+','+str(round(hit['lon'],4))}"
          f"  [{used}]")

miss = sum(1 for s in out if s["lat"] is None)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")
