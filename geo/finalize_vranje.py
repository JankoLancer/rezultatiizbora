#!/usr/bin/env python3
"""Finalise Врање: venue-name Nominatim fallback (bounded to the Врање viewbox) for
any misses, city-centre last resort, then spread exactly co-located stations so
markers do not overlap.

Usage: python3 finalize_vranje.py
"""
import json, math, os, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "vranje_stations_geo.json")
CACHE = os.path.join(BASE, "vranje_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (vranje geocoding)"}
VIEWBOX = "21.198,43.104,22.598,42.004"
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}
CENTER = (42.5544, 21.8979)   # Врање city centre

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
cache = {k: v for k, v in cache.items() if v is not None}
data = json.load(open(GEO, encoding="utf-8"))


def search(q):
    if q in cache:
        return cache[q]
    res, ok = None, False
    for attempt in range(1, 9):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                     "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
        except Exception as exc:
            print(f"    ! {type(exc).__name__} for {q!r}: {exc}", flush=True)
            time.sleep(5.0 * attempt)
            continue
        if r.status_code == 429:
            print(f"    ~ 429 for {q!r}; sleeping 45s", flush=True)
            time.sleep(45)
            continue
        if r.status_code != 200:
            time.sleep(5.0)
            continue
        data_ = r.json()
        ok = True
        if data_:
            pick = next((d for d in data_ if d.get("class") in GOOD), data_[0])
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", ""), "type": pick.get("type")}
        break
    if ok:
        cache[q] = res
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(5.0)
    return res


def search_venue(name, municipality):
    city = "Врањска Бања" if municipality == "Градска општина Врањска Бања" else "Врање"
    for q in (f"{name}, {city}, Србија", f"{name}, Србија"):
        h = search(q)
        if h:
            return h, q
    return None, None


filled = 0
for s in data:
    if s.get("lat") is not None:
        continue
    hit, q = search_venue(s["name"], s["municipality"])
    if hit:
        s["lat"], s["lon"] = hit["lat"], hit["lon"]
        s["display"], s["source"] = hit["display"], "venue"
        s["geocoded_with"] = f"venue: {q}"
    else:
        # last resort: city centre with a small deterministic offset
        s["lat"] = CENTER[0] + (s["no"] % 7) * 0.0009
        s["lon"] = CENTER[1] + (s["no"] % 5) * 0.0009
        s["display"], s["source"] = "Врање (центар)", "center"
        s["geocoded_with"] = "center"
    filled += 1
    print(f"  fill {s['no']:>2} {s['name'][:34]:<34} -> "
          f"{round(s['lat'],4)},{round(s['lon'],4)} [{s['source']}]", flush=True)
    json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# spread exactly co-located points (e.g. one venue hosting several stations)
groups = {}
for i, s in enumerate(data):
    groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
spread = 0
for idxs in groups.values():
    if len(idxs) > 1:
        for j, i in enumerate(idxs):
            ang = 2 * math.pi * j / len(idxs)
            r = 0.0007 + 0.0002 * (j // 8)
            data[i]["lat"] += r * math.sin(ang)
            data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))
        spread += len(idxs)

json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"filled {filled}; spread {spread} co-located; total {len(data)}; "
      f"missing now {sum(1 for s in data if s.get('lat') is None)}", flush=True)
