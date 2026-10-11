#!/usr/bin/env python3
"""Finalise Novi Sad stations: venue-name Nominatim fallback + city-centre last resort.

Reads/writes geo/novisad_stations_geo.json, reusing geo/novisad_addr_cache.json.
For every station still missing coordinates after address geocoding:
  1. search Nominatim by venue (RIK 2023) name within Serbia,
  2. otherwise use the Novi Sad centre (45.255, 19.845) with a small per-station offset.
All stations are guaranteed to end up with lat/lon; source becomes "venue".
"""
import json, os, re, time, math
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "novisad_stations_geo.json")
CACHE = os.path.join(BASE, "novisad_addr_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
CENTER = (45.255, 19.845)
SLEEP = 2.0
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def search(q):
    if q in cache:
        return cache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 3, "countrycodes": "rs"},
                         headers=H, timeout=30)
        data = r.json()
        if data:
            res = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]),
                   "display": data[0].get("display_name", "")}
    except Exception:
        res = None
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    data = json.load(open(GEO, encoding="utf-8"))
    stats = {"address": 0, "venue": 0, "center": 0}
    for i, s in enumerate(data):
        if s.get("lat") is not None:
            if not s.get("source"):
                s["source"] = "address"
            stats[s["source"]] = stats.get(s["source"], 0) + 1
            continue
        hit = search(f"{s['name']}, Нови Сад, Србија")
        if hit is None:
            hit = search(f"{s['name']}, Србија")
        if hit is None and s.get("address"):
            # settlement-only fallback (e.g. Бегеч, Ченеј, Ковиљ outside the viewbox)
            head = s["address"].split(",")[0].strip().title()
            if head and head.lower() != "нови сад":
                hit = search(f"{head}, Србија")
        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["geocoded_with"] = f"venue: {s['name']}"
            s["source"] = "venue"
            stats["venue"] += 1
            print(f"  venue  {s['no']:>3} {s['name'][:44]:<44} -> {round(hit['lat'],4)},{round(hit['lon'],4)}")
        else:
            # city-centre last resort with a small deterministic per-station offset
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            s["lat"] = CENTER[0] + rad * math.sin(ang)
            s["lon"] = CENTER[1] + rad * math.cos(ang) / math.cos(math.radians(CENTER[0]))
            s["display"] = "центaр Новог Сада (процена)"
            s["geocoded_with"] = "center-fallback"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["center"] += 1
            print(f"  centre {s['no']:>3} {s['name'][:44]:<44} -> {round(s['lat'],4)},{round(s['lon'],4)}")

    # spread any remaining exactly co-located points (only those we had to guess)
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
