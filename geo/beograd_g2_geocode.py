#!/usr/bin/env python3
"""Geocode Belgrade group g2 stations by official 2022-referendum addresses."""
import json, os, re, time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "beograd_g2_locations.json")
OUT = os.path.join(BASE, "beograd_g2_geo.json")
CACHE = os.path.join(BASE, "beograd_g2_cache.json")
H = {"User-Agent": "izbori-vizualizacija-beograd-g2/1.0 (polling-station map)"}
VIEWBOX = "20.10,44.30,20.95,45.15"   # Belgrade + Sopot area
SLEEP = 4.5
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
GOOD = {"amenity", "building", "office", "leisure", "tourism", "highway", "place"}


def clean(a):
    a = re.sub(r"\bБР\.?\s*", " ", a, flags=re.I)
    a = re.sub(r"\bББ\b", " ", a)
    a = a.replace("ул.", " ")
    return re.sub(r"\s+", " ", a).strip(" ,")


def queries(addr):
    a = addr.strip()
    c = clean(a)
    qs = []
    parts = [p.strip() for p in a.split(",") if p.strip()]
    if len(parts) > 1:
        loc = clean(parts[0])
        rest = clean(",".join(parts[1:]))
        qs.append(f"{rest}, {loc}, Београд, Србија")
        street = re.sub(r"\s*\d+\w*\s*$", "", rest).strip(" ,")
        if street and street != rest:
            qs.append(f"{street}, {loc}, Београд, Србија")
        qs.append(f"{loc}, Београд, Србија")
    else:
        qs.append(f"{c}, Београд, Србија")
        street = re.sub(r"\s*\d+\w*\s*$", "", c).strip(" ,")
        if street and street != c:
            qs.append(f"{street}, Београд, Србија")
    qs.append(f"{c}, Србија")
    seen, res = set(), []
    for q in qs:
        if q and q not in seen:
            seen.add(q); res.append(q)
    return res


def search(q):
    if q in cache:
        return cache[q]
    res = None
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": q, "format": "json", "limit": 5, "countrycodes": "rs",
                                 "viewbox": VIEWBOX, "bounded": 1}, headers=H, timeout=30)
        data = r.json()
        if data:
            pick = next((d for d in data if d.get("class") in GOOD), data[0])
            res = {"lat": float(pick["lat"]), "lon": float(pick["lon"]),
                   "display": pick.get("display_name", ""), "type": pick.get("type")}
    except Exception as exc:
        print("   ! request failed:", exc)
        res = None
    cache[q] = res
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(SLEEP)
    return res


def main():
    rows = json.load(open(IN, encoding="utf-8"))
    repf = os.path.join(BASE, "beograd_g2_match_report.json")
    flagged = set()
    if os.path.exists(repf):
        for p in json.load(open(repf, encoding="utf-8")):
            if p.get("match") == "number-mismatch":
                flagged.add((p["municipality"], p["no"]))
    out = []
    for r in rows:
        hit = used = None
        src = "address"
        # venues absent from the 2022 document: resolve by venue name first
        if (r["municipality"], r["no"]) in flagged:
            for q in (f'{r["name"]}, Београд, Србија',
                      f'{r["name"]}, {r["municipality"]}, Србија'):
                hit = search(q)
                if hit:
                    used, src = q, "venue"
                    break
        if hit is None and r.get("address"):
            for q in queries(r["address"]):
                hit = search(q)
                if hit:
                    used, src = q, "address"
                    break
        out.append({**r, "lat": hit["lat"] if hit else None, "lon": hit["lon"] if hit else None,
                    "display": hit["display"] if hit else None, "source": src,
                    "geocoded_with": used})
        print(f"{r['municipality'][-12:]:<12} {r['no']:>3} {'OK ' if hit else 'X  '} "
              f"{str(r.get('address'))[:46]:<46} -> "
              f"{'' if not hit else str(round(hit['lat'],4))+','+str(round(hit['lon'],4))}")

    miss = sum(1 for s in out if s["lat"] is None)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nGeocoded {len(out)-miss}/{len(out)}; missing {miss}")


if __name__ == "__main__":
    main()
