# 02 观测（G2）

## 两类现场，别混

```
观测面  events.jsonl     被改进端产出     可作归因证据
重建面  rebuilt.jsonl    改进端补写      source=reconstructed，只能提假设
```

## 事件字段（最小集）

```json
{"run_id":"r1","seq":1,"t":1794221368.1,"type":"model/request","payload":{...},"src_seq":null}
```

必填：`run_id` `seq` `t` `type` `payload`。`seq` 严格递增，只追加不改写。

## 类型

```
run/start  block/start  block/end  model/request  model/response
tool/call  tool/result  artifact/write  verify/report  prune  run/end
```

## 三类必须有内容

```
model/request     n_messages、system_sha256、tools 数量、是否带图、图像字节数
model/response    finish_reason、tool_calls 名单
artifact/write    绝对路径、字节数、sha256
```

没有 model/request，就答不了“模型当时看到了什么”——这一条不合格，整层不合格。

## check_trace 判据

```bash
python scripts/check_trace.py runs/<id>/observe/events.jsonl
```

```
① 每行是 JSON 且有五个必填字段
② seq 严格递增
③ type 在允许集合内
④ 至少一条 model/request
⑤ tool/call 与 tool/result 按 call_id 配对；未配对必须显式解释
```

## 重建面纪律

```
① 每条带 source=reconstructed，并写它引用了哪条观测记录
② 归因只能引用观测面；重建面只能进假设档（C 档）
③ 补写者不能同时是判分者
```
