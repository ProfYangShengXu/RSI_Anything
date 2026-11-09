#!/usr/bin/env python3
"""把已有的 request/response 型 trace 转成事件流（重建面）。

用法：
  python import_trace.py TRACE.jsonl -o observe/rebuilt.jsonl --reconstructed [--run-id ID]

- run_id 默认取输出目录名（与 runs/<id> 一致），不自己造时间戳
- run/start 在最前，run/end 在最后
- 重建面通常拿不到 tool/result，末尾会报未配对数量
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--reconstructed", action="store_true")
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args()

    src = Path(a.trace)
    out_path = Path(a.out)
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]

    # run_id：显式 > 输出目录名（去掉 observe 这层）> 文件名
    run_id = a.run_id
    if not run_id:
        parent = out_path.resolve().parent
        run_id = parent.parent.name if parent.name in ("observe",) else parent.name
    tag = {"source": "reconstructed"} if a.reconstructed else {}

    out, seq = [], 0

    def emit(typ, payload, t=None):
        nonlocal seq
        seq += 1
        out.append({"run_id": run_id, "seq": seq, "t": t or time.time(),
                    "type": typ, "payload": {**payload, **tag}})

    model = "unknown"
    for r in rows:
        m = r.get("model")
        if m:
            model = m
            break

    emit("run/start", {"model": model, "imported_from": src.name,
                       "mode": "reconstructed" if a.reconstructed else "observed"}, rows[0].get("t") if rows else None)

    for r in rows:
        k = r.get("kind")
        if k == "request":
            sys_txt = r.get("system") or ""
            emit("model/request", {
                "step": r.get("seq"),
                "n_messages": r.get("n_messages"),
                "system_sha256": hashlib.sha256(sys_txt.encode("utf-8")).hexdigest()[:16] if sys_txt else None,
                "n_tools": len(r.get("tools") or []),
                "last_role": r.get("last_role"),
            }, r.get("t"))
        elif k == "response":
            calls = r.get("tool_calls") or []
            emit("model/response", {
                "step": r.get("seq"),
                "finish_reason": r.get("finish"),
                "content_len": len(r.get("content") or ""),
                "tool_calls": [((c.get("function") or {}).get("name")) for c in calls],
            }, r.get("t"))
            for c in calls:
                fn = c.get("function") or {}
                emit("tool/call", {
                    "call_id": c.get("id"),
                    "name": fn.get("name"),
                    "args_head": (fn.get("arguments") or "")[:180],
                }, r.get("t"))

    emit("run/end", {"note": "imported trace: tool/result 通常缺失"})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")

    n_calls = sum(1 for x in out if x["type"] == "tool/call")
    print(f"wrote {out_path}: {len(out)} events (run_id={run_id}, tool/call={n_calls}, tool/result=0)")
    if a.reconstructed:
        print("[warn] 全部标为 reconstructed —— G2 只能在 STATE 写 ALLOW_UNPAIRED yes 后放行，结论上限=假设")
    return 0


if __name__ == "__main__":
    sys.exit(main())
