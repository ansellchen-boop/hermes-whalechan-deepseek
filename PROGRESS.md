# PROGRESS —— hermes-whalechan-deepseek

> 给「下一个会话的我」看的。每个会话结束前改这里，开始前读这里。
> 台账细节在 `docs/state.md`；入口规矩在 `AGENTS.md`（后者是本地文档，不进仓库）。这份回答四个问题：**现在什么状态、做完什么、正在做什么、被什么卡着**。决策的「为什么」在 `DECISIONS.md`，别写这里。
> 最后更新：2026-10-31 16:05

## 当前状态

**本节不写死 commit hash** —— 写它的那个提交无法把自己写进去，记了必然滞后一个提交，下一个 agent 照着报错。要看当前在哪：

```bash
git log --oneline -1 && git status -sb    # ahead N = 有未推的
```

- 上次验证（2026-10-31 15:36）：`make check` → `Ran 38 tests OK` + 闸门 9/9 + `apply.py --check` ✓ → `✓ 全部通过`
- 人设：**3785 字符 = `~/.hermes/config.yaml` 的合成串**（口径写清，别拿源文件三篇 2573+156+1055=3784 去比，差的 2 是拼接符），插件差异无
- 指令审计：三份入口全绿，硬约束三件缺 0 条，`docs/` 缺声明 0 篇
- 观察期样本：`roll-log.jsonl` 93 行、带 `session_id` 87 行（目标 260）

## 已完成

- [x] 人设三段（prefix / user / suffix）合成写入 `agent.personalities.whalechan`，`apply.py` 幂等安装 / `--check` / `--revert`
- [x] `sticker` 工具 + 图库索引缓存（7 天）+ 模糊匹配
- [x] `/whalechan` 命令：概率 / 开关 / 追加设定 / sync / beat
- [x] **人设节拍骰**（`beat_probability`，默认 55）：宿主每轮独立掷骰，命中往 user message 塞 🎭 行。这是解决「跑几轮就变客服」的主手段
- [x] 悄悄话措辞从「最多两处、宁可空着」改成「至少一处、最多两处」，堵掉模型拿"可以省略"当借口的读法
- [x] 头两轮立锚 + 会话前两轮强制命中（`should_fire_beat(early=True)`）
- [x] `roll-log.jsonl` 命中日志（带 `session_id` / `early`）+ `scripts/measure_persona_drift.py` 测量脚本（分桶曲线 / 配对 / 表情包对照 / 节拍 A/B）
- [x] 单测 38 个全绿；闸门矩阵 9/9
- [x] 已推 GitHub `main`：`b7d31a2` → `caae43e`（docs 四篇入库）→ `b31193e`（指令审计脚本），每次都做匿名 `ls-remote` 回读，与本地 HEAD 一致
- [x] 独立复审（glm-5.3-flash 直连，只读，无执行权限）：裁决「有条件通过」，7 条指控核实 6 条属实；已按意见重拆 commit 并收掉小修
- [x] 五子系统补齐（2026-10-31）：`pyproject.toml` / `.python-version` / `Makefile`（`make check` 一条命令）/ `PROGRESS.md`（本文件）/ `scripts/probe_gates.py`（闸门矩阵探针，9/9）；AGENTS.md 加技术栈版本表、验证命令表、§8 文档索引

## 正在进行

- [ ] **观察期攒样本**：判据是 `~/.hermes/plugins/whalechan/roll-log.jsonl` 里出现带 `session_id` 的新行（= 桌面和网关都跑新模块了）
- [ ] 目标样本量：约 260 个带日志的回合（55% 命中率下，α=0.05 / power=0.8 分清 20pp 所需）
- [ ] 到量后跑 `make drift`，看「节拍命中轮 vs 未命中轮」的口癖率差

## 被阻塞 / 等拍板

- 备份分支 `backup/pre-rebuild-edc0e76` 里存着旧版 `user.md`（含私人称呼），**别 `push --all`**。确认历史没问题后可删（reflog 和 `edc0e76` 这个 hash 还能兜底）。
- 无硬阻塞。
- 待用户决定：① 要不要上方案 C（`agent/context_compressor.py` 的摘要模板加 `## Voice & Style`，需写成幂等 `apply.py` 补丁，`hermes update` 后要重跑）；② 两个测试会话要不要删（`local-8a298a43…`、`local-981e321c…`）。

## 下一步 / 开工顺序

1. `make check` —— 三秒确认地基没塌
2. `wc -l ~/.hermes/plugins/whalechan/roll-log.jsonl` —— 看样本攒到哪了
3. 读本文件「正在进行」+ `docs/state.md`（样本量与判据口径）
