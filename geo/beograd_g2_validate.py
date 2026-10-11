#!/usr/bin/env python3
"""Validate Belgrade group g2 outputs: counts, nulls, samples."""
import csv, json, os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT_DIR = os.path.join(ROOT, "rik_2023_beograd_g2")
LOC = os.path.join(BASE, "beograd_g2_locations.json")
GEO = os.path.join(BASE, "beograd_g2_geo.json")
REPORT = os.path.join(BASE, "beograd_g2_match_report.json")

with open(os.path.join(OUT_DIR, "manifest.csv"), encoding="utf-8-sig") as fh:
    manifest = list(csv.DictReader(fh))
locs = json.load(open(LOC, encoding="utf-8"))
geo = json.load(open(GEO, encoding="utf-8"))
report = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else []

print(f"manifest stations: {len(manifest)}")
print(f"locations rows:    {len(locs)}")
print(f"geo rows:          {len(geo)}")
null_lat = [g for g in geo if g["lat"] is None]
null_addr = [l for l in locs if not l.get("address")]
print(f"null coordinates:  {len(null_lat)}")
print(f"null addresses:    {len(null_addr)}")
print(f"match problems:    {len(report)}")

print("\nper municipality (manifest vs geo):")
from collections import Counter
cm = Counter(m["municipality"] for m in manifest)
cg = Counter(g["municipality"] for g in geo)
cs = Counter(g.get("source") for g in geo)
for m in cm:
    print(f"  {m:<38} manifest {cm[m]:>3}  geo {cg.get(m,0):>3}")
print("sources:", dict(cs))

print("\n5 sample rows:")
for g in geo[:5]:
    print(json.dumps(g, ensure_ascii=False))

assert len(geo) == len(manifest), "geo count != manifest count"
assert all(g["lat"] is not None and g["lon"] is not None for g in geo), "null coords!"
print("\nOK: counts match, zero null coordinates.")
