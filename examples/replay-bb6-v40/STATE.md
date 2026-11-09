# STATE — 20261109-bb6-v40

> 唯一入口。新会话先读这里，再跑 `python scripts/verify_state.py <run_dir>`。

## 当前阶段

G2 观测（未过）—— 历史 trace 缺 tool/result，38 次调用全未配对

## 目标

回放演练：用 bb6 v40 的失败现场验证 RSI_Anything 的产出物与门是否成立

## 门记录

GATE G1 fail files=prereg.md
GATE G2 fail files=observe/rebuilt.jsonl
GATE G3 pass files=attribute/findings.json,changes/CU-001.md

## 未决问题

- 判据三档自证无法补做（历史 run）
- token / 成本未记录
- CU-001 未实施，也没跑探针

## 下一步

1. 若要真跑：先补 G1（判据自证）+ 给 bb6 接上事件流（G2），再实施 CU-001
2. 若只做归因演练：到此为止，findings 全部按假设档引用

## 关键决定

| 时间 | 决定 | 理由 |
|---|---|---|
| 2026-11-09 | 不把重建面当观测面 | 38 次调用无回执，按 skill 规定结论上限=假设 |
| 2026-11-09 | 只提 CU-001 一条 | 多因并存时只改主因，F2/F3 登记为已知未处理 |

## 恢复提示

```
产物是事实，STATE 是备注。不一致时以产物为准。
产物缺失但 STATE 说过了 → 该门作废，重做。
```
