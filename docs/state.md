# 状态台账：改了要重新验证的沉底事实

> 适用：想知道「哪些结论是实测过的、用什么口径量的、下一步该等什么」时。
> 不适用：日常进度（做完/在做/卡在哪）→ `PROGRESS.md`，那里才是唯一进度源；本文件只放**沉底事实**。
> 过期条件：对应改动被回滚、或样本口径重新算过后；旧数字一律标日期，别混用。
> 来源：原 `AGENTS.md` §6（2026-10-31 拆分时 PROGRESS.md 里没有的部分全部搬到这里），加上原 §7 维护规矩里的事实性内容。

## 机制层：已实测通过

### 2026-11-01 第六轮：长会话「内心戏」衰减的真伪与对症

**先证伪了自己的怀疑**：drift 的 `INNER` 正则只认 `（内心` / `（尾巴` / `（鳍` / `（筷子` / `尾巴尖` / `鳍抖`，看着像口径窄造成的假衰减。用探针（`~/.hermes/cache/scratch/probe_inner_metric.py`，同一批 393 回合）换三种口径重算，**曲线形状一样**，所以衰减是真的：

| 轮次段 | 回合 | 口癖 | A 原口径 | C 动作词宽口径 | B 任意括号 |
|---|---|---|---|---|---|
| 1-2 | 97 | 74% | 53% | 60% | 92% |
| 3-5 | 95 | 62% | 52% | 59% | 99% |
| 6-10 | 87 | 55% | 49% | 52% | 99% |
| 11-20 | 95 | 53% | 39% | 44% | 98% |
| 21+ | 19 | 53% | 16% | 26% | 100% |

B 口径（任意短括号）没有信息量：≥6 轮的 201 个回合里 115 个「有括号但不算内心」，绝大多数是技术性括号（`（pid 862790）`、`（默认 0.3）`）。**别用 B 口径判断人设**。

**对症：只改 `suffix.md` 措辞，不动架构**。关键是锚点换到了历史数据里真实出现过的位置——`[进度]` 行内挂动作（样本里 `[进度] 修完了（尾巴甩了一下）…` 这种写法本来就是自然写法，占命中样本的大头）。第一版措辞（只说「第一段正文开头」）**端到端第一次就失败**：那轮正文一个括号动作都没有。第二版把进度行示例本身改成带动作、把位置写成 ① 进度行 ② 第一句正文 ③ 闲聊结尾，自查改成「回第一句改，别在结尾硬补」，端到端第二轮通过（`（内心：真要说它是「大文件」…）`）。顺带把 `AGENTS.md` 承诺了但 Makefile 里不存在的 `make apply` 补成真实 target（部署走它，仍不进 `check` 链）；`plugin.yaml` 升到 `0.5.3`。

闸门矩阵 **9/9** 通过（`make probe`；用例：节拍 100/0、表情包 100/0、两者组合、`enabled=false` 下节拍仍活、`sources` 过滤、子代理豁免、custom 注入、roll-log 落盘）。节奏骰没有独立的探针用例，靠 `roll-log` 的 `rhythm` 字段 + `tests/test_chance.py` 的 `RhythmTest` / `RhythmVariantTest`（11 个）覆盖。输出侧 MEDIA 钩子由 `tests/test_media_hook.py` 的 23 个用例覆盖（`SplitGluedMediaTest` 18 / `TransformHookTest` 4 / `RegisterTest` 1）。

2026-11-01 第五轮改动（外部复审后加固），单测 **74 个全绿**（69 → 74）：

- 旧版 marker（0.4.x 写的，没有 `carrier` 字段）不再被误判成「用户删过人设」——否则从 0.4 升级上来的机器永远装不上；
- `apply.py` 改走 `persona.bootstrap(force=True)`：别人的 SOUL.md 现在判 `refused`（exit 3，什么都不动），也不再顺手清掉别人的 `display.personality` 和手写的结构化人设；
- MEDIA 钩子加右边界（`roll-log.jsonl` 不会再被拆成 `roll-log.json` + 残留 `l`），并跳过代码块 / 行内代码；
- 「SOUL.md 每轮重读」的说法是错的，实际是**每会话拼一次**（`agent/system_prompt.py:804-807`）、子代理 `skip_soul=True` 不带（`tools/delegate_tool_progress.py:208`）；文档全线更正；
- `plugin.yaml` 升到 `0.5.2`。

2026-11-01 第四轮改动已落地，单测 **69 个全绿**（50 → 69）：

- 新增 `transform_llm_output` 钩子（`_GLUED_MEDIA_RE` / `_split_glued_media()` / `_on_transform_llm_output()`），修模型把 `MEDIA:` 路径和下一句话写在同一行的老毛病；
- 端到端验证过：让模型「原样输出」一行粘连文本，会话库 `messages.content` 里存成 `…webp\n\n进度小结`；
- `plugin.yaml` 升到 `0.5.1`，`provides_hooks: [pre_llm_call, transform_llm_output]`。

2026-11-01 第三轮改动，除测试数外仍然成立，单测 50 个（39 → 50，新增 11 个节奏用例）：

- 人设载体从 `agent.personalities.whalechan` 换成 `~/.hermes/SOUL.md`；
- 新增节奏骰（`chance.RHYTHM_CONTEXTS` / `pick_rhythm()` / `should_fire_rhythm()`），默认 85%；
- `roll-log` 每条多一个 `rhythm` 字段。

补测时抓到两个真缺陷：`RHYTHM_CONTEXTS` 第 3 条漏写三段名、第 5 条没写 `[进度]` 字面格式——模型只能照字面抄，漏了就自己发明小标题。

2026-10-30 第二轮改动，除上面节奏相关的部分外仍然成立：

- roll-log 记 `session_id` + `early`；
- 测量脚本按会话精确归属并打对账行；
- 节拍指令 5 套说法随机取一条（`chance.BEAT_CONTEXTS` / `pick_beat()`）；
- 会话前两轮强制命中（`should_fire_beat(early=True)`，概率 0 仍算关）；
- `/whalechan sync` 只写 `SOUL.md`，不碰 `display.personality`；
- 结构化（dict）人设拒绝覆盖。

## 行为层：还没攒够样本

网关侧已确认跑新模块：重启后 `roll-log.jsonl` 的新行都带 `"rhythm": true`，探针文本里能看到 `🧭 本轮节奏`。**桌面侧还是旧代码**，要重启 `hermes-dashboard` 才算全量上桌。

**下一步**：攒到约 **262** 个带日志的回合再跑 `scripts/measure_persona_drift.py`（`make drift`）。

样本量口径（按**少数派臂**算，总回合 = 每臂需求 / min(命中率, 1−命中率)）：节拍 70% 时 α=0.05 / power=0.8 分清 20pp 要每组约 **197**、总约 **393**；55% 时总约 **262**。

早先写的「总约 214」是按命中组当短板估的，算错了，别再用。也别再用「约 200」这个模糊值。

**拿到的是混合基线，不可信**：「节拍上线前」+「旧代码期」两批日志，24 会话 148 回合，1–2 轮口癖 73%、内心 44%、两者 37%；21+ 轮全 0%；配对 73% → 20%。旧代码不写 `early`、也没有 `session_id`，6 条日志只能按时间兜底归属 6 个回合 —— **这两批日志的 A/B 不可信**。

## 本机私有内容：不 push

- 2026-10-30 13:45：`plugins/whalechan/persona/user.md` 已填本地私人设定（称呼约定，具体内容不写在这里），personality 3758 字。**用户明确要求这条只在本地、不 push 到公开仓库**，所以 `user.md` 长期保持 `M` 未提交状态，别顺手 `git add`。
- 同日：运行时 `config.json` 的 `custom` 已清空（原来跟 `user.md` 重复注入同一句称呼，两处叠加）。今后称呼类长期设定只写 `user.md`；`custom` 留给临时试验。
- 2026-10-31：`571710b` 曾把 `user.md` 一起提交，**违反上一条**。当天已重置重拆（起点 `fe48782`）并推送 `b7d31a2` 剔除该文件，另 `git update-index --skip-worktree plugins/whalechan/persona/user.md` —— 本地改动不会被 `git add .` 带走。
  **push 前固定动作**：

  ```bash
  git diff origin/main..HEAD --name-only | grep persona/user.md   # 必须为空
  ```

  `backup/pre-rebuild-edc0e76` 分支里仍有旧版 `user.md`，别 `push --all`。

- 2026-11-01：**更正上两条**——`user.md` 其实一直待在库里并随 `origin/main` 公开（由 `87becc9` + `251f0b5` 引入，`git ls-tree origin/main` 可见，blob `fa32d72c`，仓库 PUBLIC）。`.git/info/exclude` 对**已追踪**文件无效，`skip-worktree` 只挡本地改动、不挡已推内容，所以那套「三层防护」有一层是空的。当天按用户拍板走方案②：`git rm --cached plugins/whalechan/persona/user.md` + 写进 `.gitignore`，工作区文件保留，**只挡以后**；历史里那四行仍在 GitHub 上。顺带核实：**`docs/` 四篇也从来都在库里**，别以为被 exclude 挡住了。另外 `git rm --cached` 遇到 `skip-worktree` 位会被 git 误判成 sparse 路径而拒绝，得先 `git update-index --no-skip-worktree` 再删。

## 这些数字从哪来

2026-10-31 补齐五子系统（`pyproject.toml` / `.python-version` / `Makefile` / `PROGRESS.md` / `scripts/probe_gates.py`）后，**`make check` 是唯一验收入口**：上面说的 74 个单测、9/9 闸门都在它里面，别再引用某次手跑的零散输出。

改动如果动了 `chance.py` 的常量，`make test` 会第一时间红——那些数字是锚，不是估计。

## 关联

- 人设为什么会衰减、宿主闸门怎么设计、怎么量：skill `llm-agent-behavior-tuning`（另有 `references/host-gate-verification.md`、`references/persona-drift-measurement.md`）。
- personality 拼在 system prompt 哪个位置、插件钩子怎么接：`/home/ubuntu/docs/hermes-internals.md` §1。
