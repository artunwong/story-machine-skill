---
name: story-machine
description: 生成一个中文主题故事（寓言/散文/微小说/诗歌/偈颂/神话 + 多种叙事写法）。Use when Codex is asked to 写故事、写寓言、写微小说、写偈颂、围绕某个道理/主题生成小故事，或续跑/审计 story-machine 的一次运行。
---

# Story Machine

**一句话**：动态嵌套求助架构的中文故事生成器——角色、冲突、写法、文体、提纲、评审全部由 LLM 模块按调用栈协作产出。

## 运行环境（必须先确认）

- **本 skill 必须在 agent session 内由 agent 调用**，不作为独立 CLI 面向最终用户分发。
- 目录即工作根：所有命令以本 SKILL.md 所在目录为 cwd，根状态（`work/stacks`、`logs`、`memory`、`characters`）全部写在 skill 目录内。
- Windows：命令用 `python`；macOS/Linux：用 `python3`。下文统一写 `python`，macOS 请替换为 `python3`。

## LLM 配置（session 负责注入）

`sm3_src/harness/llm.py` 按此顺序取配置：**进程环境变量 > `config/.env`**。

1. 首选：在调用前向环境注入 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`
   （端点需兼容 OpenAI /chat/completions 协议，参考 `config/.env.example`；
   agent 自行决定注入方式：临时 export、或在 `config/.env` 写入一次）。
2. 自检：`python -m sm3_src --root . doctor`——`llm.base/key` 为 true 且
   `dirsWritable` 为 true 才可开始创作；不满足就先把配置补齐，禁止降级跑。

## 核心命令（cwd = skill 根目录）

```bash
python -m sm3_src --root . doctor                       # 环境自检
python -m sm3_src --root . run --theme "主题" \
    --genre 寓言 --length 700                            # 生成一个故事（全程同步等待）
python -m sm3_src --root . resume <runId>               # 中断后续跑
python -m sm3_src --root . stack <runId>                # 查看调用栈
python -m sm3_src --root . audit <runId>                # 离线复盘+知识库更新
python -m sm3_src --root . monitor                      # 体外监控扫描
```

- `--genre` 仅为倾向提示，technique 模块可推翻并在 reason 中说明。
- `run` 输出 JSON：`answer.draft.story` 为正文，`answer.review` 为评审，
  `answer.validation` 为验收；`status: "ok"` 且 `validated: true` 才算成稿。
- 失败返回 `{"status":"failed","answer":{"stage":...,"error":...}}`：
  先 `doctor` 再按 stage 查 `logs/supervisor.jsonl` 与 `work/stacks/<frameId>.json`。

## 输出给用户的约定

把过程产物一并展示：写法/文体选择（technique.reason+form）、人物、冲突、
提纲因果链、评审 8 维分与 issues、验收结果，再给正文。

## 更多说明

- [usage.md](references/usage.md)：调用流程详解、故障排查、参数表
- 模块 BRD（一句话职责、IN/OUT 契约）：仓库内 `docs/brd/`（分发包不含，
  若需嵌入可从仓库复制到 `references/brd/`）

## 边界

- LLM 调用失败不降级、不编造结果；如实返回 failed。
- 不要手工编辑 `work/stacks/*.json`（业务持久化调用栈是权威记录）。
- 新增写法/文体属于调色板扩展，先改 `sm3_src/biz/technique.py` 的
  PALETTE/FORM_PALETTE 并经评审讨论，属 ASK FIRST 级别。
