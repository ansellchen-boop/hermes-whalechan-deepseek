"""鲸鱼娘表情包工具 + 每轮掷骰（Hermes 版）。

原版 dsh-whalechan-herself 是 DeepSeek Harness 的插件；这里把它的两件事搬到
Hermes 的插件接口上：

* ``sticker`` 工具：工具名、参数、返回的 ``![名字](链接)`` 与上游一致；
* 每轮掷骰（上游 v0.3.1 的 ``agent/pre-step``）：命中时通过 ``pre_llm_call``
  往这一轮的 user message 前面塞一行提示，人设据此决定发不发。

人设本身走 Hermes 的 ``personalities.whalechan``（本仓库的 persona/ 目录）。
"""

from __future__ import annotations

import logging
from typing import Any

from . import chance
from .stickers import STICKER_TYPES, load_archive, search_stickers

log = logging.getLogger("whalechan")

TOOLSET = "whalechan"

DESCRIPTION = (
    "按场景/心情从社区图库找一张 DeepSeek娘/鲸鱼娘表情包，返回可直接粘贴的 Markdown 图片行"
    "（`![名字](链接)`）、标签和简短描述。这一轮该发表情包时调用；或者图真的贴切时调用。"
    "永远不要自己编图片 URL，也不要用文字描述图片来代替发图。"
)

SCHEMA = {
    "name": "sticker",
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene": {
                "type": "string",
                "description": '中文场景/心情关键词，例如 "摸鱼 累"、"干完活了 讨饭"、"生气 拒绝"、"可爱 比心"。留空则随机。',
            },
            "count": {"type": "integer", "description": "候选张数，1-8，默认 1。"},
            "character": {
                "type": "string",
                "description": '角色 id 过滤，默认 deepseek；"any" 表示全站。',
            },
            "type": {"type": "string", "description": "类型过滤：" + " | ".join(STICKER_TYPES) + "。"},
            "random": {"type": "boolean", "description": "跳过匹配，直接随机挑。"},
            "refresh": {"type": "boolean", "description": "重新下载索引，不吃 7 天缓存。"},
        },
    },
}


def _render(result: dict) -> str:
    stickers = result.get("stickers") or []
    if not stickers:
        return "图库里没有符合条件的图。"
    head = (
        f"找到 {len(stickers)} 张（图库共 {result['total']} 张）"
        if result.get("matched")
        else f"没有贴合的匹配，随机给了 {len(stickers)} 张："
    )
    lines = [head]
    for i, sticker in enumerate(stickers, 1):
        tags = f" [{','.join(map(str, sticker['tags']))}]" if sticker.get("tags") else ""
        lines.append(f"{i}. {sticker['name']}{tags}\n{sticker['markdown']}")
    return "\n".join(lines)


def _handler(args: Any = None, **kwargs: Any) -> str:
    args = args if isinstance(args, dict) else {}
    try:
        index = load_archive(refresh=args.get("refresh") is True)
    except Exception as exc:  # noqa: BLE001 - 模型需要看到真实原因
        log.warning("sticker: 索引不可用: %s", exc)
        return f"表情包索引拿不到：{exc}"
    try:
        result = search_stickers(
            index,
            {
                "scene": args.get("scene"),
                "count": args.get("count", 1),
                "character": args.get("character"),
                "type": args.get("type"),
                "random": args.get("random"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("sticker: 检索失败: %s", exc)
        return f"表情包检索失败：{exc}"
    return _render(result)


def _on_pre_llm_call(**kwargs: Any) -> dict[str, str] | None:
    """每一轮（turn）开头掷一次骰；命中就给这一轮塞一行提示。

    - 子代理会话（有 parent_session_id）不掷，免得子任务也去发表情包；
    - 任何异常都吞掉：掷骰失败不能把正常轮次搞挂。
    """
    try:
        if kwargs.get("parent_session_id"):
            return None
        config = chance.load_config()
        platform = str(kwargs.get("platform") or "")
        if chance.should_fire(config, platform=platform):
            return {"context": chance.HIT_CONTEXT}
    except Exception as exc:  # noqa: BLE001
        log.warning("whalechan: 掷骰失败（已忽略）: %s", exc)
    return None


def register(ctx: Any) -> None:
    """Hermes entry point — called once per (re)load."""
    ctx.register_tool(
        name="sticker",
        toolset=TOOLSET,
        schema=SCHEMA,
        handler=_handler,
        description="鲸鱼娘表情包：按场景/心情找图，返回 Markdown 图片",
        emoji="🐳",
    )
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
