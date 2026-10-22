#!/usr/bin/env python3
"""Run the committee pipeline for a batch of municipalities.

Usage:
  python3 odbori/run_batch.py --slugs gradnis gradpancevo ...
  python3 odbori/run_batch.py --batch 1/6
  python3 odbori/run_batch.py --batch 1/6 --recheck   # two-day update

Progress is written to odbori/work/status/<slug>.json (one file per city, so
parallel workers never write the same file).
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "odbori"))
from parse_odbori import append_page2  # noqa: E402

MUNI = os.path.join(ROOT, "odbori", "municipalities_2026.json")
DATA = os.path.join(ROOT, "odbori", "data")
STATUS = os.path.join(ROOT, "odbori", "work", "status")


def load_munis():
    return json.load(open(MUNI, encoding="utf-8"))


def status_path(slug):
    os.makedirs(STATUS, exist_ok=True)
    return os.path.join(STATUS, slug + ".json")


def read_status(slug):
    p = status_path(slug)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_status(slug, **kw):
    p = status_path(slug)
    old = read_status(slug)
    old.update(kw)
    old["slug"] = slug
    json.dump(old, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def run(cmd):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    return r.returncode


def process(m, args):
    slug = m["slug"]
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_status(slug, state="running", started_at=started, name=m["name"])
    try:
        if not args.skip_scrape:
            cmd = [
                sys.executable, "odbori/scrape_odbori.py",
                "--slug", slug,
                "--id", str(m["id"]),
                "--name", m["name"],
                "--region", str(m.get("region", "")),
                "--region-name", m.get("region_name", ""),
                "--dpi", str(args.dpi),
                "--download-workers", str(args.download_workers),
                "--ocr-workers", str(args.ocr_workers),
            ]
            if run(cmd) != 0:
                raise RuntimeError("scrape failed")

        if not args.skip_parse:
            if run([sys.executable, "odbori/parse_odbori.py", slug]) != 0:
                raise RuntimeError("parse failed")
            # long decisions can spill onto page 2; OCR it only when needed
            prob_path = os.path.join(DATA, slug + "_problems.json")
            if os.path.exists(prob_path):
                probs = json.load(open(prob_path, encoding="utf-8"))
                fixed = 0
                for p in probs:
                    if p.get("error") in ("no_entries_parsed", "no_changes_parsed") and p.get("file"):
                        if append_page2(slug, p["file"], args.dpi):
                            fixed += 1
                if fixed:
                    print(f"  appended page 2 to {fixed} documents; reparsing", flush=True)
                    if run([sys.executable, "odbori/parse_odbori.py", slug]) != 0:
                        raise RuntimeError("reparse failed")

        if not args.skip_build:
            if run([sys.executable, "odbori/build_odbori.py", slug]) != 0:
                raise RuntimeError("build failed")

        d = json.load(open(os.path.join(DATA, slug + "_odbori.json"), encoding="utf-8"))
        prob_path = os.path.join(DATA, slug + "_problems.json")
        parse_problems = len(json.load(open(prob_path, encoding="utf-8"))) if os.path.exists(prob_path) else 0
        write_status(
            slug,
            state="done",
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            stations=d["summary"]["stations_total"],
            stations_stalni=d["summary"]["stations_stalni"],
            stations_prosireni=d["summary"]["stations_prosireni"],
            missing_permanent=max(0, d["summary"]["stations_total"] - d["summary"]["stations_stalni"]),
            missing_expanded=max(0, d["summary"]["stations_total"] - d["summary"]["stations_prosireni"]),
            parse_problems=parse_problems,
            build_problems=len(d.get("problems", [])),
            ok=True,
            error="",
        )
        print(f"  OK {slug}: {d['summary']['stations_total']} stations, "
              f"{d['summary']['stations_stalni']} permanent, {d['summary']['stations_prosireni']} expanded", flush=True)
        return True
    except Exception as e:
        write_status(
            slug,
            state="error",
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ok=False,
            error=str(e),
        )
        print(f"  ERROR {slug}: {e}", flush=True)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slugs", nargs="*", default=None)
    ap.add_argument("--batch", help="i/n, balanced by station count")
    ap.add_argument("--recheck", action="store_true", help="revisit completed cities (only new docs are OCRed)")
    ap.add_argument("--only-missing", action="store_true", help="only cities with missing permanent committees or errors")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-parse", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--download-workers", type=int, default=4)
    ap.add_argument("--ocr-workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    munis = load_munis()
    by_slug = {m["slug"]: m for m in munis}
    if args.slugs:
        chosen = [by_slug[s] for s in args.slugs if s in by_slug]
        missing = [s for s in args.slugs if s not in by_slug]
        if missing:
            print("unknown slugs:", missing)
    elif args.batch:
        i, n = [int(x) for x in args.batch.split("/")]
        ordered = sorted(munis, key=lambda m: -(m.get("stations") or 0))
        buckets = [[] for _ in range(n)]
        loads = [0] * n
        for m in ordered:
            j = min(range(n), key=lambda k: loads[k])
            buckets[j].append(m)
            loads[j] += m.get("stations") or 0
        chosen = buckets[i - 1]
    else:
        chosen = munis

    if args.only_missing:
        filtered = []
        for m in chosen:
            st = read_status(m["slug"])
            if st.get("state") == "done" and not st.get("missing_permanent") and not st.get("missing_expanded"):
                continue
            filtered.append(m)
        chosen = filtered
        print(f"--only-missing: {len(chosen)} municipalities", flush=True)

    if args.limit:
        chosen = chosen[: args.limit]

    print(f"batch: {len(chosen)} municipalities, {sum(m.get('stations') or 0 for m in chosen)} stations", flush=True)
    ok = 0
    for m in chosen:
        st = read_status(m["slug"])
        if not args.force and not args.recheck and st.get("state") == "done":
            print(f"skip {m['slug']} (done)", flush=True)
            ok += 1
            continue
        if process(m, args):
            ok += 1
    print(f"finished {ok}/{len(chosen)}", flush=True)


if __name__ == "__main__":
    main()
