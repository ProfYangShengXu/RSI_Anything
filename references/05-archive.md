# 05 归档（G5）

## 入库四关

```
① 体检  判据本身可信（三检过了）
② 收益  配对比较，按样本量说结论
③ 成本  cost per solved task 为正
④ 迁移  换题或换模型仍成立
```

四关全过才写。**错的经历入库，会在后面每一轮被反复引用。**

## 条目形态：写症状，不写故事

```json
{"signature": {"category": "回执缺失", "trigger": "多轮反思且工具返回不含失败原因",
               "metric": "同一目标重复请求轮数", "expected": "≤2", "actual": "6"},
 "diagnosis": "state 不回显上一轮回执",
 "fix": "把回执与错误码写回 state",
 "scope": "domain",
 "evidence": ["runs/20261109-vh/verify/readout.md"],
 "last_verified": "2026-11-09",
 "applies_to": {"model": "qwen3-vl", "tool_surface": "vrs-reflect-v3"}}
```

类别取**闭集**：题面不可达 / 回执缺失 / 语义歧义 / 预算耗尽 / 能力不足 / 判据假绿。
自由文本只做补充——闭集才能聚合统计。

## scope 三档

```
invariant        换题/换模型/换工具面都成立
 domain          只在本领域成立
 model-specific   只对本模型成立
```

## 复核与淘汰

```
每条带：最后验证时间 / 适用版本（模型 + 工具面）/ 证据链接
每个周期抽样复验（用留出集，不许用原题）
失效只降级不删：invariant → domain → 废弃，留痕
```

没有版本的经验库，三个月后就是一本过期菜谱。
