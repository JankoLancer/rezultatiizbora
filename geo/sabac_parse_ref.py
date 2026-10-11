#!/usr/bin/env python3
"""Parse the Šabac 2022-referendum polling-stations .doc (wvText output) and build
the RIK 2023 locations file.

The wvText output terminates each table cell with the BEL char \x07.  After the
table header every polling station is four consecutive cells:
    no | venue name | address | area
so a row is located by its digit-only "no" cell.

The 22.12.2021 "izmena i dopuna" decision (sabac_izmena.doc) amends two stations:
    no 44: name  ОСНОВНА ШКОЛА - СТАРА ЗГРАДА -> ОСНОВНА ШКОЛА - НОВА ЗГРАДА
    no 64: name  ДОМ КУЛТУРЕ -> ОСНОВНА ШКОЛА "ЈЕВРЕМ ОБРЕНОВИЋ - ИЗДВОЈЕНО ОДЕЉЕЊЕ МИШАР"
           addr  МИШАР -> МИШАР, Карађорђева улица б.б.
These are applied explicitly below.

Produces:
  geo/sabac_ref_rows.json           -> [{no,name,address,area}]
  geo/sabac_stations_locations.json -> [{municipality,no,name,address}] (RIK 2023 target)
  geo/sabac_align_report.txt        -> alignment notes vs RIK 2023 manifest
"""
import csv, json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
REF_TXT = os.path.join(BASE, "sabac_ref.txt")
MANIFEST = os.path.join(PROJ, "rik_2023_sabac", "manifest.csv")
REF_OUT = os.path.join(BASE, "sabac_ref_rows.json")
LOC_OUT = os.path.join(BASE, "sabac_stations_locations.json")
REPORT = os.path.join(BASE, "sabac_align_report.txt")

MUNI = "Град Шабац"

# Amendments from the 22.12.2021 izmena i dopuna decision.
AMENDMENTS = {
    44: {"name": "ОСНОВНА ШКОЛА - НОВА ЗГРАДА", "address": "СЛЕПЧЕВИЋ"},
    64: {"name": 'ОСНОВНА ШКОЛА "ЈЕВРЕМ ОБРЕНОВИЋ- ИЗДВОЈЕНО ОДЕЉЕЊЕ МИШАР"',
         "address": "МИШАР, Карађорђева улица  б.б."},
}


def norm(s):
    s = s.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_ref(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = raw.replace("\r", "\n").split("\x07")
    rows = []
    for i, c in enumerate(cells):
        if not re.fullmatch(r"\d+", c.strip()):
            continue
        no = int(c.strip())
        name = norm(cells[i + 1]) if i + 1 < len(cells) else ""
        address = norm(cells[i + 2]) if i + 2 < len(cells) else ""
        area = norm(cells[i + 3]) if i + 3 < len(cells) else ""
        rows.append({"no": no, "name": name, "address": address, "area": area})
    return rows


ref = parse_ref(REF_TXT)
ref.sort(key=lambda r: r["no"])

# Apply the amendment.
for r in ref:
    amd = AMENDMENTS.get(r["no"])
    if amd:
        r["name"] = amd["name"]
        r["address"] = amd["address"]

missing = [n for n in range(1, len(ref) + 1) if n not in {r["no"] for r in ref}]
assert len(ref) == 100 and not missing, f"expected 100 ref rows 1..100, got {len(ref)}, missing {missing}"
json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"parsed ref rows: {len(ref)} -> {REF_OUT}")
for r in ref[:3] + ref[-3:]:
    print(f"  {r['no']:>3} {r['name'][:48]:<48} | {r['address'][:40]}")

# ---- RIK 2023 target -------------------------------------------------------
riK = []
with open(MANIFEST, encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        sn = row["station_name"]
        m = re.match(r"\s*(\d+)\s*-\s*(.*)$", sn)
        no = int(m.group(1)) if m else None
        venue = (m.group(2) if m else sn).strip()
        riK.append({"station_id": row["station_id"], "no": no, "name": venue})
riK.sort(key=lambda r: (r["no"] or 0))
print(f"RIK stations: {len(riK)}")


def norm_name(s):
    s = s.upper().replace("“", '"').replace("”", '"').replace("„", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


from collections import defaultdict
by_name = defaultdict(list)
for r in ref:
    by_name[norm_name(r["name"])].append(r)

# Detect whether the 2023 numbering is shifted with respect to the 2022 ref by
# scoring exact venue-name agreement at each candidate offset.
ref_by_number = {r["no"]: r for r in ref}
rik_by_number = {s["no"]: s["name"] for s in riK}
offsets = range(-3, 4)
scores = {d: sum(1 for no, ven in rik_by_number.items()
                 if no + d in ref_by_number and norm_name(ref_by_number[no + d]["name"]) == norm_name(ven))
          for d in offsets}
best_offset = max(scores, key=scores.get)
report = [f"offset scores (rik no - ref no): {dict(sorted(scores.items()))}",
          f"best offset: {best_offset} (no numbering shift)" if best_offset == 0
          else f"best offset: {best_offset}"]

locations = []
n_by_no = n_by_name = n_fallback = 0
for s in riK:
    no, venue = s["no"], s["name"]
    match = None
    how = None
    if best_offset == 0:
        match = ref_by_number.get(no)
        how = "number"
    if match is None:
        # real shift (or missing position): rematch by exact unique venue name
        if norm_name(venue) in by_name and len(by_name[norm_name(venue)]) == 1:
            match = by_name[norm_name(venue)][0]
            how = "venue-name"
        elif no in ref_by_number:
            match = ref_by_number[no]
            how = "number(flag)"
    if match is None:
        report.append(f"MISS no={no} venue={venue!r}: no matching reference venue")
        n_fallback += 1
        how = "number(flag)"
    if how == "number":
        n_by_no += 1
        if match and norm_name(match["name"]) != norm_name(venue):
            report.append(f"RENAMED no={no}: ref {match['name']!r} -> rik {venue!r} "
                          f"(address inherited: {match['address']!r})")
    elif how == "venue-name":
        n_by_name += 1
        report.append(f"REMATCH no={no} venue={venue!r} -> ref#{match['no']} {match['name']!r}")
    locations.append({"municipality": MUNI, "no": no,
                      "name": venue, "address": match["address"] if match else None})

assert len(locations) == 100
json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(f"RIK stations: {len(riK)}; ref rows: {len(ref)}\n")
    fh.write(f"matched by number: {n_by_no}; by venue-name: {n_by_name}; flagged: {n_fallback}\n")
    fh.write("amendments applied:\n")
    for no, amd in sorted(AMENDMENTS.items()):
        fh.write(f"  no {no}: {amd['name']!r} | {amd['address']!r}\n")
    fh.write("number mismatches / notes:\n")
    for line in report:
        fh.write("  " + line + "\n")

print(f"locations: {len(locations)}; by-number {n_by_no}; by-name {n_by_name}; flagged {n_fallback}")
print(f"report -> {REPORT}")
