#!/usr/bin/env python3
"""Parse the Leskovac 2022 referendum polling-station decision(s) and build the
2023 locations file.

Sources (wvText output, each table cell terminated by BEL \\x07):
  geo/leskovac_ref.txt     -> 195 stations, row layout: empty | no | name | address | area
  geo/leskovac_izmena.txt  -> amendment: renames one station (overrides ref row 186)

Alignment: RIK 2023 (194 stations) is the target. The 2022 decision lists 195
stations; station #126 (ОСНОВНА ШКОЛА, Бабичко 2) was dropped, so RIK numbers
>= 126 are shifted by +1 relative to the 2022 document. This is pinned by the
exact venue-name anchors (RIK130 == ref131, RIK132 == ref133, ... RIK194 == ref195,
all delta +1) and by the fact that RIK126 and RIK127 are both "ОШ Бора Станковић"
(a school in Богојевце), so they must map to the two Богојевце rows (ref127/ref128),
not to ref126 (Бабичко). RIK numbers <= 125 map 1:1 (anchors RIK116 == ref116,
RIK125 == ref125).

Produces:
  geo/leskovac_ref_rows.json           -> [{municipality,no,name,address,area}]
  geo/leskovac_stations_locations.json -> [{municipality,no,name,address}] (RIK 2023 target)
  geo/leskovac_align_report.txt        -> alignment notes vs RIK 2023 manifest
"""
import csv, json, os, re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
REF_TXT = os.path.join(BASE, "leskovac_ref.txt")
IZM_TXT = os.path.join(BASE, "leskovac_izmena.txt")
MANIFEST = os.path.join(PROJ, "rik_2023_leskovac", "manifest.csv")
REF_OUT = os.path.join(BASE, "leskovac_ref_rows.json")
LOC_OUT = os.path.join(BASE, "leskovac_stations_locations.json")
REPORT = os.path.join(BASE, "leskovac_align_report.txt")

MUNI = "Град Лесковац"
SHIFT_START = 126   # RIK no >= 126 -> ref#(no+1); ref#126 is the dropped station


def norm(s):
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_cells(path):
    raw = open(path, encoding="utf-8", errors="replace").read().replace("\r", "\n")
    return raw.split("\x07")


def parse_stations(cells):
    """Row layout: empty | no | name | address | area (no is a digit-only cell)."""
    rows = []
    for i, c in enumerate(cells):
        if not re.fullmatch(r"\d+", c.strip()):
            continue
        no = int(c.strip())
        name = norm(cells[i + 1]) if i + 1 < len(cells) else ""
        address = norm(cells[i + 2]) if i + 2 < len(cells) else ""
        area = norm(cells[i + 3]) if i + 3 < len(cells) else ""
        if not name or not address:
            continue
        address = re.sub(r"\s*,\s*", ", ", address)
        address = re.sub(r"\s+", " ", address).strip(" ,")
        rows.append({"municipality": MUNI, "no": no, "name": name,
                     "address": address, "area": area})
    return rows


ref = parse_stations(parse_cells(REF_TXT))
ref.sort(key=lambda r: r["no"])
assert len(ref) == 195, f"expected 195 ref rows, got {len(ref)}"
assert [r["no"] for r in ref] == list(range(1, 196)), "ref numbering not contiguous"

# ---- apply 2022 amendment (izmena) ----------------------------------------
izmena = parse_stations(parse_cells(IZM_TXT))
print(f"izmena rows: {len(izmena)}")
for z in izmena:
    print(f"  izmena no={z['no']} {z['name'][:50]!r} | {z['address'][:40]!r}")
    old = ref[z["no"] - 1]
    if norm(old["name"]) != z["name"]:
        print(f"    ref#{z['no']} name {old['name']!r} -> {z['name']!r}")
    old.update({k: z[k] for k in ("name", "address", "area")})

json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"parsed ref rows: {len(ref)} -> {REF_OUT}")

# ---- RIK 2023 target -------------------------------------------------------
with open(MANIFEST, encoding="utf-8-sig") as fh:
    man_rows = list(csv.DictReader(fh))
rik = []
for row in man_rows:
    sn = row["station_name"]
    m = re.match(r"\s*(\d+)\s*-\s*(.*)$", sn)
    no = int(m.group(1)) if m else None
    venue = (m.group(2) if m else sn).strip()
    rik.append({"station_id": row["station_id"], "no": no, "name": venue})
rik.sort(key=lambda r: (r["no"] or 0))
print(f"RIK stations: {len(rik)}")


def norm_name(s):
    s = s.upper().replace("“", '"').replace("”", '"').replace("„", '"')
    s = s.replace("’", "'").replace("‘", "'").replace("`", "'")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    s = re.sub(r"\bОСНОВНА\s+ШКОЛА\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


by_name = defaultdict(list)
for r in ref:
    by_name[norm_name(r["name"])].append(r)


def map_ref(no):
    """2022 ref row for a RIK 2023 station number (see module docstring)."""
    if no is None:
        return None
    rno = no + 1 if no >= SHIFT_START else no
    return ref[rno - 1] if 1 <= rno <= len(ref) else None


# sanity: every exact venue-name anchor must agree with the shift model
anchors_ok, anchors_bad = 0, []
for s in rik:
    hits = by_name.get(norm_name(s["name"]), [])
    if len(hits) == 1:
        if hits[0]["no"] == map_ref(s["no"])["no"]:
            anchors_ok += 1
        else:
            anchors_bad.append((s["no"], s["name"], hits[0]["no"], map_ref(s["no"])["no"]))
assert not anchors_bad, f"shift model contradicts exact anchors: {anchors_bad}"

locations, report = [], []
used_ref, n_name_match, n_name_diff, n_flag = set(), 0, 0, 0
for s in rik:
    no, venue = s["no"], s["name"]
    match = map_ref(no)
    if match is None:
        report.append(f"MISS no={no} venue={venue!r}: no reference row")
        n_flag += 1
        locations.append({"municipality": MUNI, "no": no, "name": venue, "address": None})
        continue
    used_ref.add(match["no"])
    if norm_name(match["name"]) == norm_name(venue):
        n_name_match += 1
    else:
        n_name_diff += 1
        report.append(f"NAME-DIFF no={no} rik={venue!r} <- ref#{match['no']} {match['name']!r}")
    locations.append({"municipality": MUNI, "no": no, "name": venue,
                      "address": match["address"]})

unused = [r["no"] for r in ref if r["no"] not in used_ref]
json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(f"RIK stations: {len(rik)}; ref rows: {len(ref)}\n")
    fh.write(f"shift: RIK no >= {SHIFT_START} -> ref#(no+1); dropped ref#126 "
             f"({ref[125]['name']!r}, {ref[125]['address']!r})\n")
    fh.write(f"exact venue-name anchors consistent with shift: {anchors_ok}; "
             f"contradictions: {anchors_bad}\n")
    fh.write(f"exact name matches: {n_name_match}; name diffs (2023 uses specific school "
             f"names): {n_name_diff}; flagged: {n_flag}\n")
    fh.write(f"ref rows unused (absent from RIK 2023): {unused}\n")
    fh.write("notes:\n")
    for line in report:
        fh.write("  " + line + "\n")

print(f"locations: {len(locations)}; exact-name matches {n_name_match}; "
      f"name-diffs {n_name_diff}; flagged {n_flag}")
print(f"shift anchors consistent: {anchors_ok}; unused ref rows: {unused}")
print(f"report -> {REPORT}")
