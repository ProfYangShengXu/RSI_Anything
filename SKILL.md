---
name: rsi-anything
description: Use when 要对可改代码的 agent/harness 做迭代调优（RSI 改进端）。五道门、磁盘状态、可恢复。
metadata:
  trigger: agent调优, 改进端, RSI, 迭代调优, 提升agent分数, 修harness, 调壳, 复盘失败, 经验库, 改进循环
---

# RSI_Anything —— 改进端

**这个 skill 让 agent 当一个“改进端”**：看现场 → 归因 → 提改动 → 验证 → 归档。
被改进端必须**可读、可写、可加日志**；不能改代码的系统不接（那只能做结果级对比，叫评测，不叫调优）。

---

## 铁律：不靠记忆，靠磁盘

每次执行都在 `runs/<id>/` 留一套可恢复状态。
**判断这个 skill 有没有做对的唯一标准**：把 `STATE.md` 和目录交给一个完全不知情的会话，它不问一句就能接着干。

---

## 可改边界：改「怎么干活」，不改「谁给我打分」

```
可改    提示词 / 工具 / 记忆 / 编排 / 技能 / 输出解析 / 错误处理 / 重试
不可改  评测器 / 题集与 GT / 基础模型 / 迭代预算 / 父代选择机制 / 入库闸
```

判据：一次改动如果让“评分方式”变了，它不是改进，是换尺子。

---

## 目录（每个 run 一份）

```
runs/<YYYYMMDD-HHMM>-<target>/
  STATE.md                 唯一入口：阶段 / 门记录 / 未决 / 下一步
  prereg.md                H0、预算、判据、样本量、聚合口径
  hashes/{code,data,judge}.sha256
  observe/events.jsonl     观测面（被改进端产出）
  observe/rebuilt.jsonl    重建面（历史数据；source=reconstructed）
  attribute/findings.json  归因列表
  changes/CU-001.md        改动单（含撤销三件套）
  verify/readout.md        读数与结论强度
  archive/experience.db    SQLite 经验库：items / evidence / trials / events
  archive/experience.jsonl 导出副本（archive_db.py export，给人读）
  logs/
```

---

## 出题：先算，再写

`scripts/check_task.py` 把「这题能不能用来做 RSI」变成三个可算的判据：

```bash
python scripts/check_task.py mde --n 30              # 这题数能测出多大的 Δ
python scripts/check_task.py calibrate --runs runs.jsonl --delta 0.08
python scripts/check_task.py grader --scores scores.json
python scripts/check_task.py all --task-dir tasks/0001 --delta 0.08
```

```
MDE(n=30)=32pp, n=60=23pp, n=100=18pp, n=200=13pp   (q=0.4, α=.05, power=.8)
预期 Δ < 2×MDE → 这题别写；写完也测不出来
外部题同标准：只挑题、调预算、包判据；过不了就换题，不放松判据
```

规格见 `templates/task-spec.md`（三条准入 + 六条可信 + 五件交付）。

---

## 归档：用库，别用手写 JSONL

```bash
python scripts/archive_db.py add --db archive/experience.db --id F1 --kind pitfall \
  --title "契约写绝对路径会和相对路径规则打架" --when "契约同时给落点与相对规则" \
  --how "统一相对路径，绝对路径只出现在回执" --sig path-conflict --evidence "v40:trace 76 行"
python scripts/archive_db.py search --db archive/experience.db 回执 落点
python scripts/archive_db.py trial  --db archive/experience.db --item F1 --run r12 --outcome neg
python scripts/archive_db.py stats  --db archive/experience.db      # 连续三败的方向会浮出来
python scripts/archive_db.py verify --db archive/experience.db      # 无证据条目 / 断链
```

三条硬约束：**没证据只能是 hypothesis**；**相似条目先拦下来判 新增/合并/替换**；**合并是软删 + 留痕**。

---

## 五道门（二值，不过不进下一阶段）

| 门 | 阶段 | 过关条件 |
|---|---|---|
| **G1 冻结** | P1 任务 | `prereg.md` **五项**齐（H0 / 预算 / 判据 / 样本量 / 聚合口径，无未填占位符）+ **判据体检四件套**：标定（ref 最高、junk ≤ 0.1·ref、ref−orig ≥ 0.1）、对抗集（≥5 类假答案逐类报分，ref−fake_max ≥ 0.5·(ref−orig)）、敏感度（已知有效改动让判据动 ≥ 0.5·(ref−orig)）、鲁棒性（同产物 3 次差 ≤0.02、换序/批量差 ≤0.02、judge hash 冻结）+ 题面三检（唯一/可达/体检者≠作者） |
| **G2 观测** | P2 现场 | `check_trace.py` 通过：字段齐、seq 单调、`model/request` 存在、未配对调用为 0 或已解释 |
| **G3 归因** | P3 翻译 | 每条 finding 有 `component/locator/granularity/evidence` + 来源档；候选**不超过两个**（两个的来源是 Harness² 的 invariant / domain 两类候选，不是随手定的数）；只落地一个；**没有探针的候选不许落地** |
| **G4 验证** | P4 执行验证 | 三条同（起点/预算/评测壳）+ 单变量 + 判据 hash 未变 + 结论按样本量分级 + 成本带分母 |
| **G5 归档** | P5 归档 | 入库四关全过（体检/收益/成本/迁移）+ 签名闭集 + scope 有依据 + 带版本与验证时间 |

**过门就往 STATE.md 追加一行**（脚本能解析的格式）：

```
GATE G2 pass files=observe/events.jsonl
```

---

## 恢复协议（上下文丢了照这个接）

```bash
python scripts/verify_state.py runs/<id>
```

```
① 读 STATE.md
② verify_state 会：重算 hash 与冻结值比对、查 prereg 是否真的填了、
   查 findings 有没有缺字段、并（在 STATE 写 ALLOW_UNPAIRED yes 时）跑 check_trace
③ 不一致以产物为准（产物是事实，STATE 是备注）
④ 从第一个未过门的阶段继续，已过的门不重做
⑤ 产物缺失但 STATE 说过了 → 该门作废，重做
```

---

## 反模式（先读这一节，比流程重要）

```
□ 只报分数不报成本、不报分母
□ 单次通过当结论（n<50 就写“显著提升”）
□ 改了判据/题集/聚合口径还说“提升”
□ 归因写不出组件名，只有“模型不够聪明”
□ 撤销声明只写“改回去”，没有快照与自检
□ 一次改两个变量
□ 候选没有探针就落地
□ 拿重建面（reconstructed）当证据下结论
□ 没跑留出集就写 scope: invariant
□ 把“我要求不合理”当成“模型能力不行”（先查源够不够）
```

---

## 快速开始

```bash
# 所有命令都在 skill 根目录下执行（scripts/ 与 runs/ 是同级）
cd <skill_dir>

# 1 建 run（先定 RUN，后面一律用它，别再写 <id>）
RUN=runs/$(date +%Y%m%d-%H%M)-mytarget
mkdir -p $RUN/{hashes,observe,attribute,changes,verify,archive,logs}
cp templates/STATE.md  $RUN/STATE.md
cp templates/prereg.md $RUN/prereg.md

# 2 冻结（路径写绝对路径最稳）
python scripts/freeze_hashes.py $RUN --code ./src --judge ./judge.py --data ./tasks

# 3 观测
#   有事件流直接用；只有历史 trace 时导入重建面
python scripts/import_trace.py trace.jsonl -o $RUN/observe/rebuilt.jsonl --reconstructed
#   ← 重建面没有 tool/result，check_trace 会判红。确认无法补时，在 STATE.md 加一行：
#     ALLOW_UNPAIRED yes  (原因：历史 trace 无回执)
python scripts/check_trace.py $RUN/observe/rebuilt.jsonl --allow-unpaired

# 4 归因 → 改动单
cp templates/findings.json $RUN/attribute/findings.json
cp templates/change-unit.md $RUN/changes/CU-001.md
cp templates/readout.md     $RUN/verify/readout.md

# 5 收尾自检（会重算 hash、查 prereg 与 findings，不只看文件在不在）
python scripts/verify_state.py $RUN
```

**G2 认哪个文件**：优先 `observe/events.jsonl`（观测面）；只有 `rebuilt.jsonl` 时，必须在 STATE 里写 `ALLOW_UNPAIRED yes`，且结论降为假设。

---

## 参考文件

```
references/01-freeze.md        预注册四项 + 判据体检四件套 + 题面三检
references/02-observe.md       事件契约、check_trace 判据、重建面纪律
references/03-attribute.md     三出口、粒度三字段、来源三档、探针
references/04-verify.md        三条同、样本量分级、成本口径、迁移三轴
references/05-archive.md       入库四关、签名闭集、scope、复核淘汰
```

---

## 外部先验（判据的出处，不是装饰）

| 判据 | 出处 |
|---|---|
| 评测即实验、先算样本量 | 2411.00640 |
| < 几百条别用正态近似 | 2503.01747 |
| 定位粒度本身是变量 | 2604.00167 |
| 无外部反馈时自纠退化 | 2310.01798 |
| 允许弃权、但别过度弃权 | 2611.06158 / 2402.15610 |
| 三段式：定位→修复→验证 + 成本口径 | 2407.01489 Agentless |
| 接口要给反馈（ACI） | 2405.15793 |
| 留出集选择 | 2606.28374 |
| 判据单一化会引来作弊 | 2605.21384 SpecBench |
| 审计本身也有失败模式 | 2607.02586 |
| 审计链要如实回答实际状态 | 2609.00406 |
