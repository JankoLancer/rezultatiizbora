#!/usr/bin/env python3
"""Finalise a city's coordinates: fill any missing (null) lat/lon.

Usage: python3 finish_city.py <slug> <center_lat> <center_lon> [geo_file]

Reads geo/<slug>_stations_geo.json (address-geocoding output), and for every row
with lat=null tries Nominatim by venue name, then falls back to the city center
with a small deterministic offset. Offsets any co-located duplicates.
"""
import json, math, os, re, sys, time
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
H = {"User-Agent": "izbori-vizualizacija/1.0"}


def geocode(q, cache, cache_path):
    if q in cache:
        return cache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 1, "countrycodes": "rs"},
                         headers=H, timeout=30)
        d = r.json()
        if d:
            res = {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]),
                   "display": d[0].get("display_name", "")}
    except Exception:
        res = None
    cache[q] = res
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(1.1)
    return res


def main():
    slug = sys.argv[1]
    clat, clon = float(sys.argv[2]), float(sys.argv[3])
    geo_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(ROOT, f"{slug}_stations_geo.json")
    geo_path = geo_path if os.path.isabs(geo_path) else os.path.join(ROOT, geo_path)
    if not os.path.exists(geo_path):
        print("MISSING", geo_path); sys.exit(1)
    cache_path = os.path.join(ROOT, f"{slug}_finish_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}

    data = json.load(open(geo_path, encoding="utf-8"))
    filled = 0
    for s in data:
        if s.get("lat") is not None:
            continue
        name = s.get("name") or s.get("venue") or ""
        hit = geocode(f"{name}, Србија", cache, cache_path)
        if hit:
            s["lat"], s["lon"], s["display"] = hit["lat"], hit["lon"], hit.get("display", "")
            s["source"] = "venue"
        else:
            s["lat"], s["lon"] = clat, clon
            s["source"] = "center"
        filled += 1
    # offset co-located
    groups = {}
    for i, s in enumerate(data):
        groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
    for idxs in groups.values():
        if len(idxs) > 1:
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                r = 0.0008 + 0.0002 * (j // 8)
                data[i]["lat"] += r * math.sin(ang)
                data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))
    json.dump(data, open(geo_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    miss = sum(1 for s in data if s.get("lat") is None)
    print(f"{slug}: filled {filled}, rows {len(data)}, null now {miss}")


if __name__ == "__main__":
    main()
