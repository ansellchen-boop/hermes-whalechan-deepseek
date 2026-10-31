# 验证：改完怎么确认没坏

> 适用：改完任何文件、准备说「好了」之前；或怀疑某条链路没生效时。
> 不适用：查怎么装 → `README.md`；查某个坑为什么踩 → `pitfalls.md`。
> 过期条件：`Makefile` 的 target 改名/增删，或 Hermes venv 路径变了。
> 来源：原 `AGENTS.md` §4，2026-10-31 拆分；已与 `Makefile`（`check: syntax test apply-check probe`）逐条对齐——原文档漏写了 `probe`，这里按实现写。

## 一条命令

```bash
make check          # = syntax + test(38) + apply-check + probe
```

三秒返回，**不碰网络、不改配置、不重启服务**。改完任何东西先跑它。

需要写配置的动作（`apply.py` 不带 `--check`）刻意不放进 `check`：那是「部署」不是「验证」。

## 拆开按需跑

| 命令 | 查什么 | 什么时候必须跑 |
| --- | --- | --- |
| `make check` | 语法编译 + 单测 + 仓库与已安装配置是否一致 + 闸门探针 | 每次改完 |
| `make syntax` | `compileall` 编译 `plugins` / `scripts` / `tests` | 只改了一行想快验 |
| `make test` | 单测 38 个（`chance` / `persona` 纯逻辑） | 改了 `chance.py` / `persona.py` |
| `make apply-check` | 仓库 vs `~/.hermes/` 已安装的人设/插件是否一致（只读） | 怀疑副本没同步 |
| `make probe` | 闸门矩阵 9 个用例：直接调 `_on_pre_llm_call`，断言**注入文本**，临时 `HERMES_HOME` 不碰真配置 | 改了钩子或掷骰逻辑 |
| `make drift` | 人设漂移曲线 + 节拍 A/B（读 `state.db` 和 `roll-log.jsonl`） | 攒够样本后 |
| `make lint` / `make typecheck` | ruff / mypy | 本机都没装，会打印「跳过」而不是报红 |
| `make help` | 上面这些的一句话说明 | 忘了 target 名 |

`make lint` 没装 ruff 时**跳过而不是失败**是故意的：验证命令必须真能跑，宁可跳过并说清楚，也不留一条永远红的命令。

## 用错 Python 会假装插件坏了

- `python3`（3.12）跑单测够用。
- 跑 `apply.py`、`scripts/*.py` 这类要读 Hermes 配置的**用 `make`**（内部已指向 `~/.hermes/hermes-agent/venv/bin/python`）。
- **不要**用 `~/.hermes/tools/python-3.14.9*/bin/python3.14` —— 没 yaml，`persona.py` 的配置读写会直接炸，症状像「插件坏了」。

## 节拍骰到底有没有在跑，只看一处

```bash
wc -l ~/.hermes/plugins/whalechan/roll-log.jsonl
```

有没有**新行**。没有 = `pre_llm_call` 没走到那一步，三种可能：进程跑旧代码 / 平台被 `sources` 过滤 / 子代理豁免。

新代码的判据是出现**带 `session_id`** 的行 —— 说明桌面和网关都跑上新模块了。

## 人设同步看哪

别信 `persona-state.json` 的 `chars`（自举那一刻的字数，之后不更新）。直接读安装后的长度：

```bash
~/.hermes/hermes-agent/venv/bin/python -c "import yaml,os;c=yaml.safe_load(open(os.path.expanduser('~/.hermes/config.yaml')));print(len(c['agent']['personalities']['whalechan']))"
```

`make apply-check` 报「插件差异: 无」才算仓库与运行副本对齐。
