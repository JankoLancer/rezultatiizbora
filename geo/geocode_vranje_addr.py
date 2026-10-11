#!/usr/bin/env python3
"""Geocode Врање (Град Врање + Градска општина Врањска Бања) stations by address.

Query order per station: full address -> street/building only (number stripped)
-> settlement -> city. Nominatim, bounded to the Врање viewbox.

Nominatim is shared with other agents (same IP); successful lookups are cached in
geo/vranje_cache.json, failures are retried with backoff and NEVER cached.
"""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "vranje_stations_locations.json")
OUT = os.path.join(BASE, "vranje_stations_geo.json")
CACHE = os.path.join(BASE, "vranje_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (vranje geocoding)"}
VIEWBOX = "21.198,43.104,22.598,42.004"   # lon_min,lat_max,lon_max,lat_min around Врање
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}
CITY_GRAD = "Врање"
CITY_BANJA = "Врањска Бања"


def clean(a):
    a = a.replace("–", "-").replace("—", "-")
    a = re.sub(r"\s*\([^)]*\)", " ", a)              # drop parenthetical alternatives
    a = re.sub(r"\bБР\.\s*", " ", a, flags=re.I)     # require the dot: never strip "БРАЋЕ"
    a = re.sub(r"\bББ\b", " ", a)
    a = a.replace(", ,", ",")
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def strip_number(a):
    a = re.sub(r"\s*\b\d+[A-Za-zА-Яа-я]?(?:[/-]\d+[A-Za-zА-Яа-я]?)?\s*$", "", a)
    return a.strip(" ,")


def queries(addr, municipality):
    a = clean(addr)
    up = a.upper()
    if CITY_BANJA.upper() in up:
        city = CITY_BANJA
    elif re.search(r"\bВРАЊЕ\b", up):
        city = CITY_GRAD
    else:
        city = CITY_GRAD if municipality == "Град Врање" else CITY_BANJA

    parts = [p.strip() for p in a.split(",") if p.strip()]
    settlement = None
    street = None
    if len(parts) >= 2:
        if parts[0].upper() not in (CITY_GRAD.upper(), CITY_BANJA.upper()):
            settlement = parts[0]
        street = parts[-1]
    elif parts:
        # single component: usually a village + number
        settlement = strip_number(parts[0]) or parts[0]

    qs = []
    qs.append(f"{a}, {city}, Србија" if city.upper() not in up else f"{a}, Србија")
    if street and street != a:
        qs.append(f"{street}, {city}, Србија")
    if street:
        sn = strip_number(street)
        if sn and sn != street:
            qs.append(f"{sn}, {city}, Србија")
    if settlement:
        qs.append(f"{settlement}, {city}, Србија")
        qs.append(f"{settlement}, Србија")
    qs.append(f"{city}, Србија")

    seen, out = set(), []
    for q in qs:
        q = re.sub(r"\s+", " ", q).strip(" ,")
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
# drop any previously cached error/None results so they get retried
cache = {k: v for k, v in cache.items() if v is not None}


def search(q):
    if q in cache:
        return cache[q]
    res = None
    ok = False
    for attempt in range(1, 9):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
        except Exception as exc:
            print(f"    ! {type(exc).__name__} for {q!r}: {exc}")
            time.sleep(5.0 * attempt)
            continue
        if r.status_code == 429:
            print(f"    ~ 429 for {q!r}; sleeping 45s (attempt {attempt})")
            time.sleep(45)
            continue
        if r.status_code != 200:
            print(f"    ~ {r.status_code} for {q!r} (attempt {attempt})")
            time.sleep(5.0)
            continue
        data = r.json()
        ok = True
        if data:
            pick = next((d for d in data if d.get("class") in GOOD), data[0])
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", ""), "type": pick.get("type")}
        break
    if ok:
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(5.0)
    return res


def save(out):
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    rows = json.load(open(IN, encoding="utf-8"))
    key_of = lambda r: (r["municipality"], r["no"])
    done = {}
    if os.path.exists(OUT):
        for s in json.load(open(OUT, encoding="utf-8")):
            if s.get("lat") is not None:
                done[(s["municipality"], s["no"])] = s

    out = []
    for r in rows:
        prev = done.get(key_of(r))
        if prev is not None:
            out.append(prev)
            continue
        hit = used = None
        for q in queries(r["address"], r["municipality"]):
            hit = search(q)
            if hit:
                used = q
                break
        rec = {**r, "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
               "display": hit["display"] if hit else None, "source": "address",
               "geocoded_with": used}
        out.append(rec)
        code = "" if not hit else f"{round(hit['lat'],4)},{round(hit['lon'],4)}"
        print(f"{r['municipality'][:9]:<9} {r['no']:>2} {'OK ' if hit else 'X  '} "
              f"{r['address'][:38]:<38} -> {code}  [{used}]", flush=True)
        save(out)   # incremental, survives interruption

    miss = sum(1 for s in out if s["lat"] is None)
    save(out)
    print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}", flush=True)


if __name__ == "__main__":
    main()
