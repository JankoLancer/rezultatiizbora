#!/usr/bin/env python3
"""Finalise Grad Subotica station coordinates.

For any station left without coordinates after address geocoding, fill it using a
venue-name Nominatim lookup, then a settlement lookup, and as a last resort the
Subotica city centre (46.100, 19.665) with a small per-station offset.  All
stations end with lat/lon.
"""
import json
import math
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "subotica_stations_geo.json")
CACHE = os.path.join(BASE, "subotica_addr_cache.json")
OUT = GEO
H = {"User-Agent": "izbori-vizualizacija/1.0"}
VIEWBOX = "19.25,45.75,20.05,46.35"          # Grad Subotica municipality
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}
CENTER = (46.100, 19.665)

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def nom(q):
    if q in cache:
        return cache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                 "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
        data = r.json()
        if data:
            pick = next((d for d in data if d.get("class") in GOOD), data[0])
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", ""), "type": pick.get("type")}
    except Exception:
        res = None
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(2.0)
    return res


def venue_variants(venue):
    """Full name + cleaned variants (drop parentheticals / '- SALA' suffixes)."""
    out = [venue]
    base = re.sub(r"\s*\([^)]*\)", " ", venue)            # drop (...)
    base = re.sub(r"\s*[-–]\s*(МАЛА|ВЕЛИКА)\s+САЛА.*$", "", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip(" -–")
    if base and base.upper() != venue.upper():
        out.append(base)
    return out


data = json.load(open(GEO, encoding="utf-8"))
stats = {"venue": 0, "settlement": 0, "center": 0}
for s in data:
    if s["lat"] is not None and s.get("fallback") != "center":
        continue
    venue = s["name"]
    hit = used = None
    for v in venue_variants(venue):
        for q in (f"{v}, Суботица, Србија", f"{v}, Град Суботица, Србија",
                  f"{v}, Србија"):
            hit = nom(q)
            if hit:
                used = q
                break
        if hit:
            break
    kind = "venue"
    if not hit:
        first = s["address"].split(",")[0].strip()
        if first and first.upper() != "СУБОТИЦА":
            hit = nom(f"{first}, Суботица, Србија")
            if hit:
                used = f"{first}, Суботица, Србија"
                kind = "settlement"
    if hit:
        s["lat"], s["lon"] = hit["lat"], hit["lon"]
        s["display"] = hit["display"]
        s["geocoded_with"] = used
        s["source"] = "venue"
        s["fallback"] = kind
        stats[kind] += 1
        print(f"  fill {s['no']:>3} [{kind:10}] {venue[:42]:<42} -> "
              f"{round(hit['lat'],4)},{round(hit['lon'],4)}")
    else:
        s["lat"], s["lon"] = CENTER
        s["source"] = "venue"
        s["fallback"] = "center"
        s["display"] = s.get("display") or "Суботица (центар)"
        s["geocoded_with"] = "городские центар"
        stats["center"] += 1
        print(f"  fill {s['no']:>3} [center    ] {venue[:42]:<42} -> {CENTER}")

# offset co-located stations so markers do not overlap exactly
groups = {}
for i, s in enumerate(data):
    groups.setdefault((round(s["lat"], 5), round(s["lon"], 5)), []).append(i)
for idxs in groups.values():
    if len(idxs) > 1:
        for j, i in enumerate(idxs):
            ang = 2 * math.pi * j / len(idxs)
            r = 0.0007 + 0.0002 * (j // 8)
            data[i]["lat"] += r * math.sin(ang)
            data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))

json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
nulls = [s["no"] for s in data if s["lat"] is None or s["lon"] is None]
print(f"\nvenue fallback: {stats['venue']}, settlement: {stats['settlement']}, "
      f"center: {stats['center']}; still null: {nulls}; total: {len(data)}")
