#!/usr/bin/env python3
"""Finalise Belgrade-g1 stations: venue-name Nominatim fallback + centre last resort.

Reads/writes geo/beograd_g1_geo.json, reusing geo/beograd_g1_cache.json.
For every station still missing coordinates after address geocoding:
  1. search Nominatim by venue name (RIK 2023), bounded to the Belgrade area,
  2. then by venue name + settlement,
  3. otherwise use the municipality centre with a small per-station offset.
All stations are guaranteed lat/lon; those not from the address step get
source="venue".  Exactly co-located points are slightly spread for display.
"""
import json
import math
import os
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g1_geo.json")
CACHE = os.path.join(BASE, "beograd_g1_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
VIEWBOX = "20.10,44.30,20.95,45.15"
SLEEP = 4.5
CENTER = {
    "Градска општина Нови Београд": (44.8080, 20.4200),
    "Градска општина Земун": (44.8454, 20.4095),
    "Градска општина Сурчин": (44.7936, 20.2836),
    "Градска општина Барајево": (44.5792, 20.4147),
}
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def search(q, bounded):
    key = ("B:" if bounded else "N:") + q
    if key in cache:
        return cache[key]
    res = None
    params = {"q": q, "format": "json", "limit": 3, "countrycodes": "rs"}
    if bounded:
        params.update({"viewbox": VIEWBOX, "bounded": 1})
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


def settlement_of(addr):
    """First comma part if it looks like a settlement, else None."""
    if not addr:
        return None
    head = addr.split(",")[0].strip()
    return head if 2 <= len(head) <= 30 else None


def main():
    data = json.load(open(GEO, encoding="utf-8"))
    stats = {"address": 0, "venue": 0, "center": 0}
    for i, s in enumerate(data):
        if s.get("lat") is not None:
            s.setdefault("source", "address")
            stats[s["source"]] = stats.get(s["source"], 0) + 1
            continue

        hit = search(f"{s['name']}, Београд, Србија", True)
        if hit is None:
            hit = search(f"{s['name']}, Србија", False)
        if hit is None:
            st = settlement_of(s.get("address"))
            if st:
                hit = search(f"{s['name']}, {st}, Београд, Србија", True)

        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["geocoded_with"] = f"venue: {s['name']}"
            s["source"] = "venue"
            stats["venue"] += 1
            print(f"  venue  {s['no']:>3} {s['name'][:48]:<48} -> {round(hit['lat'], 4)},{round(hit['lon'], 4)}")
        else:
            c = CENTER[s["municipality"]]
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            s["lat"] = c[0] + rad * math.sin(ang)
            s["lon"] = c[1] + rad * math.cos(ang) / math.cos(math.radians(c[0]))
            s["display"] = "центар општине (процена)"
            s["geocoded_with"] = "center-fallback"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["center"] += 1
            print(f"  centre {s['no']:>3} {s['name'][:48]:<48} -> {round(s['lat'], 4)},{round(s['lon'], 4)}")

    # spread exactly co-located points for display
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
