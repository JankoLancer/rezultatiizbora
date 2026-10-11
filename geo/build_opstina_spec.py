#!/usr/bin/env python3
"""Build geo/opstina_spec.json: the long-tail municipalities (opstine) that are
NOT standalone cities / city municipalities handled with dedicated pipelines.

Inputs (regenerate with the helpers if missing):
  /tmp/opencode/rik_municipalities.json  -> [{region,value,name,stations}]
  /tmp/opencode/ref_docs_map.json        -> {"MunicipalityName": ["/extfile/..", ...]}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from city_slugs import city_slug  # noqa: E402

RIK = "https://www.rik.parlament.gov.rs"

# standalone cities and city municipalities handled by the dedicated per-city pipeline
CITY_NAMES = {
    # standalone cities (all 25)
    "Нови Сад", "Лесковац", "Крагујевац", "Крушевац", "Краљево", "Чачак",
    "Ваљево", "Суботица", "Шабац", "Нови Пазар", "Јагодина", "Лозница",
    "Пирот", "Врање", "Ужице", "Смедерево", "Сомбор", "Панчево", "Зрењанин",
    "Зајечар", "Кикинда", "Пожаревац", "Сремска Митровица", "Вршац", "Бор",
    # city municipalities of cities
    "Врањска Бања", "Севојно", "Костолац",
    "Медијана", "Нишка Бања", "Пантелеј", "Црвени крст",
    # Belgrade city municipalities
    "Барајево", "Вождовац", "Врачар", "Гроцка", "Земун", "Звездара",
    "Лазаревац", "Младеновац", "Нови Београд", "Обреновац", "Раковица",
    "Савски Венац", "Сопот", "Стари Град", "Сурчин", "Чукарица",
    # Palilula appears for Beograd and Niš (both handled)
    "Палилула (Београд)", "Палилула (Ниш)",
}


def base_name(n):
    n = re.sub(r"\s*\(.*?\)\s*$", "", n).strip()
    n = re.sub(r"^(Град|Градска општина|Општина)\s+", "", n).strip()
    return n


def main():
    munis = json.load(open("/tmp/opencode/rik_municipalities.json", encoding="utf-8"))
    docs = json.load(open("/tmp/opencode/ref_docs_map.json", encoding="utf-8"))
    docbases = {}
    for k, v in docs.items():
        docbases.setdefault(base_name(k), []).extend(v)

    spec, missing = [], []
    for m in munis:
        if m["region"] == 5:            # Kosovo: no address docs, skip here
            continue
        b = base_name(m["name"])
        if b in CITY_NAMES:
            continue
        urls = docbases.get(b)
        if not urls:
            missing.append((m["region"], m["value"], m["name"]))
            continue
        spec.append({
            "slug": city_slug(b),
            "name": b,
            "region": m["region"],
            "value": m["value"],
            "stations": m["stations"],
            "docs": [RIK + u for u in urls],
        })

    spec.sort(key=lambda s: -s["stations"])
    json.dump(spec, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "opstina_spec.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    total = sum(s["stations"] for s in spec)
    print(f"opstina spec: {len(spec)} municipalities, {total} stations")
    if missing:
        print(f"WARNING {len(missing)} municipalities without docs (excluded):")
        for x in missing:
            print("   ", x)
    for s in spec[:10]:
        print(f"  {s['stations']:>4}  {s['name']:<22} {s['slug']}")


if __name__ == "__main__":
    main()
