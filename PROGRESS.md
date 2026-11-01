# 进度

**最后验证**：2026-11-01 14:05 CST —— `make check` → `✓ syntax` / `Ran 69 tests OK` / `apply.py --check` ✓（人设 4137 = 4137）/ `probe` 9/9 / `✓ 无临时工件` → `✓ 全部通过`。

## 当前状态

**0.5.1：人设住 SOUL.md，输出侧钩子修 MEDIA 行。**

- `~/.hermes/SOUL.md` = **4137 字符**（strip 口径）；prefix 2572 + user 98 + suffix 3447，差值是两个拼接符
- `grep -n personality ~/.hermes/config.yaml` → **无输出**（旧载体全清）
- 备份：`~/.hermes/backups/whalechan/state-20261101-135817.json` + 同名 `plugin-*.tar.gz`（含旧 SOUL.md，`--revert` 一起还原）
- 三条独立骰：表情包 66.6% / 人设节拍 70%（用户自己调的）/ 节奏 85%（会话前两轮必中）
- 两个钩子：`pre_llm_call`（三条骰往 user message 末尾补料）+ `transform_llm_output`（MEDIA 行粘连兜底）
- 已提交 `6d21eb3 feat(persona): 人设迁到 SOUL.md，结构规矩交给节奏骰`；**钩子这批改动还没提交**

## 已完成

- `persona.py` 全量重写：`soul_file()` / `write_soul()` / `read_soul()` / `bootstrap()` 七种 action（installed / updated / already / drift / removed-by-user / refused / failed）/ `status()`
- `chance.py` 加第三个骰子：`DEFAULT_RHYTHM_PROBABILITY = 85.0`、`RHYTHM_CONTEXTS`（5 条变体）、`pick_rhythm()`、`should_fire_rhythm()`
- `__init__.py`：`_on_pre_llm_call` 注入 `🧭 本轮节奏`、`_log_roll` 加 `rhythm` 字段、`/whalechan rhythm N`、docstring 改成 SOUL 口径
- `__init__.py` 输出侧：`_MEDIA_EXTS` / `_EXT_ALT` / `_TERMINATORS` / `_GLUED_MEDIA_RE` / `_split_glued_media()` / `_on_transform_llm_output()`，`register()` 挂第二个钩子
- `apply.py`：写 SOUL + 清旧键 + 同步插件；`--check` 判 `soul_same and not legacy_left and not drift`；备份包带 SOUL.md；`--revert` 先还原 SOUL 再还原插件
- 测试 **69 个**：`test_persona.py` 12 个 SOUL 用例、`test_chance.py` 50 个（含 `RhythmTest` + `RhythmVariantTest` 11 个）、`test_media_hook.py` 18 个（`SplitGluedMediaTest` 14 + `TransformHookTest` 4）+ `RegisterTest` 1 个验证钩子真挂在 `transform_llm_output` 上
- 文档：`README.md`、`docs/architecture.md`、`docs/pitfalls.md` §4/§6/§8、`docs/state.md`、`docs/verify.md`、`AGENTS.md`、顶层 `/home/ubuntu/AGENTS.md`、`DECISIONS.md`（2026-11-01 五栏，旧 10-29 条标注已被取代）

## 已验证的证据（不是「应该能行」）

1. **节奏骰真的注入了**：重启 gateway 后跑 `hermes chat -q`，`roll-log.jsonl` 每条都带 `"rhythm": true`，探针文本里能看到 `🧭 本轮节奏（宿主自动补的提醒，不是老板说的话）`。
2. **输出侧钩子真的改写了落库文本**：让模型「原样输出」`MEDIA:…/ee244a0cc5a70ccb.webp进度小结`，会话库里存的是 `…ee244a0cc5a70ccb.webp\n\n进度小结` —— 粘连被补成了空行（会话 `local-bc0951ca…`，消息 id 13142）。
3. **SOUL.md 每轮重读**：日志里每次都打 `whalechan: 人设 already（4137 字）`，改人设不用重启。

## 待办

1. **桌面端口吻还没实测。** 桌面会话活在 `hermes-dashboard` 里，重启它才加载 0.5.1；现在这个会话跑的仍是旧代码。判据：新开桌面会话聊五轮，看有没有真报 `[进度]`、真收尾三段。
2. 钩子这批改动要提交（`__init__.py` / `plugin.yaml` / `tests/test_media_hook.py` / 这几份文档）。
3. 观察期样本：目标约 262 个带非空 `session_id` 的回合，到量跑 `make drift`。0.5.x 改了口径，之前的样本只当基线。
4. 测试会话堆积：`local-6403bb0d…`、`local-bc0951ca…`、`local-2d9fd7f7…`、`local-81cf37a1…` 都是我这几次实测建的，要不要删等用户定。

## 下一步（新会话开工顺序）

1. 重启 dashboard（`systemd-run --user --on-active=60 systemctl --user restart hermes-dashboard`，避免掐断手上正在说的话）→ 开新会话聊五轮
2. 口吻不对就调 `suffix.md` 措辞或 `rhythm_probability`，别动架构
3. 提交钩子这批；`persona/user.md` 仍被 `.git/info/exclude` 挡着，别 `git add`
4. 稳定后再考虑 `agent/context_compressor.py` 摘要模板加 `## Voice & Style`（旧方案 C，仍待决）
