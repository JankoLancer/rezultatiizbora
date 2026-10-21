#!/usr/bin/env python3
"""Build the committee dataset used by map/odbori.html.

Reads parsed decisions from odbori/data/<municipality>_decisions.json, applies
appointments / supplements / replacements chronologically, normalises proposers
into lists, and writes map/odbori.json.

Usage: python3 odbori/build_odbori.py [municipality]
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "odbori", "data")
OUT = os.path.join(ROOT, "map", "odbori.json")
RIK = "https://www.rik.parlament.gov.rs"

# Canonical lists / parliamentary groups. `aliases` are matched against the raw
# proposer text, case-insensitively, in this order.
LISTS = [
    {
        "key": "sns",
        "name": "Александар Вучић – Уједињена Србија / СНС",
        "short": "SNS",
        "color": "#1a6fb5",
        "aliases": ["александар вучић", "србија не сме да стане", "уједињена србија"],
    },
    {
        "key": "sps",
        "name": "Ивица Дачић – Фактор стабилности / СПС",
        "short": "SPS",
        "color": "#e6550d",
        "aliases": ["ивица дачић", "фактор стабилности", "социјалистичка партија србије"],
    },
    {
        "key": "nps",
        "name": "Народни покрет Србије – Ново лице Србије",
        "short": "НПС",
        "color": "#8856a7",
        "aliases": ["народни покрет србије", "ново лице србије"],
    },
    {
        "key": "studenti",
        "name": "Студентска листа – Студенти побеђују",
        "short": "Студенти",
        "color": "#31a354",
        "aliases": ["студентска листа", "студенти побеђују", "посланици уз студенте", "студенти"],
    },
    {
        "key": "ssp",
        "name": "Европска Србија / Странка слободе и правде",
        "short": "ССП",
        "color": "#bd9e00",
        "aliases": ["странка слободе и правде", "европска србија", "ссп"],
    },
    {
        "key": "zlf",
        "name": "Зелено-леви фронт – Не давимо Београд",
        "short": "ЗЛФ",
        "color": "#6b6b6b",
        "aliases": ["зелено-леви фронт", "зелено леви фронт", "не давимо београд"],
    },
    {
        "key": "ljajic",
        "name": "Расим Љајић – Људски (СДП – ЦДП)",
        "short": "Људски",
        "color": "#d7301f",
        "aliases": ["расим љајић", "људски"],
    },
    {
        "key": "desnica",
        "name": "Аутентична десница / Нови ДСС – НАДА",
        "short": "АД",
        "color": "#7fa8c9",
        "aliases": ["аутентична десница", "милош јовановић", "нови дсс", "монархисти"],
    },
    {
        "key": "karic",
        "name": "Богољуб Карић – Покрет снага Србије",
        "short": "БК",
        "color": "#c49c94",
        "aliases": ["богољуб карић", "покрет снага србије"],
    },
    {
        "key": "sda",
        "name": "СДА Санџака – Чувари Санџака",
        "short": "СДА",
        "color": "#8c6d31",
        "aliases": ["сда санџака", "sda sandžaka", "чувари санџака"],
    },
    {
        "key": "sdps",
        "name": "Социјалдемократска партија Србије",
        "short": "СДПС",
        "color": "#9c9ede",
        "aliases": ["социјалдемократска партија србије", "сдпс"],
    },
    {
        "key": "js",
        "name": "Драган Марковић Палма – Јединствена Србија",
        "short": "ЈС",
        "color": "#8c564b",
        "aliases": ["једиствена србија", "драган марковић"],
    },
    {
        "key": "pups",
        "name": "ПУПС – Солидарност и правда",
        "short": "ПУПС",
        "color": "#e377c2",
        "aliases": ["пупс"],
    },
    {
        "key": "svm",
        "name": "Савез војвођанских Мађара",
        "short": "СВМ",
        "color": "#17becf",
        "aliases": ["савез војвођанских мађара", "svm"],
    },
    {
        "key": "psg",
        "name": "Покрет слободних грађана – СДА Санџака",
        "short": "ПСГ",
        "color": "#bcbd22",
        "aliases": ["покрет слободних грађана", "псг"],
    },
    {
        "key": "srce",
        "name": "Србија центар – СРЦЕ",
        "short": "СРЦЕ",
        "color": "#9467bd",
        "aliases": ["србија центар", "срце"],
    },
    {
        "key": "radnicka",
        "name": "Радничка партија – Руска странка – Уједињена сељачка странка",
        "short": "РП",
        "color": "#a55194",
        "aliases": ["радничка партија"],
    },
    {
        "key": "gradska_uprava",
        "name": "Градска управа (предлог начелника)",
        "short": "ГУ",
        "color": "#6b6b6b",
        "aliases": ["начелника градске управе", "градске управе", "начелник градске управе"],
    },
]
DEFAULT_LIST = {
    "key": "ostalo",
    "name": "Остали предлагачи",
    "short": "Остало",
    "color": "#9aa5b1",
}

PROPOSER_FIXES = {
    (19, "ДРАГАНА МИЛОЈЕВИЋ"): "Посланичке групе АЛЕКСАНДАР ВУЧИЋ - Србија не сме да стане",
}

NAME_FIXES = {
    "ГОРАННИКОЛИЋ": "ГОРАН НИКОЛИЋ",
    "БРАНКОШОШКИЋ": "БРАНКО ШОШКИЋ",
    "ЗОРАНДИМИЋ": "ЗОРАН ДИМИЋ",
    "МИРОСЛАВ: ЖИВАНОВИЋ": "МИРОСЛАВ ЖИВАНОВИЋ",
    "ЗОРАНОБРАДОВИЋ": "ЗОРАН ОБРАДОВИЋ",
    "СРЂАНПАВИЋЕВИЋ": "СРЂАН ПАВИЋЕВИЋ",
}

ROLE_LABEL = {
    "predsednik": "Председник",
    "zamenik_predsednika": "Заменик председника",
    "clan": "Члан",
    "zamenik_clana": "Заменик члана",
}


def clean(s):
    s = re.sub(r"\s+", " ", s or "").strip(" ,;.")
    return s


def slug(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "ostalo"


CYR2LAT = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","ђ":"dj","е":"e","ж":"z","з":"z",
    "и":"i","ј":"j","к":"k","л":"l","љ":"lj","м":"m","н":"n","њ":"nj","о":"o",
    "п":"p","р":"r","с":"s","т":"t","ћ":"c","у":"u","ф":"f","х":"h","ц":"c",
    "ч":"c","џ":"dz","ш":"s",
    "č":"c","ć":"c","š":"s","ž":"z","đ":"dj",
})


def fold(s):
    s = (s or "").lower().translate(CYR2LAT)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def list_for(proposer):
    p = fold(proposer)
    for item in LISTS:
        for a in item["aliases"]:
            if fold(a) in p:
                return item
    return DEFAULT_LIST


def role_label(role, index):
    base = ROLE_LABEL.get(role, role)
    if role in ("clan", "zamenik_clana") and index:
        return f"{base} {index}"
    return base


def station_title_parts(title):
    m = re.match(r"\s*(\d+)\s*-\s*(.+)", title or "")
    if not m:
        return None, clean(title)
    return int(m.group(1)), clean(m.group(2))


def place_from_ocr(text):
    m = re.search(
        r"МЕСТО\s+БРОЈ\s+\d+\s+ГРАДУ\s+[^\n]+\s*\n(.+?)\n\s*1\.\s+У\s+бирачки",
        text,
        re.S | re.I,
    )
    if not m:
        return ""
    s = clean(re.sub(r"\s+", " ", m.group(1)))
    return s


def apply_decisions(decisions):
    """Return roster per station/composition after applying all documents."""
    stations = defaultdict(lambda: {"stalni": [], "prosireni": [], "docs": []})
    problems = []
    # stable order: date, then base before supplements before changes
    prio = {"imenovanje": 0, "dopuna": 1, "izmena": 2, "ispravka": 2, "other": 3}
    decisions = sorted(
        decisions,
        key=lambda d: (d.get("datetime") or 0, prio.get(d.get("type"), 3), d.get("url") or ""),
    )
    for d in decisions:
        no = d.get("station_no")
        comp = d.get("composition")
        if not no or comp not in ("stalni", "prosireni"):
            continue
        st = stations[no]
        st["docs"].append(
            {
                "url": RIK + d["url"] if d["url"].startswith("/") else d["url"],
                "type": d.get("type"),
                "composition": comp,
                "datetime": d.get("datetime"),
                "title": d.get("decision_title"),
            }
        )
        if d.get("type") == "imenovanje":
            # A fresh base decision replaces the roster for this composition.
            st[comp] = []
            for e in d.get("entries") or []:
                add_entry(st[comp], e, problems, no, comp, d)
        elif d.get("type") == "dopuna":
            for e in d.get("entries") or []:
                add_entry(st[comp], e, problems, no, comp, d)
        elif d.get("type") in ("izmena", "ispravka"):
            for ch in d.get("changes") or []:
                apply_change(st[comp], ch, problems, no, comp, d)
    return stations, problems


def add_entry(roster, e, problems, no, comp, doc):
    name = NAME_FIXES.get(clean(e.get("name")), clean(e.get("name")))
    if not name:
        return
    role = e.get("role")
    idx = e.get("index")
    if idx is None and role in ("clan", "zamenik_clana"):
        used = {x.get("index") for x in roster if x.get("role") == role and x.get("index")}
        idx = (max(used) if used else 0) + 1
    proposer = PROPOSER_FIXES.get((no, name), clean(e.get("proposer")))
    url = doc.get("url") or ""
    item = {
        "role": role,
        "index": idx,
        "name": name,
        "proposer_raw": proposer,
        "source": (RIK + url) if url.startswith("/") else url,
    }
    # Do not duplicate the same person in the same role.
    for old in roster:
        if old["role"] == item["role"] and old.get("index") == item.get("index") and old["name"].lower() == name.lower():
            return
    roster.append(item)


def apply_change(roster, ch, problems, no, comp, doc):
    old_name = clean(ch.get("old_name"))
    if not roster:
        problems.append(
            {
                "station": no,
                "composition": comp,
                "error": "change_without_base",
                "old": old_name,
                "new": clean(ch.get("name")),
                "url": doc.get("url"),
            }
        )
        return
    new_name = clean(ch.get("name"))
    role = ch.get("role")
    idx = ch.get("index")
    if not new_name:
        return
    # find old entry by name first
    candidate = None
    for e in roster:
        if e["name"].lower() == old_name.lower():
            candidate = e
            break
    if candidate is None:
        # fuzzy by name
        from difflib import SequenceMatcher
        best, score = None, 0
        for e in roster:
            r = SequenceMatcher(None, e["name"].lower(), old_name.lower()).ratio()
            if r > score:
                best, score = e, r
        if best is not None and score >= 0.78:
            candidate = best
    if candidate is None:
        # fall back to role/index only when unambiguous
        cands = [e for e in roster if e["role"] == role and (idx is None or e.get("index") == idx)]
        if len(cands) == 1:
            candidate = cands[0]
    if candidate is None:
        problems.append(
            {
                "station": no,
                "composition": comp,
                "error": "change_old_not_found",
                "old": old_name,
                "new": new_name,
                "role": role,
                "index": idx,
                "url": doc.get("url"),
            }
        )
        # Add the new person rather than silently losing them.
        roster.append(
            {
                "role": role,
                "index": idx,
                "name": new_name,
                "proposer_raw": clean(ch.get("proposer")),
                "unresolved_change": True,
            }
        )
        return
    candidate["name"] = new_name
    if ch.get("proposer"):
        candidate["proposer_raw"] = clean(ch.get("proposer"))
    url = doc.get("url") or ""
    candidate["source"] = (RIK + url) if url.startswith("/") else url
    candidate["changed"] = True


def build(municipality="kragujevac", election=None, municipality_name="Град Крагујевац"):
    decisions = json.load(open(os.path.join(DATA, municipality + "_decisions.json"), encoding="utf-8"))
    # de-duplicate by URL (the RIK API repeats some documents)
    seen = set()
    unique = []
    for d in decisions:
        if d["url"] in seen:
            continue
        seen.add(d["url"])
        unique.append(d)
    stations, problems = apply_decisions(unique)

    out_stations = []
    by_list = {"stalni": defaultdict(lambda: {"members": 0, "deputies": 0, "stations": set()}),
               "prosireni": defaultdict(lambda: {"members": 0, "deputies": 0, "stations": set()})}
    for no in sorted(stations):
        st = stations[no]
        title = ""
        for d in st["docs"]:
            # title is in the decision record; recover from the parsed file below
            pass
        # station title from the first document's metadata is attached during parse
        title = st.get("title") or ""
        committees = {}
        for comp in ("stalni", "prosireni"):
            roster = st[comp]
            # de-duplicate by (role,index,name)
            uniq = {}
            for e in roster:
                key = (e["role"], e.get("index"), e["name"].lower())
                uniq[key] = e
            roster = sorted(
                uniq.values(),
                key=lambda e: (
                    {"predsednik": 0, "zamenik_predsednika": 1, "clan": 2, "zamenik_clana": 3}.get(e["role"], 9),
                    e.get("index") or 0,
                    e["name"],
                ),
            )
            members = []
            counts = Counter()
            for e in roster:
                lst = list_for(e.get("proposer_raw"))
                e2 = dict(e)
                e2["list"] = lst["key"]
                e2["list_name"] = lst["name"]
                e2["list_short"] = lst["short"]
                e2["role_label"] = role_label(e["role"], e.get("index"))
                e2["deputy"] = e["role"] in ("zamenik_predsednika", "zamenik_clana")
                members.append(e2)
                counts[lst["key"]] += 1
                is_deputy = e2["deputy"]
                by_list[comp][lst["key"]]["members" if not is_deputy else "deputies"] += 1
                if not is_deputy:
                    by_list[comp][lst["key"]]["stations"].add(no)
            committees[comp] = {
                "members": members,
                "counts": dict(counts),
                "total": len(members),
            }
        out_stations.append(
            {
                "no": no,
                "title": title,
                "name": re.sub(r"^\d+\s*-\s*", "", title),
                "place": st.get("place", ""),
                "committees": committees,
                "docs": st["docs"],
            }
        )

    # fill titles/places from metadata of the decisions
    # (parse_odbori keeps station_title; attach it to the first doc of the station)
    meta_by_no = {}
    for d in unique:
        no = d.get("station_no")
        if not no:
            continue
        old = meta_by_no.get(no)
        if old is None or (not old.get("place") and d.get("place")):
            meta_by_no[no] = d
    for s in out_stations:
        d = meta_by_no.get(s["no"])
        if d:
            s["title"] = d.get("station_title") or s["title"]
            s["name"] = re.sub(r"^\d+\s*-\s*", "", s["title"])
            s["place"] = d.get("place") or s["place"]

    lists_meta = []
    for item in LISTS + [DEFAULT_LIST]:
        lists_meta.append(
            {
                "key": item["key"],
                "name": item["name"],
                "short": item["short"],
                "color": item["color"],
            }
        )

    summary = {
        "stations_total": len(out_stations),
        "stations_stalni": sum(1 for s in out_stations if s["committees"]["stalni"]["total"]),
        "stations_prosireni": sum(1 for s in out_stations if s["committees"]["prosireni"]["total"]),
        "by_list": {},
    }
    for comp in ("stalni", "prosireni"):
        rows = []
        for item in lists_meta:
            k = item["key"]
            v = by_list[comp].get(k)
            if not v:
                continue
            rows.append(
                {
                    "key": k,
                    "name": item["name"],
                    "short": item["short"],
                    "color": item["color"],
                    "members": v["members"],
                    "deputies": v["deputies"],
                    "total": v["members"] + v["deputies"],
                    "stations": len(v["stations"]),
                }
            )
        rows.sort(key=lambda r: (-r["members"], -r["total"], r["name"]))
        summary["by_list"][comp] = rows

    data = {
        "meta": {
            "election": election or {"id": "parl2026", "name": "Парламентарни 2026", "date": "2026-10-25"},
            "municipality": {"name": municipality_name, "slug": municipality},
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "https://www.rik.parlament.gov.rs/dokumenta/41985",
            "lists": lists_meta,
            "notes": [
                "Подаци су извучени из решења Градске изборне комисије објављених на сајту РИК-а.",
                "Проширени састав чине чланови и заменици чланова које предлажу подносиоци изборних листа (контролори).",
                "Стални састав чине председник, заменик председника, два члана и два заменика чланова које предлажу посланичке групе.",
                "Приказан је састав после примене свих измена, допуна и замена објављених до датума израде.",
            ],
        },
        "stations": out_stations,
        "summary": summary,
        "problems": problems,
    }
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    csv_path = os.path.join(os.path.dirname(OUT), "odbori.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([
            "station_no", "station_title", "place", "composition", "role",
            "index", "name", "list_key", "list_short", "proposer_raw", "source",
        ])
        for s in out_stations:
            for comp in ("stalni", "prosireni"):
                for p in s["committees"][comp]["members"]:
                    w.writerow([
                        s["no"], s["title"], s["place"], comp, p["role"],
                        p.get("index") or "", p["name"], p["list"], p["list_short"],
                        p["proposer_raw"], p.get("source", ""),
                    ])
    print(f"wrote {csv_path}")
    print(f"wrote {OUT}: {len(out_stations)} stations, {len(problems)} problems")
    print("permanent stations:", summary["stations_stalni"], "expanded stations:", summary["stations_prosireni"])
    for comp in ("stalni", "prosireni"):
        print(comp, [(r["short"], r["members"], r["deputies"]) for r in summary["by_list"][comp]])


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "kragujevac")
