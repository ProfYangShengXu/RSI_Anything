#!/usr/bin/env python3
"""archive_db.py — 经验库（SQLite）。

一条经验 = 断言 + 何时用 + 怎么做 + 证据链 + 试过几次。
没有证据的条目只能是 hypothesis；失败条目和成功条目同权。

用法
  python archive_db.py init   --db archive.db
  python archive_db.py add    --db archive.db --id F1 --kind pitfall \
        --title "契约里写绝对路径会与系统提示的相对路径规则打架" \
        --when "任务契约同时出现 output 路径与'路径一律相对'" \
        --how "契约统一用相对路径；绝对路径只在回执里用于确认落点" \
        --component contract --sig "path-conflict" --scope global \
        --evidence "v40:obs:24 次围绕 program.py, 6 次 heredoc 失败"
  python archive_db.py search --db archive.db "回执 路径"
  python archive_db.py merge  --db archive.db --from F1b --into F1 --why "同一条"
  python archive_db.py stats  --db archive.db
  python archive_db.py verify --db archive.db
  python archive_db.py export --db archive.db --out experience.jsonl
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  id TEXT PRIMARY KEY, target TEXT, model TEXT, ts TEXT,
  h_code TEXT, h_data TEXT, h_judge TEXT, prereg TEXT);

CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('strategy','pitfall','invariant','neutral')),
  title TEXT NOT NULL,
  when_to_use TEXT NOT NULL,
  how TEXT NOT NULL,
  component TEXT, symptom_sig TEXT,
  scope TEXT CHECK(scope IN ('invariant','domain','model-specific')) DEFAULT 'domain',
  status TEXT NOT NULL DEFAULT 'hypothesis'
    CHECK(status IN ('hypothesis','validated','refuted','merged','retired')),
  merged_into TEXT,
  created_at TEXT, updated_at TEXT);

CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(id),
  run_id TEXT,
  observed INTEGER NOT NULL DEFAULT 1,
  source_kind TEXT CHECK(source_kind IN ('white','gray','black')) DEFAULT 'white',
  note TEXT);

CREATE TABLE IF NOT EXISTS trials(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(id),
  run_id TEXT, applied INTEGER NOT NULL DEFAULT 1,
  delta REAL, mde REAL,
  outcome TEXT CHECK(outcome IN ('pos','neg','indistinguishable')));

CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, item_id TEXT, payload TEXT);

CREATE INDEX IF NOT EXISTS idx_items_sig ON items(symptom_sig);
CREATE INDEX IF NOT EXISTS idx_items_comp ON items(component);
CREATE INDEX IF NOT EXISTS idx_ev_item ON evidence(item_id);
"""


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def log(c, kind, item_id, payload):
    c.execute("INSERT INTO events(ts,kind,item_id,payload) VALUES(?,?,?,?)",
              (now(), kind, item_id, json.dumps(payload, ensure_ascii=False)))


def find_similar(c, title, sig):
    """P5.9：入库前找相似条目。先按签名精确，再按标题词重合。"""
    hits = []
    if sig:
        hits += c.execute(
            "SELECT id,title,status FROM items WHERE symptom_sig=? AND status NOT IN ('merged','retired')",
            (sig,)).fetchall()
    words = [w for w in title.replace("，", " ").replace(",", " ").split() if len(w) >= 2][:4]
    for w in words:
        hits += c.execute(
            "SELECT id,title,status FROM items WHERE title LIKE ? AND status NOT IN ('merged','retired') LIMIT 3",
            (f"%{w}%",)).fetchall()
    seen, out = set(), []
    for h in hits:
        if h["id"] not in seen:
            seen.add(h["id"])
            out.append(h)
    return out[:5]


def cmd_init(a):
    c = conn(a.db)
    c.executescript(SCHEMA)
    c.commit()
    print(f"ok {a.db}")


def cmd_add(a):
    c = conn(a.db)
    c.executescript(SCHEMA)
    if c.execute("SELECT 1 FROM items WHERE id=?", (a.id,)).fetchone():
        print(f"[拒绝] id 已存在：{a.id}", file=sys.stderr)
        return 1
    evs = []
    for ev in (a.evidence or []):
        ev = (ev or "").strip()
        run_id, _, note = ev.partition(":")
        if not run_id or not note.strip():
            print(f"[拒绝] 证据必须写成 run_id:说明（收到 {ev!r}）", file=sys.stderr)
            return 1
        evs.append((run_id, note.strip()))

    status = a.status
    if not evs:
        status = "hypothesis"
        print("[提示] 没给证据 → status 强制为 hypothesis（P5 入库四关）", file=sys.stderr)
    elif status == "validated" and a.reconstructed:
        status = "hypothesis"
        print("[提示] 只有重建面证据（reconstructed）→ 强制 hypothesis："
              "补写的东西只能提假设，不能进已验证档", file=sys.stderr)

    sim = find_similar(c, a.title, a.sig)
    if sim:
        print("相似条目（先判 新增/合并/替换，别直接堆）：")
        for s in sim:
            print(f"  {s['id']:<12} {s['status']:<10} {s['title'][:60]}")
        if not a.force:
            print("\n[停下] 加 --force 才继续新增；否则先 merge。")
            return 1

    ts = now()
    c.execute("""INSERT INTO items(id,kind,title,when_to_use,how,component,symptom_sig,
                                  scope,status,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (a.id, a.kind, a.title, a.when, a.how, a.component, a.sig,
               a.scope, status, ts, ts))
    for run_id, note in evs:
        c.execute("INSERT INTO evidence(item_id,run_id,observed,source_kind,note) VALUES(?,?,?,?,?)",
                  (a.id, run_id, 0 if a.reconstructed else 1, a.source, note))
    log(c, "add", a.id, {"kind": a.kind, "sig": a.sig, "n_ev": len(evs)})
    c.commit()
    print(f"ok {a.id} kind={a.kind} status={status} 证据 {len(evs)} 条")


def cmd_search(a):
    c = conn(a.db)
    where, params = ["status NOT IN ('merged','retired')"], []
    for w in a.words:
        where.append("(title LIKE ? OR when_to_use LIKE ? OR how LIKE ?)")
        params += [f"%{w}%"] * 3
    rows = c.execute("""SELECT id,kind,status,component,symptom_sig,title,when_to_use
                        FROM items
                        WHERE """ + " AND ".join(where) + """
                        ORDER BY CASE status WHEN 'validated' THEN 0 ELSE 1 END, id""",
                     params).fetchall()
    if not rows:
        print("没有匹配")
        return 0
    for r in rows:
        print(f"{r['id']:<12} {r['status']:<10} {r['kind']:<9} {r['symptom_sig'] or '-':<18} {r['title'][:70]}")
        if a.verbose:
            print(f"   何时用：{r['when_to_use'][:120]}")
    print(f"\n{len(rows)} 条")
    return 0


def cmd_merge(a):
    c = conn(a.db)
    src = c.execute("SELECT * FROM items WHERE id=?", (a.from_id,)).fetchone()
    dst = c.execute("SELECT * FROM items WHERE id=?", (a.into,)).fetchone()
    if not src or not dst:
        print("[失败] from 或 into 不存在", file=sys.stderr)
        return 1
    if a.from_id == a.into:
        print("[拒绝] 不能把条目并进自己", file=sys.stderr)
        return 1
    if dst["status"] == "merged":
        print(f"[拒绝] 目标是已合并条目（→{dst['merged_into']}），请并到最终条目", file=sys.stderr)
        return 1
    c.execute("UPDATE items SET status='merged', merged_into=?, updated_at=? WHERE id=?",
              (a.into, now(), a.from_id))
    c.execute("UPDATE evidence SET item_id=? WHERE item_id=?", (a.into, a.from_id))
    c.execute("UPDATE trials SET item_id=? WHERE item_id=?", (a.into, a.from_id))
    log(c, "merge", a.from_id, {"into": a.into, "why": a.why})
    c.commit()
    print(f"ok {a.from_id} → {a.into}（证据与试跑记录已迁移，原条目软删留痕）")


def cmd_trial(a):
    c = conn(a.db)
    c.execute("INSERT INTO trials(item_id,run_id,applied,delta,mde,outcome) VALUES(?,?,?,?,?,?)",
              (a.item, a.run, 1 - int(a.not_applied), a.delta, a.mde, a.outcome))
    log(c, "trial", a.item, {"run": a.run, "outcome": a.outcome, "delta": a.delta})
    c.commit()
    print("ok")


def cmd_stats(a):
    c = conn(a.db)
    print("按状态：")
    for r in c.execute("SELECT status, COUNT(*) n FROM items GROUP BY status ORDER BY n DESC"):
        print(f"  {r['status']:<12} {r['n']}")
    print("\n按类型：")
    for r in c.execute("SELECT kind, COUNT(*) n FROM items GROUP BY kind ORDER BY n DESC"):
        print(f"  {r['kind']:<11} {r['n']}")
    print("\n连续三败的方向（P5.6：除非带新证据，不许再提）：")
    rows = []
    for it in c.execute("SELECT id,title FROM items WHERE status NOT IN ('merged','retired')").fetchall():
        last = c.execute("SELECT outcome FROM trials WHERE item_id=? ORDER BY id DESC LIMIT 3",
                         (it["id"],)).fetchall()
        if len(last) == 3 and all(r["outcome"] == "neg" for r in last):
            rows.append({"id": it["id"], "title": it["title"], "n": 3})
    if not rows:
        print("  （无）")
    for r in rows:
        print(f"  {r['id']:<12} 试 {r['n']} 次 0 胜  {r['title'][:60]}")
    print("\n无证据的条目（只能是 hypothesis）：")
    rows = c.execute("""SELECT id,title,status FROM items i
                        WHERE i.status NOT IN ('merged','retired')
                          AND NOT EXISTS(SELECT 1 FROM evidence e WHERE e.item_id=i.id)""").fetchall()
    if not rows:
        print("  （无）")
    for r in rows:
        print(f"  {r['id']:<12} {r['status']:<10} {r['title'][:60]}")
    return 0


def cmd_verify(a):
    c = conn(a.db)
    bad = []
    for r in c.execute("""SELECT id FROM items WHERE status='validated'
                          AND NOT EXISTS(SELECT 1 FROM evidence e WHERE e.item_id=items.id)"""):
        bad.append(f"{r['id']} 标了 validated 却没有证据")
    for r in c.execute("""SELECT i.id FROM items i WHERE i.status='validated'
                          AND NOT EXISTS(SELECT 1 FROM evidence e
                                         WHERE e.item_id=i.id AND e.observed=1)"""):
        bad.append(f"{r['id']} 标了 validated 但只有重建面证据（observed=0）")
    for r in c.execute("""SELECT e.id FROM evidence e LEFT JOIN items i ON i.id=e.item_id
                          WHERE i.id IS NULL"""):
        bad.append(f"evidence#{r['id']} 指向不存在的条目")
    for r in c.execute("SELECT id, merged_into FROM items WHERE status='merged' AND merged_into IS NULL"):
        bad.append(f"{r['id']} 标了 merged 却没有 merged_into")
    for b in bad:
        print("✗", b)
    print(f"\nitems={c.execute('SELECT COUNT(*) FROM items').fetchone()[0]} "
          f"evidence={c.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]} "
          f"trials={c.execute('SELECT COUNT(*) FROM trials').fetchone()[0]}")
    print("完整性 OK" if not bad else f"{len(bad)} 处问题")
    return 0 if not bad else 1


def cmd_export(a):
    c = conn(a.db)
    out = []
    for r in c.execute("SELECT * FROM items WHERE status!='merged'").fetchall():
        d = dict(r)
        d["evidence"] = [dict(x) for x in c.execute(
            "SELECT run_id,observed,source_kind,note FROM evidence WHERE item_id=?", (r["id"],))]
        d["trials"] = [dict(x) for x in c.execute(
            "SELECT run_id,applied,delta,mde,outcome FROM trials WHERE item_id=?", (r["id"],))]
        out.append(d)
    Path(a.out).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n", encoding="utf-8")
    print(f"ok {a.out}  {len(out)} 条")


def main():
    ap = argparse.ArgumentParser(description="RSI 经验库")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def base(p):
        p.add_argument("--db", default="archive.db")
        return p

    base(sub.add_parser("init")).set_defaults(func=cmd_init)

    p = base(sub.add_parser("add"))
    p.add_argument("--id", required=True)
    p.add_argument("--kind", required=True, choices=["strategy", "pitfall", "invariant", "neutral"])
    p.add_argument("--title", required=True)
    p.add_argument("--when", required=True)
    p.add_argument("--how", required=True)
    p.add_argument("--component")
    p.add_argument("--sig")
    p.add_argument("--scope", default="domain", choices=["invariant", "domain", "model-specific"])
    p.add_argument("--status", default="hypothesis",
                   choices=["hypothesis", "validated", "refuted"])
    p.add_argument("--evidence", nargs="*", help="run_id:note，可多条")
    p.add_argument("--source", default="white", choices=["white", "gray", "black"])
    p.add_argument("--reconstructed", action="store_true")
    p.add_argument("--force", action="store_true", help="存在相似条目也强行新增")
    p.set_defaults(func=cmd_add)

    p = base(sub.add_parser("search"))
    p.add_argument("words", nargs="+")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_search)

    p = base(sub.add_parser("merge"))
    p.add_argument("--from", dest="from_id", required=True)
    p.add_argument("--into", required=True)
    p.add_argument("--why", default="")
    p.set_defaults(func=cmd_merge)

    p = base(sub.add_parser("trial"))
    p.add_argument("--item", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--delta", type=float)
    p.add_argument("--mde", type=float)
    p.add_argument("--outcome", choices=["pos", "neg", "indistinguishable"], default="indistinguishable")
    p.add_argument("--not-applied", action="store_true")
    p.set_defaults(func=cmd_trial)

    base(sub.add_parser("stats")).set_defaults(func=cmd_stats)
    base(sub.add_parser("verify")).set_defaults(func=cmd_verify)

    p = base(sub.add_parser("export"))
    p.add_argument("--out", default="experience.jsonl")
    p.set_defaults(func=cmd_export)

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
