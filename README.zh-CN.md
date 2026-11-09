# RSI_Anything

中文 · [English](README.md)

一套给**允许你改代码**的 agent 做改进的流程。

大部分“自我改进 agent”的做法是：让模型反思一下刚才哪里错了，然后照着改。断点就在这一步——反思是从摘要里生成的，摘要来自一个已经把证据丢掉的壳，改完之后无法归因到任何具体东西。这个仓库做的是另一半：把证据留住、逼出一个结论、让每个改动都能撤回。

状态：研究原型。脚本在一个真实 run 上跑通过（见 `examples/`）。它不是生产工具，也不会告诉你 agent 好不好。它只回答两件事：这次失败具体来自哪里；你为修它做的改动到底有没有用。

## 它不是什么

- 不是 agent 框架。它套在你已有的 agent 外面。
- 不是评测器。判据你自己带；它只坚持一件事——判据必须先自证。
- 不是无人值守的自我改进循环。五道门任何一道都能把它停下，而且经常真的会停。
- 不适合闭源系统。读不到、改不了、加不了日志的系统，最多给你一个分数，给不了诊断。

## 结构

五个阶段、五道门，每个 run 一个目录。

```
P1 任务    冻结 H0、预算、判据、样本量 ──► G1
P2 现场    原样记录发生了什么，不解释   ──► G2
P3 翻译    归因、选改法、写撤销        ──► G3
P4 验证    同起点、同预算、同判据      ──► G4
P5 归档    四关全过才留下              ──► G5
```

每个 run 落在 `runs/<id>/`，自带状态：

```
STATE.md            唯一入口：阶段、门记录、未决问题、下一步
prereg.md           H0、预算、判据、样本量、聚合口径
hashes/             代码 / 数据 / 判据，跑前冻结
observe/events.jsonl
attribute/findings.json
changes/CU-001.md   改动单，含撤销
verify/readout.md
archive/experience.jsonl
```

最要紧的一条：**状态在磁盘上，不在对话里。** 一个完全没有上文记忆的会话，读 `STATE.md`、跑 `verify_state.py`，就能从第一道没过门的地方接着做。

## 五道门

| 门 | 什么算过 |
|---|---|
| G1 冻结 | 预注册四项齐；判据过四件套——标定（参考解最高、垃圾 ≤ 0.1×参考解、参考解比原版高至少 0.1）、对抗集（至少五类假答案逐类报分，最高那个假答案距参考解的差距，至少是参考解与原版差距的一半）、敏感度（已知有效的改动必须让判据动过半个差距）、稳定性（同一产物判三次、换题序，分差 ≤ 0.02）；题面唯一且可达，且审判据的人不是写判据的人 |
| G2 现场 | `check_trace.py` 通过：必填字段齐、`seq` 单调、至少一条 `model/request`、每次 `tool/call` 都配上 `tool/result` |
| G3 归因 | 每条 finding 写得出组件、位置、粒度；每个候选都有探针；只落地一条 |
| G4 验证 | 同起点、同预算、同判据（判据 hash 未变）、只变一个变量；结论按样本量说 |
| G5 归档 | 过四关：体检、收益、成本、迁移 |

门是二值的。不过就不进下一阶段。

## 快速开始

装成 skill（agent 读的是 `SKILL.md`，不是这个文件）：

```bash
# Hermes
cp -r SKILL.md references templates scripts \
  ~/AppData/Local/hermes/skills/software-development/rsi-anything/

# Claude Code
mkdir -p .claude/skills/rsi-anything
cp -r SKILL.md references templates scripts .claude/skills/rsi-anything/

# dsh
mkdir -p ~/.dsh/skills/rsi-anything
cp -r SKILL.md references templates scripts ~/.dsh/skills/rsi-anything/
```

每个 run：

```bash
RUN=runs/$(date +%Y%m%d-%H%M)-mytarget
mkdir -p $RUN/{hashes,observe,attribute,changes,verify,archive,logs}
cp templates/STATE.md $RUN/STATE.md
cp templates/prereg.md $RUN/prereg.md

python scripts/freeze_hashes.py $RUN --code ./src --judge ./judge.py --data ./tasks
python scripts/import_trace.py trace.jsonl -o $RUN/observe/rebuilt.jsonl --reconstructed
python scripts/check_trace.py $RUN/observe/rebuilt.jsonl
python scripts/verify_state.py $RUN
```

所有脚本只用标准库。

## 一个真实案例

`examples/replay-bb6-v40/` 是回放的真实 run。被改进的壳是一个多块编码 agent，在 COBOL 迁移题上跑了 26 分钟，得零分。trace 里有 38 次工具调用，其中 24 次围着同一个交付物转。

产出的三条归因：

| 归因 | 组件 | 位置 |
|---|---|---|
| 24/38 次调用围着一个交付物 | 契约 | 交付物路径规范化 |
| 15 次写文件尝试，两条路来回换 | 工具面 | `shell_run` 重定向与 `files_write` 并存 |
| 写完之后反复 `pwd`/`ls`/`cat` | 工具 | 写回执没有路径、字节数、hash |

三条全落在壳上，没有一条归到模型能力——这和代码里实际有的东西对得上。

这个例子同时展示了门**拒绝放行**。trace 是历史数据，没有工具回执：38 次调用、零回执。G2 判红，证据被标成 reconstructed，结论停在假设层。这是设计意图，也是这个例子值得读的原因：**一个对重建数据放绿灯的工具，比没有工具更糟。**

另一个细节：`verify_state.py` 正反两向都测过，包括删掉一份被门标记为已通过的产物。它会报 `stale` 并以非零码退出。

## 为什么这样设计

**先有证据，再谈归因。** 这类工作最常见的错不是改错了地方，而是改的地方从来没被观察过。先记录、后解释，是唯一能让两者不混在一起的顺序。

**重建的证据要标出身。** 当 run 发生在加日志之前，还是能从日志里重建一部分经过。那部分单独存放、标 `source=reconstructed`、只允许用来提假设；归因只许引用观测记录。没有这条分界，猜出来的东西早晚会被当成读数引用。

**每个改动自带撤销。** 快照、可执行的撤回、撤回后必须重新变绿的那条判据。“我记得怎么改回去”不算撤销方案。

**结论受样本量约束。** 每臂不到 50 条就只报方向，不报 p 值；上百到几百用精确配对检验。这个仓库不报它证不了的误差棒。

**成本是结果的一部分。** 分数涨了但 token 花三倍，不算改进，所以 `cost per solved task` 和分数并排放。

## 已知局限

- 门只和你的判据一样好。G1 能查判据一致、不易被骗，查不了判据测的是不是你以为的那个东西。
- 小样本就是小样本。每臂 15 道题，能诚实说的只有方向。
- `import_trace.py` 认的是 request/response 型 trace。原生消息日志（带工具结果）要另写导入器。
- 这里没有自动决定“该改什么”。归因仍然是最难的一步，而且仍然靠读。

## 规则的出处

每道门都挂在已发表的工作上，不是凭直觉：

| 规则 | 出处 |
|---|---|
| 评测即实验，先算样本量 | 2411.00640 |
| 少于几百条别用正态近似 | 2503.01747 |
| 定位粒度本身是变量 | 2604.00167 |
| 没有外部反馈时自纠会退化 | 2310.01798 |
| 允许弃权，但别过度弃权 | 2611.06158、2402.15610 |
| 定位 → 修复 → 验证，并报成本 | 2407.01489 |
| 接口设计会改变能力 | 2405.15793 |
| 用留出集做选择 | 2606.28374 |
| 判据只剩一个面就会招来作弊 | 2605.21384 |
| 审计本身也有失败模式 | 2607.02586 |

## 许可

MIT，见 `LICENSE`。
