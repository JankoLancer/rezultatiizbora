#!/usr/bin/env python3
"""Pre-warm the Nominatim cache with addresses from the 2022 referendum docs.

Runs in parallel with the (much slower) PDF download so the final geocode pass
finds everything cached.
"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import beograd_g2_build_locations as B
from beograd_g2_geocode import queries, search

addrs = set()
for muni, f in B.DOCS.items():
    rows = B.parse_rows(os.path.join(BASE, f))
    for r in rows.values():
        if r["address"]:
            addrs.add(r["address"])
addrs = sorted(addrs)
print(f"pre-warm: {len(addrs)} unique addresses")
for i, a in enumerate(addrs, 1):
    for q in queries(a):
        h = search(q)
        if h:
            break
    print(f"  {i}/{len(addrs)} {a[:60]}")
print("pre-warm done")
