#!/usr/bin/env python3
"""Validate Grad Čačak artifacts: counts, coordinate nulls, alignment sources."""
import csv
import json
import os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_cacak", "manifest.csv")
LOC = os.path.join(BASE, "cacak_stations_locations.json")
GEO = os.path.join(BASE, "cacak_stations_geo.json")
REF = os.path.join(BASE, "cacak_ref_rows.json")

manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
loc = json.load(open(LOC, encoding="utf-8"))
geo = json.load(open(GEO, encoding="utf-8"))
ref = json.load(open(REF, encoding="utf-8"))

print(f"manifest stations : {len(manifest)}")
print(f"2022 ref rows     : {len(ref)}")
print(f"locations rows    : {len(loc)}")
print(f"geo rows          : {len(geo)}")

nos_l = [r["no"] for r in loc]
nos_g = [r["no"] for r in geo]
print(f"no range          : {min(nos_l)}..{max(nos_l)} contiguous={nos_l == list(range(1, len(nos_l)+1))}")

nulls = [s["no"] for s in geo if s.get("lat") is None or s.get("lon") is None]
print(f"null coordinates  : {nulls}")

srcs = Counter(s.get("source") for s in geo)
print(f"geocode sources   : {dict(srcs)}")
fbs = Counter(s.get("fallback") for s in geo if s.get("fallback"))
print(f"venue fallbacks   : {dict(fbs)}")

out_of_area = [s["no"] for s in geo
               if not (43.60 <= s["lat"] <= 44.15 and 20.00 <= s["lon"] <= 20.70)]
print(f"out-of-area coords: {out_of_area}")

with open(os.path.join(BASE, "cacak_align_report.txt"), encoding="utf-8") as fh:
    report = fh.read()
for line in report.splitlines()[:4]:
    print(f"report: {line}")

print("\n5 sample rows:")
for s in geo[:5]:
    print(json.dumps({k: s[k] for k in ("municipality", "no", "name", "address",
                                         "lat", "lon", "source", "geocoded_with")},
                     ensure_ascii=False))
