#!/usr/bin/env python3
"""Build the RIK 2023 polling-station locations for ГРАД СМЕДЕРЕВО.

Inputs (generic tooling where possible):
  geo/smederevo_ref.doc      -- 2022 referendum "glasacka mesta" (base, 78 rows)
  geo/smederevo_izmena1.docx -- 22.12.2021 izmena resenja (renames + addresses)
  geo/smederevo_izmena2.docx -- 30.12.2021 izmena i dopuna (areas only)
  rik_2023_smederevo/manifest.csv -- RIK 2023 authoritative station list

The generic opstina_docs parser returns 100 rows for the base doc because many
venue names wrap onto a continuation table line; the numbered-row ratio (78/231)
falls below its 0.40 threshold so it runs in sequential mode.  We therefore
group the raw antiword table lines by the address column: every real polling
station has a non-empty address, while continuation fragments (e.g.
"-учионица бр. 7") do not.  That reconstructs the 78 stations stated in the doc.

The amendment decisions are paragraph text (no tables), so opstina_docs returns
0 rows for them.  We parse the docx paragraph text for
"<назив|адреса> гласачког места ... уместо: «OLD» треба да стоји: «NEW»"
clauses and override by polling-station number (numbering matches the base doc).

Output rows are aligned to the RIK 2023 manifest by station number and written
as geo/smederevo_stations_locations.json -> [{municipality,no,name,address}].

Also writes geo/smederevo_ref_rows.json and geo/smederevo_align_report.txt.
"""
import csv
import html
import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import opstina_docs  # noqa: E402

REF = os.path.join(HERE, "smederevo_ref.doc")
IZ1 = os.path.join(HERE, "smederevo_izmena1.docx")
IZ2 = os.path.join(HERE, "smederevo_izmena2.docx")
MANIFEST = os.path.join(ROOT, "rik_2023_smederevo", "manifest.csv")
LOC_OUT = os.path.join(HERE, "smederevo_stations_locations.json")
REF_OUT = os.path.join(HERE, "smederevo_ref_rows.json")
REPORT = os.path.join(HERE, "smederevo_align_report.txt")

MUNI = "Град Смедерево"
EXPECTED = 78


# ------------------------------------------------------------------ ref doc
def parse_ref(path):
    """Group raw antiword table lines into logical stations (by address)."""
    txt = subprocess.run(["antiword", "-w", "0", path],
                         capture_output=True).stdout.decode("utf-8", "replace")
    raw = []
    for line in txt.splitlines():
        if "|" not in line:
            continue
        raw.append([opstina_docs._clean(c) for c in line.strip().strip("|").split("|")])
    raw = [r for r in raw if any(r)]

    out, cur = [], None
    for r in raw:
        c0 = r[0] if len(r) > 0 else ""
        name = r[1] if len(r) > 1 else ""
        addr = r[2] if len(r) > 2 else ""
        area = " ".join(x for x in r[3:] if x)
        up = (name or "").upper()
        if "НАЗИВ" in up or (c0 or "").upper().rstrip(".") in ("РЕД", "БР", "БРОЈ", "БРОЈ ГМ"):
            continue
        if addr:
            # every real polling station has an address; continuation fragments don't
            cur = {"no": len(out) + 1, "name": name, "address": addr, "area": area}
            out.append(cur)
        elif cur is not None:
            if name:
                cur["name"] = (cur["name"] + " " + name).strip()
            if area:
                cur["area"] = (cur["area"] + " " + area).strip()
    return out


# --------------------------------------------------------------- amendments
def docx_paragraphs(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "replace")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        txt = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, re.S))
        txt = html.unescape(txt).strip()
        if txt:
            paras.append(txt)
    return " ".join(paras)


PAIR_RE = re.compile(
    r"(назив|адреса)\s+гласачког места[^«]*?"
    r"уместо[^«]*?«(.*?)»\s*треба да стоји[^«]*?«(.*?)»", re.S)


def parse_amendment(path, label):
    """Return {no: {"name":.., "address":..}} overrides for one amendment doc."""
    text = docx_paragraphs(path)
    overrides, notes = {}, []
    # split into clauses keyed by "на гласачком месту број N"
    parts = re.split(r"на гласачком месту број\s*", text)
    for part in parts[1:]:
        m = re.match(r"\s*(\d+)", part)
        if not m:
            continue
        no = int(m.group(1))
        # only look at this clause, up to the next "на гласачком месту" (already split)
        for field, old, new in PAIR_RE.findall(part):
            patch = overrides.setdefault(no, {})
            key = "name" if field == "назив" else "address"
            patch[key] = new.strip()
            notes.append((label, no, key, old.strip(), new.strip()))
    return overrides, notes


# ----------------------------------------------------------------- manifest
def load_manifest():
    out = []
    with open(MANIFEST, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            sn = row["station_name"].strip()
            m = re.match(r"^\s*(\d+)\s*-\s*(.*)$", sn)
            no = int(m.group(1)) if m else 0
            venue = (m.group(2) if m else sn).strip()
            out.append({"station_id": row["station_id"], "no": no, "venue": venue,
                        "muni": row.get("municipality") or MUNI})
    out.sort(key=lambda r: r["no"])
    return out


def norm_name(s):
    s = (s or "").upper().replace("“", '"').replace("”", '"').replace("„", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = parse_ref(REF)
    print(f"ref rows (grouped): {len(ref)}")
    assert len(ref) == EXPECTED, f"ref rows {len(ref)} != {EXPECTED}"
    nums = [r["no"] for r in ref]
    assert nums == list(range(1, EXPECTED + 1)), "non-contiguous doc numbering"

    amd, amd_notes = {}, []
    for path, label in ((IZ1, "izmena1"), (IZ2, "izmena2")):
        ov, nt = parse_amendment(path, label)
        amd_notes += nt
        for no, patch in ov.items():
            amd.setdefault(no, {}).update(patch)  # izmena2 applied last
    print(f"amendment overrides: {len(amd)} stations ({len(amd_notes)} field changes)")

    for no, patch in amd.items():
        for r in ref:
            if r["no"] == no:
                r.update(patch)
    json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ref rows (after amendments): {len(ref)} -> {REF_OUT}")

    man = load_manifest()
    print(f"manifest stations: {len(man)}")
    assert len(man) == EXPECTED, f"manifest {len(man)} != {EXPECTED}"

    ref_by_no = {r["no"]: r for r in ref}
    locations, report = [], []
    n_by_no = n_struct = n_flag = 0
    for m in man:
        no, venue = m["no"], m["venue"]
        match, how = None, None
        d = ref_by_no.get(no)
        if d is not None and norm_name(d["name"]) == norm_name(venue):
            match, how = d, "number"
        else:
            cand = [r for r in ref if norm_name(r["name"]) == norm_name(venue)]
            if len(cand) == 1:
                match, how = cand[0], "venue-name"
            elif d is not None:
                match, how = d, "number(structural)"
                n_struct += 1
                report.append(f"STRUCT no={no}: doc {d['name']!r} vs rik {venue!r} "
                              f"(address inherited: {d['address']!r})")
        if match is None:
            n_flag += 1
            addr = ""
            report.append(f"MISS no={no} venue={venue!r}: no matching ref venue")
        else:
            addr = (match.get("address") or "").strip()
            if how == "venue-name":
                report.append(f"REMATCH no={no} venue={venue!r} -> ref#{match['no']} "
                              f"{match['name']!r} ({addr!r})")
                n_by_no += 1
            elif how == "number":
                n_by_no += 1
                if norm_name(match["name"]) != norm_name(venue):
                    report.append(f"RENAMED no={no}: doc {match['name']!r} -> rik {venue!r}")
        locations.append({"municipality": m["muni"], "no": no, "name": venue, "address": addr})

    assert len(locations) == EXPECTED, f"locations {len(locations)} != {EXPECTED}"
    json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    empty = [l for l in locations if not l["address"]]
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"manifest stations: {len(man)}; ref rows: {len(ref)}\n")
        fh.write(f"matched by number: {n_by_no} (structural {n_struct}); "
                 f"unmatched: {n_flag}; empty addresses: {len(empty)}\n")
        fh.write("amendments applied (in order):\n")
        for label, no, key, old, new in amd_notes:
            fh.write(f"  {label} no {no} {key}: {old!r} -> {new!r}\n")
        fh.write("number mismatches / notes:\n")
        fh.write("".join("  " + line + "\n" for line in report) or "  (none)\n")
        if empty:
            fh.write("stations with empty address:\n")
            for l in empty:
                fh.write(f"  no={l['no']} {l['name']!r}\n")
    print(f"locations: {len(locations)}; by-number {n_by_no} (structural {n_struct}); "
          f"flagged {n_flag}; empty addresses {len(empty)}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
