#!/usr/bin/env python3
"""Parse OCR text of RIK decisions on polling-station committees (birački odbori).

Input:
  odbori/ocr/<municipality>/*.txt   OCR of the first two pages of each decision
  odbori/meta/<municipality>.json   document list from the RIK API

Output:
  odbori/data/<municipality>_decisions.json   one parsed record per unique document
  odbori/data/<municipality>_problems.json    diagnostics for manual review

The parser intentionally keeps the raw proposer text; normalisation into lists is
done later in build_odbori.py.
"""
import json
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
OCR = os.path.join(ROOT, "ocr")
META = os.path.join(ROOT, "meta")
DATA = os.path.join(ROOT, "data")


def norm(text):
    text = text.replace("\u00ad", "")
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_name(s):
    s = s.strip(" \n\t-–—•*|:;,.")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+и$", "", s).strip()
    # OCR sometimes puts a stray leading digit/letter from a bullet
    s = re.sub(r"^[|!]+", "", s).strip()
    return s


def clean_proposer(s):
    s = s.strip(" \n\t-–—•*|:;,.")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+од\s+\d{1,2}\.\s*[а-шА-Ш]+\s+\d{4}\.?\s*(године)?\.?$", "", s)
    s = re.sub(r"\s+од\s+\d{1,2}\.\d{1,2}\.\d{4}\.?\s*(године)?\.?$", "", s)
    s = re.sub(r"\s*[.;]+$", "", s).strip()
    return s


ROLE_RE = re.compile(
    r"(?P<marker>"
    r"(?:ПРЕДСЕДНИК|председник)\s*:"
    r"|(?:заменик|ЗАМЕНИК)\s+(?:председника|ПРЕДСЕДНИКА)\s*:"
    r"|(?:заменик|ЗАМЕНИК)\s+(?:(?P<didx>\d+)\s*[.,:;]*\s*)?(?:члана|ЧЛАНА)\s*[:;]"
    r"|(?:(?P<idx>\d+)\.\s*)?(?:члан|ЧЛАН|члана|ЧЛАНА)\s*[:;]"
    r")"
)


def parse_role_from_text(s):
    low = s.lower()
    idx = None
    m = re.search(r"(\d+)\.", low)
    if m:
        idx = int(m.group(1))
    if "заменик" in low and "председник" in low:
        return "zamenik_predsednika", None
    if "председник" in low:
        return "predsednik", None
    if "заменик" in low and "члан" in low:
        return "zamenik_clana", idx
    if "члан" in low:
        return "clan", idx
    return None, None


def role_from_marker(m):
    marker = m.group("marker")
    low = marker.lower()
    if "заменик" in low and "председник" in low:
        return "zamenik_predsednika", None
    if "председник" in low:
        return "predsednik", None
    if "заменик" in low and "члан" in low:
        idx = m.group("didx")
        return "zamenik_clana", int(idx) if idx else None
    if "члан" in low:
        idx = m.group("idx")
        return "clan", int(idx) if idx else None
    return None, None


def extract_proposer(segment):
    m = re.search(r"на\s+предлог\s+(.+)", segment, re.S)
    if not m:
        return ""
    p = m.group(1)
    p = re.split(r"\n\s*(?:" + ROLE_RE.pattern + r")", p)[0]
    p = re.split(r";", p)[0]
    p = re.split(r"\n\s*\d+\)\s*", p)[0]
    return clean_proposer(p)


def extract_name(segment):
    # name is before the first comma or the end of the first line
    s = segment.strip()
    # strip leading bullets / numbering
    s = re.sub(r"^[\s\-–—•*|]+", "", s)
    s = re.sub(r"^\d+\)\s*", "", s)
    m = re.match(r"(.+?)(?:,|\s+на\s+предлог|$)", s, re.S)
    if not m:
        return ""
    return clean_name(m.group(1))


def disposition(text):
    """Text between the operative sentence and the closing paragraph."""
    starts = [
        r"именују\s+се\s*:",
        r"именује\s+се\s*:",
        r"тако\s+што\s+се\s+у\s+бирачки\s+одбор\s*:",
    ]
    start = 0
    for pat in starts:
        m = re.search(pat, text, re.I)
        if m:
            start = m.end()
            break
    end = len(text)
    for pat in [r"\n\s*2\.\s*Ово\s+решење", r"\n\s*Ово\s+решење\s+објављује", r"\n\s*Образложење"]:
        m = re.search(pat, text, re.I)
        if m and m.start() > start:
            end = m.start()
            break
    return text[start:end]


def parse_base(text):
    body = disposition(text)
    entries = []
    matches = list(ROLE_RE.finditer(body))
    for i, m in enumerate(matches):
        role, idx = role_from_marker(m)
        if role is None:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        segment = body[m.end():end]
        name = extract_name(segment)
        if not name:
            continue
        proposer = extract_proposer(segment)
        entries.append(
            {"role": role, "index": idx, "name": name, "proposer": proposer}
        )
    # In the expanded composition the proposer is written after the deputy,
    # so the member and deputy share the same "на предлог ..." text.
    for i, e in enumerate(entries):
        if not e["proposer"] and i + 1 < len(entries) and entries[i + 1]["role"] in ("zamenik_clana", "zamenik_predsednika"):
            e["proposer"] = entries[i + 1]["proposer"]
    # Grouped bullet lists (dopune) sometimes put one "на предлог ..." after
    # several members; copy it to the preceding members of the same group.
    for i, e in enumerate(entries[:-1]):
        if (
            not e["proposer"]
            and e["role"] == "clan"
            and e.get("index") is None
            and entries[i + 1]["role"] == "clan"
            and entries[i + 1].get("index") is None
            and entries[i + 1].get("proposer")
        ):
            e["proposer"] = entries[i + 1]["proposer"]
    return entries


IZMENA_RE = re.compile(
    r"уместо\s+(?P<old>[^,;]+?)\s+за\s+(?P<role>[^\n,;]+?)\s+именује\s+(?:се\s+)?"
    r"(?P<new>[^,;]+?)(?=,|;|\.\s|\s+на\s+предлог|$)(?P<rest>[^;]*)",
    re.I | re.S,
)


def parse_izmena(text):
    body = disposition(text)
    out = []
    for m in IZMENA_RE.finditer(body):
        old = clean_name(m.group("old"))
        new = clean_name(m.group("new"))
        role, idx = parse_role_from_text(m.group("role"))
        if not old or not new or role is None:
            continue
        rest = m.group("rest") or ""
        # The proposer may be in the rest of the sentence, sometimes on the next line.
        tail = body[m.end():]
        tail = re.split(r"\n\s*\d+\)\s*", tail)[0]
        tail = re.split(r"\n\s*2\.\s*Ово", tail)[0]
        proposer = extract_proposer(rest + " " + tail)
        out.append(
            {
                "old_name": old,
                "role": role,
                "index": idx,
                "name": new,
                "proposer": proposer,
            }
        )
    return out


def place_from_ocr(text):
    m = re.search(
        r"МЕСТО\s+БРОЈ\s+\d+[^\n]*\n(.*?)\n\s*1\.",
        text,
        re.S | re.I,
    )
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip(" ,")


ISPRAVKA_RE = re.compile(
    r"име\s+(?P<old>.+?)\s+замењује\s+именом\s+(?P<new>.+?)(?:,|\.|\n|тако да)",
    re.I | re.S,
)


def parse_ispravka(text):
    m = re.search(
        r"име\s+(?P<old>.+?)\s+замењује\s+именом\s+(?P<new>.+?)(?:,\s*тако\s+да|\n\s*тако\s+да|\.)",
        text,
        re.I | re.S,
    )
    if not m:
        return []
    old = clean_name(m.group("old"))
    new = clean_name(m.group("new"))
    role_m = re.search(r"у\s+делу\s+који\s+се\s+односи\s+на\s+([^,]+?)(?:,|\s+име\b)", text, re.I | re.S)
    role, idx = parse_role_from_text(role_m.group(1)) if role_m else (None, None)
    proposer = ""
    # The operative part ends with a bullet that repeats the corrected entry.
    b = re.search(r"тако\s+да\s+гласи\s*:\s*(.+?)(?:\n\s*2\.|\Z)", text, re.I | re.S)
    if b:
        bm = ROLE_RE.search(b.group(1))
        if bm:
            role2, idx2 = role_from_marker(bm)
            seg = b.group(1)[bm.end():]
            n2 = extract_name(seg)
            p2 = extract_proposer(seg)
            if n2:
                new = n2
            if role2:
                role, idx = role2, idx2
            if p2:
                proposer = p2
    if not proposer:
        proposer = extract_proposer(text[m.end():])
    if role is None:
        role = "clan"
    if not old or not new:
        return []
    return [{"old_name": old, "role": role, "index": idx, "name": new, "proposer": proposer}]

def classify(text):
    # The explanation often mentions both compositions ("у сталном и
    # проширеном саставу"), so decide from the heading only.
    head = re.split(r"Образложење", text, maxsplit=1, flags=re.I)[0]
    low = head.lower()
    comp = None
    if "проширеном саставу" in low:
        comp = "prosireni"
    elif "сталном саставу" in low:
        comp = "stalni"
    if comp is None:
        low = text.lower()
        if "проширеном саставу" in low:
            comp = "prosireni"
        elif "сталном саставу" in low:
            comp = "stalni"
    if "исправк" in low:
        typ = "ispravka"
    elif "допун" in low:
        typ = "dopuna"
    elif "измен" in low:
        typ = "izmena"
    elif "именовању" in low:
        typ = "imenovanje"
    else:
        typ = "other"
    return comp, typ


def station_no(text):
    m = re.search(r"бирачко\s+место\s+број\s+(\d+)", text, re.I)
    if not m:
        m = re.search(r"БИРАЧКО\s+МЕСТО\s+БРОЈ\s+(\d+)", text)
    return int(m.group(1)) if m else None


def fuzzy_find(name, candidates, threshold=0.72):
    best, score = None, 0.0
    name_n = re.sub(r"\W+", "", name.lower())
    for c in candidates:
        c_n = re.sub(r"\W+", "", c["name"].lower())
        r = SequenceMatcher(None, name_n, c_n).ratio()
        if r > score:
            best, score = c, r
    if best and score >= threshold:
        return best, score
    return None, score


def main(municipality="kragujevac"):
    meta_path = os.path.join(META, municipality + ".json")
    if not os.path.exists(meta_path):
        # fallback for the initial Kragujevac scrape
        meta_path = "/tmp/opencode/kragujevac_docs.json"
    meta = json.load(open(meta_path, encoding="utf-8"))
    records = meta.get("documents", []) if isinstance(meta, dict) else meta
    ocr_dir = os.path.join(OCR, municipality)
    out = []
    problems = []
    seen_urls = set()
    for r in records:
        link = r.get("_url") or ""
        if not link:
            m = re.search(r'href="([^"]+)"', r["extfiles_link"][0])
            link = m.group(1) if m else ""
        if link in seen_urls:
            continue
        seen_urls.add(link)
        parts = link.rstrip("/").split("/")
        key = parts[-2] + "_" + os.path.splitext(parts[-1])[0] + ".txt"
        path = os.path.join(ocr_dir, key)
        if not os.path.exists(path):
            problems.append({"url": link, "error": "missing_ocr", "file": key})
            continue
        text = norm(open(path, encoding="utf-8").read())
        no = station_no(text) or station_no(r.get("election_station_title", ""))
        comp, typ = classify(text)
        if not no:
            m = re.match(r"(\d+)", r.get("election_station_title", ""))
            no = int(m.group(1)) if m else None
        rec = {
            "url": link,
            "file": key,
            "station_no": no,
            "station_title": r.get("election_station_title", ""),
            "datetime": int(r.get("datetime") or 0),
            "decision_title": r.get("election_board_decision", ""),
            "place": place_from_ocr(text),
            "document_name": r.get("document_name", ""),
            "document_bearer": r.get("document_bearer", ""),
            "composition": comp,
            "type": typ,
        }
        if typ == "izmena":
            rec["changes"] = parse_izmena(text)
            if not rec["changes"]:
                problems.append({"url": link, "station": no, "error": "no_changes_parsed", "text": text[:2000]})
        elif typ == "ispravka":
            rec["changes"] = parse_ispravka(text)
            if not rec["changes"]:
                problems.append({"url": link, "station": no, "error": "no_changes_parsed", "text": text[:2000]})
        elif typ in ("imenovanje", "dopuna"):
            rec["entries"] = parse_base(text)
            if not rec["entries"]:
                problems.append({"url": link, "station": no, "error": "no_entries_parsed", "text": text[:2000]})
        else:
            problems.append({"url": link, "station": no, "error": "unknown_type", "text": text[:1000]})
        out.append(rec)

    # diagnostics for base documents with an unexpected number of entries
    for rec in out:
        if rec["type"] == "imenovanje":
            n = len(rec.get("entries", []))
            bad = False
            if rec["composition"] == "stalni" and n != 6:
                bad = True
            if rec["composition"] == "prosireni" and (n < 3 or n > 12):
                bad = True
            if bad:
                problems.append(
                    {
                        "url": rec["url"],
                        "station": rec["station_no"],
                        "error": "unexpected_entry_count",
                        "composition": rec["composition"],
                        "n": n,
                        "entries": rec.get("entries"),
                    }
                )

    os.makedirs(DATA, exist_ok=True)
    json.dump(out, open(os.path.join(DATA, municipality + "_decisions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(problems, open(os.path.join(DATA, municipality + "_problems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(out)} unique decisions, {len(problems)} problems")
    from collections import Counter

    print("types:", Counter((r["composition"], r["type"]) for r in out))
    print("stations:", len({r["station_no"] for r in out if r["station_no"]}))
    for p in problems[:20]:
        print("PROBLEM", p.get("station"), p.get("error"), p.get("url"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kragujevac")
