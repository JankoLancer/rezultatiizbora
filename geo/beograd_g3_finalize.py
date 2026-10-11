#!/usr/bin/env python3
"""Finalise Belgrade g3 stations: venue-name Nominatim fallback + opstina-centre
last resort, then spread exactly co-located points.

Reads/writes geo/beograd_g3_geo.json, reusing geo/beograd_g3_cache.json.
Guarantees no null coordinates (source becomes "venue" for filled rows).
"""
import json
import math
import os
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g3_geo.json")
CACHE = os.path.join(BASE, "beograd_g3_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "20.10,44.30,20.95,45.15"
SLEEP = 4.5

SHORT = {
    "Градска општина Вождовац": "Вождовац",
    "Градска општина Звездара": "Звездара",
    "Градска општина Врачар": "Врачар",
    "Градска општина Стари Град": "Стари Град",
}
CENTER = {
    "Градска општина Вождовац": (44.7750, 20.4900),
    "Градска општина Звездара": (44.7950, 20.5050),
    "Градска општина Врачар": (44.8000, 20.4700),
    "Градска општина Стари Град": (44.8200, 20.4600),
}
# rough per-municipality bounding box to reject wildly wrong Nominatim hits
BBOX = {
    "Градска општина Вождовац": (44.63, 20.38, 44.83, 20.62),
    "Градска општина Звездара": (44.72, 20.42, 44.86, 20.62),
    "Градска општина Врачар": (44.77, 20.42, 44.83, 20.51),
    "Градска општина Стари Град": (44.79, 20.42, 44.85, 20.49),
}
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def in_bbox(muni, lat, lon):
    b = BBOX.get(muni)
    return True if not b else (b[0] <= lat <= b[2] and b[1] <= lon <= b[3])


def search(q, bounded=True):
    key = q
    if key in cache:
        return cache[key]
    res = None
    params = {"q": q, "format": "json", "limit": 3,
              "countrycodes": "rs", "viewbox": VIEWBOX}
    if bounded:
        params["bounded"] = 1
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params=params, headers=H, timeout=30)
        data = r.json()
        if data:
            res = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]),
                   "display": data[0].get("display_name", "")}
    except Exception:
        res = None
    cache[key] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    data = json.load(open(GEO, encoding="utf-8"))
    stats = {"address": 0, "venue": 0}
    for i, s in enumerate(data):
        if s.get("lat") is not None:
            s["source"] = s.get("source") or "address"
            stats["address"] += 1
            continue
        short = SHORT.get(s["municipality"], s["municipality"])
        hit = None
        for q, bounded in [(f"{s['name']}, {short}, Београд, Србија", True),
                           (f"{s['name']}, Београд, Србија", True),
                           (f"{s['name']}, Београд, Србија", False)]:
            hit = search(q, bounded=bounded)
            if hit and not in_bbox(s["municipality"], hit["lat"], hit["lon"]):
                print(f"  reject {s['name'][:30]} outside bbox: {round(hit['lat'],4)},{round(hit['lon'],4)}")
                hit = None
            if hit:
                break
        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["geocoded_with"] = f"venue: {s['name']}"
            s["source"] = "venue"
            stats["venue"] += 1
            print(f"  venue {s['no']:>3} {s['name'][:40]:<40} -> "
                  f"{round(hit['lat'], 5)},{round(hit['lon'], 5)}")
        else:
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            lat0, lon0 = CENTER.get(s["municipality"], (44.79, 20.48))
            s["lat"] = lat0 + rad * math.sin(ang)
            s["lon"] = lon0 + rad * math.cos(ang) / math.cos(math.radians(lat0))
            s["display"] = f"центар општине {short} (процена)"
            s["geocoded_with"] = "center-fallback"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["venue"] += 1
            print(f"  centre{s['no']:>3} {s['name'][:40]:<40} -> "
                  f"{round(s['lat'], 5)},{round(s['lon'], 5)}")

    # spread exactly co-located points so each station is individually visible
    groups = {}
    for i, s in enumerate(data):
        groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
    for idxs in groups.values():
        if len(idxs) > 1:
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                r = 0.0006 + 0.0002 * (j // 8)
                data[i]["lat"] += r * math.sin(ang)
                data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))

    json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    missing = sum(1 for s in data if s.get("lat") is None or s.get("lon") is None)
    print(f"\nsource counts: {stats}")
    print(f"total {len(data)}; missing now {missing}")


if __name__ == "__main__":
    main()
