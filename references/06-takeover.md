# 接管：把 VH / bb6 接到改进端上

改进端（这个 skill）不关心被改进端内部长什么样，只要四类事件。
**每个目标只需要写四个调用点**，别的一行都不用改。

## 一、被改进端要加的四行

```python
from emitter import Emitter                       # 1. 放在目标仓库里，或加 sys.path

E = Emitter(run_dir/"observe/events.jsonl", run_id=RUN_ID)

E.run_start(model=MODEL, budget={"calls": 80, "wall_s": 1200})     # 循环开始前
E.request(messages, system=SYS, tools=TOOLS, images=n_img)          # 调模型前
E.response(finish_reason=fr, content_len=len(text), usage=u)        # 拿到回复后
E.tool_call(call_id, name, args)                                    # 执行工具前
E.tool_result(call_id, status, exit_code, stdout, stderr)           # 执行工具后
E.artifact(path)                                                    # 产物落盘后
E.run_end(reason=...)                                               # 循环结束（异常也走）
```

`Emitter` 是上下文管理器：`with Emitter(...) as E:` 会在异常时兜底写 `run/end`，
并把没有回执的调用补一条 `status="missing"` —— 这就是「调用成对」的机械保证。

## 二、bb6 怎么接

bb6 的模型流量已经有代理（`/root/bb6trace_proxy.py`, :8901），但代理**看不到工具执行**，
所以 tool 事件必须在 bb6 自己的工具层打。

```
① 模型层：代理里把 request/response 两条改调 E.request/E.response（或保留代理，另起一个消费端）
② 工具层：bb6 执行工具前后各一行 E.tool_call / E.tool_result  ← 关键，代理补不了
③ 产物层：写完文件调 E.artifact(path)
④ 起跑：把 run_dir 通过环境变量 RSI_RUN_DIR 传进去
```

## 三、VH 怎么接

VH 的入口是 `vrs_skills`（目标仓库，路径见该项目的目标记忆）：

```
① 入口包一层：起跑时 E = Emitter(run_dir/"observe/events.jsonl", run_id=...)；结束 E.run_end
② 模型调用点：reflect.py 里调模型前后各一行
③ 工具点：读帧 / 读 GT / 写结果的前后各一行（这三处正好是"回执缺落点"高发区）
④ 产物：每题的 result.json 调 E.artifact
```

## 四、跑一次

```bash
python scripts/run_target.py targets/vh.json --run-dir runs/20261110-vh-a
python scripts/run_target.py targets/bb6.json --run-dir runs/20261110-bb6-a
```

它做四件事：冻结三类 hash → 按配置执行 → 事件流过 `check_trace` → 打印
「这次的数据能支持什么结论」（含 n<19 不能做显著性这条）。

## 五、边开发边收敛怎么落

每跑一次，除了读数，还顺手产出三样收敛证据：

```
① 哪些机制 fire 了      数 events 里的事件类型，没 fire 的记 0
② 哪些断言有了反例      失败签名分布
③ 哪些条目该并/该删     喂进 archive_db（trial 行）
```

所以"接管"不是先接完再用，而是**每接一个调用点，就有一项 `[实验]` 从「没上场」变成「有读数」**。
当前状态：12 项全部 `[实验]` 未接（批 1 实测）。
