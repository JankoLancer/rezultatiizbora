#!/usr/bin/env python3
"""Build geo/cacak_stations_locations.json by aligning the RIK 2023 station
manifest (target) with the 2022 referendum decision rows (address source).

RIK 2023 is authoritative for station number and venue name.  Addresses are
taken from the 2022 decision, matched first by station number, then by exact
venue name when a shift is detected.  Genuine venue mismatches are reported to
geo/cacak_align_report.txt (abbreviation-only differences such as
"ОШ" == "ОСНОВНА ШКОЛА" are not treated as mismatches).
"""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_cacak", "manifest.csv")
REF = os.path.join(BASE, "cacak_ref_rows.json")
OUT = os.path.join(BASE, "cacak_stations_locations.json")
REPORT = os.path.join(BASE, "cacak_align_report.txt")

MUNI = "Град Чачак"


def norm_name(s):
    """Canonical comparison key: fold the school abbreviations used differently
    by the RIK site and the 2022 decision."""
    s = s.upper()
    for q in '„“”"':
        s = s.replace(q, " ")
    s = re.sub(r"\bОСНОВНЕ\s+ШКОЛЕ\b", " ОСНОВНАШКОЛА ", s)
    s = re.sub(r"\bОСНОВНА\s+ШКОЛА\b", " ОСНОВНАШКОЛА ", s)
    s = re.sub(r"\bОШ\b", " ОСНОВНАШКОЛА ", s)
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = json.load(open(REF, encoding="utf-8"))
    ref_by_no = {r["no"]: r for r in ref}
    ref_by_name = {}
    for r in ref:
        ref_by_name.setdefault(norm_name(r["name"]), []).append(r)

    manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    locations, mismatches, rematches, rows_report = [], [], [], []
    for m in manifest:
        sid = m["station_id"]
        sn = m["station_name"].strip()
        mm = re.match(r"(\d+)\s*-\s*(.*)", sn)
        if not mm:
            mismatches.append((sid, sn, "no number prefix"))
            continue
        no, venue = int(mm.group(1)), mm.group(2).strip()
        r = ref_by_no.get(no)
        address = r["address"] if r else ""
        status = "number-match"
        if r and norm_name(r["name"]) != norm_name(venue):
            cands = ref_by_name.get(norm_name(venue), [])
            if len(cands) == 1 and cands[0]["no"] != no:
                address = cands[0]["address"]
                status = f"name-rematch<-{cands[0]['no']}"
                rematches.append((no, venue, cands[0]["no"]))
            else:
                status = "MISMATCH"
                mismatches.append((sid, f"{no} - {venue}", f"ref#{no}={r['name']}"))
        elif not r:
            status = "NO-REF-ROW"
            mismatches.append((sid, f"{no} - {venue}", "no 2022 row for number"))
        locations.append({"municipality": MUNI, "no": no, "name": venue, "address": address})
        rows_report.append((no, status, venue, address))

    locations.sort(key=lambda x: x["no"])
    json.dump(locations, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"manifest rows: {len(manifest)}; ref rows: {len(ref)}; "
                 f"locations: {len(locations)}\n")
        fh.write(f"name-rematches: {len(rematches)}\n")
        for no, venue, rno in rematches:
            fh.write(f"  rematch {no} '{venue}' <- ref#{rno}\n")
        fh.write(f"genuine mismatches: {len(mismatches)}\n")
        for sid, sn, note in mismatches:
            fh.write(f"  MISMATCH sid={sid} '{sn}' ({note})\n")
        fh.write("\nall rows:\n")
        for no, status, venue, address in rows_report:
            fh.write(f"  {no:>3} [{status:>16}] {venue[:46]:<46} {address}\n")

    print(f"manifest {len(manifest)}; ref {len(ref)}; locations {len(locations)}")
    print(f"name-rematches {len(rematches)}; genuine mismatches {len(mismatches)}")
    for sid, sn, note in mismatches:
        print(f"  MISMATCH {sn} ({note})")
    for no, venue, rno in rematches:
        print(f"  rematch {no} '{venue}' <- ref#{rno}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
