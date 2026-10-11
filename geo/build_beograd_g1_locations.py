#!/usr/bin/env python3
"""Align RIK 2023 Belgrade-g1 stations with the 2022 referendum address list.

Reads  rik_2023_beograd_g1/manifest.csv     (station_name like "N - VENUE")
and    geo/beograd_g1_ref_rows.json         (parsed 2022 decisions, per municipality)
Writes geo/beograd_g1_locations.json        [{municipality, no, name, address}, ...]

RIK 2023 venue names are authoritative.  Addresses come from the 2022 decision
row with the same number; when the 2023 ballot shifted/added stations the row is
re-matched by exact normalised venue name.  Stations absent from the 2022 doc
inherit the address of the identical venue, otherwise keep the same-number
address and are flagged.  All mismatches are printed.
"""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_beograd_g1", "manifest.csv")
DOC = os.path.join(BASE, "beograd_g1_ref_rows.json")
OUT = os.path.join(BASE, "beograd_g1_locations.json")

# RIK municipality name -> key used in beograd_g1_ref_rows.json
MUNI_KEY = {
    "Градска општина Нови Београд": "Нови Београд",
    "Градска општина Земун": "Земун",
    "Градска општина Сурчин": "Сурчин",
    "Градска општина Барајево": "Барајево",
}
ORDER = ["Градска општина Нови Београд", "Градска општина Земун",
         "Градска општина Сурчин", "Градска општина Барајево"]

_QUOTES = "„“”\"'❝❞«»"


def norm(s):
    s = s.upper()
    for q in _QUOTES:
        s = s.replace(q, " ")
    s = re.sub(r"[^0-9A-ZА-ШЂЈЉЊЋЏЂ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return set(w for w in norm(s).split() if len(w) >= 3)


def main():
    rows = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    doc_all = json.load(open(DOC, encoding="utf-8"))

    out, report = [], {}
    for muni in ORDER:
        key = MUNI_KEY[muni]
        doc = doc_all.get(key, [])
        doc_by_no = {d["no"]: d for d in doc}
        by_norm = {}
        for d in doc:
            by_norm.setdefault(norm(d["name"]), []).append(d)

        mismatches, missing, used_addr = [], [], {}
        for r in rows:
            if r["municipality"] != muni:
                continue
            name = r["station_name"].strip()
            num_s, venue = name.split(" - ", 1) if " - " in name else name.split(" ", 1)
            num, venue = int(num_s), venue.strip()
            d = doc_by_no.get(num)
            address = d["address"] if d else ""
            rematch = None
            if norm(venue) in by_norm:
                exact = by_norm[norm(venue)]
                chosen = next((c for c in exact if c["no"] == num), exact[0])
                if chosen["no"] != num:
                    rematch = chosen["no"]
                    address = chosen["address"]
            elif not d:
                # station absent from 2022 decision: best token-overlap row
                v = toks(venue)
                best, bo = None, 0
                for c in doc:
                    ov = len(v & toks(c["name"]))
                    if ov > bo:
                        best, bo = c, ov
                if best and bo >= 1:
                    rematch = best["no"]
                    address = best["address"]
            if not d:
                missing.append(num)
            if d and norm(venue) != norm(d["name"]):
                mismatches.append({"no": num, "rik": venue, "doc": d["name"],
                                   "address_used": address, "rematch_doc_no": rematch})
            used_addr[num] = address
            out.append({"municipality": muni, "no": num, "name": venue, "address": address})

        report[muni] = {"rik": len(used_addr), "doc": len(doc),
                        "missing": missing, "mismatches": mismatches}

    out.sort(key=lambda x: (ORDER.index(x["municipality"]), x["no"]))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"total stations: {len(out)}")
    for muni in ORDER:
        rep = report[muni]
        print(f"\n[{muni}] RIK 2023={rep['rik']}  2022 doc rows={rep['doc']}")
        print(f"  numbers missing from doc: {rep['missing']}")
        print(f"  name mismatches vs decision doc: {len(rep['mismatches'])}")
        for m in rep["mismatches"]:
            extra = f" -> addr from doc no {m['rematch_doc_no']}" if m["rematch_doc_no"] else " (kept same-no address)"
            print(f"    {m['no']:>3} RIK={m['rik'][:40]:<40} DOC={m['doc'][:40]:<40}{extra}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
