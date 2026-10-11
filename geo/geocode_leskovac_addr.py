#!/usr/bin/env python3
"""Geocode Leskovac stations from the 2022 referendum addresses.

Query order per station: full address -> street/building only (number stripped)
-> settlement (no city) -> city. Nominatim, bounded to the Leskovac viewbox.

Nominatim is shared with other agents (same IP) and often returns HTTP 429;
failures are retried with backoff and are NEVER written to the cache.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "leskovac_stations_locations.json")
OUT = os.path.join(BASE, "leskovac_stations_geo.json")
CACHE = os.path.join(BASE, "leskovac_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (leskovac geocoding)"}
VIEWBOX = "21.246,43.545,22.646,42.445"   # lon_min,lat_max,lon_max,lat_min around Leskovac
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
# drop any previously cached error/None results so they get retried
cache = {k: v for k, v in cache.items() if v is not None}


def save_cache():
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


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
    """2022 addresses are written as 'SETTLEMENT/CITY, STREET' (city first).

    Fallback chain: full address -> street/building only -> settlement -> city.
    """
    a = clean(addr)
    if "," in a:
        settlement, street = a.split(",", 1)
        settlement, street = clean(settlement), clean(street)
    else:
        settlement, street = a, ""
    qs = []
    if street:
        qs.append(f"{street}, {settlement}, Србија")
        sn = strip_number(street)
        if sn and sn != street:
            qs.append(f"{sn}, {settlement}, Србија")
    if settlement:
        qs.append(f"{settlement}, Србија")
        plain = re.sub(r"\s*\([^)]*\)\s*", " ", settlement).strip()
        if plain and plain != settlement:
            qs.append(f"{plain}, Србија")          # e.g. ОРУГЛИЦА (ГОРЊА) -> ОРУГЛИЦА
    qs.append("Лесковац, Србија")
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
    for attempt in range(6):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
            if r.status_code == 429:
                print(f"    ~ 429 for {q!r} (attempt {attempt+1}); sleeping 45s")
                time.sleep(45)
                continue
            if r.status_code != 200:
                print(f"    ~ {r.status_code} for {q!r} (attempt {attempt+1})")
                time.sleep(5)
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
            time.sleep(5)
    if ok:
        cache[q] = res
        save_cache()
    time.sleep(5.0)   # shared IP: space out uncached requests
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
