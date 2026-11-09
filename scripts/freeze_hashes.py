#!/usr/bin/env python3
"""冻结代码/数据/判据的 hash。跑前跑后各算一次，变了就作废。

用法：
  python freeze_hashes.py RUN_DIR --code <path> [<path> ...] \
      --data <path> ... --judge <path> ...

目录会递归（跳过 .git / __pycache__ / node_modules / runs / .venv），
每个文件一行："<sha256>  <相对路径>"。
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

SKIP = {".git", "__pycache__", "node_modules", "runs", ".venv", ".mypy_cache", ".pytest_cache"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(paths):
    rows = []
    for raw in paths:
        p = Path(raw).resolve()
        if p.is_file():
            rows.append((sha256_file(p), p.name))
            continue
        if not p.is_dir():
            print(f"[warn] 不存在，跳过：{p}", file=sys.stderr)
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for fn in sorted(files):
                fp = Path(root) / fn
                try:
                    rows.append((sha256_file(fp), str(fp.relative_to(p.parent))))
                except OSError as e:
                    print(f"[warn] 读不了 {fp}: {e}", file=sys.stderr)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--code", nargs="*", default=[])
    ap.add_argument("--data", nargs="*", default=[])
    ap.add_argument("--judge", nargs="*", default=[])
    a = ap.parse_args()

    run = Path(a.run_dir)
    (run / "hashes").mkdir(parents=True, exist_ok=True)
    snap = {}
    for name, paths in (("code", a.code), ("data", a.data), ("judge", a.judge)):
        if not paths:
            continue
        rows = collect(paths)
        out = run / "hashes" / f"{name}.sha256"
        out.write_text("".join(f"{h}  {rel}\n" for h, rel in rows), encoding="utf-8")
        snap[name] = {"files": len(rows), "path": str(out)}
        print(f"{name}: {len(rows)} 个文件 -> {out}")

    snap["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (run / "hashes" / "SNAPSHOT.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"G1 hashes: {len(snap) - 1} 类")
    return 0


if __name__ == "__main__":
    sys.exit(main())
