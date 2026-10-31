#!/usr/bin/env python3
"""鲸鱼娘掷骰闸门矩阵探针：9 个用例，断言**注入文本**而不是「返回非空」。

为什么要这个而不是只靠单测：单测只验 chance.py 的纯函数，验不到
「`_on_pre_llm_call` 到底往 user message 里塞了什么」——而节拍骰失效最常见
的方式就是「函数对、但钩子没接上」。这里直接调钩子，看注入的字符串。

安全：HERMES_HOME 指到临时目录，绝不碰真 config.json 和真 roll-log.jsonl。

跑法：make probe   （或 ~/.hermes/hermes-agent/venv/bin/python scripts/probe_gates.py）
退出码：全过 0，有失败 1（可直接接进 CI / pre-commit）。
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = REPO / "plugins"

tmp = Path(tempfile.mkdtemp(prefix="whalechan-probe-"))
(tmp / "plugins" / "whalechan").mkdir(parents=True)
os.environ["HERMES_HOME"] = str(tmp)

# 测的是**仓库里的源头**，不是 ~/.hermes/plugins/whalechan 的安装副本：
# 副本可能滞后（apply.py 没跑），拿副本测会得出「改了却没生效」的假结论。
sys.path.insert(0, str(PLUGINS))
for mod in [m for m in list(sys.modules) if m.startswith("whalechan")]:
    del sys.modules[mod]

wc = importlib.import_module("whalechan")
chance = wc.chance

CFG = tmp / "plugins" / "whalechan" / "config.json"
LOG = tmp / "plugins" / "whalechan" / "roll-log.jsonl"

results: list[tuple[str, bool, str, int]] = []


def write_cfg(**over):
    base = {"enabled": True, "probability": 66.6, "beat_probability": 55.0,
            "sources": [], "custom": ""}
    base.update(over)
    CFG.write_text(json.dumps(base), encoding="utf-8")


def call(**kw):
    return wc._on_pre_llm_call(**kw)


def lines(path: Path) -> int:
    return path.read_text(encoding="utf-8").count("\n") if path.is_file() else 0


def check(name, cfg, kwargs, expect):
    write_cfg(**cfg)
    before = lines(LOG)
    out = call(**kwargs)
    text = (out or {}).get("context", "") or ""
    after = lines(LOG)
    ok = (
        ("🎲" in text) == expect.get("dice", "🎲" in text)
        and ("🎭" in text) == expect.get("beat", "🎭" in text)
        and after - before == expect.get("logged", 1)
    )
    results.append((name, ok, text.replace("\n", " ⏎ ")[:110], after - before))
    return text


# 1. 节拍 100 / 表情包 0 → 只该有 🎭
check("beat=100 sticker=0", {"beat_probability": 100.0, "probability": 0.0},
      {"platform": "desktop"}, {"dice": False, "beat": True})
# 2. 节拍 0 / 表情包 100 → 只该有 🎲
check("beat=0 sticker=100", {"beat_probability": 0.0, "probability": 100.0},
      {"platform": "desktop"}, {"dice": True, "beat": False})
# 3. 都 0 → 完全无注入（0 就是关，不许「随机一下」）
check("both=0", {"beat_probability": 0.0, "probability": 0.0},
      {"platform": "desktop"}, {"dice": False, "beat": False})
# 4. 都 100 → 两行都在
check("both=100", {"beat_probability": 100.0, "probability": 100.0},
      {"platform": "desktop"}, {"dice": True, "beat": True})
# 5. 关掉表情包 enabled=false，节拍仍要活（关图 ≠ 想变客服腔）
check("enabled=false beat=100", {"enabled": False, "beat_probability": 100.0, "probability": 100.0},
      {"platform": "desktop"}, {"dice": False, "beat": True})
# 6. sources 过滤：只开 telegram，desktop 两条都不掷。
#    注意日志仍会写一行 false/false —— 钩子只认「这一轮有没有信号」，
#    分不清「没掷」和「掷了没中」。这对 A/B 无害（都是无信号轮），
#    但想按平台统计命中率就得先确认该平台的 sources 配置。
check("sources=[telegram] desktop", {"sources": ["telegram"], "beat_probability": 100.0,
                                     "probability": 100.0}, {"platform": "desktop"},
      {"dice": False, "beat": False, "logged": 1})
# 7. sources 命中 telegram → 两条都在
check("sources=[telegram] telegram", {"sources": ["telegram"], "beat_probability": 100.0,
                                      "probability": 100.0}, {"platform": "telegram"},
      {"dice": True, "beat": True})
# 8. 子代理（有 parent_session_id）一律不掷、不写日志
write_cfg(beat_probability=100.0, probability=100.0)
before = lines(LOG)
out = call(parent_session_id="abc", platform="desktop")
results.append(("subagent 豁免", out is None and lines(LOG) == before, repr(out)[:60], 0))
# 9. custom 注入：只出 custom，不该顺带触发节拍
write_cfg(beat_probability=0.0, probability=0.0, custom="叫我船长")
before = lines(LOG)
ctx = (call(platform="desktop") or {}).get("context", "")
results.append(("custom 注入", "叫我船长" in ctx and "🎭" not in ctx, ctx[:60], lines(LOG) - before))

print(f"临时 HERMES_HOME = {tmp}")
print(f"{'用例':<28}{'结果':<6}日志新增  注入文本")
for name, ok, text, logged in results:
    print(f"{name:<28}{'PASS' if ok else 'FAIL':<6}{logged:<8}{text}")

bad = [r for r in results if not r[1]]
print(f"\n{len(results) - len(bad)}/{len(results)} 通过")
if bad:
    print("失败：", [r[0] for r in bad])
print("\nroll-log 内容：")
print(LOG.read_text(encoding="utf-8").strip() if LOG.is_file() else "(空)")
sys.exit(1 if bad else 0)
