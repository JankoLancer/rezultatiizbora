#!/usr/bin/env python3
"""Build RIK 2023 polling-station locations for ГРАД ПОЖАРЕВАЦ (+ ГО Костолац).

Inputs:
  geo/pozarevac_ref.doc               -- 2022 referendum "glasacka mesta" doc
  rik_2023_pozarevac/manifest.csv     -- RIK 2023 authoritative station list

The reference document contains TWO tables with independent R.БР. numbering:
  * table 1: 57 stations for Град Пожаревац  (колоне: Р.БР. | НАЗИВ | АДРЕСА | ПОДРУЧЈЕ)
  * table 2: 11 stations for Градска општина Костолац (numbering restarts at 1)

The generic `geo/opstina_docs.py` parser assumes a single numbered table and,
because many venue names wrap onto continuation table lines, returns 75 rows in
sequential mode (over-count).  As with the Smедерево builder we therefore group
the raw antiword table lines by their R.БР. column: a new logical station starts
whenever column 0 holds a number; otherwise the line is a wrapped continuation
of the current station's name/address/area.

Alignment: manifest rows are grouped in manifest order by municipality
(Град Пожаревац first, then Градска општина Костолац); each group is matched
1:1 in order with the corresponding doc table.  The `no` field is the station
number as printed in the manifest, `name` the manifest venue (without the
"N - " prefix) and `address` the doc address.

Outputs:
  geo/pozarevac_stations_locations.json  -> [{municipality,no,name,address}]
  geo/pozarevac_align_report.txt
"""
import csv
import json
import os
import re
import subprocess
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REF = os.path.join(HERE, "pozarevac_ref.doc")
MANIFEST = os.path.join(ROOT, "rik_2023_pozarevac", "manifest.csv")
LOC_OUT = os.path.join(HERE, "pozarevac_stations_locations.json")
REPORT = os.path.join(HERE, "pozarevac_align_report.txt")

MUNI1 = "Град Пожаревац"
MUNI2 = "Градска општина Костолац"
EXPECTED = 68


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _is_num(s):
    return bool(re.match(r"^\d{1,3}\.?$", (s or "").strip()))


def parse_ref(path):
    """Group raw antiword table lines into logical stations by Р.БР. column."""
    txt = subprocess.run(["antiword", "-w", "0", path],
                         capture_output=True).stdout.decode("utf-8", "replace")
    stations = []
    for line in txt.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        c0 = cells[0] if len(cells) > 0 else ""
        c1 = cells[1] if len(cells) > 1 else ""
        c2 = cells[2] if len(cells) > 2 else ""
        c3 = cells[3] if len(cells) > 3 else ""
        # skip repeated table headers ("Р.БР. | НАЗИВ БИРАЧКОГ МЕСТА | ...")
        if "Р.БР" in c0.upper() or c1.upper().startswith("НАЗИВ БИРАЧКОГ"):
            continue
        if _is_num(c0):
            stations.append({"no": int(c0.rstrip(".")), "name": c1,
                             "address": c2, "area": c3})
        else:
            if not stations:
                continue
            # wrapped continuation of name/address/area
            if c1:
                stations[-1]["name"] = (stations[-1]["name"] + " " + c1).strip()
            if c2:
                stations[-1]["address"] = (stations[-1]["address"] + " " + c2).strip()
            if c3:
                stations[-1]["area"] = (stations[-1]["area"] + " " + c3).strip()
    return [s for s in stations if s["name"] or s["address"]]


def read_manifest():
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    out = []
    for r in rows:
        rk = r["station_name"].strip()
        m = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
        no = int(m.group(1)) if m else 0
        venue = (m.group(2) if m else rk).strip()
        out.append({"station_id": r["station_id"],
                    "municipality": r["municipality"], "no": no, "venue": venue})
    return out


def main():
    man = read_manifest()
    docs = parse_ref(REF)

    # split manifest by municipality, preserving order of first appearance
    groups = []
    for m in man:
        if not groups or groups[-1][0] != m["municipality"]:
            groups.append((m["municipality"], []))
        groups[-1][1].append(m)

    # split doc into the two contiguous tables (numbering resets to 1)
    tables, cur = [], []
    for d in docs:
        if d["no"] == 1 and cur:
            tables.append(cur)
            cur = []
        cur.append(d)
    if cur:
        tables.append(cur)

    # map doc table -> manifest municipality group (by size, in order)
    doc_by_muni = {}
    if len(tables) == len(groups):
        for (muni, _), tbl in zip(groups, tables):
            doc_by_muni[muni] = tbl

    loc, report = [], []
    for muni, mans in groups:
        tbl = doc_by_muni.get(muni, [])
        for i, m in enumerate(mans):
            d = tbl[i] if i < len(tbl) else None
            addr = (d.get("address") or "").strip() if d else ""
            dname = d.get("name", "") if d else ""
            loc.append({"municipality": muni, "no": m["no"],
                        "name": m["venue"], "address": addr})
            flag = []
            if d is None:
                flag.append("NO DOC ROW")
            else:
                s = sim(dname, m["venue"])
                if s < 0.4:
                    flag.append(f"NAME MISMATCH (sim={s:.2f}, doc='{dname}')")
                if not addr:
                    flag.append("EMPTY ADDRESS")
            if flag:
                report.append(f"{muni} no={m['no']} '{m['venue']}' -> " +
                              "; ".join(flag))

    json.dump(loc, open(LOC_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    counts = {}
    for x in loc:
        counts[x["municipality"]] = counts.get(x["municipality"], 0) + 1
    empty = sum(1 for x in loc if not x["address"])
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"doc rows parsed: {len(docs)} (tables: "
                 f"{[len(t) for t in tables]})\n")
        fh.write(f"manifest rows: {len(man)}  groups: {counts}\n")
        fh.write(f"locations written: {len(loc)}  empty addresses: {empty}\n")
        fh.write(f"issues: {len(report)}\n")
        for line in report:
            fh.write("  " + line + "\n")

    print(f"doc rows={len(docs)} tables={[len(t) for t in tables]} "
          f"manifest={len(man)} groups={counts}")
    print(f"wrote {LOC_OUT} ({len(loc)} rows, empty addresses {empty}, "
          f"issues {len(report)})")
    if report:
        print("issues:")
        for line in report:
            print("  " + line)
    if len(loc) != EXPECTED:
        raise SystemExit(f"expected {EXPECTED} locations, got {len(loc)}")


if __name__ == "__main__":
    main()
