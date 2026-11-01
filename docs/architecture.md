# 架构：人设怎么进模型，插件补哪一段

> 适用：要动插件代码、想知道人设怎么进 system prompt、三条骰各管什么。
> 不适用：改完怎么验证 → `verify.md`；踩过的坑 → `pitfalls.md`。
> 过期条件：宿主换身份注入机制（SOUL 不再走 identity slot），或骰子模型重构成统一闸门。
> 来源：2026-11-01 人设从 `agent.personalities.whalechan` 迁到 `SOUL.md` 时整篇重写；依据 `agent/prompt_builder.py` 的 identity slot 与 `cron/scheduler.py` 显式 `load_soul_identity=True`。

## 一句话

人设（前缀 + 称呼 + 硬规矩）合成一份文本，写进 `~/.hermes/SOUL.md`；
插件不提供人设文本，只提供「每轮掷骰」和 `sticker` 工具。
config 里**不再有任何** `personalities.whalechan` / `display.personality`。

## 为什么从 config 搬到 SOUL.md

| | `agent.personalities.whalechan`（0.4.x） | `SOUL.md`（0.5.0+） |
|---|---|---|
| 注入位置 | `ephemeral_system_prompt`，system prompt **最末尾** | identity slot，system prompt **第一段** |
| cron / 定时任务 | 不传 | `cron/scheduler.py` 显式 `load_soul_identity=True`，带 |
| 子代理 / 后台 | 多数不传 | 走同一条 `build_system_prompt`，带 |
| 覆盖范围 | 只影响选中的那个会话类型 | 整个 Hermes 进程内所有对话 |

代价是**位置变了**：人设现在在 system prompt 开头，离当前用户消息最远，
长会话里后半段那些「报进度 / 三段小结」的硬规矩容易被稀释。
所以结构性的硬规矩交给插件的**节奏骰**每轮补一句，人设文件里只写「为什么」和「语气」。

## 三段拼接

`plugins/whalechan/persona/` 下三个文件按序拼（`persona.compose()`）：

1. `prefix.md` —— 身份、说话方式、性格、情绪、心思、表达、干活的样子、表情包规则
2. `user.md` —— 称呼等用户追加设定（`老板` / `大肥鱼` / `嘎啦嘛`）
3. `suffix.md` —— 每轮回复的硬规矩（出声、三段小结、找帮手、悄悄话）+ 思考语言

拼完即 `SOUL.md` 全文。改完跑 `python3 apply.py`，或 `/whalechan sync`。

**拼接用 `\n\n` 连接，注释 `<!-- -->` 会被剥掉。**

## 插件做什么

`plugins/whalechan/`：

- **`sticker` 工具** —— 按 scene 从社区图库取图，返回 `MEDIA:/绝对路径`
- **`pre_llm_call` 钩子，三条独立掷骰**（都在 `chance.py` 里，纯逻辑，不 import Hermes）：
  - 🎲 表情包（默认 66.6%）—— 管**发不发图**
  - 🎭 人设节拍（默认 55%）—— 管**嘴在不在**（口癖 + 内心戏/小动作）
  - 🧭 节奏（默认 85%，会话前两轮必中）—— 管**结构在不在**（报 `[进度]` + 收尾三段小结）
- **`/whalechan` 命令** —— 查/改概率、`sync` 重写 SOUL、`custom` 运行时追加设定
- **自举** —— 首次加载时若 `SOUL.md` 还是出厂英文身份，自动写入并清掉 config 旧键
- **`roll-log.jsonl`** —— 每次掷骰一行，含 `beat` / `sticker` / `rhythm` / `early`，给 `scripts/measure_persona_drift.py` 用

三条骰故意分开：图、语气、结构是三个独立维度，捆在一起调一个必然带歪另两个。

## SOUL.md 的三种状态（自举判定）

| SOUL.md 里是什么 | 插件怎么做 |
|---|---|
| 空 / 出厂英文身份（`You are Hermes Agent…`） | 写入人设（`installed` / `updated`） |
| 已经是本预设（含「鲸鱼娘」） | 相同 → `already` 不动；不同 → `drift`，等 `force` |
| 别的内容（既非出厂也不含鲸鱼娘） | `refused`，**`force` 也不覆盖** |

用户手动清空 SOUL.md 之后不会自动装回来（`removed-by-user`），要 `/whalechan sync` 才恢复。

## 文件职责

| 文件 | 管什么 |
|---|---|
| `plugins/whalechan/__init__.py` | 工具注册、钩子挂载、三条骰的调度、`/whalechan` 命令、日志 |
| `plugins/whalechan/chance.py` | 概率与配置读写、骰子逻辑（纯函数，可单测） |
| `plugins/whalechan/persona.py` | 人设合成、SOUL.md 读写、自举、状态查询 |
| `plugins/whalechan/stickers.py` | 图库检索 |
| `plugins/whalechan/persona/*.md` | 人设正文（随插件分发） |
| `plugins/whalechan/config.json` | 运行时概率（gitignore） |
| `apply.py` | 幂等安装：写 SOUL + 清旧键 + 同步插件；`--check` / `--dry-run` / `--revert` |
| `scripts/probe_gates.py` | 闸门矩阵：9 个场景各跑一遍钩子，断言注入文本对不对 |
| `scripts/measure_persona_drift.py` | 从 roll-log 统计掷骰命中率与口吻漂移 |

零第三方依赖，测试用标准库 `unittest`（39 个用例）。

## 生效方式

- **SOUL.md 改动**：网关下一条消息起生效（每次调用重拼）；桌面 / TUI 要新会话
- **插件代码改动**：重启承载进程 —— 桌面 `systemctl --user restart hermes-dashboard`，网关 `hermes-gateway`
- **概率改动**：`/whalechan 80` 立即生效，不用重启
