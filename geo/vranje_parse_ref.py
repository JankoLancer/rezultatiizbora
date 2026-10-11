#!/usr/bin/env python3
"""Parse the Врање 2022 referendum polling-stations .doc and build the 2023 locations file.

Source is the wvText dump (geo/vranje_ref.txt); each table cell ends with BEL \\x07.
Layout after the header is: empty | no | name | address | area | empty | no | ...
so rows are located by their digit-only "no" cell. The document numbers the whole
city continuously 1..106: rows 1..85 are "Град Врање", rows 86..106 are
"Градска општина Врањска Бања" whose RIK 2023 numbering restarts at 1.

Produces:
  geo/vranje_ref_rows.json           -> [{no,name,address,area}]
  geo/vranje_stations_locations.json -> [{municipality,no,name,address}] (RIK 2023 target)
  geo/vranje_align_report.txt        -> alignment notes vs RIK 2023 manifest
"""
import csv, json, os, re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
REF_TXT = os.path.join(BASE, "vranje_ref.txt")
MANIFEST = os.path.join(PROJ, "rik_2023_vranje", "manifest.csv")
REF_OUT = os.path.join(BASE, "vranje_ref_rows.json")
LOC_OUT = os.path.join(BASE, "vranje_stations_locations.json")
REPORT = os.path.join(BASE, "vranje_align_report.txt")

MUNI_GRAD = "Град Врање"
MUNI_BANJA = "Градска општина Врањска Бања"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def clean_addr(a):
    a = a.replace("–", "-").replace("—", "-")
    a = re.sub(r"\s*,\s*", ", ", a)
    a = re.sub(r"\s+", " ", a)
    return a.strip(" ,")


def parse_ref(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = raw.replace("\r", "\n").split("\x07")
    rows = []
    for i, c in enumerate(cells):
        if not re.fullmatch(r"\d+", c.strip()):
            continue
        no = int(c.strip())
        name = norm(cells[i + 1]) if i + 1 < len(cells) else ""
        address = clean_addr(norm(cells[i + 2])) if i + 2 < len(cells) else ""
        area = norm(cells[i + 3]) if i + 3 < len(cells) else ""
        rows.append({"no": no, "name": name, "address": address, "area": area})
    return rows


def norm_name(s):
    s = s.upper().replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = parse_ref(REF_TXT)
    ref.sort(key=lambda r: r["no"])
    missing = [n for n in range(1, len(ref) + 1) if n not in {r["no"] for r in ref}]
    json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed ref rows: {len(ref)}; missing numbers: {missing}")
    for r in ref[:3] + ref[-3:]:
        print(f"  {r['no']:>3} {r['name'][:40]:<40} @ {r['address'][:44]}")

    # ---- RIK 2023 target ---------------------------------------------------
    rik = []
    with open(MANIFEST, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            sn = row["station_name"]
            m = re.match(r"\s*(\d+)\s*-\s*(.*)$", sn)
            no = int(m.group(1)) if m else None
            venue = norm(m.group(2) if m else sn)
            rik.append({"station_id": row["station_id"], "municipality": row["municipality"],
                        "no": no, "name": venue})
    grad_count = sum(1 for r in rik if r["municipality"] == MUNI_GRAD)
    print(f"RIK stations: {len(rik)} (Град Врање {grad_count}, "
          f"Врањска Бања {len(rik) - grad_count})")

    # name -> ref rows index (only unambiguous names are useful)
    by_name = defaultdict(list)
    for r in ref:
        by_name[norm_name(r["name"])].append(r)

    locations, report = [], []
    n_by_no = n_by_name = n_fallback = 0
    for s in rik:
        no, venue = s["no"], s["name"]
        # doc numbers continuously: Град Врање keeps its number, Врањска Бања is
        # shifted by the number of Град Врање stations.
        doc_no = no if s["municipality"] == MUNI_GRAD else grad_count + no
        ref_by_no = ref[doc_no - 1] if doc_no and 1 <= doc_no <= len(ref) else None
        match, how = None, None
        if ref_by_no:
            match, how = ref_by_no, "number"
            if norm_name(ref_by_no["name"]) != norm_name(venue) \
                    and norm_name(venue) in by_name \
                    and len(by_name[norm_name(venue)]) == 1:
                cand = by_name[norm_name(venue)][0]
                if cand["no"] != doc_no:
                    match, how = cand, "venue-name"
        if match is None and norm_name(venue) in by_name and len(by_name[norm_name(venue)]) == 1:
            match, how = by_name[norm_name(venue)][0], "venue-name"
        if match is None:
            report.append(f"MISS muni={s['municipality']} no={no} venue={venue!r}: "
                          f"no matching reference venue")
            n_fallback += 1
        if how == "number":
            n_by_no += 1
        elif how == "venue-name":
            n_by_name += 1
            report.append(f"REMATCH muni={s['municipality']} no={no} venue={venue!r} "
                          f"-> ref#{match['no']} {match['name']!r}")
        elif how is None:
            report.append(f"FLAG muni={s['municipality']} no={no} venue={venue!r}: "
                          f"address inherited from ref row {doc_no}")
        if match is not None and how == "number" \
                and norm_name(match["name"]) != norm_name(venue):
            report.append(f"VENUE-RENAME no={no} muni={s['municipality']}: RIK={venue!r} "
                          f"-> ref#{match['no']} {match['name']!r} @ {match['address']}")
        locations.append({"municipality": s["municipality"], "no": no,
                          "name": venue, "address": match["address"] if match else None})

    assert len(locations) == 106, f"expected 106 locations, got {len(locations)}"
    json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"RIK stations: {len(rik)}; ref rows: {len(ref)}\n")
        fh.write(f"matched by number: {n_by_no}; by venue-name: {n_by_name}; flagged: {n_fallback}\n")
        fh.write("number mismatches / notes:\n")
        for line in report:
            fh.write("  " + line + "\n")

    print(f"locations: {len(locations)}; by-number {n_by_no}; by-name {n_by_name}; "
          f"flagged {n_fallback}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
