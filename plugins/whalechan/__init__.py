"""鲸鱼娘表情包工具 + 每轮掷骰（Hermes 版）。

原版 dsh-whalechan-herself 是 DeepSeek Harness 的插件；这里把它的两件事搬到
Hermes 的插件接口上：

* ``sticker`` 工具：工具名、参数、返回的 ``![名字](链接)`` 与上游一致；
* 每轮掷骰（上游 v0.3.1 的 ``agent/pre-step``）：命中时通过 ``pre_llm_call``
  往这一轮的 user message **末尾**追加一行提示（宿主是 ``content + "\n\n" + injection``，
  不是插在前面），人设据此决定发不发。

人设本身走 Hermes 的 ``personalities.whalechan``，但文本是插件自带的
``persona/`` 三段：首次加载时 ``persona.bootstrap()`` 自动写进 config，
之后改人设用 ``/whalechan sync``。为什么不能塞进 ``register_system_prompt_section``
（位置只允许 after_memory、4000 字上限、会话级冻结）见 ``persona.py`` 顶部说明。
"""

from __future__ import annotations

import logging
from typing import Any

from . import chance, persona
from .stickers import STICKER_TYPES, load_archive, materialize, search_stickers

log = logging.getLogger("whalechan")

TOOLSET = "whalechan"

DESCRIPTION = (
    "按场景/心情从社区图库找一张 DeepSeek娘/鲸鱼娘表情包。每张图会给一条 `MEDIA:/绝对路径`："
    "**原样单独占一行发出去，不要再包成 `![名字](路径)`** —— 包了方括号里的字会漏成散字显示在图片角落。"
    "这一轮该发表情包时调用；或者图真的贴切时调用。永远不要自己编图片 URL，也不要用文字描述图片来代替发图。"
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
    sent = 0
    for sticker in stickers:
        tags = f" [{','.join(map(str, sticker['tags']))}]" if sticker.get("tags") else ""
        # 只给裸 MEDIA: 行，落不了地就跳过这张。
        # 绝不退回 sticker["markdown"]（`![名字](外链)`）—— 模型会原样抄进回复，
        # 方括号里的字就漏成图注散字。2026-10-31 连犯三次，用户两次报障，
        # 根源就是这条兜底 + 人设/工具描述当时都写着「返回 Markdown 图片行」。
        body = sticker.get("media")
        if not body:
            continue
        sent += 1
        lines.append(f"{sent}. {sticker['name']}{tags}\n{body}")
    if not sent:
        return "图没落到本地，这一轮先别发（不要用外链兜底）。"
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

    # 落地到本机再给：客户端直连外链可能被墙，本机路径不经过网络。
    # 单张失败只退回外链，不影响其它候选。
    for sticker in result.get("stickers") or []:
        local = materialize(sticker)
        if local:
            sticker["media"] = f"MEDIA:{local}"
    return _render(result)


def _is_early_turn(kwargs: dict[str, Any]) -> bool:
    """会话前两轮。

    宿主的 ``is_first_turn``（``agent/turn_context.py``）只覆盖第一轮，
    第二轮要自己数 user 消息——而这两轮恰恰是后面几十轮的参照样本。
    """
    if kwargs.get("is_first_turn"):
        return True
    users = 0
    for message in kwargs.get("conversation_history") or []:
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
        if role == "user":
            users += 1
            if users >= 2:
                return False
    return True


def _on_pre_llm_call(**kwargs: Any) -> dict[str, str] | None:
    """每一轮（turn）开头掷一次骰；命中就给这一轮塞一行提示。

    - 子代理会话（有 parent_session_id）不掷，免得子任务也去发表情包；
    - 用户写的「追加设定」每轮现读，写进同一个 context，改完下一轮生效；
    - 前两轮节拍强制命中（概率为 0 时除外）：锚点不交给骰子；
    - 任何异常都吞掉：掷骰失败不能把正常轮次搞挂。
    """
    try:
        if kwargs.get("parent_session_id"):
            return None
        config = chance.load_config()
        parts: list[str] = []
        custom = config.get("custom") or ""
        if custom:
            parts.append(f"{chance.CUSTOM_HEADER}\n\n{custom}")
        platform = str(kwargs.get("platform") or "")
        early = _is_early_turn(kwargs)
        # 两条骰子互相独立：表情包管「发不发图」，节拍管「嘴还在不在」。
        sticker_hit = chance.should_fire(config, platform=platform)
        beat_hit = chance.should_fire_beat(config, platform=platform, early=early)
        if sticker_hit:
            parts.append(chance.HIT_CONTEXT)
        if beat_hit:
            # 命中时换一种说法：同一条指令原样重复会被历史自举磨成背景噪音，
            # 新鲜度比频率有用（见 chance.py 里 BEAT_CONTEXTS 的注释）。
            parts.append(chance.BEAT_EARLY_CONTEXT if early else chance.pick_beat())
        # 命中记录：注入的这行不进 state.db 的 user message，事后无法从库里
        # 区分「命中轮」和「未命中轮」，也就没法判断节拍骰到底有没有用。
        _log_roll(
            session_id=str(kwargs.get("session_id") or ""),
            platform=platform,
            beat=beat_hit,
            sticker=sticker_hit,
            early=early,
        )
        if parts:
            return {"context": "\n\n".join(parts)}
    except Exception as exc:  # noqa: BLE001
        log.warning("whalechan: 掷骰失败（已忽略）: %s", exc)
    return None


#: 命中日志：一行一次掷骰，测量脚本按 session_id + 时间戳跟 state.db 的回合对齐做 A/B。
ROLL_LOG = "roll-log.jsonl"
_ROLL_LOG_MAX_BYTES = 512 * 1024


def _log_roll(*, session_id: str, platform: str, beat: bool, sticker: bool, early: bool) -> None:
    """追加一行命中记录。写失败只记 debug，绝不影响这一轮。

    带 ``session_id`` 是为了让测量脚本精确归属：老版本只按时间戳找「最近的前一个
    回合」，跨会话会错配（实测 5 条日志只归属上 4 个回合，还查不出丢的是哪条）。
    超过上限是**轮转**不是删除——直接删会把测量窗口静默清零。
    """
    try:
        path = chance.config_path().with_name(ROLL_LOG)
        if path.is_file() and path.stat().st_size > _ROLL_LOG_MAX_BYTES:
            path.replace(path.with_name(ROLL_LOG + ".1"))
        import json
        import time

        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {
                    "ts": time.time(),
                    "session_id": session_id,
                    "platform": platform,
                    "beat": beat,
                    "sticker": sticker,
                    "early": early,
                },
                ensure_ascii=False,
            ) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.debug("whalechan: 命中日志写不了（不影响掷骰）: %s", exc)


_USAGE = (
    "用法：/whalechan 80 · /whalechan off · /whalechan on · /whalechan beat 55 · "
    "/whalechan custom <文本> · /whalechan custom clear · /whalechan sync"
)


def _persona_line() -> str:
    """状态行：插件里多少字、config 里多少字、选中没有。"""
    try:
        info = persona.status()
    except Exception as exc:  # noqa: BLE001 - 读配置失败不该让状态命令挂掉
        return f"人设：读不到配置（{exc}）"
    head = f"人设：插件自带 {info['local_chars']} 字"
    if not info["config_chars"]:
        return f"{head} · config 里没装 → /whalechan sync"
    where = f"config {info['config_chars']} 字（{info['source']}），display.personality={info['display'] or '(空)'}"
    if not info["same"]:
        return f"{head} · {where} → 和插件不一致，/whalechan sync 同步"
    if info["display"] != persona.PERSONALITY_NAME:
        return f"{head} · {where} → 没选中，/whalechan sync 会重选"
    return f"{head} · 已同步（{where}）"


def _cmd_whalechan(raw_args: str = "") -> str:
    """会话内 ``/whalechan``：替代上游的设置页（Hermes 插件没有 web route）。"""
    args = (raw_args or "").strip()
    config = chance.load_config()
    if not args:
        custom = config.get("custom") or ""
        state = "开" if config.get("enabled", True) else "关"
        tail = f"「{custom[:24]}…」" if len(custom) > 24 else (f"「{custom}」" if custom else "空")
        sources_line = chance.describe_sources(config)
        return (
            f"表情包掷骰：{state} · 概率 {config.get('probability')}%\n"
            f"人设节拍：{config.get('beat_probability')}%（0 关；前两轮强制命中；跟表情包互相独立）\n"
            + (f"{sources_line}\n" if sources_line else "")
            + f"追加设定：{len(custom)}/{chance.DEFAULT_CUSTOM_MAX} 字，{tail}\n"
            f"{_persona_line()}\n"
            f"{_USAGE}"
        )
    lowered = args.lower()
    head = lowered.split(None, 1)[0] if lowered else ""
    if lowered in {"sync", "sync force", "重装"}:
        return persona.bootstrap(force=True)["message"]
    if lowered in {"off", "关"}:
        config = chance.save_config({"enabled": False})
        return "表情包掷骰：关。要开回来就 /whalechan on"
    if lowered in {"on", "开"}:
        config = chance.save_config({"enabled": True})
        return f"表情包掷骰：开，概率 {config.get('probability')}%"
    if lowered in {"custom clear", "clear"}:
        chance.save_config({"custom": ""})
        return "追加设定已清空，下一轮生效。"
    if lowered == "custom":
        custom = config.get("custom") or ""
        return "追加设定：空。" + _USAGE if not custom else f"追加设定（{len(custom)} 字）：\n{custom}"
    if head == "custom":
        text = args[len("custom"):].strip()
        if not text:
            return _USAGE
        config = chance.save_config({"custom": text})
        return f"追加设定已写入（{len(config.get('custom') or '')} 字），下一轮生效。"
    if lowered.startswith("beat"):
        text = args[len("beat"):].strip()
        if not text:
            return f"人设节拍：{config.get('beat_probability')}%（0 关，100 每轮都提醒）"
        try:
            value = float(text)
        except ValueError:
            return f"看不懂「{text}」。" + _USAGE
        config = chance.save_config({"beat_probability": value})
        return f"人设节拍钉在 {config.get('beat_probability')}%（0 关；跟表情包那条骰子各掷各的）"
    try:
        value = float(args)
    except ValueError:
        return f"看不懂「{args}」。" + _USAGE
    config = chance.save_config({"probability": value})
    return f"概率改成 {config.get('probability')}%（0 等于关，100 每轮都发）"


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
    ctx.register_command(
        "whalechan",
        _cmd_whalechan,
        description="鲸鱼娘表情包设置：概率 / 开关 / 追加设定 / 人设同步",
        args_hint="[80|off|on|beat 55|custom <文本>|sync]",
    )
    # 人设自举：只在「config 里从没装过」时写一次。失败不能拖垮插件加载。
    try:
        result = persona.bootstrap()
        log.info("whalechan: 人设 %s（%s 字）— %s", result["action"], result["chars"], result["message"])
    except Exception as exc:  # noqa: BLE001
        log.warning("whalechan: 人设自举失败（插件其余功能照常）: %s", exc)
