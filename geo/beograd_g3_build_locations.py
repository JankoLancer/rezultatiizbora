#!/usr/bin/env python3
"""Align the parsed 2022 referendum rows with the RIK 2023 manifest for the
Belgrade g3 municipalities and emit geo/beograd_g3_locations.json.

RIK 2023 is the target (station_name = "N - VENUE").  Venues are matched by a
type-aware, normalised name comparison (quotes/case/diacritics, station index
suffixes, common abbreviations and generic words are normalised away):

  1. same number + compatible name          -> "matched"
  2. strong match at another number         -> "rematched"
  3. same number, partial name overlap      -> "inherited"
  4. not found in the 2022 document          -> address="" (source unresolved;
     STEP 5 geocodes these by venue name)

Output: geo/beograd_g3_locations.json
    [{municipality, no, name, address, _match}, ...] ordered by municipality, no.
"""
import csv
import difflib
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_beograd_g3", "manifest.csv")
REF = os.path.join(BASE, "beograd_g3_ref_rows.json")
OUT = os.path.join(BASE, "beograd_g3_locations.json")

ORDER = ["Градска општина Вождовац", "Градска општина Звездара",
         "Градска општина Врачар", "Градска општина Стари Град"]

_QUOTES = "„“”\"'❝❞«»"
_STOP = {"И", "У", "НА", "ОД", "ДО", "ЗА", "БР", "БРОЈ", "А", "THE", "OF"}
_GENERIC = {
    "ОСНОВНА", "ШКОЛА", "СРЕДЊА", "ГИМНАЗИЈА", "ВИСОКА", "ФАКУЛТЕТ",
    "АКАДЕМИЈА", "УНИВЕРЗИТЕТ", "ДЕЧЈИ", "ВРТИЋ", "ПРЕДШКОЛСКА", "УСТАНОВА",
    "МЕСНА", "ЗАЈЕДНИЦА", "ДОМ", "ЦЕНТАР", "ЗАВОД", "ПРОСТОР", "ОБЈЕКАТ",
    "ЗГРАДА", "БЕОГРАДСКА", "БЕОГРАД", "ГРАДСКА", "ОПШТИНА", "ИСТУРЕНО",
    "ОДЕЉЕЊЕ", "БОРАВАК",
}
_ABBR = [("ОШ", "ОСНОВНА ШКОЛА"), ("ЕТШ", "ЕЛЕКТРОТЕХНИЧКА ШКОЛА"),
         ("МЗ", "МЕСНА ЗАЈЕДНИЦА"), ("ДВ", "ДЕЧЈИ ВРТИЋ"),
         ("ПУ", "ПРЕДШКОЛСКА УСТАНОВА"), ("ДЗ", "ДОМ ЗДРАВЉА")]
_ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV"}


def norm(s):
    s = (s or "").upper()
    s = s.replace(".", "")          # Д.В. -> ДВ, 25. -> 25
    for q in _QUOTES:
        s = s.replace(q, " ")
    s = re.sub(r"[^0-9A-ZА-ШЂЈЉЊЋЏЂ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sig_tokens(name):
    s = norm(name)
    for a, b in _ABBR:
        s = re.sub(rf"\b{a}\b", b, s)
    toks = []
    for w in s.split():
        if w.isdigit() or w in _ROMAN:
            continue
        if w in _STOP or w in _GENERIC:
            continue
        toks.append(w)
    return set(toks)


def typ(name):
    u = " " + norm(name) + " "
    if "ВРТИЋ" in u or "ПРЕДШКОЛСКА" in u or re.search(r"\bДВ\b", u):
        return "vrtic"
    if "ОСНОВНА" in u or re.search(r"\bОШ\b", u):
        return "osnovna"
    if "ГИМНАЗИЈА" in u:
        return "gimnazija"
    if "ФАКУЛТЕТ" in u or "ВИСОКА ШКОЛА" in u or "АКАДЕМИЈА" in u:
        return "visoka"
    if "МЕСНА" in u or re.search(r"\bМЗ\b", u):
        return "mz"
    if "ЗДРАВЉА" in u or re.search(r"\bДЗ\b", u) or "ЗДРАВСТВЕНА" in u or "ГЕРОНТОЛОШКИ" in u:
        return "zdravstvo"
    if any(k in u for k in ("БИБЛИОТЕКА", "КУЛТУРЕ", "КУЛТУРНИ", "ОБРАЗОВАЊЕ")):
        return "kultura"
    if any(k in u for k in ("СПОРТСКИ", "АМК", "КЛУБ", "ФК ")):
        return "sport"
    if "ШКОЛА" in u:
        return "srednja"
    return "other"


def compatible(a, b):
    ta, tb = typ(a), typ(b)
    return ta == tb or ta == "other" or tb == "other"


def main():
    man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    ref = json.load(open(REF, encoding="utf-8"))
    ref_by = {(r["municipality"], r["no"]): r for r in ref}
    by_muni = {}
    for r in ref:
        by_muni.setdefault(r["municipality"], []).append(r)
    for lst in by_muni.values():
        for r in lst:
            r["_sig"] = sig_tokens(r["name"])

    # uniqueness of each significant token within a municipality
    def uniq(m, tok):
        n = sum(1 for r in by_muni.get(m, []) if tok in r["_sig"])
        return n == 1

    out, report = [], []
    used = set()
    for m in ORDER:
        rows = [r for r in man if r["municipality"] == m]
        rows.sort(key=lambda r: int(r["station_name"].split(" - ", 1)[0]))
        cands = by_muni.get(m, [])
        for r in rows:
            nm = r["station_name"].strip()
            no = int(nm.split(" - ", 1)[0])
            venue = nm.split(" - ", 1)[1].strip() if " - " in nm else nm
            rsig = sig_tokens(venue)
            same = ref_by.get((m, no))
            chosen, how = None, None

            # 1. same number, identical normalised name
            if same and rsig == same["_sig"]:
                chosen, how = same, "matched"
            if chosen is None:
                # 2. strong match at any number (type-compatible)
                scored = []
                for c in cands:
                    inter = rsig & c["_sig"]
                    if not inter:
                        continue
                    if not compatible(venue, c["name"]):
                        continue
                    scored.append((len(inter), -abs(c["no"] - no), c, inter))
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                for sc, _, c, inter in scored:
                    if sc >= 2 or (sc == 1 and all(uniq(m, t) for t in inter)):
                        chosen, how = c, "rematched"
                        break
            # 2b. fuzzy match on the normalised full name (typos/variants)
            if chosen is None:
                best = None
                vnorm = norm(venue)
                for c in cands:
                    if not compatible(venue, c["name"]):
                        continue
                    ratio = difflib.SequenceMatcher(None, vnorm, norm(c["name"])).ratio()
                    if ratio >= 0.88 and (best is None or ratio > best[0]):
                        best = (ratio, c)
                if best is not None:
                    chosen, how = best[1], "rematched"
            # 3. same number, partial name overlap
            if chosen is None and same is not None and (rsig & same["_sig"]):
                chosen, how = same, "inherited"
            # 4. unresolved
            if chosen is None:
                address = ""
                how = "unresolved"
            else:
                address = chosen["address"]
                used.add((m, chosen["no"]))
            out.append({"municipality": m, "no": no, "name": venue,
                        "address": address})
            if how in ("rematched", "inherited", "unresolved"):
                report.append((m, no, venue, how,
                               (chosen["no"], chosen["name"]) if chosen else None))

    extras = [(r["municipality"], r["no"], r["name"], r["address"])
              for r in ref if (r["municipality"], r["no"]) not in used]

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    counts = {}
    for (_, _, _, how, _) in report:
        counts[how] = counts.get(how, 0) + 1
    counts["matched"] = len(out) - len(report)
    print(f"manifest stations: {len(man)}   locations rows: {len(out)}")
    print("match types:", counts)
    print("\nnon-matched detail:")
    for m, no, venue, how, ch in report:
        c = f"-> {ch[0]} {ch[1][:34]}" if ch else ""
        print(f"   {m.split()[-1]:<10} {no:>3} {venue[:42]:<42} [{how}] {c}")
    print(f"\nparsed rows not referenced by any 2023 station ({len(extras)}):")
    for m, no, name, addr in extras:
        print(f"   {m.split()[-1]:<10} {no:>3} {name[:44]:<44} {addr}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
