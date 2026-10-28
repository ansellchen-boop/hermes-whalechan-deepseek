# hermes-whalechan

给 Hermes Agent 的**鲸鱼娘（Whale-chan / DeepSeek娘）**预设：完整干活能力 + 人设，开工吐槽、收工讨饭，按宿主掷骰发表情包。

工具清单不打折，整条回复都长着鲸鱼娘的脸：中途出声报进度、挨骂委屈、被夸得意、收尾三段小结。
移植自 [Weidows/dsh-whalechan-herself](https://github.com/Weidows/dsh-whalechan-herself)（MIT，DeepSeek Harness 版），人设与插件在这里按 Hermes 的机制重新落地并自行维护。

---

## 装

```bash
git clone https://github.com/ansellchen-boop/hermes-whalechan-deepseek.git ~/hermes-whalechan
cd ~/hermes-whalechan
python3 apply.py            # 装 / 更新（先自动备份）
python3 apply.py --check    # 只对比
python3 apply.py --revert   # 回滚到最近一次备份
```

`apply.py` 做三件事：

1. 合成 `persona/{prefix,user,suffix}.md` → `~/.hermes/config.yaml` 的 `personalities.whalechan`
2. 把 `display.personality` 设成 `whalechan`
3. 把 `plugins/whalechan` 同步进 `~/.hermes/plugins/whalechan`

改完人设或插件后重跑一次。**personality 是会话级拼进 system prompt 的**：网关（Telegram 等）下一条消息生效，
桌面 / TUI 要新会话，或者用 `/personality whalechan` 重选一次。

---

## 为什么人设能压得住

Hermes 把 `personalities.<name>` 的文本在**每次 API 调用时拼到 system prompt 的最末尾**
（`agent/turn_context.py`：`effective_system = effective_system + "\n\n" + ephemeral_system_prompt`）。
位置本身就是最强的约束——这也是上游 v0.3.0 把硬规矩拆成 `suffix` 想要的效果。

所以本仓库的分工是：

| 文件 | 装什么 | 拼在哪 |
| --- | --- | --- |
| `persona/prefix.md` | 身份、说话方式、性格、情绪、表达、干活节奏、表情包规则 | 最前 |
| `persona/user.md` | 你自己的追加设定（称呼、口癖、额外规矩），留空即无 | 中间 |
| `persona/suffix.md` | 每轮硬规矩：出声报进度、收尾三段、找帮手、中文思考 | **最后** |

只写 prefix 的话，规矩全挤在提示词开头，聊过几十轮口气会飘回正式腔；suffix 落在最后一段，位置本身就是约束。

---

## 表情包掷骰

发不发表情包**由宿主决定**，不靠模型自觉（上游 v0.3.1 的做法）。

- 每轮开头 `pre_llm_call` 掷一次骰，命中就在这一轮的 user message 前面塞一行
  `🎲 表情包掷骰：命中（本轮）…`
- 人设认这句话：收到就调一次 `sticker`，只发一张；没收到就不发、也不调工具
- 子代理会话不掷骰（有 `parent_session_id` 就跳过），免得子任务也去发表情包

调概率：`~/.hermes/plugins/whalechan/config.json`

```json
{
  "enabled": true,
  "probability": 66.6,
  "sources": []
}
```

| 字段 | 说明 |
| --- | --- |
| `enabled` | `false` 彻底关掉掷骰（工具还在，人设不会再主动发） |
| `probability` | 0–100，保留一位小数；0 永不发，100 每轮都发 |
| `sources` | 空数组 = 所有平台都掷；填了就只在这些 `platform` 上掷（如 `["telegram"]`） |

改完配置下一轮就生效，不用重启。

`sticker` 工具参数：`scene`（中文场景，如 `摸鱼 累`）、`count`（1–8）、`character`（默认 `deepseek`，`any` 全站）、
`type`（`meme` / `illustration` / `standing` / `comic` / `setting` / `other`）、`random`、`refresh`。
图库索引首次调用下载，缓存 7 天。

---

## 目录

```
hermes-whalechan/
├── persona/            人设三段（见上表）
├── plugins/whalechan/
│   ├── __init__.py     sticker 工具 + pre_llm_call 掷骰
│   ├── chance.py       掷骰纯逻辑（不依赖 Hermes，可单测）
│   ├── stickers.py     图库索引下载 / 缓存 / 模糊匹配
│   └── plugin.yaml
├── tests/              python3 -m unittest discover -s tests
└── apply.py            幂等安装 / 检查 / 回滚
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
