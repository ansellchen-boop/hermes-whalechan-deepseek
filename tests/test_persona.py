"""persona.py 的单测：人设合成 + 自举（不联网，不写真实 ~/.hermes）。

跑法：``python3 -m unittest discover -s tests -v``（在仓库根目录）

人设载体从 2026-11-01 起是 ``<HERMES_HOME>/SOUL.md``（身份槽），
不再是 ``agent.personalities.whalechan``。这里的用例跟着换：断言 SOUL.md 的内容，
以及「config 里的旧键被清掉」——两处同时注入会互相稀释。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "whalechan"
sys.path.insert(0, str(PLUGIN_DIR))

import persona  # noqa: E402

import yaml  # noqa: E402


def _fake_writer_factory(config_path: Path):
    """模拟 hermes_cli.config_backend.write_config_key：设/删一个点号键。"""

    def writer(_path: Path, dotted: str, value):
        data = {}
        if config_path.is_file():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        node = data
        parts = dotted.split(".")
        for key in parts[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    return writer


class Sandbox(unittest.TestCase):
    """每个用例一个临时 HERMES_HOME + 一份人设目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.config = self.home / "config.yaml"
        self.soul = self.home / "SOUL.md"
        self.writer = _fake_writer_factory(self.config)

        self.persona_dir = self.home / "persona"
        self.persona_dir.mkdir()
        (self.persona_dir / "prefix.md").write_text("前缀<!-- 注释不算 -->", encoding="utf-8")
        (self.persona_dir / "user.md").write_text("用户设定", encoding="utf-8")
        (self.persona_dir / "suffix.md").write_text("硬规矩", encoding="utf-8")

        env = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def bootstrap(self, **kwargs):
        kwargs.setdefault("writer", self.writer)
        kwargs.setdefault("root", self.persona_dir)
        kwargs.setdefault("config_path", self.config)
        return persona.bootstrap(**kwargs)

    def read_config(self):
        return yaml.safe_load(self.config.read_text(encoding="utf-8")) or {}

    def read_soul(self):
        return self.soul.read_text(encoding="utf-8") if self.soul.is_file() else ""

    def write_soul(self, text: str):
        self.soul.write_text(text, encoding="utf-8")


class ComposeTest(Sandbox):
    def test_order_and_comment_stripping(self):
        self.assertEqual(persona.compose(self.persona_dir), "前缀\n\n用户设定\n\n硬规矩\n")

    def test_missing_file_is_skipped(self):
        (self.persona_dir / "user.md").unlink()
        self.assertEqual(persona.compose(self.persona_dir), "前缀\n\n硬规矩\n")

    def test_empty_dir_returns_empty(self):
        empty = self.home / "empty"
        empty.mkdir()
        self.assertEqual(persona.compose(empty), "")


class BootstrapTest(Sandbox):
    def test_first_run_writes_soul(self):
        result = self.bootstrap()
        self.assertEqual(result["action"], "installed")
        self.assertEqual(self.read_soul(), persona.compose(self.persona_dir))
        self.assertTrue((self.home / "plugins" / "whalechan" / "persona-state.json").is_file())

    def test_first_run_clears_legacy_config_keys(self):
        """旧载体留着就是两份人设打对台：装 SOUL 的同时必须清掉。"""
        self.config.write_text(yaml.safe_dump(
            {"agent": {"personalities": {"whalechan": "旧的人设"}},
             "display": {"personality": "whalechan"}}, allow_unicode=True), encoding="utf-8")
        result = self.bootstrap()
        self.assertEqual(result["action"], "installed")
        config = self.read_config()
        self.assertNotIn("whalechan", (config.get("agent") or {}).get("personalities") or {})
        self.assertNotIn("personality", config.get("display") or {})

    def test_second_run_is_noop(self):
        self.bootstrap()
        before = self.read_soul()
        result = self.bootstrap()
        self.assertEqual(result["action"], "already")
        self.assertEqual(self.read_soul(), before)

    def test_removed_by_user_stays_removed(self):
        """用户把 SOUL.md 清掉过，就别自动装回去——那是他的意思。"""
        self.bootstrap()
        self.soul.unlink()
        result = self.bootstrap()
        self.assertEqual(result["action"], "removed-by-user")
        self.assertEqual(self.read_soul(), "")

    def test_legacy_marker_without_carrier_does_not_block_migration(self):
        """0.4.x 的 marker 没有 ``carrier`` 字段——那时人设还住 config。

        把它当成「用户删过」会让从 0.4 升级过来的机器永远装不上（复审抓到）：
        SOUL 空着、旧键还在、插件一句话不说。
        """
        marker_dir = self.home / "plugins" / "whalechan"
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / "persona-state.json").write_text(
            json.dumps({"bootstrap": "done", "chars": 3472, "at": 1793208774}),
            encoding="utf-8",
        )
        result = self.bootstrap()
        self.assertEqual(result["action"], "installed")
        self.assertEqual(self.read_soul(), persona.compose(self.persona_dir))

    def test_force_restores_after_removal(self):
        self.bootstrap()
        self.soul.unlink()
        result = self.bootstrap(force=True)
        self.assertIn(result["action"], {"installed", "updated"})
        self.assertEqual(self.read_soul(), persona.compose(self.persona_dir))

    def test_hand_edited_soul_is_not_overwritten_without_force(self):
        """SOUL.md 被改过（但仍是本预设写的）→ 判 drift，等 force。"""
        self.bootstrap()
        self.write_soul("鲸鱼娘手改过的一段\n")
        result = self.bootstrap()
        self.assertEqual(result["action"], "drift")
        self.assertEqual(self.read_soul(), "鲸鱼娘手改过的一段\n")

    def test_foreign_soul_is_refused(self):
        """SOUL.md 里是别人写的内容：无条件拒绝，连 force 都不碰。"""
        self.write_soul("# 我的自定义身份\n\n你是一个严谨的代码审查员。\n")
        result = self.bootstrap(force=True)
        self.assertEqual(result["action"], "refused")
        self.assertIn("不敢覆盖", result["message"])
        self.assertEqual(self.read_soul(), "# 我的自定义身份\n\n你是一个严谨的代码审查员。\n")

    def test_factory_soul_is_replaced(self):
        """出厂英文身份 = 用户没写过东西，可以安全覆盖。"""
        self.write_soul("You are Hermes Agent, an intelligent AI assistant created by Nous Research.\n")
        result = self.bootstrap()
        self.assertEqual(result["action"], "updated")
        self.assertEqual(self.read_soul(), persona.compose(self.persona_dir))

    def test_other_display_personality_is_kept(self):
        """display.personality 指向别的人设时不动它。"""
        self.config.write_text(yaml.safe_dump({"display": {"personality": "kawaii"}},
                                              allow_unicode=True), encoding="utf-8")
        self.bootstrap(force=True)
        self.assertEqual(self.read_config()["display"]["personality"], "kawaii")

    def test_structured_persona_is_left_alone(self):
        """手写的结构化人设（dict）不替用户删。"""
        self.config.write_text(yaml.safe_dump(
            {"agent": {"personalities": {"whalechan": {"text": "别人写的结构"}}}},
            allow_unicode=True), encoding="utf-8")
        self.bootstrap(force=True)
        self.assertEqual(self.read_config()["agent"]["personalities"]["whalechan"],
                         {"text": "别人写的结构"})

    def test_missing_persona_files_fail_soft(self):
        empty = self.home / "empty"
        empty.mkdir()
        result = self.bootstrap(root=empty)
        self.assertEqual(result["action"], "failed")
        self.assertFalse(self.soul.exists())


class StatusTest(Sandbox):
    def test_status_before_and_after(self):
        before = persona.status(self.persona_dir)
        self.assertEqual(before["soul_chars"], 0)
        self.assertFalse(before["same"])
        self.assertEqual(before["local_chars"], len(persona.compose(self.persona_dir).strip()))

        self.bootstrap()
        after = persona.status(self.persona_dir)
        self.assertTrue(after["same"])
        self.assertEqual(after["soul_chars"], len(persona.compose(self.persona_dir).strip()))
        self.assertFalse(after["legacy"])


if __name__ == "__main__":
    unittest.main()
