#!/usr/bin/env python3
"""Prewarm the Krusevac Nominatim cache from the 2022 reference addresses.

Reuses the query construction and cached search from krusevac_geocode_addr.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from krusevac_geocode_addr import queries, search  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(BASE, "krusevac_ref_rows.json")


def main():
    rows = json.load(open(REF, encoding="utf-8"))
    seen = set()
    total = 0
    for r in rows:
        for q in queries(r["address"]):
            if q in seen:
                continue
            seen.add(q)
            total += 1
            hit = search(q)
            if hit:
                break
        if total % 10 == 0:
            print(f"  prewarmed {total} queries", flush=True)
    print(f"prewarm done; {total} queries touched")


if __name__ == "__main__":
    main()
