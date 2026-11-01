# 进度

**最后验证**：2026-11-01 13:46 CST —— `make check` → `✓ syntax` / `Ran 50 tests OK` / `apply.py --check` ✓（人设 3781 = 3781）/ `probe` 9/9 / `✓ 无临时工件` → `✓ 全部通过`；`make audit` → 三份入口全 ✓。

## 当前状态

**0.5.0：人设从 config 搬进 SOUL.md。**

- `~/.hermes/SOUL.md` = **3781 字符**（strip 口径；`wc -m` 报 3782 是因为文件末尾留了一个换行）；prefix 2572 + user 98 + suffix 3091，差值是两个拼接符，首行是「你是「鲸鱼娘」…」
- `grep -n personality ~/.hermes/config.yaml` → **无输出**（`agent.personalities.whalechan` 和 `display.personality` 全清）
- 备份：`~/.hermes/backups/whalechan/state-20261101-134553.json` + `plugin-20261101-134553.tar.gz`（包里含旧 SOUL.md、旧插件全套；`--revert` 一起还原）
- 三条独立骰：表情包 66.6% / 人设节拍 55% / 节奏 85%（会话前两轮必中）
- 人设位置换了：现在在 system prompt **第一段**（identity slot），不在最末尾。代价是离当前用户消息远，所以「报进度 + 三段小结」这类结构性规矩靠节奏骰每轮补，人设文件只写为什么。

## 已完成

- `persona.py` 全量重写：`soul_file()` / `write_soul()` / `read_soul()` / `bootstrap()` 七种 action（installed / updated / already / drift / removed-by-user / refused / failed）/ `status()`
- `chance.py` 加第三个骰子：`DEFAULT_RHYTHM_PROBABILITY = 85.0`、`RHYTHM_CONTEXTS`（5 条变体）、`pick_rhythm()`、`should_fire_rhythm()`
- `__init__.py`：`_on_pre_llm_call` 注入 `🧭 本轮节奏`、`_log_roll` 加 `rhythm` 字段、`/whalechan rhythm N`、docstring 改成 SOUL 口径
- `apply.py`：写 SOUL + 清旧键 + 同步插件；`--check` 判 `soul_same and not legacy_left and not drift`；备份包带 SOUL.md；`--revert` 先还原 SOUL 再还原插件
- `tests/test_persona.py` 重写为 12 个 SOUL 用例（外人文拒绝测试确认 **force 也不覆盖**）
- `tests/test_chance.py` 补 `RhythmTest` + `RhythmVariantTest` 共 11 个（39 → 50）。**补测抓到两个真缺陷**：`RHYTHM_CONTEXTS` 第 3 条漏写三段名、第 5 条没写 `[进度]` 字面格式 —— 模型只能照字面抄，漏了就自己发明小标题
- 文档全线更新：`README.md`（原理对比表 + 命令 + config 示例）、`docs/architecture.md`（整篇重写）、`docs/pitfalls.md` §4/§6/§8、`docs/state.md`（50 测试 + 第三轮事实）、`docs/verify.md`、`AGENTS.md`、顶层 `/home/ubuntu/AGENTS.md`
- `DECISIONS.md` 补 2026-11-01 那条五栏，旧 10-29 那条标注「已被取代」

## 待办

1. **实测口吻——还是没做过。** 上面全是静态验证：测试、闸门矩阵、字数比对。真判据是开一个新会话聊五轮，看是否真的报 `[进度]`、真的收尾三段、语气有没有掉成客服。这是 0.5.0 唯一没有证据的部分。
2. **插件代码改动要重启承载进程才生效。** 桌面 `systemctl --user restart hermes-dashboard`（会掐断当前桌面会话，要先用 `systemd-run --user --on-active=60` 排延迟）；网关 `hermes-gateway`。**当前桌面会话跑的还是 0.4.x 的插件代码**，所以现在跟鲸鱼娘说话，节奏骰是不会注进来的。
3. 观察期样本：目标约 262 个带非空 `session_id` 的回合，到量跑 `make drift` 看节奏骰命中率和口吻漂移。0.5.0 改了口径，之前的样本只能当基线。
4. 本地 15 个文件还没提交（人设、插件、测试、文档一整套）。

## 下一步（新会话开工顺序）

1. 重启 dashboard → 开新会话聊五轮 → 对照 `~/.hermes/plugins/whalechan/roll-log.jsonl` 的 `rhythm` 字段看注入有没有真发生
2. 口吻不对就调 `suffix.md` 措辞或 `rhythm_probability`，别动架构
3. 提交这 15 个文件（`persona/user.md` 仍被 skip-worktree 挡着，别 `git add`）
4. 稳定后再考虑 `agent/context_compressor.py` 摘要模板加 `## Voice & Style`（旧方案 C，仍待决）
