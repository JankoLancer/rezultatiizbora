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
import subprocess
import sys
import tempfile
import unicodedata
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
OCR = os.path.join(ROOT, "ocr")
META = os.path.join(ROOT, "meta")
DATA = os.path.join(ROOT, "data")


def append_page2(slug, ocr_file, dpi=150):
    """OCR page 2 and append it to the cached text (fallback for long decisions)."""
    key = os.path.splitext(os.path.basename(ocr_file))[0]
    pdf = os.path.join(ROOT, "pdf", slug, key + ".pdf")
    dst = os.path.join(OCR, slug, os.path.basename(ocr_file))
    if not os.path.exists(pdf) or not os.path.exists(dst):
        return False
    if "\f" in open(dst, encoding="utf-8").read():
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="rikp2_") as td:
            base = os.path.join(td, "p")
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-f", "2", "-l", "2", pdf, base],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
            )
            chunks = []
            for img in sorted(__import__("glob").glob(base + "*.png")):
                r = subprocess.run(
                    ["tesseract", img, "stdout", "-l", "srp"],
                    capture_output=True, text=True, timeout=90,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
                chunks.append(r.stdout)
            with open(dst, "a", encoding="utf-8") as fh:
                fh.write("\n\f\n" + "\n\f\n".join(chunks))
        return True
    except Exception:
        return False


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
    s = s.strip(" \n\t-–—•*|:;,.\"„“”")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+и$", "", s).strip()
    # OCR sometimes puts a stray leading digit/letter from a bullet
    s = re.sub(r"^[|!]+", "", s).strip()
    return s


def clean_proposer(s):
    s = s.strip(" \n\t-–—•*|:;,.\"„“”")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+од\s+\d{1,2}\.\s*[а-шА-Ш]+\s+\d{4}\.?\s*(године)?\.?$", "", s)
    s = re.sub(r"\s+од\s+\d{1,2}\.\d{1,2}\.\d{4}\.?\s*(године)?\.?$", "", s)
    s = re.sub(r"\s*[.;]+$", "", s).strip()
    if re.fullmatch(r"[\d\W]+", s or ""):
        return ""
    return s


ROLE_RE = re.compile(
    r"(?P<marker>"
    r"(?:ПРЕДСЕДНИК|председник)\s*:"
    r"|(?:заменик|ЗАМЕНИК)\s+(?:председника|ПРЕДСЕДНИКА)\s*:"
    r"|(?:заменик|ЗАМЕНИК)\s+(?:(?P<didx>\d+)\s*[.,:;]*\s*)?(?:члана|ЧЛАНА)\s*[:;/.]?"
    r"|(?:(?P<idx>\d+)\.\s*)?(?:члан|ЧЛАН|члана|ЧЛАНА)\s*[:;.]?"
    r"|(?m:^\s*[-–—•*]?\s*(?:члан|ЧЛАН|члана|ЧЛАНА)\s+(?=\S))"
    r"|(?:заменик|ЗАМЕНИК)\s*[.:]"
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
    if low.strip().startswith("заменик"):
        # OCR sometimes drops "člana" and leaves just "zamenik :".
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
    if low.strip().startswith("заменик"):
        return "zamenik_clana", None
    if "члан" in low:
        idx = m.group("idx")
        return "clan", int(idx) if idx else None
    return None, None


PARTY_ABBREV = {
    "СНС", "СПС", "НПС", "СВМ", "СДА", "СДПС", "ЈС", "ПУПС", "ПСГ",
    "СРЦЕ", "РС", "ЛЗС", "РСС", "ЕУ", "АЛТ", "БП", "СН", "СПП", "ГУ",
    "ССП", "ЗЛФ", "АД", "БК", "ЋАЛЕ", "НУ", "СП", "САМ", "ЕКО", "ЗС",
    "МИ", "РП", "НИС", "НПЛС", "НЛС", "3С-ПС",
}


def extract_proposer(segment):
    m = re.search(r"на\s+предлог\s+(.+)", segment, re.S)
    if m:
        p = m.group(1)
        p = re.split(r"\n\s*(?:" + ROLE_RE.pattern + r")", p)[0]
        p = re.split(r";", p)[0]
        p = re.split(r"\n\s*\d+\)\s*", p)[0]
        return clean_proposer(p)
    # Some municipal commissions write only the parliamentary-group acronym
    # after the name: "Milan Pavlović, SNS" (no "na predlog ...").
    matches = re.findall(r",\s*([^,\n;]{2,80})", segment)
    if matches:
        candidate = clean_proposer(matches[-1])
        token = candidate.upper().strip()
        # Accept only known party acronyms. Leaving other OCR debris empty
        # lets fill_pair_proposers copy the proposer from the deputy line.
        if token in PARTY_ABBREV or any(token.startswith(x + "-") for x in PARTY_ABBREV):
            return candidate
    return ""


def extract_name(segment):
    # name is before the first comma or the end of the first line
    s = segment.strip()
    # strip leading bullets / numbering
    s = re.sub(r"^[\s\-–—•*|_]+", "", s)
    s = re.sub(r"^\d+\)\s*", "", s)
    m = re.match(r"(.+?)(?:,|\s*[„“\"']?\s*на\s+предлог|$)", s, re.S)
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


def extract_headings(body):
    """List headings written before the members, e.g. Bojnik:
    "1. На предлог подносиоца изборне листе X; члан: ..."
    """
    out = []
    pat = re.compile(
        r"(?:На|на)\s+предлог\s+(.+?)(?=;\s*\n|:\s*\n|\n\s*(?:члан|Члан|заменик|Заменик|\d+\.)|$)",
        re.S,
    )
    for m in pat.finditer(body):
        p = clean_proposer(m.group(1))
        if p:
            out.append((m.start(), p))
    return out


def fill_pair_proposers(entries):
    for i, e in enumerate(entries):
        p = (e.get("proposer") or "").strip().lower()
        truncated = not p or p in ("подносиоца изборне листе", "посланичке групе") or p.endswith(("листе", "групе"))
        if truncated and i + 1 < len(entries) and entries[i + 1]["role"] in ("zamenik_clana", "zamenik_predsednika"):
            if entries[i + 1].get("proposer"):
                e["proposer"] = entries[i + 1]["proposer"]
        if truncated and e["role"] in ("zamenik_clana", "zamenik_predsednika") and i > 0:
            if entries[i - 1]["role"] == "clan" and entries[i - 1].get("proposer"):
                e["proposer"] = entries[i - 1]["proposer"]
    return entries


def heading_first(body):
    h = body.find("На предлог")
    if h < 0:
        h = body.find("на предлог")
    r = re.search(r"(?:члан|заменик\s+члана|заменик\s+председника|председник)\b", body, re.I)
    return h >= 0 and (r is None or h < r.start())


def parse_base_lines(text):
    """Parser for decisions that put the list heading before the members:
    "1. На предлог подносиоца изборне листе X; члан: Име ..."
    """
    body = disposition(text)
    entries = []
    current = ""
    buf = ""
    collecting = False
    role_re = re.compile(
        r"^[-–—•*]?\s*(заменик\s+члана|заменик\s+председника|председник|члан)\s*:?\s*(.*)$",
        re.I,
    )
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if collecting:
            buf += " " + line
            if line.endswith((";", ":")):
                current = clean_proposer(buf)
                collecting = False
            continue
        if re.match(r"^\d+\.\s*(?:На|на)\s+предлог", line) or re.match(r"^(?:На|на)\s+предлог", line):
            buf = re.sub(r"^\d+\.\s*", "", line)
            if line.endswith((";", ":")):
                current = clean_proposer(buf)
            else:
                collecting = True
            continue
        m = role_re.match(line)
        if not m:
            continue
        low = m.group(1).lower()
        if "заменик" in low and "председник" in low:
            role = "zamenik_predsednika"
        elif "председник" in low:
            role = "predsednik"
        elif "заменик" in low:
            role = "zamenik_clana"
        else:
            role = "clan"
        name = extract_name(m.group(2))
        if not name:
            continue
        entries.append({"role": role, "index": None, "name": name, "proposer": current})
    return entries


SHIFTED_RE = re.compile(
    r"(\d+)\.\s*члан:\s*(.+?)\s*\n+\s*([^\n]+?)\s*-\s*заменик\s+члана:\s*,?\s*на\s+предлог\s+(.+?);",
    re.S | re.I,
)


def parse_base_shifted(text):
    """Layout used in some Vojvodina municipalities:
    "1. члан: NAME и
     DEPUTY - заменик члана: , на предлог ... LIST;"
    """
    body = disposition(text)
    out = []
    for m in SHIFTED_RE.finditer(body):
        member = clean_name(re.sub(r"\s+и$", "", m.group(2)))
        deputy = clean_name(m.group(3))
        proposer = clean_proposer(m.group(4))
        if (
            not member
            or "члан" in member.lower()
            or "заменик" in member.lower()
            or "члан" in deputy.lower()
            or "заменик" in deputy.lower()
            or len(member) > 60
        ):
            continue
        out.append({"role": "clan", "index": int(m.group(1)), "name": member, "proposer": proposer})
        if deputy:
            out.append({"role": "zamenik_clana", "index": int(m.group(1)), "name": deputy, "proposer": proposer})
    return out


def parse_base(text):
    body = disposition(text)
    if heading_first(body):
        return parse_base_lines(text)
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
    entries = fill_pair_proposers(entries)
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


ROLE_NC = re.compile(
    r"(?P<marker>"
    r"Заменик\s+председника|заменик\s+председника"
    r"|Заменик\s+члана|заменик\s+члана"
    r"|ПРЕДСЕДНИК|председник"
    r"|ЧЛАН|Члан|члан"
    r")\b\s+(?:(?P<idx>\d+)\.?\s*)?",
    re.I,
)


def parse_base_nocolon(text):
    """Fallback for decisions that write "Члан Име ..." without a colon."""
    body = disposition(text)
    entries = []
    matches = list(ROLE_NC.finditer(body))
    for i, m in enumerate(matches):
        marker = m.group("marker").lower()
        if "заменик" in marker and "председник" in marker:
            role = "zamenik_predsednika"
        elif "председник" in marker:
            role = "predsednik"
        elif "заменик" in marker and "члан" in marker:
            role = "zamenik_clana"
        else:
            role = "clan"
        idx = m.group("idx")
        idx = int(idx) if idx else None
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        segment = body[m.end():end]
        name = extract_name(segment)
        if not name:
            continue
        proposer = extract_proposer(segment)
        entries.append({"role": role, "index": idx, "name": name, "proposer": proposer})
    return fill_pair_proposers(entries)


LOOSE_RE = re.compile(
    r"(?:(?P<num>\d+)[.)]?\s*)?"
    r"(?P<role>заменик\s+члана|заменик\s+председника|председник|члан)\b\s*[:;/. ]?\s*",
    re.I,
)


def parse_loose(text):
    """Recover all role/name pairs from a messy OCR text.

    Used when the strict parser merged several people into one name.
    """
    body = disposition(text)
    if len(body) < 50:
        body = text
    matches = list(LOOSE_RE.finditer(body))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        segment = body[m.end():end]
        name = extract_name(segment)
        if not name:
            continue
        low = m.group("role").lower()
        if "заменик" in low and "председник" in low:
            role = "zamenik_predsednika"
        elif "председник" in low:
            role = "predsednik"
        elif "заменик" in low:
            role = "zamenik_clana"
        else:
            role = "clan"
        idx = m.group("num")
        out.append({
            "role": role,
            "index": int(idx) if idx else None,
            "name": name,
            "proposer": extract_proposer(segment),
        })
    return fill_pair_proposers(out)


IZMENA_RE = re.compile(
    r"(?:уместо|место)\s*:?\s*(?P<old>[^,;]+?)[\s,]+(?:за|као)\s*(?P<role>[^\n,;]+?)\s+именује\s*[:;,]?\s*(?:се\s+)?"
    r"(?P<new>[^,;]+?)(?=,|;|\.\s|\s+на\s+предлог|$)(?P<rest>[^\n;]*)",
    re.I | re.S,
)

# Common wording in several municipalities:
# "уместо NAME, ROLE, треба да стоји NEW_NAME, ROLE"
IZMENA_STOJI_RE = re.compile(
    r"(?:уместо|место)\s*:?\s*(?P<old>[^,;]+?)\s*,\s*(?P<role>[^\n,;]+?)\s*,?\s*"
    r"треба\s+да\s+стоји\s+(?P<new>[^,;]+?)"
    r"(?=,|;|\.\s|\s+на\s+предлог|$)(?P<rest>[^\n;]*)",
    re.I | re.S,
)


def parse_izmena(text):
    body = disposition(text)
    out = []
    seen = set()
    matches = list(IZMENA_RE.finditer(body)) + list(IZMENA_STOJI_RE.finditer(body))
    for m in matches:
        old = clean_name(m.group("old"))
        new = clean_name(m.group("new"))
        role, idx = parse_role_from_text(m.group("role"))
        if not old or not new or role is None:
            continue
        if "име и презиме" in (old + " " + new).lower():
            continue
        key = (old.lower(), role, new.lower())
        if key in seen:
            continue
        seen.add(key)
        rest = m.group("rest") or ""
        # The proposer may be in the rest of the sentence, sometimes on the next line.
        tail = body[m.end():]
        tail = re.split(r"\n\s*\d+[\.\)]\s*", tail)[0]
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
    if (
        ("мења се назив" in low or "у називу решења" in low)
        and "бирачког места" in low
        and "именују се" not in low
        and "именује се" not in low
    ):
        typ = "station_change"
    elif "исправк" in low:
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


def needs_page2(rec):
    if rec.get("type") in ("imenovanje", "dopuna"):
        return not rec.get("entries")
    if rec.get("type") in ("izmena", "ispravka"):
        return not rec.get("changes")
    return False

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
        rec = None
        no = None
        title = r.get("election_station_title", "") or ""
        title_no = re.match(r"\s*(\d+)", title)
        for attempt in range(2):
            text = norm(open(path, encoding="utf-8").read())
            # The RIK title is authoritative. OCR sometimes reads an extra
            # trailing digit in the "biračko mesto broj" line (17 -> 177),
            # which used to create phantom stations.
            no = int(title_no.group(1)) if title_no else station_no(text)
            comp, typ = classify(text)
            # The API's decision title is authoritative. OCR headings are
            # often clipped (e.g. "О ИЗМЕ" / "НИ РЕШЕЊА"), which used to
            # misclassify changes as fresh appointments.
            meta_title = (r.get("election_board_decision") or "").lower()
            if "проширеном саставу" in meta_title:
                comp = "prosireni"
            elif "сталном саставу" in meta_title:
                comp = "stalni"
            if "исправк" in meta_title or "исправц" in meta_title:
                typ = "ispravka"
            elif "допун" in meta_title:
                typ = "dopuna"
            elif "измен" in meta_title or "разрешењ" in meta_title:
                typ = "izmena"
            elif "именовању" in meta_title:
                typ = "imenovanje"
            if not no:
                no = station_no(text)
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
            elif typ == "ispravka":
                rec["changes"] = parse_ispravka(text)
            elif typ in ("imenovanje", "dopuna"):
                normal = parse_base(text)
                if not normal:
                    normal = parse_base_nocolon(text)
                shifted = parse_base_shifted(text)
                if len(shifted) >= 2:
                    seen = {e["name"].lower() for e in shifted}
                    for e in normal:
                        n = e["name"].lower()
                        if "заменик" in n or "члан" in n or " и " in n or n in seen:
                            continue
                        if any(n == x["name"].lower() for x in shifted):
                            continue
                        shifted.append(e)
                        seen.add(n)
                    rec["entries"] = shifted
                else:
                    rec["entries"] = normal
            else:
                rec["entries"] = []
            if attempt == 0 and needs_page2(rec) and append_page2(municipality, key):
                continue
            break
        if rec.get("type") == "izmena" and not rec.get("changes"):
            problems.append({"url": link, "file": key, "station": no, "error": "no_changes_parsed", "text": text[:2000]})
        elif rec.get("type") == "ispravka" and not rec.get("changes"):
            problems.append({"url": link, "file": key, "station": no, "error": "no_changes_parsed", "text": text[:2000]})
        elif rec.get("type") in ("imenovanje", "dopuna") and not rec.get("entries"):
            problems.append({"url": link, "file": key, "station": no, "error": "no_entries_parsed", "text": text[:2000]})
        elif rec.get("type") not in ("imenovanje", "dopuna", "izmena", "ispravka"):
            problems.append({"url": link, "file": key, "station": no, "error": "unknown_type", "text": text[:1000]})
        out.append(rec)

    # diagnostics for base documents with an unexpected number of entries
    for rec in out:
        if rec["type"] == "imenovanje":
            n = len(rec.get("entries", []))
            bad = False
            if rec["composition"] == "stalni" and n != 6:
                bad = True
            if rec["composition"] == "prosireni" and (n < 3 or n > 20):
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
