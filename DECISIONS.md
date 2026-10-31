# DECISIONS —— hermes-whalechan-deepseek

> 只记「什么决策、为什么、什么时候」，不写设计文档。想看机制细节去 `docs/architecture.md`，
> 想看当前进度去 `PROGRESS.md`。
> **什么时候写这里**：改了对外行为、换了实现路线、否决过一个看起来更简单的方案 —— 三者任一即写。
> 不写：纯重构、改名、格式化。
> 最后更新：2026-10-31

格式：日期 / 决策 / 原因 / 否决了什么 / 由此带来的约束。原因和否决方案是这两栏的价值所在，别省。

---

## 2026-10-29 人设住 `agent.personalities.whalechan`，不用插件系统提示段

- **原因**：`register_system_prompt_section` 只允许 `after_memory` 位置（`hermes_cli/plugins_dispatch.py:98`），渲染顺序是 `skills → memory → 插件段落 → profile → 时间戳 → 环境提示`，**不在末尾**；单节上限 4000 字（人设当时 3471 字），docstring 明确写「会话级冻结」。而 `personalities.<name>` 是 API 调用时拼在 system prompt 最末尾（`agent/turn_context.py:1354-1356`）。
- **否决**：用插件 `register_system_prompt_section` 加人设；用 `pre_llm_call` 返回 `{"context": ...}` 改行为（那拼进的是 **user message**，`agent/turn_context.py:803-805`）。
- **约束**：`agent.personalities` 会覆盖顶层 `personalities`（`hermes_cli/personality.py`）；人设改了要新开会话才生效。

## 2026-10-31 行为衰减靠宿主闸门，不靠继续加提示词

- **原因**：实测 126–137 个回合，口癖率 1–2 轮 76% → 21+ 轮 0%，内心戏 39% → 0%；同期**有宿主骰子的表情包** 61%→86% 完全不退。差距不在提示词，在「有没有一个外部信号每轮强制提醒」。
- **否决**：只改措辞（试过，只能延后一两轮）；只加 few-shot 例子（被历史自身的措辞覆盖）。
- **约束**：节拍骰 **故意不看 `enabled`**，只认 `beat_probability` 和 `sources` —— 关插件不该顺带关人设节拍。

## 2026-10-31 「悄悄话」从「宁可空着」改成「至少一处」

- **原因**：原文写「一轮最多两处……宁可空着」，等于给模型留了合法省略的借口。模型在长对话里会挑最省力的读法。
- **否决**：保持原措辞、只靠节拍骰兜。措辞和闸门是两件事，都得到位。
- **约束**：改完要 `make apply-check`，确认仓库与 `~/.hermes/` 副本一致。

## 2026-10-31 `persona/user.md` 不入库

- **原因**：填的是私人设定（称呼约定）。公开仓库不该承载这些。
- **否决**：把私人称呼写进 `prefix.md`/`suffix.md`（那两篇是入库文件）。
- **约束**：三层防护 —— `git update-index --skip-worktree`（`git ls-files -v` 显示 `S`）、`.git/info/exclude`、提交前 `git diff --cached | grep` 私人称呼应为 0。备份分支 `backup/pre-rebuild-edc0e76` 里仍有旧版，**别 `push --all`**。

## 2026-10-31 `docs/` 用文件级时效声明，不逐条标三件

- **原因**：全仓 53 条真指令里 38 条缺「来源/适用/过期」，但其中大半是技术事实而非可执行指令（「`base_url` 必须连 `api_key` 一起给」是防 401 的事实）。逐条挂三件会把排障手册变成表格，可读性赔光。
- **否决**：所有文档一条一条标来源；只标入口硬约束、docs 完全不标（那样文档过期没人发现）。
- **约束**：入口硬约束逐条标（已 100%）；`docs/*.md` 每篇顶部四行 `适用 / 不适用 / 过期条件 / 来源`；归档篇标「过期条件：无（冻结）」。

## 2026-10-31 `make audit` 单独成 target，不并进 `make check`

- **原因**：审计慢（扫三份入口 + 12 篇文档）、会写 `~/.hermes/cache/audit/history.jsonl`，属于体检不属于构建。并进 `check` 会让「三秒跑完」的承诺失效，人就不跑了。
- **否决**：并进 `check`。
- **约束**：退出码 0 全绿 / 1 有硬失败 / 2 只有警告；周更 cron `6e4bbfb9ae63` 每周一 9:00 兜底。

## 2026-10-31 复审用 GLM 直连 API，不动 Hermes 的 review 槽位

- **原因**：`auxiliary.review` 与 `delegation` 都钉在 kimi-coding/k3.1-pro，改配置要重启 gateway，代价大于一次性复审的收益。
- **否决**：改 `config.yaml` 的 review 槽位；继续等 Kimi 额度（试过，429 五小时限额，602 秒白烧）。
- **约束**：资源包**只覆盖 `glm-5.3` / `glm-5.3-flash` / `glm-5.3-flashx`**（其余模型返回 `1113 余额不足或无可用资源包`）；该系列默认开思考且不认 `thinking` 参数，**必须流式**，否则 read timeout 掐死。脚本在 `~/.hermes/cache/scratch/glm_review2.py`。

## 2026-10-31 提交按原子单元切；重拆时 `git reset --soft` 到真实远端 tip

- **原因**：第一次重拆把起点当成 `ab1c89b`，真实远端 tip 是 `fe48782`（它是 `571710b` 的父），reset 吃掉了它的边界，push 被拒 `non-fast-forward`。
- **否决**：`git rebase -i`（改动散在多个原始 commit 的同一批文件里，交互式拆分更容易切错）。
- **约束**：重拆前先 `git fetch && git rev-parse origin/main` 拿真实 tip；切完用 `git diff <原HEAD> HEAD` 必须为空来证明树没变。

## 2026-10-31 `make lint` / `make typecheck` 没装工具时跳过而非失败

- **原因**：验证命令必须真能跑。留一条永远红的命令，人就会开始无视所有红。
- **否决**：把 ruff/mypy 塞进 `dependencies` 强制安装（本机两个都没装，装了也得先确认 Python 版本兼容）。
- **约束**：跳过时**打印「跳过」并说明**，不静默。

## 2026-10-31 状态文件不写死自己的 commit hash

- **原因**：找个没上下文的子代理照「上班」流程（当时四步，现在是五步）实测，它照着 `PROGRESS.md` 报「最新 commit `b31193e` 已推」，而写这一行的提交本身是 `7a0b86b`、且没推 —— 文档在生成的那一刻就过期了。流程里没有任何一步回读远端，所以照文档走完全程也发现不了，只有额外跑 `git ls-remote` 才抓得住。
- **否决**：commit 之后 `git commit --amend` 把 hash 补进去（破坏原子性，且 amend 后 hash 又变了，循环）；提交完再补一个小提交更新 hash（提交数翻倍，且第二次写完又滞后）。
- **约束**：`PROGRESS.md` 的「当前状态」只写**上次验证的时间 + 测试结果**，要看当前 commit 一律现场跑 `git log --oneline -1 && git status -sb`。上下班流程的「上班」第 3 步就是这条命令，不许信文档里的 hash。

## 2026-10-31 判据按命令的真实输出写，不按概念写

- **原因**：我写「判据 = `apply.py --check` ✓」，而 `make check` 的真实输出里**没有 `apply.py` 字样**（那一行叫 `✓ 已是最新`）；又写「闸门 9/9」，实际输出是 `9/9 通过`。照字面 grep 判绿，永远判红。这种错比结论写错更阴 —— 它长得最像「有据可查」。
- **否决**：写「测试通过、闸门通过、人设一致」这类概念性描述（人读了懂，脚本判不了，等于没判据）。
- **约束**：判据一律抄命令的原始输出行，判据里出现的每个字符串都要能在终端里 `grep` 到。测试条数不写死（写 `OK`/0 失败），因为加删测试后条数会变。
