"""表情包掷骰：由宿主每轮决定这一轮要不要发表情包。

移植自 dsh-whalechan-herself v0.3.1 的 ``agent/pre-step`` 掷骰（MIT）。
纯逻辑、不 import Hermes 运行时，方便单测和单独调试。
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

#: 命中时注入 user message 前面的一行提示；人设里的表情包规则认这句话。
HIT_CONTEXT = (
    "🎲 表情包掷骰：命中（本轮）。"
    "按这一刻的场景调一次 sticker，只发一张，放在情绪那句旁边或回复末尾；结论、代码、命令照常写。"
)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "probability": DEFAULT_PROBABILITY,
    # 空列表 = 所有来源都参与；填了就只在这些 platform 上掷骰。
    "sources": [],
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
    sources = raw.get("sources")
    if isinstance(sources, list):
        config["sources"] = [str(item) for item in sources if str(item).strip()]
    return config


def roll(probability: float, rng: random.Random | None = None) -> bool:
    """按百分比掷一次。0 永不命中，100 必中。"""
    generator = rng or random
    return generator.random() * 100.0 < probability


def should_fire(
    config: dict[str, Any],
    platform: str = "",
    rng: random.Random | None = None,
) -> bool:
    """综合开关、来源过滤和概率，判断这一轮要不要命中。"""
    if not config.get("enabled", True):
        return False
    sources = config.get("sources") or []
    if sources and platform and platform not in sources:
        return False
    return roll(float(config.get("probability", DEFAULT_PROBABILITY)), rng=rng)
