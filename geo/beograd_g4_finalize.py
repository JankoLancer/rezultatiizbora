#!/usr/bin/env python3
"""Finalise the g4 Belgrade-municipality stations.

Stations with no coordinates after address geocoding, and stations geocoded
outside their municipality's expected extent (a broad viewbox can match a
same-named settlement elsewhere), are re-geocoded with a *tight per-municipality
bounding box* using venue-name / address / settlement queries.  Any point still
unresolved gets the municipality centre with a small per-station offset.

Reads/writes geo/beograd_g4_geo.json, reusing geo/beograd_g4_cache.json.
"""
import json
import math
import os
import re
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
GEO = os.path.join(BASE, "beograd_g4_geo.json")
CACHE = os.path.join(BASE, "beograd_g4_cache.json")
H = {"User-Agent": "izbori-vizualizacija/1.0 (polling-station mapping)"}
SLEEP = 4.5

MUNI_SHORT = {
    "Градска општина Раковица": "Раковица",
    "Градска општина Лазаревац": "Лазаревац",
    "Градска општина Младеновац": "Младеновац",
    "Градска општина Обреновац": "Обреновац",
    "Градска општина Гроцка": "Гроцка",
}
CENTERS = {
    "Градска општина Раковица": (44.742, 20.443),
    "Градска општина Лазаревац": (44.384, 20.258),
    "Градска општина Младеновац": (44.439, 20.697),
    "Градска општина Обреновац": (44.664, 20.200),
    "Градска општина Гроцка": (44.672, 20.717),
}
# minlon,minlat,maxlon,maxlat  (generous municipality extents)
BOXES = {
    "Градска општина Раковица": (20.37, 44.66, 20.51, 44.80),
    "Градска општина Лазаревац": (20.08, 44.25, 20.50, 44.58),
    "Градска општина Младеновац": (20.50, 44.27, 20.92, 44.62),
    "Градска општина Обреновац": (19.90, 44.42, 20.45, 44.72),
    "Градска општина Гроцка": (20.45, 44.52, 20.92, 44.85),
}
# venue names made of only these tokens are too generic for a name search
GENERIC = {"ОШ", "ОСНОВНА", "ШКОЛА", "СРЕДЊА", "ГИМНАЗИЈА", "ДОМ", "КУЛТУРЕ", "МЕСНЕ",
           "ЗАЈЕДНИЦЕ", "МЗ", "МЕСНА", "ЛОКАЛ", "ПРОСТОРИЈА", "САЛА", "ОБЈЕКАТ", "ЗГРАДА",
           "ПУ", "ВРТИЋ", "УПРАВА", "ГРАДСКА", "ОПШТИНА", "ЦЕНТАР", "ЗА", "СОЦИЈАЛНИ",
           "РАД", "ФК", "КЛУБ", "БИВША", "ПРОДАВНИЦА", "ПРЕДУЗЕЋА", "КАФАНА", "КАФИЋ",
           "РЕСТОРАН", "ГО", "СО", "КАНЦЕЛАРИЈА", "ОДЕЉЕЊЕ", "АМБУЛАНТА", "ЗДРАВЉА",
           "СУД", "ХОЛ", "ШКОЛЕ", "ШКОЛСКА", "ВАТРОГАСНИ", "УСТАНОВА", "ЦЕНТАР"}

cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def clean(a):
    a = re.sub(r"\([^)]*\)", " ", a)
    a = re.sub(r"\bБР\.?(?=\s*\d)", " ", a)
    a = re.sub(r"\bББ\b", " ", a)
    return re.sub(r"\s+", " ", a).strip(" ,")


def strip_num(rest):
    return re.sub(r"\s*\d+\s*([/\-]\s*[А-ЯЂЈЉЊЋЏA-Z0-9]+)?\s*$", "", rest).strip(" ,")


def addr_queries(addr, muni_short):
    a = addr.strip()
    c = clean(a)
    qs = []
    if "," in a:
        sett, rest_raw = a.split(",", 1)
        sett = sett.strip()
        rest = clean(rest_raw)
        qs.append(f"{rest}, {sett}, Београд, Србија")
        st = strip_num(rest)
        if st and st != rest:
            qs.append(f"{st}, {sett}, Београд, Србија")
        qs.append(f"{sett}, Београд, Србија")
        qs.append(f"{sett}, {muni_short}, Србија")
        qs.append(f"{sett}, Србија")
    else:
        qs.append(f"{c}, Београд, Србија")
        st = strip_num(c)
        if st and st != c:
            qs.append(f"{st}, Београд, Србија")
        qs.append(f"{c}, {muni_short}, Србија")
        qs.append(f"{c}, Србија")
    return qs


def search(q, box):
    key = f"{box}::{q}"
    if key in cache and cache[key]:
        return cache[key]     # reuse good value; retry previously-failed (None) queries
    b = [float(x) for x in box.split(",")]
    in_box = lambda lat, lon: b[0] <= lon <= b[2] and b[1] <= lat <= b[3]

    def request(bounded):
        params = {"q": q, "format": "json", "limit": 5, "countrycodes": "rs"}
        if bounded:
            params.update({"viewbox": box, "bounded": 1})
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params=params, headers=H, timeout=30)
        if r.status_code != 200:
            return None
        return r.json() or None

    res = None
    for bounded in (1, 0):        # bounded first, then unbounded (validated in-box)
        data = None
        for attempt in range(1, 3):
            try:
                data = request(bounded)
                break
            except Exception:
                time.sleep(3 * attempt)
        for d in (data or []):
            lat, lon = float(d["lat"]), float(d["lon"])
            if in_box(lat, lon):
                res = {"lat": lat, "lon": lon, "display": d.get("display_name", "")}
                break
        if res:
            break
        time.sleep(SLEEP)
    cache[key] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    data = json.load(open(GEO, encoding="utf-8"))
    stats = {"address": 0, "venue": 0, "center": 0}

    def in_box(s):
        b = BOXES.get(s["municipality"])
        if not b or s.get("lat") is None:
            return False
        return b[0] <= s["lon"] <= b[2] and b[1] <= s["lat"] <= b[3]

    for i, s in enumerate(data):
        reliable = s.get("lat") is not None and in_box(s)
        if reliable:
            stats[s.get("source", "address")] = stats.get(s.get("source", "address"), 0) + 1
            continue

        box = ",".join(str(x) for x in BOXES[s["municipality"]])
        was = "null" if s.get("lat") is None else "out-of-box"
        s["lat"] = s["lon"] = None

        def is_specific(name):
            return bool({t for t in re.findall(r"[А-ШЂЈЉЊЋЏA-Z0-9]+", name.upper())
                         if len(t) >= 3} - GENERIC)

        qs = addr_queries(s["address"], MUNI_SHORT[s["municipality"]])
        if is_specific(s["name"]):
            qs += [f'{s["name"]}, Београд, Србија',
                   f'{s["name"]}, {MUNI_SHORT[s["municipality"]]}, Србија']
        hit = used = None
        for q in qs:
            hit = search(q, box)
            if hit:
                used = q
                break
        if hit:
            s["lat"], s["lon"] = hit["lat"], hit["lon"]
            s["display"] = hit.get("display", "")
            s["geocoded_with"] = f"refine[{was}]: {used}"
            s["source"] = "venue"
            s["fallback"] = "refine"
            stats["venue"] += 1
            print(f"  refine {s['municipality'].split()[-1]:<10} {s['no']:>3} {s['name'][:30]:<30} "
                  f"-> {round(hit['lat'],4)},{round(hit['lon'],4)}  {used[:40]}")
        else:
            c = CENTERS.get(s["municipality"], (44.75, 20.45))
            ang = 2 * math.pi * (i % 24) / 24
            rad = 0.0008 + 0.0004 * (i // 24)
            s["lat"] = c[0] + rad * math.sin(ang)
            s["lon"] = c[1] + rad * math.cos(ang) / math.cos(math.radians(c[0]))
            s["display"] = "центар општине (процена)"
            s["geocoded_with"] = f"center-fallback[{was}]"
            s["source"] = "venue"
            s["fallback"] = "center"
            stats["center"] += 1
            print(f"  centre {s['municipality'].split()[-1]:<10} {s['no']:>3} {s['name'][:30]:<30} "
                  f"-> {round(s['lat'],4)},{round(s['lon'],4)}")

    # spread exactly co-located points so co-located stations stay visible
    groups = {}
    for i, s in enumerate(data):
        groups.setdefault((round(s["lat"], 5), round(s["lon"], 5)), []).append(i)
    for idxs in groups.values():
        if len(idxs) > 1:
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                r = 0.0006 + 0.0002 * (j // 8)
                data[i]["lat"] += r * math.sin(ang)
                data[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(data[i]["lat"]))

    json.dump(data, open(GEO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    missing = sum(1 for s in data if s.get("lat") is None or s.get("lon") is None)
    print(f"\nsource counts: {stats}")
    print(f"total {len(data)}; missing now {missing}")


if __name__ == "__main__":
    main()
