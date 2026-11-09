# STATE — <run id>

> 这是唯一入口。新会话先读这里，再跑 `python scripts/verify_state.py <run_dir>`。

## 当前阶段

G1 冻结（未过）

## 目标

<一句话：改什么系统的什么毛病>

## 门记录

<!-- 格式固定：GATE <id> <pass|fail> files=<逗号分隔> -->

GATE G1 fail files=prereg.md

## 未决问题

- 

## 下一步

1. 填 `prereg.md` 四项
2. `python scripts/freeze_hashes.py . --code <repo> --judge <judge> --data <tasks>`

## 关键决定（写下来，别只留在对话里）

| 时间 | 决定 | 理由 |
|---|---|---|
|  |  |  |

## 恢复提示

```
产物是事实，STATE 是备注。不一致时以产物为准。
产物缺失但 STATE 说过了 → 该门作废，重做。
```
