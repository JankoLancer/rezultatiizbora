#!/usr/bin/env python3
"""Fill any null coordinates in geo/*_stations_geo.json from the file's centroid
and offset exactly co-located points. Idempotent.
"""
import glob
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def offset_dupes(d):
    groups = {}
    for i, s in enumerate(d):
        groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
    for idxs in groups.values():
        if len(idxs) > 1:
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                r = 0.0010 + 0.0003 * (j // 10)
                d[i]["lat"] += r * math.sin(ang)
                d[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(d[i]["lat"]))


def main():
    fixed = 0
    for p in sorted(glob.glob(os.path.join(HERE, "*_stations_geo.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        nulls = [x for x in d if x.get("lat") is None]
        if not nulls:
            continue
        good = [x for x in d if x.get("lat") is not None]
        if good:
            clat = sum(x["lat"] for x in good) / len(good)
            clon = sum(x["lon"] for x in good) / len(good)
        else:
            clat, clon = 44.0, 21.0
        for x in nulls:
            x["lat"], x["lon"] = clat, clon
            x["source"] = "center"
            x["display"] = x.get("display", "") or ""
        offset_dupes(d)
        tmp = p + ".tmp"
        json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        fixed += 1
        print(f"fixed {os.path.basename(p)}: {len(nulls)} nulls")
    print("files fixed:", fixed)


if __name__ == "__main__":
    main()
