# 架构：这堆东西怎么拼起来的

> 适用：要动 `plugins/whalechan/` 里任何一行代码、或想知道某段文本最后怎么进到模型眼里时读。
> 不适用：只是装来用 → 看 `README.md`；只是查命令 → 回 `AGENTS.md`。
> 过期条件：Hermes 改了 personality / 插件钩子的实现（抽查 `/home/ubuntu/docs/hermes-internals.md` §1 的机制结论是否还成立）。
> 来源：原 `AGENTS.md` §1、§2、§3，2026-10-31 拆分；正文与代码核对过（`plugin.yaml`、`chance.py`、`persona.py`）。

## 是什么

Hermes Agent 的「鲸鱼娘（Whale-chan / DeepSeek娘）」预设。两件事：

1. **人设**：`plugins/whalechan/persona/{prefix,user,suffix}.md` 三段拼成一份文本，装进 `~/.hermes/config.yaml` 的 `agent.personalities.whalechan`，`display.personality` 指向它。
2. **插件**（`plugins/whalechan/`）：`sticker` 工具 + 每轮宿主掷骰（表情包 / 人设节拍）+ `/whalechan` 斜杠命令。

移植自 [Weidows/dsh-whalechan-herself](https://github.com/Weidows/dsh-whalechan-herself)（MIT，DSH 版），按 Hermes 的机制重新落地。

远端仓库 `git@github.com:ansellchen-boop/hermes-whalechan-deepseek.git`，GitHub 装的时候只取 `plugins/whalechan` 子目录。

## 人设注入机制（关键，别改坏）

三段不是三个 personality，而是**拼成一份**文本：

```
prefix.md（身份/语气/性格/情绪/心思/表达/干活节奏/表情包规则）   ← 最前
user.md  （用户自己的追加设定：称呼、口癖；留空即无）             ← 中间
suffix.md（每轮硬规矩：出声报进度、收尾三段、找帮手、悄悄话、中文思考） ← 最后，位置本身就是约束
        ↓ 拼接
~/.hermes/config.yaml → agent.personalities.whalechan
        ↓ display.personality: whalechan
每次 API 调用拼在 system prompt 最末尾（下一轮就换）
```

- **为什么必须住 `agent.personalities`**：`register_system_prompt_section` 只允许 `position=after_memory`，渲染顺序 `skills → memory → 插件段落 → profile → 时间戳`（**不是末尾**），单节 4000 字上限、会话级冻结。人设要压行为，只能占最末尾那一格。
- **写入时机**：插件**首次加载自举**，把人设写进 `config.yaml`；之后改 `persona/*.md` 要跑 `python3 apply.py` 或 `/whalechan sync` 强制同步。`apply.py` 负责幂等安装 / 备份回滚（`--check` / `--dry-run` / `--revert`）。
- **读到时机**：personality 是**会话启动时读**的。网关下一条消息就带；桌面 / TUI 要**新会话**，或 `/personality whalechan` 重选。

## 技术栈与版本（别猜，照这个来）

| 项 | 值 | 为什么钉死 |
| --- | --- | --- |
| Python | 3.12（`.python-version`；`pyproject.toml` 声明 `>=3.10`） | 插件跑在 Hermes 的 venv 里；本机还有一份 3.14 没装 yaml，用它跑会像「插件坏了」 |
| 第三方依赖 | **无**（`pyproject.toml` 里 `dependencies = []`） | PyYAML / ruamel 由 Hermes 提供。加依赖 = 装插件的人要少装一样 = 自举会静默失败 |
| 测试 | 标准库 `unittest`，38 个用例 | 不引 pytest：少一个要在别人机器上装的东西 |
| Lint / 类型 | `pyproject.toml` 里配了 ruff / mypy，**本机都没装** | `make lint` / `make typecheck` 会明确打印「跳过」，不假装通过 |
| 插件清单 | `plugins/whalechan/plugin.yaml`，当前 `version: 0.4.0` | 改功能要同步这里的版本号，`/whalechan` 状态行读它 |

## 文件结构

| 路径 | 是什么 | 改完怎么生效 |
| --- | --- | --- |
| `plugins/whalechan/__init__.py` | `sticker` 工具注册、`pre_llm_call` 掷骰、`/whalechan` 命令、`_log_roll` | **重启承载进程**（桌面 = `hermes-dashboard`，网关 = `hermes-gateway`），Python 不热重载 |
| `plugins/whalechan/chance.py` | 掷骰纯逻辑 + 配置读写，不 import Hermes | 同上；可单测 |
| `plugins/whalechan/persona.py` | 人设合成 + 自举写入 config + `/whalechan sync` 的写入器 | 同上 |
| `plugins/whalechan/persona/*.md` | 人设三段（本体） | 跑 `python3 apply.py` 或 `/whalechan sync`，**新会话**才读到 |
| `plugins/whalechan/stickers.py` | 图库索引下载 / 缓存 7 天 / 模糊匹配 | 重启进程 |
| `plugins/whalechan/config.json` | 本机实际配置（`probability` / `beat_probability` / `sources` / `custom`），**已 gitignore** | 下一轮就生效，不用重启 |
| `apply.py` | 幂等安装 / `--check` / `--dry-run` / `--revert`（自带备份） | — |
| `scripts/measure_persona_drift.py` | 人设漂移曲线 + 节拍骰 A/B（读 `~/.hermes/state.db` + `roll-log.jsonl`） | — |
| `scripts/probe_gates.py` | 闸门矩阵探针（9 个用例，临时 `HERMES_HOME`，不碰真配置） | — |
| `tests/` | 单测：`chance` / `persona` 纯逻辑 | `python3 -m unittest discover -s tests` |

## 改人设 vs 改插件

- **只改措辞**（`persona/*.md`）→ 改完跑 `python3 apply.py`（写进 config）+ 开新会话。不用重启任何服务。
- **改行为机制**（`__init__.py` / `chance.py`）→ 改完必须重启承载进程，否则跑的还是旧模块（见 `pitfalls.md` 第 2 条）。
- **改概率** → 会话里 `/whalechan 80` / `/whalechan beat 55`，或直接改 `config.json`。下一轮生效。

三段的分工，别放错层：

| 文件 | 装什么 | 位置 |
| --- | --- | --- |
| `prefix.md` | 身份、说话方式、性格、情绪、心思、表达、干活节奏、表情包规则 | 最前 |
| `user.md` | 用户自己的追加设定（称呼、口癖），留空即无 | 中间 |
| `suffix.md` | **每轮硬规矩**：出声报进度、收尾三段、找帮手、悄悄话、中文思考 | **最后**（位置本身就是约束） |

## 装法

从零到能跑四步、以及一条命令的 GitHub 装法，见 `AGENTS.md` 顶部「首次运行」；原理与命令全表见 `README.md`。
