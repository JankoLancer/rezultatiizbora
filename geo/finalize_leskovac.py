#!/usr/bin/env python3
"""Finalise Leskovac: venue-name Nominatim fallback for any misses, city-centre last
resort, then spread exactly co-located polling stations so markers do not overlap."""
import json, math, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "leskovac_stations_geo.json")
CACHE = os.path.join(BASE, "leskovac_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (leskovac geocoding)"}
VIEWBOX = "21.246,43.545,22.646,42.445"
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}
CENTER = (42.9951, 21.9464)   # Лесковац city centre

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
cache = {k: v for k, v in cache.items() if v is not None}
data = json.load(open(GEO, encoding="utf-8"))


def save_cache():
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def search(q):
    if q in cache:
        return cache[q]
    res, ok = None, False
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
                time.sleep(5)
                continue
            data_ = r.json()
            ok = True
            if data_:
                pick = next((d for d in data_ if d.get("class") in GOOD), data_[0])
                res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                       "display": pick.get("display_name", ""), "type": pick.get("type")}
            break
        except Exception:
            time.sleep(5)
    if ok:
        cache[q] = res
        save_cache()
    time.sleep(5.0)
    return res


def search_venue(name):
    for q in (f"{name}, Лесковац, Србија", f"{name}, Србија"):
        h = search(q)
        if h:
            return h, q
    return None, None


filled = []
for s in data:
    if s["lat"] is not None:
        continue
    hit, q = search_venue(s["name"])
    if hit:
        s["lat"], s["lon"] = hit["lat"], hit["lon"]
        s["display"], s["source"], s["geocoded_with"] = hit["display"], "venue", f"venue: {q}"
    else:
        s["lat"], s["lon"] = CENTER[0] + (s["no"] % 7) * 0.0009, CENTER[1] + (s["no"] % 5) * 0.0009
        s["display"], s["source"], s["geocoded_with"] = "Лесковац (центар)", "center", "center"
    filled.append((s["no"], s["name"], s["source"]))

# spread exactly co-located points (same venue, multiple stations)
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
print(f"filled {len(filled)}; spread {spread} co-located; total {len(data)}; "
      f"missing now {sum(1 for s in data if s['lat'] is None)}")
for no, name, src in filled[:40]:
    print(f"  fill {no:>3} {name[:40]:<40} [{src}]")
