#!/usr/bin/env python3
"""Finalise Grad Krusevac stations: venue-name Nominatim fallback + city-centre last resort.

Reads/writes geo/krusevac_stations_geo.json, reusing geo/krusevac_cache.json.
For every station still missing coordinates after address geocoding:
  1. search Nominatim by venue (RIK 2023) name within Serbia,
  2. otherwise by settlement (first address token),
  3. otherwise use the Krusevac centre (43.5833, 21.3267) with a small per-station offset.
All stations end up with lat/lon; source becomes "venue".
"""
import json
import math
import os
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "krusevac_stations_geo.json")
CACHE = os.path.join(BASE, "krusevac_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (krusevac)"}
CENTER = (43.5833, 21.3267)         # Град Крушевац, центар
SLEEP = 4.0                         # shared IP
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def search(q):
    if q in cache:
        return cache[q]
    data, ok = None, False
    for attempt in range(3):
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 3, "countrycodes": "rs"},
                             headers=H, timeout=30)
            data = r.json()
            ok = True
            break
        except Exception:
            time.sleep(2 * (attempt + 1))
    if not ok:
        return None
    res = None
    if data:
        res = {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]),
               "display": data[0].get("display_name", "")}
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    data = json.load(open(GEO, encoding="utf-8"))
    stats = {"address": 0, "venue": 0, "center": 0}
    for i, s in enumerate(data):
        s.pop("_ref_no", None)
        if s.get("lat") is not None:
            if not s.get("source"):
                s["source"] = "address"
            stats[s["source"]] = stats.get(s["source"], 0) + 1
            continue

        addr = (s.get("address") or "").strip()
        head = addr.split(",")[0].strip()
        is_village = bool(head) and not head.upper().startswith("КРУШЕВАЦ")
        hit, how = None, None

        # 1) rural: the settlement is the most reliable anchor
        if is_village:
            hit = search(f"{head}, Србија")
            how = f"settlement: {head}"
        # 2) venue name (city stations)
        if hit is None:
            hit = search(f"{s['name']}, Крушевац, Србија")
            how = f"venue: {s['name']}"
        if hit is None:
            hit = search(f"{s['name']}, Србија")
            how = f"venue: {s['name']}"
        # 3) settlement fallback for any remaining
        if hit is None and is_village:
            hit = search(f"{head}, Град Крушевац, Србија")
            how = f"settlement: {head}"
        # 4) full address, unbounded
        if hit is None and addr:
            hit = search(f"{addr}, Србија")
            how = f"address: {addr}"

        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["geocoded_with"] = how
            s["source"] = "venue"
            stats["venue"] += 1
            print(f"  venue  {s['no']:>3} {s['name'][:40]:<40} -> {round(hit['lat'],4)},{round(hit['lon'],4)}  {how[:40]}")
        else:
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            s["lat"] = CENTER[0] + rad * math.sin(ang)
            s["lon"] = CENTER[1] + rad * math.cos(ang) / math.cos(math.radians(CENTER[0]))
            s["display"] = "центар Крушевца (процена)"
            s["geocoded_with"] = "center-fallback"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["center"] += 1
            print(f"  centre {s['no']:>3} {s['name'][:40]:<40} -> {round(s['lat'],4)},{round(s['lon'],4)}")

    # spread exactly co-located points
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
