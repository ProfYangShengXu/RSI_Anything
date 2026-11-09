#!/usr/bin/env python3
"""把已有的 request/response 型 trace 转成事件流（重建面）。

用法：
  python import_trace.py TRACE.jsonl -o observe/rebuilt.jsonl --reconstructed

支持形如 {"kind":"request","model":...,"n_messages":...,"system":...,"last_content":...}
与      {"kind":"response","finish":...,"content":...,"tool_calls":[...]} 的记录。

注意：重建面通常拿不到 tool/result，末尾会报告未配对数量。
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
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    run_id = a.run_id or f"{src.stem}-{int(time.time())}"
    tag = {"source": "reconstructed"} if a.reconstructed else {}

    out, seq = [], 0

    def emit(typ, payload, t=None):
        nonlocal seq
        seq += 1
        out.append({"run_id": run_id, "seq": seq, "t": t or time.time(),
                    "type": typ, "payload": {**payload, **tag}})

    model = "unknown"
    for r in rows:
        k = r.get("kind")
        if k == "request":
            model = r.get("model") or model
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

    emit("run/start", {"model": model, "imported_from": str(src)})
    emit("run/end", {"note": "imported trace: tool/result 通常缺失"})

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")

    n_calls = sum(1 for x in out if x["type"] == "tool/call")
    print(f"wrote {a.out}: {len(out)} events (tool/call={n_calls}, tool/result=0)")
    if a.reconstructed:
        print("[warn] 全部标为 reconstructed —— 结论上限=假设")
    return 0


if __name__ == "__main__":
    sys.exit(main())
