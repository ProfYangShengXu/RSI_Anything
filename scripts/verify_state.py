#!/usr/bin/env python3
"""恢复入口：校验 STATE.md 的门记录与磁盘产物 —— 包括 hash 与内容，不只是存在性。

用法：python verify_state.py RUN_DIR [--json]

STATE.md 里的门记录格式：
  GATE G2 pass files=observe/events.jsonl,hashes/judge.sha256
放行未配对需要在 STATE 里写一行：
  ALLOW_UNPAIRED yes  (原因：历史 trace 无回执)

检查项：
  G1  prereg.md 存在、≥400 字、无未填占位符；hashes/SNAPSHOT 可复验且无差异
  G2  events.jsonl 或 rebuilt.jsonl 存在，且 check_trace 通过
  G3  attribute/findings.json 存在，每条有 component/locator/granularity/evidence
  G4  verify/readout.md 存在
  G5  archive/experience.jsonl 存在且至少一条
产物缺失但记了 pass  -> STALE（该门作废，重做）
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_trace  # noqa: E402
import freeze_hashes  # noqa: E402

LINE = re.compile(r"^GATE\s+(G\d)\s+(pass|fail)\s+files=(.*)$")
ALLOW = re.compile(r"^ALLOW_UNPAIRED\s+(yes|no)", re.I | re.M)
PLACEHOLDER = re.compile(r"<[^<>\n]{1,30}>")


def check_prereg(run: Path):
    p = run / "prereg.md"
    if not p.exists():
        return "prereg.md 不存在"
    txt = p.read_text(encoding="utf-8")
    if len(txt) < 400:
        return f"prereg.md 只有 {len(txt)} 字，没填内容"
    left = [m for m in PLACEHOLDER.findall(txt) if not m.startswith("<http")]
    if left:
        return f"prereg.md 还有 {len(left)} 个未填占位符，如 {left[:3]}"
    return None


def check_hashes(run: Path):
    snap = run / "hashes" / "SNAPSHOT.json"
    if not snap.exists():
        return "hashes/SNAPSHOT.json 不存在（没冻结）"
    data = json.loads(snap.read_text(encoding="utf-8"))
    cats = data.get("categories")
    if not cats:
        return "SNAPSHOT 缺 categories（旧格式），无法复验"
    bad = []
    for name, info in cats.items():
        cur = freeze_hashes.collect(info["paths"])
        stored = {}
        f = run / "hashes" / f"{name}.sha256"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if "  " in line:
                    h, rel = line.split("  ", 1)
                    stored[rel] = h
        bad += [f"{name}:{k}" for k in set(cur) ^ set(stored)]
        bad += [f"{name}:{k}" for k in set(cur) & set(stored) if cur[k] != stored[k]]
    return ("hash 有差异：" + ", ".join(bad[:5])) if bad else None


def check_observe(run: Path, allow_unpaired: bool):
    f = None
    for cand in ("observe/events.jsonl", "observe/rebuilt.jsonl"):
        if (run / cand).exists():
            f = run / cand
            break
    if f is None:
        return "没有 observe/events.jsonl 或 observe/rebuilt.jsonl"

    class A:
        pass
    a = A()
    a.path = str(f)
    a.allow_unpaired = allow_unpaired
    a.lenient = False
    a.json = True
    import subprocess
    cmd = [sys.executable, str(Path(__file__).parent / "check_trace.py"), str(f)]
    if allow_unpaired:
        cmd.append("--allow-unpaired")
    r = subprocess.run(cmd, capture_output=True, text=True)
    return None if r.returncode == 0 else (r.stdout.strip().splitlines() or ["check_trace 失败"])[-1]


def check_findings(run: Path):
    p = run / "attribute" / "findings.json"
    if not p.exists():
        return "attribute/findings.json 不存在"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return f"findings.json 不是合法 JSON：{e}"
    items = data.get("findings") or []
    if not items:
        return "findings 为空"
    need = ("component", "locator", "granularity", "evidence")
    bad = [f.get("id") for f in items if any(not f.get(k) for k in need)]
    return ("findings 缺字段：" + ", ".join(map(str, bad))) if bad else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    run = Path(a.run_dir).resolve()
    if not (run / "STATE.md").exists():
        print(f"[fail] 没有 STATE.md：{run}")
        return 2

    text = (run / "STATE.md").read_text(encoding="utf-8")
    allow = bool(ALLOW.search(text) and ALLOW.search(text).group(1).lower() == "yes")
    gates = {}
    for ln in text.splitlines():
        m = LINE.match(ln.strip())
        if m:
            gates[m.group(1)] = {"status": m.group(2),
                                 "files": [x.strip() for x in m.group(3).split(",") if x.strip()]}

    checks = {}
    checks["G1"] = check_prereg(run) or check_hashes(run)
    checks["G2"] = check_observe(run, allow)
    checks["G3"] = check_findings(run)
    checks["G4"] = None if (run / "verify" / "readout.md").exists() else "verify/readout.md 不存在"
    exp = run / "archive" / "experience.jsonl"
    checks["G5"] = None if (exp.exists() and exp.stat().st_size > 10) else "archive/experience.jsonl 不存在或为空"

    report = {"run_dir": str(run), "allow_unpaired": allow, "gates": {}, "stale": [], "pending": []}
    for gid in ("G1", "G2", "G3", "G4", "G5"):
        g = gates.get(gid)
        if not g or g["status"] == "fail":
            report["pending"].append(gid)
            report["gates"][gid] = "fail" if g else "pending"
            continue
        missing = [p for p in g["files"] if not (run / p).exists()]
        if missing:
            report["stale"].append({gid: {"missing": missing}})
            report["gates"][gid] = "stale"
            continue
        if checks.get(gid):
            report["stale"].append({gid: checks[gid]})
            report["gates"][gid] = "stale"
        else:
            report["gates"][gid] = "ok"

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for gid in ("G1", "G2", "G3", "G4", "G5"):
            print(f"  {gid}: {report['gates'][gid]}")
        for s in report["stale"]:
            print("  STALE " + json.dumps(s, ensure_ascii=False))
        nxt = report["pending"][0] if report["pending"] else "完成"
        print(f"  下一步：{nxt}")

    return 1 if report["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
