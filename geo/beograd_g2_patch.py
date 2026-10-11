#!/usr/bin/env python3
"""Patch a few g2 stations whose exact street could not be geocoded, using
settlement/street fallbacks already stored in the cache, then re-offset clusters.
"""
import json, math, os

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g2_geo.json")
CACHE = os.path.join(BASE, "beograd_g2_cache.json")

PATCH = {
    ("Градска општина Чукарица", 52): ("Бреза, Београд, Србија", "address-fallback"),
    ("Градска општина Чукарица", 53): ("Бреза, Београд, Србија", "address-fallback"),
    ("Градска општина Чукарица", 73): ("Војнотехнички институт, Београд, Србија", "venue"),
    ("Градска општина Чукарица", 82): ("Булевар младих, Београд, Србија", "address-fallback"),
    ("Градска општина Чукарица", 83): ("Булевар младих, Београд, Србија", "address-fallback"),
    ("Градска општина Палилула (Београд)", 9): ("Браће Грим, Београд, Србија", "address-fallback"),
    ("Градска општина Палилула (Београд)", 10): ("Браће Грим, Београд, Србија", "address-fallback"),
    ("Градска општина Палилула (Београд)", 11): ("Браће Грим, Београд, Србија", "address-fallback"),
    ("Градска општина Палилула (Београд)", 12): ("Браће Грим, Београд, Србија", "address-fallback"),
}

cache = json.load(open(CACHE, encoding="utf-8"))
data = json.load(open(GEO, encoding="utf-8"))

patched = []
for i, s in enumerate(data):
    key = (s["municipality"], s["no"])
    if key in PATCH:
        q, src = PATCH[key]
        h = cache.get(q)
        if h:
            s["lat"], s["lon"], s["display"] = h["lat"], h["lon"], h.get("display", "")
            s["source"], s["geocoded_with"], s["fallback"] = src, q, True
            patched.append(i)
            print(f"patched {s['municipality'][-12:]} {s['no']:>3} -> "
                  f"{round(s['lat'],4)},{round(s['lon'],4)}  {q}")

# re-offset only clusters that contain patched points
pset = set(patched)
groups = {}
for i, s in enumerate(data):
    groups.setdefault((round(s["lat"], 6), round(s["lon"], 6)), []).append(i)
for idxs in groups.values():
    members = [i for i in idxs if i in pset]
    if not members:
        continue
    if len(idxs) > 1:
        for j, i in enumerate(idxs):
            ang = 2 * math.pi * j / len(idxs)
            r = 0.00045 + 0.00015 * (j // 8)
            data[i]["lat"] += r * math.sin(ang)
            data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))

json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"patched {len(patched)}; missing now {sum(1 for s in data if s['lat'] is None)}")
