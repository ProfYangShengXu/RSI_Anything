# STATE — <run id>

> 这是唯一入口。新会话先读这里，再跑 `python scripts/verify_state.py <run_dir>`。

## 被测系统

```
仓库路径：
判据脚本：
任务集路径：
起跑命令（可复制执行）：
事件来源：observe/events.jsonl  |  observe/rebuilt.jsonl（重建面）
```

## 当前阶段

G1 冻结（未过）

## 目标

<一句话：改什么系统的什么毛病>

## 门记录

<!-- 格式固定：GATE <id> <pass|fail> files=<逗号分隔> -->

GATE G1 fail files=prereg.md

<!-- 只有重建面、且确认回执补不回来时，才写下面这行，并写明原因 -->
<!-- ALLOW_UNPAIRED yes  (原因：历史 trace 无 tool/result) -->

## 未决问题

-

## 下一步

1. 填 `prereg.md` 五项（H0 / 预算 / 判据 / 样本量 / 聚合口径），别留 `<...>` 占位符
2. `python scripts/freeze_hashes.py $RUN --code <repo> --judge <judge> --data <tasks>`

## 关键决定

| 时间 | 决定 | 理由 |
|---|---|---|
|  |  |  |

## 恢复提示

```
产物是事实，STATE 是备注。verify_state 会重算 hash、查 prereg 是否真的填了、查 findings 缺不缺字段。
产物缺失或校验不过但 STATE 说过了 → 该门作废，重做。
```
