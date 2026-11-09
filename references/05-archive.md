# 05 归档（G5）

## 入库四关

```
① 体检  判据本身可信（四件套 + 题面三检都过）
② 收益  配对比较；留出题上保留率 ≥ 0.5
③ 成本  cost per solved task 为正
④ 迁移  至少一个迁移轴成立，且 scope 有依据
```

四关全过才写。**错的经历入库，会在后面每一轮被反复引用。**

## scope 与迁移轴怎么对应

```
验了 3 轴（题/模型/工具面）且都成立 → invariant
验了 2 轴且都成立                  → domain
只在 1 轴成立                      → domain（换题）或 model-specific（换模型）
都不成立或保留率 < 0.5             → 不入库
```

## 条目形态

```json
{"signature": {"category": "回执缺失", "trigger": "多轮反思且工具返回不含失败原因",
               "metric": "同一目标重复请求轮数", "expected": "<=2", "actual": "6"},
 "diagnosis": "state 不回显上一轮回执",
 "fix": "把回执与错误码写回 state",
 "scope": "domain",
 "gate": {"preflight": true, "benefit": true, "cost": true, "transfer": true},
 "evidence": ["verify/readout.md"],
 "last_verified": "2026-11-09",
 "reviewed_by": "<会话 id 或人名>",
 "applies_to": {"model": "<model>", "tool_surface": "<surface>"}}
```

**`gate` 四项必须全为 true 才能写入**；任何一项 false 就不入库，留在 run 目录里当草稿。

类别取**闭集**：题面不可达 / 回执缺失 / 语义歧义 / 预算耗尽 / 能力不足 / 判据假绿 / 证据不足。
最后两项分别对应“模型层的账”与“不可归因”，不要硬塞进别的类。

## 复核与淘汰（周期与落盘位置）

```
触发      每新增 20 条，或每季度一次，以先到为准
做法      抽 3 条，用留出集重跑；记录保留率
落盘      archive/review-log.jsonl，每条一行：
          {"date":"...","entry":"<signature>","result":"hold|downgrade|retire","retention":0.62}
动作      保留率 < 0.5 → 降一档；连续两次降档 → 废弃（标 retired，不删）
```

降级链：`invariant → domain → model-specific → 废弃`。

没有版本的经验库，三个月后就是一本过期菜谱。
