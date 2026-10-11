#!/usr/bin/env python3
"""Run the opstina pipeline for a strided slice of geo/opstina_spec.json.

Usage:
  python3 geo/run_opstina_group.py <group_index> <num_groups> [--shuffle-seed N]

Processes spec[group_index::num_groups] sequentially; resumes by skipping
municipalities whose geo file already has the expected count and no nulls.
Writes a progress log next to this file: geo/_opstina_progress_<gi>.log
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def geo_ok(slug, expected):
    p = os.path.join(HERE, f"{slug}_stations_geo.json")
    if not os.path.exists(p):
        return False
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return len(d) == expected and not any(x.get("lat") is None for x in d)


def main():
    gi = int(sys.argv[1]); ng = int(sys.argv[2])
    force = "--force" in sys.argv
    spec = json.load(open(os.path.join(HERE, "opstina_spec.json"), encoding="utf-8"))
    spec.sort(key=lambda s: -s["stations"])
    group = spec[gi::ng]
    log = open(os.path.join(HERE, f"_opstina_progress_{gi}.log"), "a", encoding="utf-8")

    def note(msg):
        log.write(msg + "\n"); log.flush()
        print(f"[g{gi}] {msg}", flush=True)

    note(f"=== group {gi}/{ng}: {len(group)} municipalities (force={force}) ===")
    for s in group:
        slug = s["slug"]
        if not force and geo_ok(slug, s["stations"]):
            note(f"skip {slug} (done)")
            continue
        note(f"start {slug} ({s['name']}, {s['stations']})")
        try:
            cmd = [sys.executable, os.path.join(HERE, "pipeline_opstina.py"), slug]
            if force:
                cmd.append("--force-geo")
            r = subprocess.run(cmd, cwd=ROOT, timeout=3600,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            tail = r.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
            note(f"done {slug} rc={r.returncode} :: " + " | ".join(tail))
        except subprocess.TimeoutExpired:
            note(f"TIMEOUT {slug}")
        except Exception as exc:  # noqa: BLE001
            note(f"ERROR {slug}: {exc}")
    note(f"=== group {gi} finished ===")


if __name__ == "__main__":
    main()
