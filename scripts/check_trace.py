#!/usr/bin/env python3
"""校验事件流能否作为归因证据（G2 的判据）。

用法：python check_trace.py events.jsonl [--allow-unpaired] [--lenient] [--json]

判据：
  (1) 每行 JSON，且有 run_id / seq / t / type / payload
  (2) seq 严格递增
  (3) type 在允许集合内
  (4) 至少一条 model/request
  (5) payload 里要有“能答问题”的字段（--lenient 可跳过）：
      model/request   n_messages，且 system_sha256 / tools_hash / n_tools 至少一个
      model/response  finish_reason 或 content_len
      tool/call       call_id + name
      tool/result     call_id
      artifact/write  path_abs（或 path）+ bytes + sha256
  (6) tool/call 与 tool/result 按 call_id 配对
"""
import argparse
import json
import sys
from pathlib import Path

TYPES = {
    "run/start", "run/end", "block/start", "block/end",
    "model/request", "model/response",
    "tool/call", "tool/result", "artifact/write",
    "verify/report", "prune",
}
REQUIRED = ("run_id", "seq", "t", "type", "payload")


def payload_problems(typ, p):
    p = p or {}
    if typ == "model/request":
        if "n_messages" not in p:
            return "model/request 缺 n_messages"
        if not any(k in p for k in ("system_sha256", "tools_hash", "n_tools")):
            return "model/request 缺 system/tools 标识（答不了“它看到了什么”）"
    elif typ == "model/response":
        if "finish_reason" not in p and "content_len" not in p:
            return "model/response 缺 finish_reason/content_len"
    elif typ == "tool/call":
        if not p.get("call_id") or not p.get("name"):
            return "tool/call 缺 call_id 或 name"
    elif typ == "tool/result":
        if not p.get("call_id"):
            return "tool/result 缺 call_id"
    elif typ == "artifact/write":
        if not (p.get("path_abs") or p.get("path")) or "bytes" not in p or not p.get("sha256"):
            return "artifact/write 缺 path/bytes/sha256"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--allow-unpaired", action="store_true")
    ap.add_argument("--lenient", action="store_true", help="不检查 payload 字段")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    p = Path(a.path)
    if not p.exists():
        print(f"[fail] 文件不存在：{p}")
        return 1

    problems, rows = [], []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"line {i}: 不是 JSON（{e}）")
            continue
        miss = [k for k in REQUIRED if k not in r]
        if miss:
            problems.append(f"line {i}: 缺字段 {miss}")
        if r.get("type") not in TYPES:
            problems.append(f"line {i}: 非法 type {r.get('type')!r}")
        if not a.lenient:
            msg = payload_problems(r.get("type"), r.get("payload"))
            if msg:
                problems.append(f"line {i}: {msg}")
        rows.append(r)

    seqs = [r.get("seq") for r in rows if isinstance(r.get("seq"), int)]
    for prev, cur in zip(seqs, seqs[1:]):
        if cur <= prev:
            problems.append(f"seq 不递增：{prev} -> {cur}")
            break

    types = [r.get("type") for r in rows]
    n_req = types.count("model/request")
    if n_req == 0:
        problems.append("没有 model/request —— 答不了模型当时看到了什么")

    calls, results = {}, set()
    for r in rows:
        d = r.get("payload") or {}
        if r.get("type") == "tool/call":
            calls[d.get("call_id") or d.get("callId") or f"#{r.get('seq')}"] = r.get("seq")
        elif r.get("type") == "tool/result":
            results.add(d.get("call_id") or d.get("callId"))
    unpaired = [c for c in calls if c not in results]
    reconstructed = sum(1 for r in rows if (r.get("payload") or {}).get("source") == "reconstructed")

    summary = {
        "records": len(rows), "model_request": n_req, "tool_calls": len(calls),
        "unpaired": len(unpaired), "reconstructed": reconstructed, "problems": len(problems),
    }
    if a.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"records={len(rows)} model/request={n_req} tool_calls={len(calls)} "
              f"unpaired={len(unpaired)} reconstructed={reconstructed}")
        for x in problems[:10]:
            print("  - " + x)

    hard_fail = bool(problems)
    soft_fail = bool(unpaired) and not a.allow_unpaired
    if hard_fail or soft_fail:
        if soft_fail:
            print(f"[fail] {len(unpaired)} 次调用没有回执。补不齐就只能当重建面用（结论上限=假设），"
                  f"或加 --allow-unpaired 显式放行")
        print("G2: FAIL")
        return 1

    if reconstructed and reconstructed == len(rows):
        print("[warn] 全部事件都是 reconstructed —— G2 可过，但结论上限是假设（C 档）")
    print("G2: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
