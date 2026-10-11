#!/usr/bin/env python3
"""Geocode an existing geo/<slug>_stations_locations.json into
geo/<slug>_stations_geo.json, using the shared Nominatim limiter.

Usage:
  python3 geo/geocode_locations.py <slug> <municipality_query> [--force]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pipeline_opstina as P  # noqa: E402


def main():
    slug = sys.argv[1]
    muni = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else slug
    loc_path = os.path.join(HERE, f"{slug}_stations_locations.json")
    if not os.path.exists(loc_path):
        raise SystemExit(f"missing {loc_path}")
    loc = json.load(open(loc_path, encoding="utf-8"))
    for x in loc:
        x["_venue"] = x.get("name", "")
        x.setdefault("municipality", muni)
    spec = {"slug": slug, "name": muni, "stations": len(loc)}
    force = "--force" in sys.argv
    geo = P.geocode(spec, loc, force=force)
    nulls = sum(1 for x in geo if x.get("lat") is None)
    src = {}
    for x in geo:
        src[x.get("source", "?")] = src.get(x.get("source", "?"), 0) + 1
    print(f"{slug}: geo={len(geo)} nulls={nulls} sources={src}")


if __name__ == "__main__":
    main()
