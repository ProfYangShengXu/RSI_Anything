#!/usr/bin/env python3
"""run_target.py — 用一个 target 配置跑一次被改进端，产出可验证的 run 目录。

    python run_target.py targets/bb6.json --run-dir runs/20261110-bb6-a

它只做四件事，每件都可复验：
  1. 冻结三样 hash（代码 / 数据 / 判据）
  2. 按配置的执行体跑一次，stdout/stderr 落 logs/
  3. 事件流过 check_trace
  4. 打印一张「这次能验什么」的表

不改被改进端的代码 —— 事件流由被改进端用 emitter.py 自己写。
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="只冻结 + 打印命令，不真跑")
    a = ap.parse_args()

    cfg = json.loads(Path(a.target).read_text(encoding="utf-8"))
    run = Path(a.run_dir).resolve()
    for sub in ("observe", "hashes", "logs", "attribute", "verify", "archive", "changes"):
        (run / sub).mkdir(parents=True, exist_ok=True)

    if not (run / "prereg.md").exists():
        print(f"[停] {run/'prereg.md'} 不存在 —— 先写预注册（H0/预算/判据/样本量/聚合口径）")
        return 2

    # 1) 冻结
    print("[1/4] 冻结 hash")
    r = sh([sys.executable, str(HERE / "freeze_hashes.py"), str(run),
            "--code", *cfg["code"], "--data", *cfg["data"], "--judge", *cfg["judge"]])
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        print("[停] 冻结失败（缺类别 / 路径不存在 / 0 文件）")
        return 2

    # 2) 跑
    cmd = [c.replace("{run_dir}", str(run)) for c in cfg["cmd"]]
    print(f"[2/4] 执行：{shlex.join(cmd)}  (cwd={cfg.get('cwd','.')})")
    if a.dry_run:
        print("      --dry-run，停在这里")
        return 0
    env = dict(os.environ, **{k: str(v).replace("{run_dir}", str(run))
                              for k, v in (cfg.get("env") or {}).items()})
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cfg.get("cwd") or None, env=env,
                           capture_output=True, text=True,
                           timeout=a.timeout or cfg.get("timeout_s", 1800))
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        rc = "TIMEOUT"
    wall = time.time() - t0
    (run / "logs" / "stdout.log").write_text(out, encoding="utf-8")
    (run / "logs" / "stderr.log").write_text(err, encoding="utf-8")
    print(f"      exit={rc}  wall={wall:.1f}s  stdout={len(out)}B  stderr={len(err)}B")

    # 3) 事件流
    ev = run / cfg.get("events", "observe/events.jsonl")
    print("[3/4] 事件流校验")
    if not ev.exists() or ev.stat().st_size == 0:
        print("      [fail] 没有事件流 —— 被改进端没接 emitter，G2 无法过")
        g2 = False
        summary = {}
    else:
        r = sh([sys.executable, str(HERE / "check_trace.py"), str(ev), "--json"])
        line = next((x for x in r.stdout.splitlines() if x.strip().startswith("{")), "")
        summary = json.loads(line) if line else {}
        g2 = r.returncode == 0
        print(f"      {'PASS' if g2 else 'FAIL'}  {summary}")

    # 4) 能验什么
    print("[4/4] 这次的数据能支持什么结论")
    if summary:
        n_req = summary.get("model_request", 0)
        n_calls = summary.get("tool_calls", 0)
        unpaired = summary.get("unpaired", 0)
        recon = summary.get("reconstructed", 0)
        print(f"      模型请求 {n_req}  工具调用 {n_calls}  未配对 {unpaired}  重建 {recon}")
        if recon and recon >= summary.get("records", 1):
            print("      结论上限 = 假设（全是重建面）")
        if n_calls >= 10:
            print("      可做：修复轮数、同目标重复次数、回执字段覆盖率（计数型）")
        if n_req < 19:
            print("      不可做：任何主指标显著性（n<19 到不了 80% 功效）")

    print(f"\nrun_dir={run}\n下一步：写 verify/readout.md 与 attribute/findings.json，再跑 verify_state.py")
    return 0 if g2 else 1


if __name__ == "__main__":
    sys.exit(main())
