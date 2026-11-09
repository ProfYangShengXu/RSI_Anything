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


def collect(paths, strict=True):
    """返回 (rows, errors)。strict=True 时任何问题都进 errors（调用方据此判红）。"""
    rows, errors = {}, []
    for raw in paths:
        p = Path(raw).resolve()
        if p.is_file():
            key = p.name
            if key in rows:
                errors.append(f"同名文件只记一个会漏：{key}（用目录或改名）")
            rows[key] = sha256_file(p)
            continue
        if not p.is_dir():
            errors.append(f"路径不存在：{p}")
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for fn in sorted(files):
                fp = Path(root) / fn
                try:
                    rows[str(fp.relative_to(p.parent))] = sha256_file(fp)
                except OSError as e:
                    errors.append(f"读不了 {fp}: {e}")
    return rows, errors


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
            cur, errs = collect(info["paths"])
            for e in errs:
                print(f"  ! {name}: {e}")
            bad += len(errs)
            if info.get("files", 0) == 0 or not cur:
                print(f"{name}: FAIL 冻结时就是 0 个文件 —— 这不是一次冻结")
                bad += 1
                continue
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

    missing = [n for n, v in (("code", a.code), ("data", a.data), ("judge", a.judge)) if not v]
    if missing:
        print(f"[fail] 缺类别：{', '.join(missing)} —— 代码/数据/判据三样都要冻结，"
              f"少一样后面就不知道是什么变了", file=sys.stderr)
        return 2

    hdir.mkdir(parents=True, exist_ok=True)
    cats = {}
    problems = 0
    for name, paths in (("code", a.code), ("data", a.data), ("judge", a.judge)):
        rows, errs = collect(paths)
        for e in errs:
            print(f"[fail] {name}: {e}", file=sys.stderr)
        problems += len(errs)
        if not rows:
            print(f"[fail] {name}: 0 个文件 —— 空快照不算冻结", file=sys.stderr)
            problems += 1
        (hdir / f"{name}.sha256").write_text(
            "".join(f"{h}  {rel}\n" for rel, h in sorted(rows.items())), encoding="utf-8")
        cats[name] = {"paths": [str(Path(p).resolve()) for p in paths], "files": len(rows)}
        print(f"{name}: {len(rows)} 个文件 -> hashes/{name}.sha256")

    snap_path.write_text(json.dumps({
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "categories": cats,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if problems:
        print(f"[fail] {problems} 处问题，快照不可信", file=sys.stderr)
        return 2
    print(f"G1 hashes: {len(cats)} 类（校验：--verify）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
