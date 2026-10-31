# PROGRESS —— hermes-whalechan-deepseek

> 给「下一个会话的我」看的。每个会话结束前改这里，开始前读这里。
> 台账细节在 `AGENTS.md` §6；这份只回答三个问题：**做完什么、正在做什么、被什么卡着**。
> 最后更新：2026-10-31 14:10

## 已完成

- [x] 人设三段（prefix / user / suffix）合成写入 `agent.personalities.whalechan`，`apply.py` 幂等安装 / `--check` / `--revert`
- [x] `sticker` 工具 + 图库索引缓存（7 天）+ 模糊匹配
- [x] `/whalechan` 命令：概率 / 开关 / 追加设定 / sync / beat
- [x] **人设节拍骰**（`beat_probability`，默认 55）：宿主每轮独立掷骰，命中往 user message 塞 🎭 行。这是解决「跑几轮就变客服」的主手段
- [x] 悄悄话措辞从「最多两处、宁可空着」改成「至少一处、最多两处」，堵掉模型拿"可以省略"当借口的读法
- [x] 头两轮立锚 + 会话前两轮强制命中（`should_fire_beat(early=True)`）
- [x] `roll-log.jsonl` 命中日志（带 `session_id` / `early`）+ `scripts/measure_persona_drift.py` 测量脚本（分桶曲线 / 配对 / 表情包对照 / 节拍 A/B）
- [x] 单测 38 个全绿；闸门矩阵 9/9
- [x] 推上 GitHub `main`（commit `ab1c89b` 及其后），匿名拉取验证过内容
- [x] 独立复审通过（glm-5.3，逐条复跑验证）

## 正在进行

- [ ] **观察期攒样本**：判据是 `~/.hermes/plugins/whalechan/roll-log.jsonl` 里出现带 `session_id` 的新行（= 桌面和网关都跑新模块了）
- [ ] 目标样本量：约 260 个带日志的回合（55% 命中率下，α=0.05 / power=0.8 分清 20pp 所需）
- [ ] 到量后跑 `make drift`，看「节拍命中轮 vs 未命中轮」的口癖率差

## 被阻塞 / 等拍板

- 无硬阻塞。
- 待用户决定：① 要不要上方案 C（`agent/context_compressor.py` 的摘要模板加 `## Voice & Style`，需写成幂等 `apply.py` 补丁，`hermes update` 后要重跑）；② 两个测试会话要不要删（`local-8a298a43…`、`local-981e321c…`）。

## 下一个会话开工顺序

1. `make check` —— 三秒确认地基没塌
2. `wc -l ~/.hermes/plugins/whalechan/roll-log.jsonl` —— 看样本攒到哪了
3. 读本文件「正在进行」+ `AGENTS.md` §6
