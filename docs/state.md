# 状态台账：改了要重新验证的沉底事实

> 适用：想知道「哪些结论是实测过的、用什么口径量的、下一步该等什么」时。
> 不适用：日常进度（做完/在做/卡在哪）→ `PROGRESS.md`，那里才是唯一进度源；本文件只放**沉底事实**。
> 过期条件：对应改动被回滚、或样本口径重新算过后；旧数字一律标日期，别混用。
> 来源：原 `AGENTS.md` §6（2026-10-31 拆分时 PROGRESS.md 里没有的部分全部搬到这里），加上原 §7 维护规矩里的事实性内容。

## 机制层：已实测通过

闸门矩阵 **9/9** 通过（`make probe`；用例：节拍 100/0、表情包 100/0、两者组合、`enabled=false` 下节拍仍活、`sources` 过滤、子代理豁免、custom 注入、roll-log 落盘）。

2026-10-30 第二轮改动已落地，单测 **38 个全绿**：

- roll-log 记 `session_id` + `early`；
- 测量脚本按会话精确归属并打对账行；
- 节拍指令 5 套说法随机取一条（`chance.BEAT_CONTEXTS` / `pick_beat()`）；
- 会话前两轮强制命中（`should_fire_beat(early=True)`，概率 0 仍算关）；
- `/whalechan sync` 不再抢 `display.personality`；
- 结构化（dict）人设拒绝覆盖。

## 行为层：还没攒够样本

新代码 13:33 才上桌。判据仍是 `roll-log.jsonl` 里出现带 `session_id` 的新行 → 说明桌面/网关都跑新模块了。

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

## 这些数字从哪来

2026-10-31 补齐五子系统（`pyproject.toml` / `.python-version` / `Makefile` / `PROGRESS.md` / `scripts/probe_gates.py`）后，**`make check` 是唯一验收入口**：上面说的 38 个单测、9/9 闸门都在它里面，别再引用某次手跑的零散输出。

改动如果动了 `chance.py` 的常量，`make test` 会第一时间红——那些数字是锚，不是估计。

## 关联

- 人设为什么会衰减、宿主闸门怎么设计、怎么量：skill `llm-agent-behavior-tuning`（另有 `references/host-gate-verification.md`、`references/persona-drift-measurement.md`）。
- personality 拼在 system prompt 哪个位置、插件钩子怎么接：`/home/ubuntu/docs/hermes-internals.md` §1。
