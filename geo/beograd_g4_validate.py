#!/usr/bin/env python3
"""Validate the g4 Belgrade-municipality output: counts, nulls, mismatches,
geocode sources.  Prints 5 sample rows.

Reads geo/beograd_g4_geo.json and geo/beograd_g4_align_report.txt.
"""
import json
import os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g4_geo.json")
LOC = os.path.join(BASE, "beograd_g4_locations.json")

data = json.load(open(GEO, encoding="utf-8"))
loc = json.load(open(LOC, encoding="utf-8"))

print(f"locations: {len(loc)}   geo: {len(data)}")
print("\nper-municipality counts (locations):")
for k, v in Counter(r["municipality"] for r in loc).items():
    print(f"  {k:<30} {v:>3}")

nulls = [s for s in data if s.get("lat") is None or s.get("lon") is None]
print(f"\nnull coordinates: {len(nulls)}")
print("geocode sources:", dict(Counter(s.get("source", "?") for s in data)))
print("fallbacks (center):",
      sum(1 for s in data if s.get("fallback") == "center"))

# out-of-viewbox sanity
bad = [s for s in data if not (44.30 <= s["lat"] <= 45.15 and 20.10 <= s["lon"] <= 20.95)]
print(f"outside viewbox: {len(bad)}")
for s in bad[:10]:
    print(f"   {s['municipality'].split()[-1]} {s['no']} {s['name'][:30]} "
          f"{round(s['lat'],4)},{round(s['lon'],4)}")

print("\nsample rows:")
for s in data[:5]:
    print(f"  {s['municipality'].split()[-1]:<10} {s['no']:>3} {s['name'][:30]:<30} "
          f"{s['address'][:30]:<30} {round(s['lat'],5)},{round(s['lon'],5)} "
          f"[{s.get('source')}] {str(s.get('geocoded_with'))[:36]}")

# per-municipality source breakdown
print("\nper-municipality geocode source:")
for m in sorted(set(s["municipality"] for s in data)):
    c = Counter(s.get("source", "?") for s in data if s["municipality"] == m)
    print(f"  {m.split()[-1]:<12} {dict(c)}")
