#!/usr/bin/env python3
"""Finalise Belgrade group g2: venue-name fallback + municipality centre for misses.

Guarantees zero null coordinates. Offsets co-located points so markers separate.
"""
import json, math, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g2_geo.json")
CACHE = os.path.join(BASE, "beograd_g2_cache.json")
VCACHE = os.path.join(BASE, "beograd_g2_venue_cache.json")
H = {"User-Agent": "izbori-vizualizacija-beograd-g2/1.0 (polling-station map)"}
VIEWBOX = "20.10,44.30,20.95,45.15"
SLEEP = 4.5

# municipality centres (approx)
GO = {
    "Градска општина Чукарица": (44.7770, 20.4200),
    "Градска општина Палилула (Београд)": (44.8100, 20.4900),
    "Градска општина Савски Венац": (44.7950, 20.4550),
    "Градска општина Сопот": (44.5200, 20.5750),
}

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
vcache = json.load(open(VCACHE, encoding="utf-8")) if os.path.exists(VCACHE) else {}
data = json.load(open(GEO, encoding="utf-8"))


def search(q):
    if q in cache:
        return cache[q]
    if q in vcache:
        return vcache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                 "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
        d = r.json()
        if d:
            pick = d[0]
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", "")}
    except Exception as exc:
        print("   ! request failed:", exc)
    vcache[q] = res
    json.dump(vcache, open(VCACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


filled = 0
for s in data:
    if s["lat"] is not None:
        continue
    muni = s["municipality"]
    hit = None
    for q in (f'{s["name"]}, Београд, Србија',
              f'{s["name"]}, {muni}, Србија'):
        hit = search(q)
        if hit:
            break
    if hit:
        s["lat"], s["lon"], s["display"] = hit["lat"], hit["lon"], hit["display"]
        s["source"], s["geocoded_with"] = "venue", f'venue: {s["name"]}'
    else:
        s["lat"], s["lon"] = GO.get(muni, (44.81, 20.46))
        s["source"], s["geocoded_with"] = "municipality", "центар општине"
        s["display"] = None
    s["fallback"] = True
    filled += 1
    print(f"  fill {muni[-12:]:<12} {s['no']:>3} {s['name'][:36]:<36} -> "
          f"{round(s['lat'],4)},{round(s['lon'],4)}  {s['source']}")

# separate co-located markers
groups = {}
for i, s in enumerate(data):
    groups.setdefault((round(s["lat"], 6), round(s["lon"], 6)), []).append(i)
for idxs in groups.values():
    if len(idxs) > 1:
        for j, i in enumerate(idxs):
            ang = 2 * math.pi * j / len(idxs)
            r = 0.00045 + 0.00015 * (j // 8)
            data[i]["lat"] += r * math.sin(ang)
            data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))

json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nfilled {filled}; total {len(data)}; "
      f"missing now {sum(1 for s in data if s['lat'] is None)}")
