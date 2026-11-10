#!/usr/bin/env python3
"""emitter.py — 被改进端的事件上报 SDK（四类契约）。

被改进端只需要 import 它，在四个位置各调一次；剩余的事（seq、配对、落盘）由它做。

    from emitter import Emitter
    with Emitter("observe/events.jsonl", run_id="r12") as E:
        E.run_start(model="qwen3-vl", budget={"calls": 80, "wall_s": 1200})
        E.request(messages, system=sys_prompt, tools=tools, images=n_img)
        E.response(finish_reason="stop", content_len=812, usage={"in": 1200, "out": 300})
        E.tool_call(call_id="c1", name="read", args={"path": "a.py"})
        E.tool_result(call_id="c1", status="ok", exit_code=0, stdout="...")
        E.artifact("out/program.py")
        E.run_end(reason="done")

三条规矩：
  1. 绝不截断计数相关字段：args 存 sha256 + 长度 + 全文旁路文件
  2. 每次 tool_call 必有 tool_result（异常也补一条 status=error）
  3. run_end 由 context manager 兜底，崩溃也必须落一条
"""

import hashlib
import json
import os
import time
from pathlib import Path


class Emitter:
    def __init__(self, path, run_id, sidecar_dir=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.seq = 0
        self.open_calls = {}
        self.sidecar = Path(sidecar_dir) if sidecar_dir else self.path.parent / "args"
        self.sidecar.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a", encoding="utf-8")

    # ---- 内部 ----
    def _emit(self, typ, payload):
        self.seq += 1
        rec = {"run_id": self.run_id, "seq": self.seq, "t": round(time.time(), 3),
               "type": typ, "payload": payload}
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()
        return rec

    @staticmethod
    def _digest(obj):
        raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    # ---- 四类 ----
    def run_start(self, model=None, budget=None, **kw):
        return self._emit("run/start", {"model": model, "budget": budget or {}, **kw})

    def request(self, messages=None, system=None, tools=None, images=0,
                n_messages=None, **kw):
        sys_sha, _ = self._digest(system or "")
        tools_sha, _ = self._digest(tools or [])
        return self._emit("model/request", {
            "n_messages": n_messages if n_messages is not None else len(messages or []),
            "n_tools": len(tools or []),
            "system_sha256": sys_sha[:16],
            "tools_sha256": tools_sha[:16],
            "n_images": images,
            **kw})

    def response(self, finish_reason=None, content_len=None, usage=None, **kw):
        return self._emit("model/response", {
            "finish_reason": finish_reason, "content_len": content_len,
            "usage": usage or {}, **kw})

    def tool_call(self, call_id, name, args=None, **kw):
        raw = json.dumps(args or {}, ensure_ascii=False).encode()
        sha = hashlib.sha256(raw).hexdigest()
        side = self.sidecar / f"{call_id}.json"
        side.write_bytes(raw)
        self.open_calls[call_id] = name
        return self._emit("tool/call", {
            "call_id": call_id, "name": name,
            "args_sha256": sha, "args_len": len(raw),
            "args_head": raw[:180].decode("utf-8", "replace"),
            "args_full": str(side), **kw})

    def tool_result(self, call_id, status="ok", exit_code=None, stdout=None,
                    stderr=None, **kw):
        self.open_calls.pop(call_id, None)
        return self._emit("tool/result", {
            "call_id": call_id, "status": status, "exit_code": exit_code,
            "stdout_len": len(stdout or ""), "stderr_len": len(stderr or ""),
            "stdout_tail": (stdout or "")[-400:], "stderr_tail": (stderr or "")[-400:],
            **kw})

    def artifact(self, path, **kw):
        p = Path(path)
        data = p.read_bytes() if p.is_file() else b""
        return self._emit("artifact/write", {
            "path": str(p), "path_abs": str(p.resolve()),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), **kw})

    def run_end(self, reason="done", **kw):
        for cid, name in list(self.open_calls.items()):
            self.tool_result(cid, status="missing", stderr="调用没有回执（emitter 兜底）")
        return self._emit("run/end", {"reason": reason, **kw})

    # ---- 生命周期 ----
    def close(self):
        try:
            self.run_end(reason="closed")
        finally:
            self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.run_end(reason="exception" if exc_type else "done")
        self._f.close()
        return False


def import_jsonl_events(src, dst, run_id=None):
    """把已有的 request/response 型 trace 转成四类事件（重建面，全部标 reconstructed）。"""
    src, dst = Path(src), Path(dst)
    out, seq = [], 0
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        kind = r.get("kind") or r.get("type")
        seq += 1
        base = {"run_id": run_id or r.get("run_id") or src.stem,
                "seq": seq, "t": r.get("t") or r.get("time") or time.time(),
                "source": "reconstructed"}
        if kind in ("request", "model/request"):
            msg = r.get("messages") or []
            base.update(type="model/request",
                        payload={"n_messages": len(msg), "n_tools": 0,
                                 "system_sha256": "", "tools_sha256": "",
                                 "n_images": 0, "source": "reconstructed"})
        elif kind in ("response", "model/response"):
            txt = r.get("content") or ""
            base.update(type="model/response",
                        payload={"finish_reason": r.get("finish_reason") or "unknown",
                                 "content_len": len(txt), "source": "reconstructed"})
        else:
            continue
        out.append(json.dumps(base, ensure_ascii=False))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(out)
