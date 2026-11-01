# 进度

**最后验证**：2026-11-01 14:16 CST —— `make check` → `✓ syntax` / `Ran 74 tests OK` / `apply.py --check` ✓（人设 4137 = 4137）/ `probe` 9/9 / `✓ 无临时工件` → `✓ 全部通过`。

## 当前状态

**0.5.2：人设住 SOUL.md，输出侧钩子修 MEDIA 行，外部复审抓到的四个缺陷已修。**

- `~/.hermes/SOUL.md` = **4137 字符**（strip 口径）；prefix 2572 + user 98 + suffix 3447，差值两个拼接符
- `grep -n personality ~/.hermes/config.yaml` → **无输出**（旧载体全清）
- 备份：`~/.hermes/backups/whalechan/state-20261101-141552.json` + 同名 `plugin-*.tar.gz`（含旧 SOUL.md）
- 三条独立骰：表情包 66.6% / 人设节拍 70%（用户自己调的）/ 节奏 85%（会话前两轮必中）
- 两个钩子：`pre_llm_call`（三条骰）+ `transform_llm_output`（MEDIA 粘连兜底，跳过代码块）
- 已提交两笔：`6d21eb3`（人设迁 SOUL）+ `655a3e6`（0.5.1 输出钩子）；**本轮加固还没提交**

## 已完成（第五轮：复审后加固）

- `persona.py` marker 判定加 `carrier == "soul"`：0.4.x 的旧 marker 不再被当成「用户删过人设」。本机 `~/.hermes/plugins/whalechan/persona-state.json` 正好是旧格式（`chars: 3472`，10-29 写的），升级路径曾经是死的
- `apply.py` 的 `install_soul()` 改走 `persona.bootstrap(force=True)`：别人的 SOUL 判 `refused`（exit 3、什么都不动），不再清别人的 `display.personality`、不再删手写的结构化人设；`LEGACY_KEYS` 常量随之删掉
- `__init__.py` 的 `_GLUED_MEDIA_RE` 加右边界 `[^…A-Za-z0-9_]`；新增 `_CODE_SPANS_RE` / `_rebuild_outside_code()`，代码块与行内代码一律不动
- 文档更正「SOUL.md 每轮重读」这个错说法（`README.md` / `docs/architecture.md` / `docs/pitfalls.md` §11 / `apply.py` 提示语 / 本文件自己）
- 测试 69 → **74**：`test_media_hook.py` +4（长扩展名、代码块、行内代码、正文+代码共存）、`test_persona.py` +1（旧 marker 迁移）

## 已验证的证据（不是「应该能行」）

1. **节奏骰真的注入了**：重启 gateway 后跑 `hermes chat -q`，`roll-log.jsonl` 每条都带 `"rhythm": true`。
2. **输出侧钩子真的改写了落库文本**：`MEDIA:…/ee244a0cc5a70ccb.webp进度小结` 在会话库里存成 `…webp\n\n进度小结`（会话 `local-bc0951ca…`，消息 id 13142）。
3. **桌面端也跑新代码**：dashboard 14:03 重启后，`roll-log` 出现 `platform=desktop` + `"rhythm": true` 的记录（会话 `20261101_131356_4deff9`）。
4. **apply.py 的三层保护实测过**（临时 `HERMES_HOME` + 软链 `hermes-agent`）：
   - 别人的 SOUL → `✗ …不敢覆盖` + exit 3，SOUL 和 config 一字未动
   - 空 SOUL + `display.personality: kawaii` + 结构化人设 → 装上人设，两样都保留
   - marker 落成 `{"bootstrap":"done","carrier":"soul","chars":4138}`
5. **SOUL.md 不是每轮重读**（更正）：系统提示按会话缓存（`agent/system_prompt.py:804-807`、`agent/turn_context.py:1141-1144`），压缩后才重建；子代理 `skip_soul=True`（`tools/delegate_tool_progress.py:208`）；只有 cron 是 `load_soul_identity=True`（`cron/scheduler.py:2537`）。

## 待办

1. **桌面端冷启动口吻还没实测。** 判据：新开会话聊五轮，看有没有真报 `[进度]`、真收尾三段。当前会话是老会话（`early: false`），只能算一半。
2. 本轮改动要提交（`__init__.py` / `persona.py` / `apply.py` / `plugin.yaml` / 两份测试 / 六份文档）；push 要单独问。
3. 观察期样本：目标约 262 个带非空 `session_id` 的回合，到量跑 `make drift`。
4. 测试会话堆积：`local-6403bb0d…`、`local-bc0951ca…`、`local-2d9fd7f7…`、`local-81cf37a1…` 要不要删等用户定。
5. `hermes-gateway` 的 systemd 单元有旧告警（`TimeoutStopSec=7s` 小于建议的 70s），要 `hermes gateway install --force` 重生成；与本仓无关。

## 下一步（新会话开工顺序）

1. 提交本轮加固（`persona/user.md` 仍被 `.git/info/exclude` 挡着，别 `git add`）
2. 新会话聊五轮验口吻；不对就调 `suffix.md` 措辞或 `rhythm_probability`，别动架构
3. 稳定后再议 `agent/context_compressor.py` 摘要模板加 `## Voice & Style`（旧方案 C，仍待决）
