#!/usr/bin/env python3
"""Finalise Grad Kraljevo stations: venue-name Nominatim fallback + city-centre last resort.

Reads/writes geo/kraljevo_stations_geo.json, reusing geo/kraljevo_cache.json.
For every station still missing coordinates after address geocoding:
  1. search Nominatim by venue (RIK 2023) name within Serbia,
  2. then try the settlement (first token of the address),
  3. otherwise use the Kraljevo centre (43.7256, 20.6894) with a small per-station offset.
All stations are guaranteed to end up with lat/lon; source becomes "venue".
"""
import json
import math
import os
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "kraljevo_stations_geo.json")
CACHE = os.path.join(BASE, "kraljevo_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
CENTER = (43.7256, 20.6894)
SLEEP = 4.0
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
    stats = {}
    for i, s in enumerate(data):
        if s.get("lat") is not None:
            if not s.get("source"):
                s["source"] = "address"
            stats[s["source"]] = stats.get(s["source"], 0) + 1
            continue

        # 1) venue name
        hit = search(f"{s['name']}, Краљево, Србија")
        used = f"venue: {s['name']}"
        if hit is None:
            hit = search(f"{s['name']}, Србија")
        # 2) settlement (first token of the address)
        if hit is None and s.get("address"):
            head = s["address"].split(",")[0].strip().title()
            head = head.replace("Краљево", "").strip()
            if head:
                hit = search(f"{head}, Србија")
                used = f"settlement: {head}"

        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["source"] = "venue"
            s["geocoded_with"] = used
            stats["venue"] = stats.get("venue", 0) + 1
            print(f"  venue  {s['no']:>3} {s['name'][:40]:<40} -> {round(hit['lat'],4)},{round(hit['lon'],4)}")
        else:
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            s["lat"] = CENTER[0] + rad * math.sin(ang)
            s["lon"] = CENTER[1] + rad * math.cos(ang) / math.cos(math.radians(CENTER[0]))
            s["display"] = "центар Краљева (процена)"
            s["geocoded_with"] = "center-fallback"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["center"] = stats.get("center", 0) + 1
            print(f"  centre {s['no']:>3} {s['name'][:40]:<40} -> {round(s['lat'],4)},{round(s['lon'],4)}")

    # spread any remaining exactly co-located points
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
