#!/usr/bin/env python3
"""Generic parser for RIK 2022 referendum "glasacka mesta" documents.

Returns rows: {no:int, name:str, address:str, area:str}.

.doc  -> antiword -w 0 (clean '|' table)
.docx -> word/document.xml tables (rows <w:tr>, cells <w:tc>)
"""
import html
import re
import subprocess
import zipfile


def _clean(s):
    s = html.unescape(s or "")
    s = s.replace("\xa0", " ").replace("\x07", "")
    return re.sub(r"\s+", " ", s).strip()


def _is_num(s):
    return bool(re.match(r"^\d{1,4}\.?$", (s or "").strip()))


def _rows_from_cells(raw_rows):
    """raw_rows: list of list of str (each row's cells). Return parsed station rows.

    Handles two layouts:
      * numbered  : col0 = station number (bilingual duplicates share the number)
      * sequential: no number column -> assign 1..N in order
    Columns are [no, name, address, area].
    """
    rows = []
    for cells in raw_rows:
        cells = [_clean(c) for c in cells]
        if any(cells):
            rows.append(cells)

    numbered = sum(1 for c in rows if c and _is_num(c[0]))
    numbered_mode = numbered >= 3

    out = []
    last = 0
    for cells in rows:
        c_no = cells[0] if len(cells) > 0 else ""
        c_name = cells[1] if len(cells) > 1 else ""
        c_addr = cells[2] if len(cells) > 2 else ""
        c_area = cells[3] if len(cells) > 3 else ""
        extra = " ".join(x for x in cells[4:] if x)

        up = (c_name or "").upper()
        if "НАЗИВ" in up:
            continue
        if (c_no or "").upper().rstrip(".") in ("РЕД", "РЕД БР", "БР", "БРОЈ", "БРОЈГМ", "БРОЈ ГМ"):
            continue

        isn = _is_num(c_no)
        n = int(c_no.strip().rstrip(".")) if isn else None

        if numbered_mode:
            if isn:
                if last and n <= last:
                    # duplicate (bilingual) or wrapped number -> merge into previous
                    if out:
                        if not out[-1]["address"] and c_addr:
                            out[-1]["address"] = c_addr
                        add = " ".join(x for x in (c_area, extra) if x)
                        if add:
                            out[-1]["area"] = (out[-1]["area"] + " " + add).strip()
                    continue
                last = n
                out.append({"no": n, "name": c_name, "address": c_addr,
                            "area": " ".join(x for x in (c_area, extra) if x)})
            # unnumbered row in a numbered doc: translation/continuation.
            # fill a missing address in the previous row (bilingual docs)
            if out:
                if not out[-1]["address"] and c_addr:
                    out[-1]["address"] = c_addr
                add = " ".join(x for x in (c_area, extra) if x)
                if add:
                    out[-1]["area"] = (out[-1]["area"] + " " + add).strip()
            continue

        # sequential mode
        if not c_name and not c_addr:
            if out:
                add = " ".join(x for x in (c_area, extra) if x)
                if add:
                    out[-1]["area"] = (out[-1]["area"] + " " + add).strip()
            continue
        last += 1
        out.append({"no": last, "name": c_name, "address": c_addr,
                    "area": " ".join(x for x in (c_area, extra) if x)})
    return out


def parse_doc(path):
    txt = subprocess.run(["antiword", "-w", "0", path], capture_output=True).stdout
    txt = txt.decode("utf-8", "replace")
    low = txt.lower()
    if "<html" in low or "<!doctype" in low or "greška" in low or "greska" in low:
        return []          # RIK error page saved as .doc
    raw_rows = []
    for line in txt.splitlines():
        if "|" not in line:
            continue
        parts = [p for p in line.strip().strip("|").split("|")]
        raw_rows.append(parts)
    return _rows_from_cells(raw_rows)


def parse_docx(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    # rows globally (handles one or many tables); careful to match <w:t> only,
    # not <w:tab/> or <w:tbl...>
    raw_rows = []
    for tr in re.findall(r"<w:tr\b.*?</w:tr>", xml, re.S):
        cells = []
        for tc in re.findall(r"<w:tc\b.*?</w:tc>", tr, re.S):
            txt = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", tc, re.S))
            cells.append(txt)
        raw_rows.append(cells)
    if not raw_rows:
        # fallback: no tables, treat paragraphs per line
        txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S))
        for line in txt.splitlines():
            raw_rows.append(line.split("\t"))
    return _rows_from_cells(raw_rows)


def parse(path):
    return parse_docx(path) if path.lower().endswith(".docx") else parse_doc(path)


if __name__ == "__main__":
    import sys
    rows = parse(sys.argv[1])
    print(f"{len(rows)} rows")
    for r in rows[:12]:
        print(r)
