#!/usr/bin/env python3
"""把本仓库的鲸鱼娘人设和 whalechan 插件装进本机 Hermes（幂等，可反复跑）。

做三件事：
1. 合成 persona/{prefix,user,suffix}.md → `config.yaml` 的 `personalities.whalechan`
2. 把 `display.personality` 设成 `whalechan`
3. 把 `plugins/whalechan` 同步进 `<HERMES_HOME>/plugins/whalechan`

用法：
    python3 apply.py              # 装 / 更新（先自动备份）
    python3 apply.py --check      # 只对比，不写
    python3 apply.py --dry-run    # 说清楚要改什么，不落盘
    python3 apply.py --revert     # 回滚到最近一次备份

改完人设或插件后重跑一次；personality 是会话级拼进 system prompt 的，
老会话不重开看不到新文本（网关侧下一条消息生效，桌面/TUI 要新会话）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HERMES_HOME = Path.home() / ".hermes"
CONFIG = HERMES_HOME / "config.yaml"
BACKUP_DIR = HERMES_HOME / "backups" / "whalechan"

PERSONA = ROOT / "persona"
PLUGIN_SRC = ROOT / "plugins" / "whalechan"
PLUGIN_DST = HERMES_HOME / "plugins" / "whalechan"

PLUGIN_FILES = ("__init__.py", "chance.py", "stickers.py", "plugin.yaml")
TARGET_KEYS = ("personalities.whalechan", "display.personality")


# ---------------------------------------------------------------- persona 合成


def _strip_comments(text: str) -> str:
    """去掉 HTML 注释，免得模板里的示例混进提示词。"""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return _strip_comments(path.read_text(encoding="utf-8")).strip()


def compose_persona() -> str:
    """prefix → 用户自定义 → suffix（硬规矩压在最末，位置本身就是约束）。"""
    parts = [
        _read(PERSONA / "prefix.md"),
        _read(PERSONA / "user.md"),
        _read(PERSONA / "suffix.md"),
    ]
    return "\n\n".join(part for part in parts if part) + "\n"


# ---------------------------------------------------------------- config 读写


def _load_yaml():
    import yaml

    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def _dig(data: dict, dotted: str):
    node = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _write_key(dotted: str, value) -> None:
    sys.path.insert(0, str(HERMES_HOME / "hermes-agent"))
    from hermes_cli.config_backend import write_config_key

    write_config_key(CONFIG, dotted, value)


def current_state() -> dict:
    data = _load_yaml()
    return {
        "persona": _dig(data, "personalities.whalechan") or "",
        "personality": _dig(data, "display.personality") or "",
    }


# ---------------------------------------------------------------- 备份 / 回滚


def backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    meta = BACKUP_DIR / f"state-{stamp}.json"
    state = current_state()
    meta.write_text(json.dumps({"ts": stamp, **state}, ensure_ascii=False, indent=2), encoding="utf-8")
    if PLUGIN_DST.is_dir():
        with tarfile.open(BACKUP_DIR / f"plugin-{stamp}.tar.gz", "w:gz") as tar:
            tar.add(PLUGIN_DST, arcname="whalechan")
    return meta


def _latest(pattern: str) -> Path | None:
    files = sorted(BACKUP_DIR.glob(pattern))
    return files[-1] if files else None


def revert() -> int:
    meta = _latest("state-*.json")
    if not meta:
        print(f"没有备份可回滚：{BACKUP_DIR}")
        return 1
    state = json.loads(meta.read_text(encoding="utf-8"))
    _write_key("personalities.whalechan", state.get("persona") or None)
    _write_key("display.personality", state.get("personality") or None)
    archive = _latest("plugin-*.tar.gz")
    if archive:
        if PLUGIN_DST.exists():
            shutil.rmtree(PLUGIN_DST)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(HERMES_HOME / "plugins")
    print(f"已回滚到 {meta.name}")
    print("提示：网关下一条消息生效；桌面 / TUI 要新会话。")
    return 0


# ---------------------------------------------------------------- 插件同步


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def plugin_drift() -> list[str]:
    drift = []
    for name in PLUGIN_FILES:
        src, dst = PLUGIN_SRC / name, PLUGIN_DST / name
        if not dst.is_file():
            drift.append(f"{name}: 未安装")
        elif _digest(src) != _digest(dst):
            drift.append(f"{name}: 内容不同")
    return drift


def install_plugin() -> None:
    PLUGIN_DST.mkdir(parents=True, exist_ok=True)
    for name in PLUGIN_FILES:
        shutil.copy2(PLUGIN_SRC / name, PLUGIN_DST / name)
    # 只在配置不存在时放一份示例；已有配置绝不覆盖（用户可能调过概率）
    example = PLUGIN_SRC / "config.example.json"
    target = PLUGIN_DST / "config.json"
    if example.is_file() and not target.exists():
        shutil.copy2(example, target)


# ---------------------------------------------------------------- 主流程


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 / 检查 / 回滚鲸鱼娘 Hermes 预设")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只对比，不写")
    group.add_argument("--dry-run", action="store_true", help="说明要改什么，不落盘")
    group.add_argument("--revert", action="store_true", help="回滚到最近一次备份")
    args = parser.parse_args()

    if args.revert:
        return revert()

    if not CONFIG.is_file():
        print(f"找不到 {CONFIG}——这台机器上没装 Hermes？")
        return 1

    persona = compose_persona()
    state = current_state()
    drift = plugin_drift()
    persona_same = state["persona"].strip() == persona.strip()
    personality_same = state["personality"] == "whalechan"

    print(f"persona: {len(persona)} 字符（当前 config 里 {len(state['persona'])}）")
    print(f"display.personality: {state['personality'] or '(空)'} → whalechan")
    print(f"插件差异: {', '.join(drift) if drift else '无'}")

    if args.check:
        ok = persona_same and personality_same and not drift
        print("✓ 已是最新" if ok else "✗ 有差异，跑一次 python3 apply.py")
        return 0 if ok else 2

    if args.dry_run:
        print("（dry-run，未写入）")
        return 0

    if persona_same and personality_same and not drift:
        print("✓ 已是最新，什么都没改")
        return 0

    meta = backup()
    print(f"备份: {meta}")
    _write_key("personalities.whalechan", persona)
    _write_key("display.personality", "whalechan")
    install_plugin()

    state = current_state()
    drift = plugin_drift()
    ok = state["persona"].strip() == persona.strip() and state["personality"] == "whalechan" and not drift
    print("✓ 写入并回读验证通过" if ok else "✗ 回读不一致，检查 config.yaml")
    print("生效方式：网关 / Telegram 下一条消息起；桌面 / TUI 需要新会话，或 /personality whalechan 重选一次。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
