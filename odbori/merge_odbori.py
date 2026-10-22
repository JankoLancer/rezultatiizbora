#!/usr/bin/env python3
"""Merge per-municipality committee datasets into map/odbori.json/.csv.

Input:  odbori/data/<slug>_odbori.json
Output: map/odbori.json, map/odbori.json.gz, map/odbori.csv, map/odbori.csv.gz

The merged file contains:
  meta.cities   — city list with coverage and last update
  meta.lists    — canonical list/group metadata
  stations[]    — all stations, each with city/city_slug
  summary       — national totals and by_list
  summary.by_city[slug] — per-city totals and by_list
"""
import csv
import glob
import gzip
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "odbori", "data")
MUNI = os.path.join(ROOT, "odbori", "municipalities_2026.json")
MAP = os.path.join(ROOT, "map")

LIST_ORDER = [
    "sns", "sps", "nps", "studenti", "ssp", "zlf", "ljajic", "desnica",
    "karic", "sda", "sdps", "js", "pups", "svm", "psg", "srce",
    "radnicka", "gradska_uprava", "ostalo",
]


def empty_summary():
    return {"members": 0, "deputies": 0, "stations": set()}


def add_person(summary, p):
    v = summary[p["list"]]
    if p.get("deputy"):
        v["deputies"] += 1
    else:
        v["members"] += 1
        v["stations"].add((p.get("city_slug"), p.get("station_no")))


def finalize_rows(summary, lists_by_key):
    rows = []
    for key, v in summary.items():
        info = lists_by_key.get(key, {"key": key, "name": key, "short": key, "color": "#9aa5b1"})
        rows.append(
            {
                "key": key,
                "name": info["name"],
                "short": info["short"],
                "color": info["color"],
                "members": v["members"],
                "deputies": v["deputies"],
                "total": v["members"] + v["deputies"],
                "stations": len(v["stations"]),
            }
        )
    rows.sort(key=lambda r: (-r["members"], -r["total"], r["name"]))
    return rows


def main():
    cities_meta = {}
    if os.path.exists(MUNI):
        for m in json.load(open(MUNI, encoding="utf-8")):
            cities_meta[m["slug"]] = m

    files = sorted(glob.glob(os.path.join(DATA, "*_odbori.json")))
    if not files:
        raise SystemExit("no per-city datasets found in odbori/data/")

    # If the same municipality was processed under two slugs, keep the newer /
    # more complete dataset.
    chosen = {}
    for path in files:
        slug = os.path.basename(path)[: -len("_odbori.json")]
        d = json.load(open(path, encoding="utf-8"))
        mid = str((d.get("meta", {}).get("municipality") or {}).get("id") or slug)
        score = (
            slug in cities_meta,
            d.get("summary", {}).get("stations_total", 0),
            d.get("summary", {}).get("stations_stalni", 0),
            d.get("meta", {}).get("generated", ""),
        )
        if mid not in chosen or score > chosen[mid][0]:
            chosen[mid] = (score, path, slug, d)
    files = [v[1] for v in chosen.values()]
    print(f"unique municipalities: {len(files)} (from {len(glob.glob(os.path.join(DATA, '*_odbori.json')))} files)")

    stations = []
    lists_by_key = {}
    city_rows = {}
    city_summary = {}
    fetched = []

    for path in files:
        slug = os.path.basename(path)[: -len("_odbori.json")]
        d = json.load(open(path, encoding="utf-8"))
        city_name = d["meta"]["municipality"]["name"]
        for li in d["meta"].get("lists", []):
            lists_by_key.setdefault(li["key"], li)
        existing = {s["no"] for s in d.get("stations", [])}
        cache_path = os.path.join(ROOT, "odbori", "stations", slug + ".json")
        if os.path.exists(cache_path):
            cache = json.load(open(cache_path, encoding="utf-8"))
            for _sid, stname in cache.items():
                mm = re.match(r"\s*(\d+)", stname or "")
                if not mm:
                    continue
                no = int(mm.group(1))
                if no in existing:
                    continue
                title = (stname or "").strip()
                d.setdefault("stations", []).append({
                    "no": no,
                    "city": city_name,
                    "city_slug": slug,
                    "title": title,
                    "name": re.sub(r"^\d+\s*-\s*", "", title),
                    "place": "",
                    "committees": {
                        "stalni": {"members": [], "counts": {}, "total": 0},
                        "prosireni": {"members": [], "counts": {}, "total": 0},
                    },
                    "docs": [],
                })
        for s in d.get("stations", []):
            s["city"] = city_name
            s["city_slug"] = slug
            stations.append(s)
        city_total = len(d.get("stations", []))
        city_stalni = sum(1 for s in d.get("stations", []) if s["committees"]["stalni"]["total"])
        city_pros = sum(1 for s in d.get("stations", []) if s["committees"]["prosireni"]["total"])
        m = cities_meta.get(slug, {})
        fetched.append(d["meta"].get("fetched_at", ""))
        city_summary[slug] = {
            "name": city_name,
            "stations_total": city_total,
            "stations_stalni": city_stalni,
            "stations_prosireni": city_pros,
            "by_list": d["summary"]["by_list"],
        }
        status_path = os.path.join(ROOT, "odbori", "work", "status", slug + ".json")
        if os.path.exists(status_path):
            try:
                st = json.load(open(status_path, encoding="utf-8"))
                st.update({
                    "stations": d["summary"]["stations_total"],
                    "stations_stalni": d["summary"]["stations_stalni"],
                    "stations_prosireni": d["summary"]["stations_prosireni"],
                    "missing_permanent": max(0, d["summary"]["stations_total"] - d["summary"]["stations_stalni"]),
                    "missing_expanded": max(0, d["summary"]["stations_total"] - d["summary"]["stations_prosireni"]),
                })
                json.dump(st, open(status_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            except Exception:
                pass
        city_rows[slug] = {
            "slug": slug,
            "name": city_name,
            "region": d["meta"]["municipality"].get("region", m.get("region", "")),
            "region_name": d["meta"]["municipality"].get("region_name", m.get("region_name", "")),
            "stations_total": city_total,
            "stations_stalni": city_stalni,
            "stations_prosireni": city_pros,
            "missing_permanent": max(0, city_total - city_stalni),
            "missing_expanded": max(0, city_total - city_pros),
            "missing_permanent_nos": [x["no"] for x in d.get("stations", []) if not x["committees"]["stalni"]["total"]],
            "missing_expanded_nos": [x["no"] for x in d.get("stations", []) if not x["committees"]["prosireni"]["total"]],
            "documents": m.get("documents"),
            "fetched_at": d["meta"].get("fetched_at", ""),
            "generated": d["meta"].get("generated", ""),
            "complete": d["summary"]["stations_stalni"] >= d["summary"]["stations_total"],
            "parse_problems": len(json.load(open(path.replace("_odbori.json", "_problems.json"), encoding="utf-8")))
            if os.path.exists(path.replace("_odbori.json", "_problems.json")) else 0,
            "build_problems": len(d.get("problems", [])),
        }

    # remember dates and coverage in the master municipality registry
    if cities_meta:
        for slug, row in city_rows.items():
            m = cities_meta.get(slug)
            if m is None:
                continue
            m.update({
                "stations_total": row["stations_total"],
                "stations_stalni": row["stations_stalni"],
                "stations_prosireni": row["stations_prosireni"],
                "missing_permanent": row["missing_permanent"],
                "missing_expanded": row["missing_expanded"],
                "missing_permanent_nos": row["missing_permanent_nos"],
                "missing_expanded_nos": row["missing_expanded_nos"],
                "complete": row["complete"],
                "last_built_at": row["generated"],
                "last_fetched_at": row["fetched_at"],
                "parse_problems": row["parse_problems"],
                "build_problems": row["build_problems"],
            })
        json.dump(list(cities_meta.values()), open(MUNI, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    missing = {}
    for slug, row in city_rows.items():
        if row["missing_permanent"] or row["missing_expanded"]:
            missing[slug] = {
                "name": row["name"],
                "missing_permanent_nos": row["missing_permanent_nos"],
                "missing_expanded_nos": row["missing_expanded_nos"],
            }
    asof = (max(fetched) if fetched else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))[:10]
    json.dump(
        {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cities": missing},
        open(os.path.join(ROOT, "odbori", f"missing_{asof}.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1,
    )

    # canonical list order
    lists = []
    for k in LIST_ORDER:
        if k in lists_by_key:
            lists.append(lists_by_key[k])
    for k, v in lists_by_key.items():
        if k not in LIST_ORDER:
            lists.append(v)

    stations.sort(key=lambda s: (s.get("city", ""), s["no"]))
    cities = sorted(city_rows.values(), key=lambda c: (c.get("region_name", ""), c["name"]))

    summary = {
        "stations_total": len(stations),
        "stations_stalni": sum(1 for s in stations if s["committees"]["stalni"]["total"]),
        "stations_prosireni": sum(1 for s in stations if s["committees"]["prosireni"]["total"]),
        "by_list": {"stalni": [], "prosireni": []},
        "by_city": city_summary,
    }
    # national by_list must be separated by composition; recompute from stations
    nat = {"stalni": defaultdict(empty_summary), "prosireni": defaultdict(empty_summary)}
    for s in stations:
        for comp in ("stalni", "prosireni"):
            for p in s["committees"][comp]["members"]:
                v = nat[comp][p["list"]]
                if p.get("deputy"):
                    v["deputies"] += 1
                else:
                    v["members"] += 1
                    v["stations"].add((s["city_slug"], s["no"]))
    summary["by_list"] = {comp: finalize_rows(nat[comp], lists_by_key) for comp in ("stalni", "prosireni")}

    data = {
        "meta": {
            "election": {"id": "parl2026", "name": "Парламентарни 2026", "date": "2026-10-25"},
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_as_of": max(fetched) if fetched else "",
            "source": "https://www.rik.parlament.gov.rs/dokumenta/41985",
            "cities": cities,
            "lists": lists,
            "notes": [
                "Подаци су извучени из решења локалних изборних комисија објављених на сајту РИК-а.",
                "Проширени састав чине чланови и заменици чланова које предлажу подносиоци изборних листа (контролори).",
                "Стални састав чине председник, заменик председника, два члана и два заменика чланова које предлажу посланичке групе.",
                "Приказан је састав после примене свих измена, допуна и замена објављених до датума израде.",
            ],
        },
        "stations": stations,
        "summary": summary,
        "problems": [],
    }

    os.makedirs(MAP, exist_ok=True)
    out_json = os.path.join(MAP, "odbori.json")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    with open(out_json, "rb") as fh, gzip.open(out_json + ".gz", "wb", compresslevel=9) as gz:
        shutil.copyfileobj(fh, gz)
    json.dump({"meta": data["meta"], "summary": data["summary"]},
              open(os.path.join(MAP, "odbori-meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # merged CSV: city columns are already in per-city CSVs
    out_csv = os.path.join(MAP, "odbori.csv")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as dst:
        w = None
        chosen_slugs = {os.path.basename(p)[: -len("_odbori.json")] for p in files}
        for slug in sorted(chosen_slugs):
            path = os.path.join(DATA, slug + "_people.csv")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8-sig", newline="") as src:
                r = csv.reader(src, delimiter=";")
                header = next(r)
                if w is None:
                    w = csv.writer(dst, delimiter=";")
                    w.writerow(header)
                for row in r:
                    w.writerow(row)
    with open(out_csv, "rb") as fh, gzip.open(out_csv + ".gz", "wb", compresslevel=9) as gz:
        shutil.copyfileobj(fh, gz)

    print(f"merged {len(files)} cities, {len(stations)} stations")
    print(f"wrote {out_json} ({os.path.getsize(out_json)/1e6:.1f} MB)")
    print(f"wrote {out_csv} ({os.path.getsize(out_csv)/1e6:.1f} MB)")
    print("by_list:", {c: [(r["short"], r["members"], r["deputies"]) for r in summary["by_list"][c]] for c in ("stalni", "prosireni")})


if __name__ == "__main__":
    main()
