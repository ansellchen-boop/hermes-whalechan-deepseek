# 坑：每条都踩过

> 适用：动手改之前扫一眼；出怪现象时先来这里对症状。
> 不适用：命令怎么跑 → `verify.md`；机制为什么这么设计 → `architecture.md`。
> 过期条件：对应代码/服务改名或行为变化时逐条失效，改一条删一条，别攒。
> 来源：原 `AGENTS.md` §5，2026-10-31 拆分，条目内容未改，只按「症状 → 原因 → 做法」重排。

## 1. 仓库不是运行副本，改完不跑 `apply.py` 等于没改

活插件在 `~/.hermes/plugins/whalechan/`（`apply.py` 拷过去的副本），仓库 `plugins/whalechan/` 只是源头。
2026-10-30 踩过：仓库里给 `_log_roll` 加了 `session_id`，跑测量脚本发现六条日志全是老格式——拷贝根本没同步。
**判据**：`apply.py --check` 报「插件差异: 无」，以及 `ls -l ~/.hermes/plugins/whalechan/__init__.py` 的 mtime 与重启时间的前后关系。

## 2. 插件代码不会热重载，重启时间 vs 文件 mtime 是唯一判据

2026-10-30 实测：`hermes-dashboard` 22:24 启动，节拍骰代码 23:17 才写完 → 桌面会话一整天跑的都是旧模块（有 🎲 表情包掷骰、没有节拍骰、不写 roll-log）；而 gateway 23:18 重启过，所以只有 gateway 那一条日志。
动手改行为前先对一下：

```bash
systemctl --user show hermes-dashboard -p ExecMainStartTimestamp
ls -l ~/.hermes/plugins/whalechan/__init__.py
```

## 3. 重启 dashboard 会掐断当前桌面会话

本会话就活在它的 cgroup 里，直接在会话里 `systemctl --user restart hermes-dashboard` 等于自己拔插头，这轮回复发不出去。
做法：把重启写成脚本（把 `is-active` / `MainPID` 落日志），排延迟执行，回复先出去，重连后读日志验证：

```bash
systemd-run --user --on-active=60 --unit=<名字> --collect /bin/bash <脚本>
```

`setsid` / `nohup` 没用——进程仍在同 cgroup，会被一起杀。

## 4. 人设不能塞进插件

`register_system_prompt_section` 只允许 `position=after_memory`（渲染顺序 `skills → memory → 插件段落 → profile → 时间戳`，**不是末尾**），单节 4000 字（人设现 3471 字），docstring 写明会话级冻结。
`personalities.*` 是每次 API 调用拼在 system prompt **最末尾**，且下一轮就换。所以人设只能住 `agent.personalities.whalechan`。

## 5. 概率绝不能写进 prompt

写进去会被读成日程表，出来的是机械节奏，比不卖萌还假。
频率只由宿主骰子决定（`chance.py` 每次 `random.random()`），人设里只写「收到信号就这么做」。

## 6. 骰子之间要独立

`enabled=false` 只关表情包，不能顺带把节拍也关掉（关图的人不代表想变客服腔）；`sources` 对两条骰子同时生效；子代理（有 `parent_session_id`）两条都不掷。

## 7. 上限会变成下限

「至多两处悄悄话」这种纯上限写法，模型会当成「允许写零」。要么写「至少一处，最多两处」，要么把频率交给骰子、文本里写清「没收到信号也按基础下限走」。
改措辞时特别注意别让上限和骰子互相打架（`llm-agent-behavior-tuning` 技能第 5 节）。

## 8. `persona-state.json` 里的 `chars` 会滞后

记录的是自举那一刻的字数，人设后来加段不会更新。别拿它判断人设有没有同步，直接读 `config.yaml` 里 `agent.personalities.whalechan` 的长度（一行命令见 `verify.md`）。

## 9. `apply.py` 写 config 要借 Hermes 的 venv

本机是 editable 安装，用系统 `python3` 调 `hermes_cli.config_backend` 会报 `ModuleNotFoundError: No module named 'hermes_yaml'`。
`persona.py` 的 `_default_writer` 已经自己把 `<HERMES_HOME>/hermes-agent` 插进 `sys.path`，别在别处另写一套。

## 10. `git add .` 会把本机配置一起带上

`plugins/whalechan/config.json`（概率、custom）已 gitignore；模板是 `config.example.json`。
新增本机私有文件时一律进 `.git/info/exclude`，**别改 `.gitignore`**（那会进仓库）。

## 11. 改完人设别急着说「生效了」

personality 是会话启动时读的：网关下一条消息就带，桌面 / TUI 要**新会话**，或用 `/personality whalechan` 重选。

## 12. 追加设定有两个入口，别两边都写

长期设定进 `persona/user.md`（进 personality，会话级）；临时试验用 `/whalechan custom`（每轮 `pre_llm_call` 注入到 user message）。
两边写同一句等于注入两遍，白烧 token 还让人设显得啰嗦；`chance.load_config()` 拿到空 `custom` 时 `__init__.py:131` 的 `if custom:` 会整段跳过。
