#!/usr/bin/env python3
"""Ensure every city in geo/city_geo_targets.json has a complete geo file.

Runs geocode_locations.py (shared limiter) for any city whose
geo/<slug>_stations_geo.json is missing / has nulls / has wrong count.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# slug -> (municipality query, expected stations)
TARGETS = {
    "leskovac": ("Град Лесковац", 194), "vranje": ("Град Врање", 106),
    "valjevo": ("Град Ваљево", 103), "sabac": ("Град Шабац", 100),
    "novipazar": ("Град Нови Пазар", 99), "loznica": ("Град Лозница", 90),
    "uzice": ("Град Ужице", 88), "pirot": ("Град Пирот", 86),
    "smederevo": ("Град Смедерево", 78), "sombor": ("Град Сомбор", 76),
    "pancevo": ("Град Панчево", 74), "zrenjanin": ("Град Зрењанин", 71),
    "zajecar": ("Град Зајечар", 69), "pozarevac": ("Град Пожаревац", 68),
    "kikinda": ("Град Кикинда", 60),
    "sremskamitrovica": ("Град Сремска Митровица", 57),
    "vrsac": ("Град Вршац", 56), "bor": ("Град Бор", 47),
}


def ok(slug, expected):
    p = os.path.join(HERE, f"{slug}_stations_geo.json")
    if not os.path.exists(p):
        return False
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return len(d) == expected and not any(x.get("lat") is None for x in d)


def main():
    for slug, (muni, exp) in TARGETS.items():
        if ok(slug, exp):
            continue
        print(f"geocoding {slug} ...", flush=True)
        subprocess.run([sys.executable, os.path.join(HERE, "geocode_locations.py"),
                        slug, muni, "--force"], cwd=ROOT)
        print(f"done {slug}: ok={ok(slug, exp)}", flush=True)
    print("ALL CITY GEO DONE", flush=True)


if __name__ == "__main__":
    main()
