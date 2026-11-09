#!/usr/bin/env python3
"""冻结 / 校验代码、数据、判据的 hash。

冻结：
  python freeze_hashes.py RUN_DIR --code <path> [...] --data <path> [...] --judge <path> [...]

校验（重算并与冻结值比）：
  python freeze_hashes.py RUN_DIR --verify

目录递归，跳过 .git / __pycache__ / node_modules / runs / .venv。
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
    rows = {}
    for raw in paths:
        p = Path(raw).resolve()
        if p.is_file():
            rows[p.name] = sha256_file(p)
            continue
        if not p.is_dir():
            print(f"[warn] 不存在，跳过：{p}", file=sys.stderr)
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for fn in sorted(files):
                fp = Path(root) / fn
                try:
                    rows[str(fp.relative_to(p.parent))] = sha256_file(fp)
                except OSError as e:
                    print(f"[warn] 读不了 {fp}: {e}", file=sys.stderr)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--code", nargs="*", default=[])
    ap.add_argument("--data", nargs="*", default=[])
    ap.add_argument("--judge", nargs="*", default=[])
    ap.add_argument("--verify", action="store_true", help="重算并与 SNAPSHOT 比，不一致则 exit 1")
    a = ap.parse_args()

    run = Path(a.run_dir)
    hdir = run / "hashes"
    snap_path = hdir / "SNAPSHOT.json"

    if a.verify:
        if not snap_path.exists():
            print(f"[fail] 没有 {snap_path}")
            return 2
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        cats = snap.get("categories")
        if not cats:
            print("[fail] SNAPSHOT 里没有 categories（旧格式或不完整）—— 无法复验，重做冻结")
            return 2
        bad = 0
        for name, info in cats.items():
            cur = collect(info["paths"])
            stored = {}
            f = hdir / f"{name}.sha256"
            if f.exists():
                for line in f.read_text(encoding="utf-8").splitlines():
                    if "  " in line:
                        h, rel = line.split("  ", 1)
                        stored[rel] = h
            added = set(cur) - set(stored)
            removed = set(stored) - set(cur)
            changed = {k for k in set(cur) & set(stored) if cur[k] != stored[k]}
            status = "ok" if not (added or removed or changed) else "CHANGED"
            print(f"{name}: {status} files={len(cur)} added={len(added)} removed={len(removed)} changed={len(changed)}")
            for k in sorted(changed)[:10]:
                print(f"  ~ {k}")
            for k in sorted(removed)[:10]:
                print(f"  - {k}")
            for k in sorted(added)[:10]:
                print(f"  + {k}")
            bad += len(added) + len(removed) + len(changed)
        print("VERIFY: " + ("PASS" if bad == 0 else f"FAIL ({bad} 处差异)"))
        return 0 if bad == 0 else 1

    hdir.mkdir(parents=True, exist_ok=True)
    cats = {}
    for name, paths in (("code", a.code), ("data", a.data), ("judge", a.judge)):
        if not paths:
            continue
        rows = collect(paths)
        (hdir / f"{name}.sha256").write_text(
            "".join(f"{h}  {rel}\n" for rel, h in sorted(rows.items())), encoding="utf-8")
        cats[name] = {"paths": [str(Path(p).resolve()) for p in paths], "files": len(rows)}
        print(f"{name}: {len(rows)} 个文件 -> hashes/{name}.sha256")

    snap_path.write_text(json.dumps({
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "categories": cats,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"G1 hashes: {len(cats)} 类（校验：--verify）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
