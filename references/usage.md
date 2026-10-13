# story-machine 调用详解

## 架构速览（写给调用它的 agent）

- 协作范式：动态嵌套求助 + 业务持久化调用栈。没有固定编排器：
  story 求 writer，writer 内部再求 character→conflict→technique→outline，
  story 再求 reviewer→validator。每个求助是一帧落盘 JSON。
- 帧在 `work/stacks/<frameId>.json`，日志在 `logs/supervisor.jsonl`，
  经验库在 `memory/knowledge/{timings.json,routes.jsonl}`。

## 写作链路

```
story ─help→ writer ─help→ character → conflict → technique → (sequence) → compose
      ─help→ reviewer ─help→ validator
```

technique 输出的 `sequence` 决定 writer 后续求助谁——这就是"写法驱动调用拓扑"。

## 调色板

写法 PALETTE：chronological / in_medias_res / flashback / frame_narrative /
parallel / circular / epistolary / incremental
文体 FORM_PALETTE：fable / prose / microfic / poem / gatha / myth

`--genre` 是 genreHint，LLM 可推翻。被 writer 自检或 reviewer 否决的
写法/文体进入 rejected 黑名单，story 自动回退重选（默认上限 2 次）。

## 故障排查

| 现象 | 处理 |
|---|---|
| `LLM provider 未配置` | 跑 `doctor`；注入 env 或写 `config/.env` |
| run 中途被杀 | `resume <runId>`；帧落盘可从断点续跑 |
| writer stage=failed, error 含 JSON | LLM 输出格式错误（已自动重试一次）；重跑即可 |
| techniqueRetries 用尽 | 所有候选写法均被否，换主题或手动调 `--genre` |
| validated=false | 看 `answer.validation.checks` 哪项 false；circular/诗体已豁免 |

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| --theme | 必填 | 主题/道理（原文进入正文回声检查） |
| --genre | 寓言 | 文体倾向 hint |
| --length | 500 | 目标字数（软约束） |
