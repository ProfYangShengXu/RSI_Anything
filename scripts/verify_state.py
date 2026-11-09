#!/usr/bin/env python3
"""恢复入口：校验 STATE.md 的门记录与磁盘产物是否一致。

用法：python verify_state.py RUN_DIR

STATE.md 里的门记录格式：
  GATE G2 pass files=observe/events.jsonl,hashes/judge.sha256

判定：
  产物缺失但记了 pass  -> STALE（该门作废，重做）
  没记 pass            -> PENDING
  全部存在             -> OK
"""
import argparse
import json
import re
import sys
from pathlib import Path

LINE = re.compile(r"^GATE\s+(G\d)\s+(pass|fail)\s+files=(.*)$")
REQUIRED_ALWAYS = ["STATE.md", "prereg.md"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    run = Path(a.run_dir).resolve()
    state = run / "STATE.md"
    if not state.exists():
        print(f"[fail] 没有 STATE.md：{run}")
        return 2

    lines = state.read_text(encoding="utf-8").splitlines()
    gates = {}
    for ln in lines:
        m = LINE.match(ln.strip())
        if m:
            gates[m.group(1)] = {"status": m.group(2),
                                 "files": [x.strip() for x in m.group(3).split(",") if x.strip()]}

    report = {"run_dir": str(run), "gates": {}, "missing_global": [], "stale": [], "pending": []}
    for f in REQUIRED_ALWAYS:
        if not (run / f).exists():
            report["missing_global"].append(f)
    if not (run / "hashes").is_dir():
        report["missing_global"].append("hashes/")

    for gid in ["G1", "G2", "G3", "G4", "G5"]:
        g = gates.get(gid)
        if not g:
            report["pending"].append(gid)
            report["gates"][gid] = "pending"
            continue
        if g["status"] == "fail":
            report["pending"].append(gid)
            report["gates"][gid] = "fail"
            continue
        missing = [p for p in g["files"] if not (run / p).exists()]
        if missing:
            report["stale"].append({gid: missing})
            report["gates"][gid] = "stale"
        else:
            report["gates"][gid] = "ok"

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for gid in ["G1", "G2", "G3", "G4", "G5"]:
            print(f"  {gid}: {report['gates'][gid]}")
        if report["missing_global"]:
            print("  缺基础文件：" + ", ".join(report["missing_global"]))
        if report["stale"]:
            print("  STALE（记了 pass 但产物不在）：" + json.dumps(report["stale"], ensure_ascii=False))
        nxt = report["pending"][0] if report["pending"] else "完成"
        print(f"  下一步：{nxt}")

    bad = bool(report["stale"] or report["missing_global"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
