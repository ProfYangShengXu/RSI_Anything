#!/usr/bin/env python3
"""check_task.py — RSI 题准入体检。

三道关：落差（p_hat）/ 信噪比（MDE）/ 判分器抗骗（三档 + 对抗集）。
只用标准库。自造题和外部题走同一套；外部题不能改题，过不了就换题。

用法
  python check_task.py mde --n 15
  python check_task.py mde --delta 0.08 --discordance 0.4
  python check_task.py calibrate --runs runs.jsonl --delta 0.08
  python check_task.py grader --scores scores.json
  python check_task.py all --task-dir tasks/0001

输入格式
  runs.jsonl   每行 {"task": "<id>", "scores": [0, 1, 0, 1, 1]}
               或每行 {"task": "<id>", "run": 3, "score": 0.7}
  scores.json  {"orig": 0.42, "ref": 1.0, "junk": 0.03,
                "fakes": {"empty": 0.0, "copy_prompt": 0.02,
                          "keyword_only": 0.35, "shaped_but_wrong": 0.4,
                          "superset_lucky": 0.55},
                "delta": 0.08}

退出码
  0 全过   1 有硬失败   2 输入有问题
"""

import argparse
import json
import math
import sys
from pathlib import Path

DISCORDANCE_DEFAULT = 0.4
ALPHA_DEFAULT = 0.05
POWER_DEFAULT = 0.8


# ---------- 统计：配对二值，精确 McNemar ----------

def _k_crit(nd, alpha):
    """n_d 个不一致对里，min(b,c) 不超过多少时判显著（精确二项双尾）。"""
    if nd == 0:
        return -1
    tail = 0.0
    total = 2.0 ** nd
    for k in range(nd + 1):
        tail += math.comb(nd, k) / total
        if 2.0 * tail > alpha:
            return k - 1
    return nd


def power(n, delta, q=DISCORDANCE_DEFAULT, alpha=ALPHA_DEFAULT):
    """精确功效：b~Bin(n, q/2+delta/2), c~Bin(n, q/2-delta/2) 独立，取 McNemar 精确检验。

    delta = 上升比例 - 下降比例（占全部题），q = 任一方向翻转的比例。
    """
    pu = q / 2 + delta / 2
    pd = q / 2 - delta / 2
    if pd < 0 or pu > 1 or n <= 0:
        return 0.0
    # 二项 pmf
    pb = [math.comb(n, b) * pu ** b * (1 - pu) ** (n - b) for b in range(n + 1)]
    pc = [math.comb(n, c) * pd ** c * (1 - pd) ** (n - c) for c in range(n + 1)]
    kc = [_k_crit(nd, alpha) for nd in range(2 * n + 1)]
    total = 0.0
    for b in range(n + 1):
        if pb[b] < 1e-12:
            continue
        for c in range(n + 1):
            if pc[c] < 1e-12:
                continue
            if min(b, c) <= kc[b + c]:
                total += pb[b] * pc[c]
    return total


def mde(n, q=DISCORDANCE_DEFAULT, alpha=ALPHA_DEFAULT, target=POWER_DEFAULT):
    """最小可测效应；返回 None 表示这个 n 下连 q 这么大的效应都到不了目标功效。"""
    lo, hi = 0.0, q
    if power(n, hi, q, alpha) < target:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if power(n, mid, q, alpha) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def required_n(delta, q=DISCORDANCE_DEFAULT, alpha=ALPHA_DEFAULT, target=POWER_DEFAULT):
    n = 2
    while n <= 5000:
        if power(n, delta, q, alpha) >= target:
            return n
        n += 1
    return None


# ---------- 子命令 ----------

def cmd_mde(args):
    q, alpha, target = args.discordance, args.alpha, args.power
    if args.delta is not None:
        need = required_n(args.delta, q, alpha, target)
        print(f"目标 Δ={args.delta:.2f}  翻转率 q={q:.2f}  α={alpha}  power={target}")
        print(f"需要题数 ≈ {need if need else '> 5000'}")
        rows = []
        for n in (15, 30, 60, 100, 200):
            m = mde(n, q, alpha, target)
            rows.append((n, m))
        print("\n各题数下能测出的最小 Δ：")
        for n, m in rows:
            print(f"  n={n:<4} " + (f"Δ ≥ {m:.2f}（{m*100:.0f}pp）" if m else "到不了 80% 功效（题太少）"))
        ok = bool(need) and need <= args.n if args.n else True
        return 0 if ok else 1

    print(f"翻转率 q={q:.2f}  α={alpha}  power={target}")
    print(f"{'n':>5}  {'MDE':>10}  备注")
    worst = None
    for n in sorted(set(args.n or [15, 30, 60, 100])):
        m = mde(n, q, alpha, target)
        worst = m
        note = "" if m else "即使所有翻转都朝上也测不出"
        print(f"{n:>5}  " + (f"{m*100:>8.0f}pp" if m else f"{'—':>10}") + f"  {note}")
    return 0 if worst else 1


def _load_runs(path):
    per_task = {}
    for ln, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"[输入错误] {path}:{ln} 不是 JSON：{e}")
        tid = obj.get("task")
        if tid is None:
            raise SystemExit(f"[输入错误] {path}:{ln} 缺 task")
        if "scores" in obj:
            per_task.setdefault(tid, []).extend(float(x) for x in obj["scores"])
        elif "score" in obj:
            per_task.setdefault(tid, []).append(float(obj["score"]))
        else:
            raise SystemExit(f"[输入错误] {path}:{ln} 缺 scores 或 score")
    return per_task


def cmd_calibrate(args):
    per_task = _load_runs(args.runs)
    if not per_task:
        print("[输入错误] 没有读到任何题")
        return 2

    ok_tasks, too_easy, too_hard = [], [], []
    print(f"{'task':<28} {'p_hat':>6}  {'n':>3}  判定")
    for tid, ss in sorted(per_task.items()):
        p = sum(ss) / len(ss)
        if p > args.easy:
            verdict, bucket = "太简单（对 RSI 无信息）", too_easy
        elif p < args.hard:
            verdict, bucket = "太低（先分清是难还是题面歧义）", too_hard
        else:
            verdict, bucket = "ok", ok_tasks
        bucket.append(tid)
        print(f"{tid:<28} {p:>6.2f}  {len(ss):>3}  {verdict}")

    n_ok = len(ok_tasks)
    m = mde(n_ok, args.discordance, args.alpha, args.power)
    print(f"\n可用题 {n_ok} / {len(per_task)}   （丢掉：太简单 {len(too_easy)}，太低 {len(too_hard)}）")
    if m is None:
        print(f"结论：n={n_ok} 到不了 {args.power:.0%} 功效 —— 加题，别加判据。")
        return 1
    print(f"结论：n={n_ok} 只能测出 Δ ≥ {m*100:.0f}pp")
    if args.delta is not None:
        if args.delta < 2 * m:
            print(f"      预期 Δ={args.delta*100:.0f}pp < 2×MDE={2*m*100:.0f}pp → 这题组不能用")
            return 1
        print(f"      预期 Δ={args.delta*100:.0f}pp ≥ 2×MDE={2*m*100:.0f}pp → 信噪比够")
    return 0


def cmd_grader(args):
    s = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    for k in ("orig", "ref", "junk"):
        if k not in s:
            print(f"[输入错误] 缺 {k}")
            return 2
    fakes = s.get("fakes") or {}
    orig, ref, junk = float(s["orig"]), float(s["ref"]), float(s["junk"])
    fails = []

    if ref < max([orig, junk] + list(map(float, fakes.values()))):
        fails.append(f"参考不是最高分：ref={ref:.3f}")
    if junk > 0.1 * ref:
        fails.append(f"垃圾分过高：junk={junk:.3f} > 0.1×ref={0.1*ref:.3f}")
    sep = ref - orig
    if sep < 0.1:
        fails.append(f"区分度不足：ref−orig={sep:.3f} < 0.1（换题，别加判据）")
    if len(fakes) < 5:
        fails.append(f"对抗集只有 {len(fakes)} 类，至少要 5 类")
    if fakes:
        worst = max(fakes.items(), key=lambda kv: float(kv[1]))
        allowed = ref - 0.5 * sep
        print(f"对抗集最差项：{worst[0]}={float(worst[1]):.3f}   上限={allowed:.3f}")
        if float(worst[1]) > allowed:
            fails.append(f"假答案骗过头：{worst[0]}={float(worst[1]):.3f} > {allowed:.3f}")

    print(f"orig={orig:.3f}  ref={ref:.3f}  junk={junk:.3f}  区分度={sep:.3f}")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print("\n判分器不合格：这题不能用（先修判据，不是先跑实验）")
        return 1
    print("\n判分器合格")
    return 0


def cmd_all(args):
    d = Path(args.task_dir)
    rc = 0
    for need in ("task.md", "grade.py"):
        if not (d / need).exists():
            print(f"[缺件] {d / need}")
            rc = 2
    if (d / "runs.jsonl").exists():
        args.runs = str(d / "runs.jsonl")
        rc = max(rc, cmd_calibrate(args))
    else:
        print("[缺件] runs.jsonl —— 落差没法算")
        rc = max(rc, 2)
    if (d / "scores.json").exists():
        args.scores = str(d / "scores.json")
        rc = max(rc, cmd_grader(args))
    else:
        print("[缺件] scores.json —— 判分器没法验")
        rc = max(rc, 2)
    return rc


def main():
    ap = argparse.ArgumentParser(description="RSI 题准入体检")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mde", help="信噪比：给定题数能测出多大的 Δ")
    m.add_argument("--n", type=int, nargs="*", default=None)
    m.add_argument("--delta", type=float, default=None, help="预期改善，问需要多少题")
    m.add_argument("--discordance", type=float, default=DISCORDANCE_DEFAULT)
    m.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    m.add_argument("--power", type=float, default=POWER_DEFAULT)
    m.set_defaults(func=cmd_mde)

    c = sub.add_parser("calibrate", help="落差：未改进臂空跑，算每题 p_hat")
    c.add_argument("--runs", required=True)
    c.add_argument("--delta", type=float, default=None)
    c.add_argument("--easy", type=float, default=0.8)
    c.add_argument("--hard", type=float, default=0.2)
    c.add_argument("--discordance", type=float, default=DISCORDANCE_DEFAULT)
    c.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    c.add_argument("--power", type=float, default=POWER_DEFAULT)
    c.set_defaults(func=cmd_calibrate)

    g = sub.add_parser("grader", help="判分器：三档 + 对抗集")
    g.add_argument("--scores", required=True)
    g.set_defaults(func=cmd_grader)

    a = sub.add_parser("all", help="按任务目录跑全部体检")
    a.add_argument("--task-dir", required=True)
    a.add_argument("--delta", type=float, default=None)
    a.add_argument("--easy", type=float, default=0.8)
    a.add_argument("--hard", type=float, default=0.2)
    a.add_argument("--discordance", type=float, default=DISCORDANCE_DEFAULT)
    a.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    a.add_argument("--power", type=float, default=POWER_DEFAULT)
    a.set_defaults(func=cmd_all)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
