# RSI_Anything 验收记录（回放演练）

日期 2026-11-09　对象 bb6 v40（cobol-modernization, Qwen3.5-27B）

## 1 四个脚本是否真能跑

| 脚本 | 用例 | 结果 |
|---|---|---|
| freeze_hashes.py | 冻结 bobanana6/src（99 文件）+ trace（1 文件） | ✅ 生成 code/data 两份 sha256 + SNAPSHOT |
| import_trace.py | 487KB 代理 trace → 事件流 | ✅ 116 事件（model/request 38、tool/call 38） |
| check_trace.py | 校验上述事件流 | ✅ 正确 FAIL：unpaired=38、reconstructed=116 |
| verify_state.py | 正常 / 产物缺失两种 | ✅ 正常返回 next=G1；删产物后报 STALE 且 exit=1；恢复后回到 ok |

## 2 五道门是否真的会拦

```
G1  fail   判据三档自证无法补做（历史 run）—— 拦住，不许进下一步
G2  fail   38 次调用无回执 —— 拦住，结论降级为假设
G3  pass   findings 三条齐全，每条有 component/locator/granularity
G4  pending / G5 pending
```

**这是本次验收最值钱的一条**：重建面没有被当成观测面。若 G2 放绿，就会拿"猜出来的现场"下结论。

## 3 归因是否对得上真值

事先（未看 findings）写下的真值三条：

```
① 契约 output 绝对路径 vs brief 要求相对
② files_write 与 shell 重定向两条写路径并存
③ files_write 回执不确认落点（无 path/bytes/sha）
```

产出 findings.json：

| id | 症状 | component | 与真值 |
|---|---|---|---|
| F1 | 24/38 次调用围绕同一交付物 | 契约 / 数据管线 | ✅ 对应 ① |
| F2 | 15 次写文件尝试，两条路反复试 | 工具 | ✅ 对应 ② |
| F3 | 写后反复 pwd/ls/cat 反查 | 工具 | ✅ 对应 ③ |

**3/3 命中**，且三条 exit 都是「壳的缺陷」，没有一条归到"模型能力不足"。

## 4 数字是否真取自现场（不是回忆）

```
总调用      38      （与 trace 一致）
含 program.py 24    （63%）
写文件类    15      （files_write 5 + heredoc/printf/echo/tee 10）
契约 output /app/program.py   （取自 request 的 last_content 原文）
```

## 5 本次演练暴露的 skill 自身缺口

```
① 没有"历史 run 如何补判据自证"的流程 —— 目前只能标 G1 fail
② import_trace.py 只能导 request/response 型 trace；
   OpenAI 原生 messages 格式（含 tool 消息）还没适配 —— 那种能补出 tool/result
③ 成本无法回填（代理没记 usage），cost per solved task 只能写"未记录"
```

## 6 结论

skill 可用：四个脚本全通、五道门会拦、归因 3/3 对上真值。
但它目前的诚实上限是"假设"——因为 bb6 v40 的历史现场本来就不完整。
要拿到可执行结论，下一轮必须让 bb6 按 S.3 契约吐事件流，而不是事后重建。
