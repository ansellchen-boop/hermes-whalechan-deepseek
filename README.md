# hermes-whalechan-deepseek

给 Hermes Agent 的**鲸鱼娘（Whale-chan / DeepSeek娘）**预设：完整干活能力 + 人设，开工吐槽、收工讨饭，按宿主掷骰发表情包。

工具清单不打折，整条回复都长着鲸鱼娘的脸：中途出声报进度、挨骂委屈、被夸得意、收尾三段小结。
移植自 [Weidows/dsh-whalechan-herself](https://github.com/Weidows/dsh-whalechan-herself)（MIT，DeepSeek Harness 版），人设与插件在这里按 Hermes 的机制重新落地并自行维护。

---

## 装

一条命令，插件自带人设（首次加载自动写进 `~/.hermes/config.yaml`）：

```bash
hermes plugins install ansellchen-boop/hermes-whalechan-deepseek/plugins/whalechan --enable
```

装完**开一个新会话**就有鲸鱼娘了——人设（personality）是会话启动时读的。
`hermes plugins update whalechan` 之后同理。

想从源码装、或者要强制同步人设：

```bash
git clone https://github.com/ansellchen-boop/hermes-whalechan-deepseek.git ~/hermes-whalechan
cd ~/hermes-whalechan
python3 apply.py            # 装 / 强制同步人设（先自动备份）
python3 apply.py --check    # 只对比
python3 apply.py --revert   # 回滚到最近一次备份
```

`apply.py` 做三件事：

1. 合成 `plugins/whalechan/persona/{prefix,user,suffix}.md` → `~/.hermes/SOUL.md`（身份层）
2. 清掉 `config.yaml` 里的旧载体（`agent.personalities.whalechan` / `display.personality`）——人设只住一处
3. 把 `plugins/whalechan`（含 `persona/`）同步进 `~/.hermes/plugins/whalechan`

**人设自举只在 `SOUL.md` 还是出厂身份时发生**：插件首次加载看到它空着、或者还是出厂英文身份
（`You are Hermes Agent…`），就写入人设，旧的自动备份成 `SOUL.md.bak-<时间戳>`。

之后遇到这三种情况**不会**自作主张：

| `SOUL.md` 里是什么 | 插件怎么做 |
| --- | --- |
| 已经是本预设、内容相同 | `already`，不动 |
| 已经是本预设、但你手改过 | `drift`，只提示；要强制同步跑 `/whalechan sync` |
| 你清空过 | `removed-by-user`，不装回来；要恢复跑 `/whalechan sync` |
| 别人的内容（既非出厂、也不含「鲸鱼娘」） | `refused`，**`sync` 也不覆盖** |

生效时机：系统提示是**按会话缓存**的（`agent/system_prompt.py:804-807` 只在
`agent._cached_system_prompt is None` 时构建、压缩后重建），所以改完 SOUL.md 要**新会话**才看得到；
日志里那行 `whalechan: 人设 already（N 字）` 每轮都会打，但它只证明 `pre_llm_call` 钩子跑过，
不代表 system prompt 重拼了。插件代码改动要重启承载进程。

---

## 为什么搬到 SOUL.md

| | `agent.personalities.whalechan`（0.4.x） | `~/.hermes/SOUL.md`（0.5.0+） |
| --- | --- | --- |
| 注入位置 | system prompt **最末尾**（`agent/turn_context.py`：`effective_system = effective_system + "\n\n" + ephemeral_system_prompt`） | identity slot，**第一段** |
| cron / 定时任务 | 不传 | `cron/scheduler.py` 显式 `load_soul_identity=True`，带 |
| 子代理 | 不传 | **也不传**：`tools/delegate_tool_progress.py:208` 显式 `skip_soul=True`（身份归父会话） |
| 刷新 | 每次 API 调用重拼（ephemeral） | 每**会话**拼一次，压缩后才重建 |

搬过去换来的是**覆盖面**：人设不再只影响某一个会话类型，整个进程内所有对话都带。
代价是**位置**：人设在最前面，离当前用户消息最远，长会话后半段容易稀释。
所以纯粹的措辞留在人设里，**结构性**的规矩（报进度、收尾三段）交给插件每轮掷骰补一句。

插件自己的 `register_system_prompt_section` 用不了：只有一个口子 `after_memory`、
单节 4000 字、会话级冻结（`hermes_cli/plugins_dispatch.py`），塞人设既不够长也不够活。

人设三段的拼法：

| 文件 | 装什么 | 拼在哪 |
| --- | --- | --- |
| `plugins/whalechan/persona/prefix.md` | 身份、说话方式、性格、情绪、心思、表达、干活节奏、表情包规则 | 最前 |
| `plugins/whalechan/persona/user.md` | 你自己的追加设定（称呼、口癖、额外规矩），留空即无 | 中间 |
| `plugins/whalechan/persona/suffix.md` | 每轮硬规矩：出声报进度、收尾三段、找帮手、悄悄话、中文思考 | **最后** |

`suffix.md` 排在拼接结果最后，但整份人设现在都住在 system prompt 第一段——所以它的「靠后」只在同一段内成立，不是全局最末。
这也是为什么要加**节奏骰**：光靠后缀的位置已经压不住，结构性的提醒得每轮重新出现一次。

---

## 表情包掷骰

发不发表情包**由宿主决定**，不靠模型自觉（上游 v0.3.1 的做法）。

- 每轮开头 `pre_llm_call` 掷一次骰，命中就在这一轮的 user message **末尾追加**一行
  （宿主是 `content + "\n\n" + injection`，不是插在前面）
  `🎲 表情包掷骰：命中（本轮）…`
- 人设认这句话：收到就调一次 `sticker`，只发一张；没收到就不发、也不调工具
- 子代理会话不掷骰（有 `parent_session_id` 就跳过），免得子任务也去发表情包

调概率有两个入口。会话里直接发斜杠命令（Hermes 插件没有 web route，上游 v0.3.1 的浏览器设置页在这里换成了命令）：

```
/whalechan                 # 看当前状态（含人设同步情况）
/whalechan 80              # 表情包概率改 80%
/whalechan off             # 关表情包
/whalechan on              # 开表情包
/whalechan beat 55         # 人设节拍概率改 55%（0 关，跟表情包互相独立）
/whalechan rhythm 85       # 节奏提醒概率改 85%（0 关；管报进度 + 收尾三段小结）
/whalechan custom <文本>    # 写追加设定（≤2000 字）
/whalechan custom          # 看写了什么
/whalechan custom clear    # 清空
/whalechan sync            # 强制把 persona/*.md 重新写进 SOUL.md（只覆盖本预设自己写的）
```

或者直接改 `~/.hermes/plugins/whalechan/config.json`：

```json
{
  "enabled": true,
  "probability": 66.6,
  "beat_probability": 55,
  "rhythm_probability": 85,
  "sources": [],
  "custom": ""
}
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | `false` 彻底关掉表情包掷骰（工具还在，人设不会再主动发） |
| `probability` | 0–100，保留一位小数；0 永不发，100 每轮都发 |
| `beat_probability` | 人设节拍骰，0–100，默认 55；**0 = 关**，建议区间 40–70 |
| `sources` | 空数组 = 所有平台都掷；填了就只在这些 `platform` 上掷（如 `["telegram"]`） |
| `custom` | 追加设定，≤2000 字；非空时每轮以「追加设定」小节注入，和掷骰提示共用同一次 `pre_llm_call` |

改完配置下一轮就生效，不用重启。

## 人设节拍骰（治「聊十轮就变客服」）

口癖、吐槽、内心戏这些**没有闸门**的行为会随会话变长一路衰减，实测（18 个会话、137 轮）：

| 会话内轮次 | 口癖率 | 内心戏/小动作 | 表情包调用 |
| --- | --- | --- | --- |
| 1–2 | 75% | 32% | 61% |
| 3–5 | 55% | 34% | 66% |
| 6–10 | 31% | 35% | 69% |
| 11–20 | 17% | 7% | 70% |
| 21+ | 0% | 0% | 86% |

同会话配对：前 3 轮 **73%** → 末 3 轮 **20%**。而表情包因为有宿主的 66.6% 骰子，一点没退。

原因不是模型忘了人设（人设是 `personality`，每轮都拼在 system prompt 最末尾），
而是**历史里再也没有新鲜信号**：模型每轮模仿自己最近几轮的输出，前几轮淡一点，
后面就照着淡的演，正反馈一路降到零。压缩（`compression.threshold: 0.5`）还会把
早期带口癖的原文压成纯技术摘要（`agent/context_compressor.py` 的
`_summary_template_sections` 十节模板里没有一节保留语气），进一步断掉参照。

所以给人设补一条**跟表情包互相独立的宿主骰**：

- 每轮 `pre_llm_call` 掷一次，命中就在 user message **末尾追加**一行（不是插在前面，同表情包那节）
- 指令有 5 套说法，命中时随机取一条（`chance.BEAT_CONTEXTS` / `chance.pick_beat()`）：
  同一句话原样重复十遍会被历史自举磨成背景噪音——频率不动，动的是新鲜度
- **会话前两轮强制命中**（`should_fire_beat(early=True)`，`beat_probability=0` 时除外）：
  这两轮是后面几十轮的参照样本，掉一次要很久才拉得回来
- 它每轮新鲜、随机、不依赖历史，压缩和自举漂移都伤不到它
- 不看 `enabled`（关表情包的人多半只是不想发图，不该顺带被改成客服腔）
- 子代理会话不掷（同表情包），`sources` 过滤照旧
- 概率是**宿主侧**的，不写进人设——写进 prompt 会变成日程表，读起来比不卖萌还假

**两套追加设定的区别**（别写重复了）：

| 位置 | 谁管 | 生效时机 | 适合 |
| --- | --- | --- | --- |
| `plugins/whalechan/persona/user.md` | 跟着插件走，自举 / `/whalechan sync` 写进 personality | 新会话 | 长期固定的称呼、口癖、规矩，跨机器同步 |
| `config.json` 的 `custom` / `/whalechan custom` | 只在这台机器 | 下一轮 | 临时试效果，或者不想动仓库 |

两边都写会叠加，`custom` 在 user message 里、位置更靠后。

`sticker` 工具参数：`scene`（中文场景，如 `摸鱼 累`）、`count`（1–8）、`character`（默认 `deepseek`，`any` 全站）、
`type`（`meme` / `illustration` / `standing` / `comic` / `setting` / `other`）、`random`、`refresh`。
图库索引首次调用下载，缓存 7 天。

---

## 目录

```
hermes-whalechan/
├── plugins/whalechan/          ← 插件本体，GitHub 装的就是这个子目录
│   ├── __init__.py             sticker 工具 + pre_llm_call 掷骰 + /whalechan
│   ├── chance.py               掷骰纯逻辑（不依赖 Hermes，可单测）
│   ├── persona.py              人设合成 + 自举写进 SOUL.md（纯逻辑，可单测）
│   ├── persona/                人设三段（见上表；跟着插件走，装子目录才带得上）
│   │   ├── prefix.md
│   │   ├── user.md
│   │   └── suffix.md
│   ├── stickers.py             图库索引下载 / 缓存 / 模糊匹配
│   └── plugin.yaml
├── tests/                      python3 -m unittest discover -s tests
└── apply.py                    幂等安装 / 检查 / 回滚（从源码装时用）
```

---

## 什么时候不要用它

- 只要一个没性格的助手 → `hermes plugins disable whalechan` + `/personality none`
- 想要"时间感知 / 天气 / 关系阶段"那一类**通用人格注入引擎** → 那是
  [kenyonxu/hermes-persona](https://github.com/kenyonxu/hermes-persona) 的领域，但它的注入落在 user message，
  且 `translate` / `debug` 两个模块和固定人设会互相干扰，本项目刻意不引入。

---

## 许可

MIT。人设与 `sticker` 工具源自 dsh-whalechan-herself（© Weidows），Hermes 移植与掷骰实现见本仓库历史。
