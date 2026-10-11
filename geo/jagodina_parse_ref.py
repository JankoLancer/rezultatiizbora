#!/usr/bin/env python3
"""Parse Jagodina 2022 referendum polling-stations .docx and build the 2023 locations file.

The number column is a Word auto-numbered list (numId=5), so numbers are assigned
sequentially in document order. Produces:
  geo/jagodina_ref_rows.json          -> [{no,name,address,area}]
  geo/jagodina_stations_locations.json -> [{municipality,no,name,address}] (RIK 2023 target)
  geo/jagodina_align_report.txt        -> alignment notes vs RIK 2023 manifest
"""
import csv, json, os, re, zipfile
from html import unescape

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
DOCX = os.path.join(BASE, "jagodina_ref.docx")
MANIFEST = os.path.join(PROJ, "rik_2023_jagodina", "manifest.csv")
REF_OUT = os.path.join(BASE, "jagodina_ref_rows.json")
LOC_OUT = os.path.join(BASE, "jagodina_stations_locations.json")
REPORT = os.path.join(BASE, "jagodina_align_report.txt")

xml = zipfile.ZipFile(DOCX).read("word/document.xml").decode("utf-8")

# Match only real text runs <w:t ...>...</w:t>, never <w:tabs>/<w:tc>/etc.
TXT = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)


def clean(s):
    s = unescape(s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def cell_text(tc):
    parts = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", tc, re.S):
        txt = clean("".join(TXT.findall(p)))
        if txt:
            parts.append(txt)
    return " ".join(parts).strip()


tbl = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S)[0]
trs = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S)

ref = []
for tr in trs:
    cells = re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)
    if not cells:
        continue
    if "<w:numPr>" not in cells[0]:
        continue  # skip title / header rows
    vals = [cell_text(c) for c in cells]
    if len(vals) < 4:
        continue
    name = vals[1]
    address = vals[2]
    area = vals[3]
    # Normalise Cyrillic dashes and stray punctuation in address
    address = address.replace("–", "-").replace("—", "-")
    address = re.sub(r"\s*,\s*", ", ", address)
    address = re.sub(r"\s+", " ", address).strip(" ,")
    ref.append({"no": len(ref) + 1, "name": name, "address": address, "area": area})

assert len(ref) == 91, f"expected 91 ref rows, got {len(ref)}"
json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"parsed ref rows: {len(ref)}")
print("first rows:")
for r in ref[:3]:
    print("  ", r["no"], r["name"], "|", r["address"][:60])

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


# name->address index (only unambiguous names are useful)
from collections import defaultdict
by_name = defaultdict(list)
for r in ref:
    by_name[norm_name(r["name"])].append(r)

locations = []
report = []
n_by_no = n_by_name = n_fallback = 0
for s in riK:
    no, venue = s["no"], s["name"]
    ref_by_no = ref[no - 1] if no and 1 <= no <= len(ref) else None
    match = None
    how = None
    if ref_by_no:
        match = ref_by_no
        how = "number"
        if norm_name(ref_by_no["name"]) != norm_name(venue) and norm_name(venue) in by_name \
                and len(by_name[norm_name(venue)]) == 1:
            cand = by_name[norm_name(venue)][0]
            if cand["no"] != no:
                match = cand
                how = "venue-name"
    if match is None and norm_name(venue) in by_name and len(by_name[norm_name(venue)]) == 1:
        match = by_name[norm_name(venue)][0]
        how = "venue-name"
    if match is None:
        report.append(f"MISS no={no} venue={venue!r}: no matching reference venue")
        n_fallback += 1
        match = ref_by_no
        how = "number(flag)"
    if how == "number":
        n_by_no += 1
    elif how == "venue-name":
        n_by_name += 1
        report.append(f"REMATCH no={no} venue={venue!r} -> ref#{match['no']} {match['name']!r}")
    locations.append({"municipality": "Град Јагодина", "no": no,
                      "name": venue, "address": match["address"] if match else None})

assert len(locations) == 91
json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(f"RIK stations: {len(riK)}; ref rows: {len(ref)}\n")
    fh.write(f"matched by number: {n_by_no}; by venue-name: {n_by_name}; flagged: {n_fallback}\n")
    fh.write("number mismatches / notes:\n")
    for line in report:
        fh.write("  " + line + "\n")

print(f"locations: {len(locations)}; by-number {n_by_no}; by-name {n_by_name}; flagged {n_fallback}")
print(f"report -> {REPORT}")
