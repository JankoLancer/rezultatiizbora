#!/usr/bin/env python3
"""Align RIK 2023 Novi Sad stations with the 2022 referendum address list.

Reads  rik_2023_novisad/manifest.csv  (station_name like "N - VENUE")
and    geo/novisad_ref_rows.json      (parsed 2022 decision + izmena overrides).
Writes geo/novisad_stations_locations.json with {municipality, no, name, address}.

The 2023 RIK venue names are the target names.  Addresses come from the 2022
decision row with the same number.  Because the 2023 ballot added polling
stations, some numbers shifted: when the RIK 2023 venue name exactly matches a
different decision row (quotes/spacing ignored), that row's address is used.
Mismatches are printed; the 5 stations absent from the 2022 decision (208-212)
inherit the address of the identical venue already present in the decision.
"""
import csv, json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_novisad", "manifest.csv")
DOC = os.path.join(BASE, "novisad_ref_rows.json")
OUT = os.path.join(BASE, "novisad_stations_locations.json")
MUNI = "Град Нови Сад"

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
    doc = json.load(open(DOC, encoding="utf-8"))
    doc_by_no = {d["no"]: d for d in doc}
    by_norm = {}
    for d in doc:
        by_norm.setdefault(norm(d["name"]), []).append(d)

    out, mismatches, missing = [], [], []
    for r in rows:
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
            # station absent from the 2022 decision: best token-overlap row
            v = toks(venue)
            best, bo = None, 0
            for c in doc:
                ov = len(v & toks(c["name"]))
                if ov > bo:
                    best, bo = c, ov
            if best:
                rematch = best["no"]
                address = best["address"]
        if not d:
            missing.append(num)
        if d and norm(venue) != norm(d["name"]):
            mismatches.append({"no": num, "rik": venue, "doc": d["name"],
                               "address_used": address, "rematch_doc_no": rematch})
        out.append({"municipality": MUNI, "no": num, "name": venue, "address": address})

    out.sort(key=lambda x: x["no"])
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"stations: {len(out)}; doc rows: {len(doc)}")
    print(f"numbers missing from doc (address inherited from same venue): {missing}")
    print(f"name mismatches vs decision doc: {len(mismatches)}")
    for m in mismatches:
        extra = f" -> address from doc no {m['rematch_doc_no']}" if m["rematch_doc_no"] else " (kept doc no address)"
        print(f"  {m['no']:>3} RIK={m['rik'][:42]:<42} DOC={m['doc'][:42]:<42}{extra}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
