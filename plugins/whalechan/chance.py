"""表情包掷骰 + 追加设定：由宿主每轮决定这一轮要不要发表情包。

移植自 dsh-whalechan-herself v0.3.1 的 ``agent/pre-step`` 掷骰与 ``chance.js``
的配置写入（MIT）。纯逻辑、不 import Hermes 运行时，方便单测和单独调试。
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any

DEFAULT_PROBABILITY = 66.6
MIN_PROBABILITY = 0.0
MAX_PROBABILITY = 100.0

#: 追加设定（用户自己写的话）最多这么多字，跟上游 chance.js 的 2000 一致。
DEFAULT_CUSTOM_MAX = 2000

#: 命中时追加在本轮 user message **末尾**的一行提示；人设里的表情包规则认这句话。
#: （宿主 `agent/turn_context.py` 是 `content + "\n\n" + injection`，不是插在前面。）
HIT_CONTEXT = (
    "🎲 表情包掷骰：命中（本轮）。"
    "按这一刻的场景调一次 sticker，只发一张，放在情绪那句旁边或回复末尾；结论、代码、命令照常写。"
)

#: 人设节拍骰：表情包讲的是「发不发图」，这条讲的是「嘴还在不在」。
#: 口癖 / 内心戏没有闸门时会被历史自举稀释到零（实测 73% → 20%，而无人设基线
#: 是 22%——末段等于归零到普通助手），所以给它一条跟表情包互相独立的骰子。
DEFAULT_BEAT_PROBABILITY = 55.0
#:
#: 为什么要变体而不是加概率：衰减的驱动是「历史自举」——模型模仿自己近几轮，
#: 同一条指令原样重复十遍，到后面就退化成背景噪音。所以骰子命中时**随机换一种
#: 说法**，让每一轮的信号都是新的；频率不动，新鲜度动。
BEAT_CONTEXTS: tuple[str, ...] = (
    (
        "🎭 人设节拍：本轮至少一处口癖（唔/诶/嘛这种）＋ 一处内心戏或小动作（括号里十个字以内），"
        "位置你自己挑——开头那句嘀咕、踩坑那一下、收尾讨饭都行；"
        "技术结论、代码、命令、报错原文照常写，别为了味道省掉信息。"
    ),
    (
        "🎭 人设节拍：这轮别写成纯客服腔。留一处真的情绪——一个语气词，或一个不超过十个字的"
        "括号动作，放在你最想说话的那一下，不用首尾都塞。命令和报错照原样写。"
    ),
    (
        "🎭 人设节拍：本轮挑一个具体的情绪露出来——得意、犯困、嫌麻烦、心虚，都行——"
        "用一句口癖或一个小动作带过（括号里十个字以内），别整段自述。数字和路径照实写。"
    ),
    (
        "🎭 人设节拍：这轮带一处反差：正经的结论旁边配一句自己的嘀咕，或者一个顺手的小动作"
        "（括号里十个字以内）。口癖一处就够，别每句都加。"
    ),
    (
        "🎭 人设节拍：本轮至少一处口癖，挑位置——卡住的时候、嫌麻烦的时候、干完讨饭的时候，"
        "别堆在开头当开场白；内心戏或小动作一处，十个字以内。技术内容不许为此省字。"
    ),
)

#: 兼容旧引用（文档/测试里叫过这个名字）。
BEAT_CONTEXT = BEAT_CONTEXTS[0]

#: 前两轮（会话锚点）强制命中用的措辞：这两轮是后面几十轮的参照样本，
#: 掉一次要好久才拉回来，所以不给骰子。仍然受 ``sources`` 和 0 概率约束。
BEAT_EARLY_CONTEXT = (
    "🎭 人设节拍（会话开头，这轮的口气会被后面几十轮模仿）："
    "按人设说话——至少一处口癖（唔/诶/嘛这种）＋ 一处内心戏或小动作（括号里十个字以内）。"
    "技术结论、命令、报错原文照常写，别为了味道省掉信息。"
)

#: 追加设定的标题；只有用户写了内容才会注入。
CUSTOM_HEADER = "## 追加设定（用户后加的；与上面的角色设定冲突时，以这里为准）"

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "probability": DEFAULT_PROBABILITY,
    # 人设节拍骰：跟 enabled / probability 互相独立——关掉表情包不代表要变回客服腔。
    "beat_probability": DEFAULT_BEAT_PROBABILITY,
    # 空列表 = 所有来源都参与；填了就只在这些 platform 上掷骰。
    "sources": [],
    # 用户自定义设定：追加进每轮的 system 侧提示，留空即无。
    "custom": "",
}


def config_path() -> Path:
    """配置文件位置：<HERMES_HOME>/plugins/whalechan/config.json。"""
    home = os.environ.get("HERMES_HOME")
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "plugins" / "whalechan" / "config.json"


def clamp_probability(value: Any, default: float = DEFAULT_PROBABILITY) -> float:
    """把概率钳到 0–100，保留一位小数；坏值回默认。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(MIN_PROBABILITY, min(MAX_PROBABILITY, round(number, 1)))


def normalize_custom(value: Any) -> str:
    """追加设定：统一换行、去首尾空白、截到 2000 字。非字符串当空。"""
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:DEFAULT_CUSTOM_MAX]


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """读配置；文件缺失/损坏一律回默认值，绝不让掷骰本身把轮次搞挂。"""
    target = Path(path) if path else config_path()
    config = dict(DEFAULTS)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if not isinstance(raw, dict):
        return config
    if "enabled" in raw:
        config["enabled"] = bool(raw["enabled"])
    if "probability" in raw:
        config["probability"] = clamp_probability(raw["probability"])
    if "beat_probability" in raw:
        config["beat_probability"] = clamp_probability(raw["beat_probability"], DEFAULT_BEAT_PROBABILITY)
    sources = raw.get("sources")
    if isinstance(sources, list):
        config["sources"] = [str(item) for item in sources if str(item).strip()]
    if "custom" in raw:
        config["custom"] = normalize_custom(raw["custom"])
    return config


def save_config(patch: dict[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    """写回配置：只覆盖认识的键，未知键原样保留；写完回读并返回实际生效值。

    上游 chance.js 由设置页 POST 写文件；Hermes 没有 web route，
    改由会话内 ``/whalechan`` 命令调这里。
    """
    target = Path(path) if path else config_path()
    raw: dict[str, Any] = {}
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    except (OSError, json.JSONDecodeError):
        raw = {}
    incoming = patch or {}
    if "enabled" in incoming:
        raw["enabled"] = bool(incoming["enabled"])
    if "probability" in incoming:
        raw["probability"] = clamp_probability(incoming["probability"])
    if "beat_probability" in incoming:
        raw["beat_probability"] = clamp_probability(incoming["beat_probability"], DEFAULT_BEAT_PROBABILITY)
    if "sources" in incoming and isinstance(incoming["sources"], list):
        raw["sources"] = [str(item) for item in incoming["sources"] if str(item).strip()]
    if "custom" in incoming:
        raw["custom"] = normalize_custom(incoming["custom"])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return load_config(target)


def roll(probability: float, rng: random.Random | None = None) -> bool:
    """按百分比掷一次。0 永不命中，100 必中。"""
    generator = rng or random
    return generator.random() * 100.0 < probability


def sources_allow(config: dict[str, Any], platform: str = "") -> bool:
    """来源过滤：``sources`` 为空=全放行；给了 platform 才比对，空 platform 不拦。"""
    sources = config.get("sources") or []
    if not sources or not platform:
        return True
    return platform in sources


def describe_sources(config: dict[str, Any]) -> str:
    """给状态命令用的一行：只在哪些 platform 掷骰（空 = 全部）。

    写错平台名是最难查的故障——两条骰子会静默全关，日志里什么都没有。
    把这行摆在 ``/whalechan`` 状态里，至少看状态时能发现。
    """
    sources = config.get("sources") or []
    return f"只在 {'、'.join(map(str, sources))} 上掷骰" if sources else ""


def pick_beat(rng: random.Random | None = None) -> str:
    """从几套说法里随机取一条节拍指令（不是每轮同一句）。"""
    generator = rng or random
    return generator.choice(BEAT_CONTEXTS)


def should_fire(
    config: dict[str, Any],
    platform: str = "",
    rng: random.Random | None = None,
) -> bool:
    """综合开关、来源过滤和概率，判断这一轮要不要命中。"""
    if not config.get("enabled", True):
        return False
    if not sources_allow(config, platform):
        return False
    return roll(float(config.get("probability", DEFAULT_PROBABILITY)), rng=rng)


def should_fire_beat(
    config: dict[str, Any],
    platform: str = "",
    rng: random.Random | None = None,
    *,
    early: bool = False,
) -> bool:
    """人设节拍骰：故意不看 ``enabled``——关掉表情包的人多半只是不想发图，
    不该顺带被改成客服腔。只认 ``beat_probability``（0 = 关）和来源过滤。

    ``early=True``（会话前两轮）时强制命中：这两轮是后面几十轮的参照样本，
    漏一次要很久才拉得回来。概率设成 0 仍然等于关——用户明确关掉就得尊重。
    """
    if not sources_allow(config, platform):
        return False
    probability = float(config.get("beat_probability", DEFAULT_BEAT_PROBABILITY))
    if early and probability > 0:
        return True
    return roll(probability, rng=rng)
