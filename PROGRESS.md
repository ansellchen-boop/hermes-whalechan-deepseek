# 进度

**最后验证**：2026-11-01 23:12 CST —— `make check` → `✓ syntax` / `Ran 74 tests OK` / `apply-check` 人设 4513 = 4513 / `probe` 9/9 / `✓ 无临时工件` → `✓ 全部通过`。

## 当前状态

**0.5.3：长会话「内心戏」衰减对症（只改措辞），`make apply` 补成真实 target。本地已提交未推送。**

- `~/.hermes/SOUL.md` = **4513 字符**（strip 口径）；`persona/suffix.md` 3782 → 4756 字节
- 三条骰：表情包 66.6% / 人设节拍 70%（用户自己调的）/ 节奏 85%（会话前两轮必中）
- 运行时实测（最近 60 条 `roll-log`）：63.3% / 75.0% / 86.7%，与设定吻合
- `git status`：`main...origin/main [ahead 4]`；老板明确说**先不推**
- 测试壳会话 `local-6403bb0d` / `local-bc0951ca` / `local-2d9fd7f7` / `local-81cf37a1` 已删（确认过都是 11-01 13:46–13:59 的 oneshot 验证，无用户内容），删后回读 `sessions=0 / messages=0`
- 磁盘备份：`~/.hermes/backups/whalechan/state-20261101-230754.json`（含改前 SOUL）

## 已完成（第六轮：长会话衰减对症）

1. **先证伪自己**：怀疑 drift 的 `INNER` 正则口径窄、可能把衰减量成假的。探针（`~/.hermes/cache/scratch/probe_inner_metric.py`，393 回合）换三种口径（原正则 / 任意短括号 / 括号含动作词）重算 → **曲线形状一致**，衰减是真的；「任意括号」口径无信息量（技术性括号占大头，≥6 轮的 201 回合里 115 个是假阳性）。
2. **`suffix.md` 改两处**：第 1 条「出声」的示例行改成 `[进度] 看完配置了（鳍抖了一下），唔，接下来改 suffix（还剩 2 步）`，并明说这就是第 4 条要的悄悄话；第 4 条「悄悄话」加标题前缀「长会话最容易掉」+ 四个子条（位置按 ① `[进度]` 行 ② 第一句正文 ③ 闲聊结尾 / 熟了也不能省 / 写成具体动作 / 发之前自查改成「回第一句改，别在结尾硬补」）。
3. **`make apply`**：`AGENTS.md` §4 一直让人跑 `make apply`，Makefile 里根本没这个 target（只有 `apply-check`，`make apply` 直接报 `No rule to make target`）。补成真实 target（部署动作，照原设计不进 `check` 链），`help` 加一行。
4. `plugin.yaml` 0.5.2 → 0.5.3；`docs/state.md` 加第六轮一节（三种口径对照表 + 「别用任意括号口径判断人设」的警告）。

## 已验证的证据（不是「应该能行」）

1. **第一版措辞端到端就失败**：新会话跑「统计 `tests/` 下 `test_` 方法个数」，输出有口癖、有三段小结，**但正文一个括号动作都没有**。改措辞不能靠想象，必须跑。
2. **第二版端到端通过**：新会话跑「统计插件目录行数」，输出含 `（内心：真要说它是「大文件」，一半是 docstring 和命令文案撑的…）`；reasoning 里自己执行了「自查：有没有至少一处括号动作/内心戏 —— 有」。
3. **MEDIA 钩子没坏（虚惊）**：CLI 屏幕上看着像 `…webp进度小结` 粘在一起，查会话库 `messages.content` 实际存的是 `…webp\n\n**进度小结**` —— 终端渲染把 `**` 和换行吃了，不是钩子失效。
4. **删会话后回读**：四个 `local-*` 前缀在 `sessions` 和 `messages` 两张表都是 0 行。
5. **第五轮的旧证据仍然成立**（`apply.py` 三层保护、SOUL 不是每轮重读、节奏骰注入），只是人设字符数从 4137 变 4513。

## 待办

1. **push**：本地 `ahead 4`（`5acb3e1` / `655a3e6` / `6d21eb3` / 本轮这笔），老板说先不推，等他说。推之前 `git diff origin/main..HEAD --name-only | grep persona/user.md` 必须为空（`user.md` 已 `git rm --cached` 停追、`.gitignore` 挡着，这条 grep 是第二道保险）。
2. **复测衰减**：新措辞 2026-11-01 23:10 起生效，现在 `make drift` 的数据全是旧措辞的。攒够新措辞的回合（建议 ≥100 回合、且含 ≥10 个 11 轮以上的会话）再跑，只看 11-20 / 21+ 两段的「内心」列。
3. **drift 的 `INNER` 口径要不要放宽到「括号含动作词」**：放宽能抓到「（把锅端起来）」这类，但历史数字会不可比。**待老板拍板**，没动。
4. **桌面长会话口吻**：只在 oneshot 上验过两轮，≥11 轮的桌面会话还没实测。
5. `hermes-gateway` 的 systemd 单元旧告警（`TimeoutStopSec=7s` < 建议 70s），要 `hermes gateway install --force` 重生成；与本仓无关。
6. ~~`persona/user.md` 早已入库且公开~~ → **已处置（2026-11-01，老板选方案②）**：`git rm --cached` 停追 + 写进 `.gitignore`，工作区文件保留，`git add -A --dry-run` 已验过不会带上；`persona.py:45 SECTION_FILES` 把 user.md 当**可选段**（`tests/test_persona.py:92 test_missing_file_is_skipped`），别人 clone 缺它照样能跑。**遗留**：历史提交 `87becc9` / `251f0b5` 里那四行称呼仍公开在 GitHub（仓库 PUBLIC），要彻底清只能重写历史 + force push，老板明确不做。

## 下一步（新会话开工顺序）

1. 读本文件 → `git status -sb` 确认还是 `ahead 4`，问老板推不推
2. 攒够新措辞样本后跑 `make drift`，只比 11-20 / 21+ 两段的「内心」列
3. 抬不起来再改 `suffix.md`（把「进度行必须带动作」再收一格），别动架构
4. 稳定后再议 `agent/context_compressor.py` 摘要模板加 `## Voice & Style`（旧方案 C，仍待决）
