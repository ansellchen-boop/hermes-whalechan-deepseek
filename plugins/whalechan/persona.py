"""人设载体：写进 ``<HERMES_HOME>/SOUL.md``，不再住 ``agent.personalities``。

**为什么换载体（2026-11-01）**

用户要的是「身份是一个文件、常驻、不靠配置项」。Hermes 里两条路都试过：

* ``agent.personalities.<name>`` —— 走 ephemeral system prompt，每次 API 调用
  拼在 system prompt **最末尾**（``agent/turn_context.py``）。位置最好，但它是
  「可切换设定」：一条 ``/personality`` 就能换走，且 cron 定时任务那条构造路径
  根本不传 ``ephemeral_system_prompt``（``cron/scheduler.py`` 的
  ``_construct_cron_agent``），人设在后台任务里等于不存在。
* ``SOUL.md`` —— 走 identity slot，是 system prompt 的**第一段**
  （``agent/system_prompt.py``：有 SOUL 就整段替换 ``DEFAULT_AGENT_IDENTITY``），
  而且 ``cron/scheduler.py`` 显式传 ``load_soul_identity=True``，后台任务也带着。

代价是位置：站在最前面，压不住后面几十 K 的工具定义和上下文。所以最吃位置的
三条（出声报进度、结尾三段小结、每轮一处悄悄话）已经从 ``persona/suffix.md``
挪进插件的「节奏骰」，由 ``pre_llm_call`` 每轮往 user message 末尾补——
那个位置比 system prompt 末尾还近。

**自举只做一次**

写成功后落一个 ``persona-state.json`` 标记；之后 SOUL.md 里没了我也不会再抢回来。
要重新装，跑 ``/whalechan sync``。SOUL.md 里如果是别人写的自定义内容
（非出厂身份、也不含本预设特征），无条件拒绝覆盖。
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

#: config 里的旧载体名。保留它只是为了「装 SOUL 之后把旧键清掉」，
#: 别让同一份人设注入两遍。
PERSONALITY_NAME = "whalechan"

#: 拼接顺序：前缀（身份/说话方式）→ 用户追加设定 → 后缀（跨场景的硬规矩）。
SECTION_FILES = ("prefix.md", "user.md", "suffix.md")

#: 自举标记文件名，跟 config.json 同目录，不进仓库。
MARKER_FILE = "persona-state.json"

COMPOSE_NOTE = "prefix → user → suffix 拼成一份，写进 <HERMES_HOME>/SOUL.md"

#: 出厂身份的识别标记。SOUL.md 里是这个 = 用户没写过东西，可以安全覆盖。
_FACTORY_PREFIX = "You are Hermes Agent"
_FACTORY_MAX_CHARS = 1200


def package_dir() -> Path:
    """插件自己的目录（``config.yaml`` 的兄弟不是它，别混）。"""
    return Path(__file__).resolve().parent


def hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME")
    return Path(home) if home else Path.home() / ".hermes"


def config_file() -> Path:
    return hermes_home() / "config.yaml"


def soul_file() -> Path:
    """人设本体：``<HERMES_HOME>/SOUL.md``。"""
    return hermes_home() / "SOUL.md"


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


# ---------------------------------------------------------------- 读 SOUL


def read_soul() -> str:
    """当前 SOUL.md 内容；不存在就是空串。读失败也不抛。"""
    try:
        return soul_file().read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _looks_factory(text: str) -> bool:
    """是不是出厂那句英文身份（用户从没写过）。"""
    head = text.lstrip()
    return head.startswith(_FACTORY_PREFIX) and len(text) <= _FACTORY_MAX_CHARS


def _looks_ours(text: str) -> bool:
    """是不是本预设写进去的（含鲸鱼娘特征）。"""
    return "鲸鱼娘" in text


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


def read_state(config_path: Path | str | None = None) -> dict[str, Any]:
    """读当前状态：SOUL.md 里多少字、config 里还留着旧键没有、选中了哪个人设。"""
    path = Path(config_path) if config_path else config_file()
    data = _load_doc(path)
    soul = read_soul()
    legacy_agent = _dig(data, f"agent.personalities.{PERSONALITY_NAME}")
    legacy_root = _dig(data, f"personalities.{PERSONALITY_NAME}")
    display = _dig(data, "display.personality")
    return {
        "soul": soul,
        "chars": len(soul),
        "legacy": legacy_agent is not None or legacy_root is not None,
        "structured": isinstance(legacy_agent, dict) or isinstance(legacy_root, dict),
        "display": str(display).strip() if isinstance(display, (str, int, float)) else "",
    }


# ---------------------------------------------------------------- 写


def _default_writer(config_path: Path, dotted: str, value: Any) -> None:
    """走 Hermes 自己的配置写入（原子写、保留注释），不手搓 YAML。

    现在只用它**清掉**旧的 personality 键，不再拿它写人设。
    """
    import sys

    root = hermes_home() / "hermes-agent"
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from hermes_cli.config_backend import write_config_key

    write_config_key(config_path, dotted, value)


def write_soul(text: str) -> None:
    """原子写 SOUL.md；旧内容先留一份带时间戳的备份。"""
    target = soul_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        old = target.read_text(encoding="utf-8", errors="replace")
        if old.strip() and old.strip() != text.strip():
            backup = target.with_name(f"SOUL.md.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            try:
                backup.write_text(old, encoding="utf-8")
            except OSError as exc:  # noqa: BLE001
                log.warning("whalechan: SOUL.md 备份失败（继续写）: %s", exc)
    tmp = target.with_name("SOUL.md.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


class _Lock:
    """跨进程互斥：gateway / dashboard / CLI 会同时 register，别一起写。

    拿不到 flock（非 POSIX 或异常）就退化成不加锁——写的是同一个幂等文件，
    最坏是白写一次。
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
            json.dumps({"bootstrap": "done", "carrier": "soul",
                        "chars": chars, "at": int(time.time())},
                       ensure_ascii=False, indent=2) + "\n",
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
    """把插件自带的人设写进 ``SOUL.md``，并清掉 config 里的旧载体。

    ``force=True`` 时无条件覆盖（``/whalechan sync`` 走这条）；
    否则只在「从没装过」时写，之后一律不动。
    """
    path = Path(config_path) if config_path else config_file()
    text = compose(root)
    if not text:
        return {"action": "failed", "chars": 0,
                "message": f"人设文件缺失：{package_dir() / 'persona'} 里没有可用的 prefix/user/suffix"}

    state = read_state(path)
    soul = state["soul"]
    same = soul.strip() == text.strip()
    marker = _read_marker()

    # 保护：SOUL.md 里是别人写的内容（既不是出厂身份，也不是本预设）就别动——
    # force 也不动。真要把鲸鱼娘压上去，先自己备份、把文件清空，再跑 sync。
    foreign = bool(soul) and not same and not _looks_ours(soul) and not _looks_factory(soul)
    if foreign:
        return {"action": "refused", "chars": state["chars"],
                "message": ("SOUL.md 里是别的内容（既不是出厂身份，也不含本预设特征）——"
                            "不敢覆盖。要真换成鲸鱼娘，先自己备份再清空，然后 /whalechan sync")}

    if not force:
        if same and not state["legacy"]:
            return {"action": "already", "chars": state["chars"],
                    "message": f"人设已是最新（SOUL.md {state['chars']} 字）"}
        if soul and not same and _looks_ours(soul):
            return {"action": "drift", "chars": state["chars"],
                    "message": (f"SOUL.md 里是 {state['chars']} 字，插件这边 {len(text)} 字——"
                                "不敢自动覆盖（可能手改过），要同步跑 /whalechan sync")}
        if marker.get("bootstrap") == "done":
            return {"action": "removed-by-user", "chars": 0,
                    "message": "SOUL.md 里的人设被你移除过，不自动装回；要恢复跑 /whalechan sync"}

    with _Lock(state_file().with_suffix(".lock")):
        # 先写人设，再清旧键：顺序反了的话中途失败会两头都空。
        write_soul(text)
        write = writer or _default_writer
        for key in (f"agent.personalities.{PERSONALITY_NAME}", f"personalities.{PERSONALITY_NAME}"):
            value = _dig(_load_doc(path), key)
            # dict（structured）是手写的东西，不替用户删；只清纯文本形态的旧载体。
            if value is not None and not isinstance(value, dict):
                write(path, key, None)
        # display.personality 指向一个已经不存在的人设名会让 Hermes 每轮去查表；
        # 清空 = 不加任何 overlay，正是我们要的。
        if state["display"] == PERSONALITY_NAME:
            write(path, "display.personality", None)

    after = read_state(path)
    ok = after["soul"].strip() == text.strip()
    if ok:
        _write_marker(len(text))
    action = "updated" if soul else "installed"
    return {
        "action": action if ok else "failed",
        "chars": after["chars"],
        "message": (
            f"人设已写入 SOUL.md（{after['chars']} 字），旧 personality 键已清理；新会话生效"
            if ok
            else "写入后回读不一致，检查 SOUL.md（其它功能不受影响）"
        ),
    }


def status(root: Path | str | None = None) -> dict[str, Any]:
    """给 ``/whalechan`` 状态行用：插件里多少字、SOUL.md 里多少字、对齐没有。"""
    local = compose(root).strip()
    state = read_state()
    return {"local_chars": len(local), "soul_chars": state["chars"],
            "legacy": state["legacy"], "display": state["display"],
            "same": bool(state["soul"]) and state["soul"].strip() == local.strip()}
