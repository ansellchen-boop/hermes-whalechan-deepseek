"""人设自举：插件自带 ``persona/`` 三段，首次加载时装进 Hermes 的 personalities。

**为什么不用 ``register_system_prompt_section``**

那个接口（``hermes_cli/plugins.py``）的 ``position`` 只有 ``after_memory`` 一个合法值，
单节上限 4000 字符，而且 docstring 写明是 "frozen into each new session prompt"——会话级冻结。
渲染顺序是 ``skills → memory → 插件段落 → profile → 时间戳 → 环境提示``
（``agent/system_prompt.py``），人设会被夹在中间。

personality 走的是 ephemeral system prompt，每次 API 调用拼在 system prompt **最末尾**
（``agent/turn_context.py``：``effective_system + "\\n\\n" + agent.ephemeral_system_prompt``），
不进缓存前缀，改完下一轮就生效。所以人设必须落在 ``config.yaml``，插件只负责「装」。

**自举只做一次**

写成功后落一个 ``persona-state.json`` 标记；之后 config 里没了我也不会再抢回来——
那多半是你主动换掉或删掉的。要重新装，跑 ``/whalechan sync``。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("whalechan")

#: personality 名字，同时是插件名；``display.personality`` 写的就是它。
PERSONALITY_NAME = "whalechan"

#: 拼接顺序：前缀（身份/说话方式）→ 用户追加设定 → 后缀（每轮硬规矩，压最末）。
SECTION_FILES = ("prefix.md", "user.md", "suffix.md")

#: 自举标记文件名，跟 config.json 同目录，不进仓库。
MARKER_FILE = "persona-state.json"

COMPOSE_NOTE = "prefix → user → suffix；suffix 硬规矩落在最末，位置本身就是约束"


def package_dir() -> Path:
    """插件自己的目录（``config.yaml`` 的兄弟不是它，别混）。"""
    return Path(__file__).resolve().parent


def hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME")
    return Path(home) if home else Path.home() / ".hermes"


def config_file() -> Path:
    return hermes_home() / "config.yaml"


def state_file() -> Path:
    return hermes_home() / "plugins" / "whalechan" / MARKER_FILE


# ---------------------------------------------------------------- persona 合成


def compose(root: Path | str | None = None) -> str:
    """合成人设三段；HTML 注释（模板里的示例）不算字数、不进提示词。"""
    base = Path(root) if root else package_dir() / "persona"
    parts: list[str] = []
    for name in SECTION_FILES:
        path = base / name
        if not path.is_file():
            continue
        text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).strip()
        if text:
            parts.append(text)
    return ("\n\n".join(parts) + "\n") if parts else ""


# ---------------------------------------------------------------- 读 config


def _load_doc(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 坏 YAML 不能让插件加载失败
        log.warning("whalechan: %s 解析失败: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _dig(data: Any, dotted: str) -> Any:
    node = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _prompt_text(value: Any) -> str:
    """config 里的人设可能是 str / list / dict（结构化人设），统一成文本。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        # 结构化人设（dict）：`str(dict)` 永远等于不了 compose() 的纯文本，
        # 拿它比对会把配置永久判成 drift，再被 sync 直接覆盖掉。所以这里返回空，
        # 由 read_state 标成 structured，bootstrap 遇到就拒绝覆盖。
        return ""
    return ""


def read_state(config_path: Path | str | None = None) -> dict[str, Any]:
    """读当前配置：人设文本、它在哪一层、``display.personality``。"""
    path = Path(config_path) if config_path else config_file()
    data = _load_doc(path)
    agent_raw = _dig(data, f"agent.personalities.{PERSONALITY_NAME}")
    root_raw = _dig(data, f"personalities.{PERSONALITY_NAME}")
    agent_value = _prompt_text(agent_raw)
    root_value = _prompt_text(root_raw)
    # 和 hermes_cli.personality.available_personalities 一致：agent.personalities 优先。
    if agent_value:
        persona, source = agent_value, "agent"
    elif root_value:
        persona, source = root_value, "root"
    else:
        persona, source = "", ""
    display = _dig(data, "display.personality")
    return {
        "persona": persona,
        "source": source,
        "display": str(display).strip() if isinstance(display, (str, int, float)) else "",
        "chars": len(persona),
        # 配置里存的是结构化人设（dict）：读不出纯文本，任何自动写入都得绕开它。
        "structured": isinstance(agent_raw, dict) or isinstance(root_raw, dict),
    }


# ---------------------------------------------------------------- 写 config


def _default_writer(config_path: Path, dotted: str, value: Any) -> None:
    """走 Hermes 自己的配置写入（原子写、保留注释），不手搓 YAML。

    必须把 ``<HERMES_HOME>/hermes-agent`` 插到 ``sys.path`` 最前面，不能指望
    「``hermes_cli`` 能 import 就行」：某些安装是 editable finder（``__editable__``
    只认包名），``config_backend`` 内部 ``from utils import …``、``utils`` 再
    ``import hermes_yaml``——顶层模块 hermes_yaml 不在 finder 的映射里，
    会报 ``No module named 'hermes_yaml'``。
    """
    import sys

    root = hermes_home() / "hermes-agent"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from hermes_cli.config_backend import write_config_key

    write_config_key(config_path, dotted, value)


class _Lock:
    """跨进程互斥：gateway / dashboard / CLI 会同时 register，别一起写 config。

    拿不到 flock（非 POSIX 或异常）就退化成不加锁——写的是同一个幂等键，最坏是白写一次。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> "_Lock":
        try:
            import fcntl

            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = open(self.path, "a+", encoding="utf-8")
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        except Exception as exc:  # noqa: BLE001
            log.debug("whalechan: 人设自举未加锁（%s）", exc)
        return self

    def __exit__(self, *exc_info: Any) -> None:
        if self._handle is None:
            return
        try:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
        self._handle.close()
        self._handle = None


def _read_marker() -> dict[str, Any]:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_marker(chars: int) -> None:
    target = state_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps({"bootstrap": "done", "chars": chars, "at": int(time.time())}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target)
    except OSError as exc:
        log.warning("whalechan: 自举标记写不了（不影响人设）: %s", exc)


# ---------------------------------------------------------------- 自举


def bootstrap(
    *,
    force: bool = False,
    config_path: Path | str | None = None,
    writer: Callable[[Path, str, Any], None] | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """把插件自带的人设装进 ``agent.personalities.<name>``，必要时选中它。

    ``force=True`` 时无条件覆盖（``/whalechan sync`` 走这条）；
    否则只在「从没装过」时写，之后一律不动——包括你主动删掉之后。
    """
    path = Path(config_path) if config_path else config_file()
    text = compose(root)
    if not text:
        return {"action": "failed", "chars": 0,
                "message": f"人设文件缺失：{package_dir() / 'persona'} 里没有可用的 prefix/user/suffix"}

    state = read_state(path)
    if state["structured"]:
        return {"action": "failed", "chars": state["chars"],
                "message": (f"config 里的 personalities.{PERSONALITY_NAME} 是结构化（dict）人设，"
                            "插件不会拿纯文本去覆盖它；要换回插件自带文本，先手动删掉那一段再跑 sync")}
    marker = _read_marker()
    same = state["persona"].strip() == text.strip()
    selected = state["display"] == PERSONALITY_NAME

    if not force:
        if state["persona"] and same and selected:
            return {"action": "already", "chars": state["chars"],
                    "message": f"人设已是最新（{state['chars']} 字，来源 {state['source']}）"}
        if state["persona"] and not same:
            return {"action": "drift", "chars": state["chars"],
                    "message": (f"config 里是 {state['chars']} 字，插件这边 {len(text)} 字——"
                                "不敢自动覆盖（可能是你手改的），要同步跑 /whalechan sync")}
        if state["persona"] and same and not selected:
            return {"action": "unselected", "chars": state["chars"],
                    "message": f"人设还在 config 里，但 display.personality={state['display'] or '(空)'}"}
        if marker.get("bootstrap") == "done":
            return {"action": "removed-by-user", "chars": 0,
                    "message": "人设被你移除过，不自动装回；要恢复跑 /whalechan sync"}

    write = writer or _default_writer
    with _Lock(state_file().with_suffix(".lock")):
        write(path, f"agent.personalities.{PERSONALITY_NAME}", text)
        # 只在「从来没选中过」时补一次，force 也不抢：`display.personality` 是
        # 「用哪个人设」的开关，跟「人设文本同步」是两件事——你在 /personality
        # 里换过别人，跑 sync 不该被切回来。
        if not state["display"]:
            write(path, "display.personality", PERSONALITY_NAME)

    after = read_state(path)
    ok = after["persona"].strip() == text.strip()
    if ok:
        _write_marker(len(text))
    action = "installed" if not state["persona"] else "updated"
    if ok and after["display"] == PERSONALITY_NAME:
        tail = f"并已选中（display.personality={PERSONALITY_NAME}）；新会话生效"
    elif ok:
        tail = (f"但没动 display.personality（当前 {after['display'] or '(空)'}）——"
                f"要用它跑 /personality {PERSONALITY_NAME}；新会话生效")
    else:
        tail = ""
    return {
        "action": action if ok else "failed",
        "chars": after["chars"],
        "message": (
            f"人设已写入 agent.personalities.{PERSONALITY_NAME}（{after['chars']} 字），{tail}"
            if ok
            else "写入后回读不一致，检查 config.yaml（人设没生效，插件其余功能不受影响）"
        ),
    }


def status(root: Path | str | None = None) -> dict[str, Any]:
    """给 ``/whalechan`` 状态行用：插件里多少字、config 里多少字、选中没有。

    字数按 ``strip()`` 后算，跟写进 config、又被 ``_prompt_text`` 读出来的口径一致，
    免得状态里出现「插件 3472 / config 3471」这种差一个换行的假差异。
    """
    local = compose(root).strip()
    state = read_state()
    return {"local_chars": len(local), "config_chars": state["chars"],
            "source": state["source"], "display": state["display"],
            "same": bool(state["persona"]) and state["persona"].strip() == local.strip()}
