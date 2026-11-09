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


FIELDS = {
    "H0": ("H0", "起点"),
    "预算": ("预算", "budget"),
    "判据": ("判据", "judge"),
    "样本量": ("样本量", "n/臂", "题/臂"),
    "聚合口径": ("聚合口径", "聚合", "汇总"),
}


def _filled(lines, keys):
    """某一项要有实打实的内容：同行冒号后 ≥6 字，或紧跟三行内有 ≥8 字。"""
    for i, l in enumerate(lines):
        if not any(k in l for k in keys):
            continue
        tail = l.split("：", 1)[1] if "：" in l else ""
        if len(re.sub(r"[\s\-*|#]", "", tail)) >= 6:
            return True
        for nxt in lines[i + 1:i + 4]:
            s = nxt.strip()
            if not s or s.startswith("#"):
                continue
            if len(re.sub(r"[\s\-*|]", "", s)) >= 8 and not PLACEHOLDER.search(s):
                return True
    return False


def check_prereg(run: Path):
    p = run / "prereg.md"
    if not p.exists():
        return "prereg.md 不存在"
    txt = p.read_text(encoding="utf-8")
    tmpl = Path(__file__).resolve().parent.parent / "templates" / "prereg.md"
    if tmpl.exists() and txt.strip() == tmpl.read_text(encoding="utf-8").strip():
        return "prereg.md 还是模板原文 —— 一个字没填"
    if len(txt.strip()) < 150:
        return f"prereg.md 只有 {len(txt.strip())} 字，没填内容"
    left = [m for m in PLACEHOLDER.findall(txt) if not m.startswith("<http")]
    if left:
        return f"prereg.md 还有 {len(left)} 个未填占位符，如 {left[:3]}"
    lines = txt.splitlines()
    empty = [k for k, keys in FIELDS.items() if not _filled(lines, keys)]
    if empty:
        return "prereg.md 这五项没填：" + "、".join(empty)
    return None


def check_judge(run: Path):
    """G1 的第四件：判据体检要留下可机读的结果（check_task.py grader --json 的输出）。"""
    p = run / "verify" / "judge_check.json"
    if not p.exists():
        return ("没有 verify/judge_check.json —— 判据没体检过。"
                "跑：check_task.py grader --scores verify/scores.json > verify/judge_check.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return f"judge_check.json 不是合法 JSON：{e}"
    if d.get("pass") is not True:
        return "judge_check.json 里 pass 不是 true"
    for k in ("orig", "ref", "junk"):
        if k not in d:
            return f"judge_check.json 缺 {k}"
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
        cur, errs = freeze_hashes.collect(info["paths"])
        bad += [f"{name}:{e}" for e in errs]
        if not cur:
            bad.append(f"{name}:0 个文件")
            continue
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


def check_readout(run: Path):
    p = run / "verify" / "readout.md"
    if not p.exists():
        return "verify/readout.md 不存在"
    txt = p.read_text(encoding="utf-8")
    if len(txt.strip()) < 80:
        return f"readout.md 只有 {len(txt.strip())} 字，写不出读数"
    need = {"样本量（n/臂）": ("n/臂", "样本量", "题/臂"),
            "结论档位": ("结论", "显著", "不可判别"),
            "成本分母": ("成本", "cost", "单价", "调用数"),
            "护栏指标": ("护栏", "负向", "副作用")}
    miss = [k for k, keys in need.items() if not any(x in txt for x in keys)]
    return ("readout.md 缺：" + "、".join(miss)) if miss else None


def check_archive(run: Path):
    p = run / "archive" / "experience.jsonl"
    if not p.exists() or p.stat().st_size <= 10:
        return "archive/experience.jsonl 不存在或为空"
    need = ("id", "title", "evidence", "status", "scope")
    bad = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad.append(f"第 {i} 行不是 JSON")
            continue
        miss = [k for k in need if not row.get(k)]
        if miss:
            bad.append(f"第 {i} 行缺 {','.join(miss)}")
    if bad:
        return "experience.jsonl 不合格：" + "; ".join(bad[:3])
    return None


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
    checks["G1"] = check_prereg(run) or check_hashes(run) or check_judge(run)
    checks["G2"] = check_observe(run, allow)
    checks["G3"] = check_findings(run)
    checks["G4"] = check_readout(run)
    checks["G5"] = check_archive(run)

    report = {"run_dir": str(run), "allow_unpaired": allow, "gates": {}, "stale": [], "pending": []}
    for gid in ("G1", "G2", "G3", "G4", "G5"):
        g = gates.get(gid)
        if not g or g["status"] == "fail":
            report["pending"].append(gid)
            report["gates"][gid] = "fail" if g else "pending"
            continue
        if not g["files"]:
            report["stale"].append({gid: {"missing": ["files= 为空：门记录不指名任何产物"]}})
            report["gates"][gid] = "stale"
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
        nxt = (report["pending"][0] if report["pending"]
               else ("先修 stale" if report["stale"] else "完成"))
        print(f"  下一步：{nxt}")

    return 1 if report["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
