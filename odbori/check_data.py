#!/usr/bin/env python3
"""Sanity checks for map/odbori.json after merge."""
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, "map", "odbori.json"), encoding="utf-8"))
stations = d["stations"]
print("cities:", len(d["meta"]["cities"]))
print("stations:", len(stations))
print("permanent:", sum(1 for s in stations if s["committees"]["stalni"]["total"]))
print("expanded:", sum(1 for s in stations if s["committees"]["prosireni"]["total"]))
print("people rows:", sum(s["committees"][c]["total"] for s in stations for c in ("stalni", "prosireni")))
keys = Counter((s["city_slug"], s["no"]) for s in stations)
print("duplicate station keys:", [k for k, v in keys.items() if v > 1][:5])
bad = []
for s in stations:
    for c in ("stalni", "prosireni"):
        for p in s["committees"][c]["members"]:
            n = p["name"].strip().lower()
            if "име и презиме" in n or len(n.strip("() ")) < 2:
                bad.append((s["city_slug"], s["no"], c, p["name"]))
print("placeholder names:", len(bad), bad[:5])
print("\nby list (expanded members / deputies):")
for r in d["summary"]["by_list"]["prosireni"]:
    print(f"  {r['short']:10} {r['members']:5} / {r['deputies']:5}  ({r['stations']} stations)")
print("\ntop missing permanent:")
for c in sorted(d["meta"]["cities"], key=lambda x: -(x.get("missing_permanent") or 0))[:15]:
    if c.get("missing_permanent"):
        print(f"  {c['name']}: {c['missing_permanent']}/{c['stations_total']}")
print("\ntop missing expanded:")
for c in sorted(d["meta"]["cities"], key=lambda x: -(x.get("missing_expanded") or 0))[:15]:
    if c.get("missing_expanded"):
        print(f"  {c['name']}: {c['missing_expanded']}/{c['stations_total']}")
