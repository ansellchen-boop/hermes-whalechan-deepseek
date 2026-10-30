"""persona.py 的单测：人设合成 + 自举（不联网，不写真实 ~/.hermes）。

跑法：``python3 -m unittest discover -s tests -v``（在仓库根目录）
"""

from __future__ import annotations

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
    def test_first_run_installs_and_selects(self):
        result = self.bootstrap()
        self.assertEqual(result["action"], "installed")
        config = self.read_config()
        self.assertEqual(config["agent"]["personalities"]["whalechan"], persona.compose(self.persona_dir))
        self.assertEqual(config["display"]["personality"], "whalechan")
        self.assertTrue((self.home / "plugins" / "whalechan" / "persona-state.json").is_file())

    def test_second_run_is_noop(self):
        self.bootstrap()
        before = self.config.read_text(encoding="utf-8")
        result = self.bootstrap()
        self.assertEqual(result["action"], "already")
        self.assertEqual(self.config.read_text(encoding="utf-8"), before)

    def test_removed_by_user_stays_removed(self):
        self.bootstrap()
        # 用户把 agent 层删掉（例如 /personality none 后手改 config）
        writer = _fake_writer_factory(self.config)
        writer(self.config, "agent.personalities.whalechan", None)
        result = self.bootstrap()
        self.assertEqual(result["action"], "removed-by-user")
        self.assertNotIn("whalechan", (self.read_config().get("agent") or {}).get("personalities") or {})

    def test_force_syncs_after_removal(self):
        self.bootstrap()
        writer = _fake_writer_factory(self.config)
        writer(self.config, "agent.personalities.whalechan", None)
        result = self.bootstrap(force=True)
        self.assertIn(result["action"], {"installed", "updated"})
        self.assertEqual(self.read_config()["agent"]["personalities"]["whalechan"],
                         persona.compose(self.persona_dir))

    def test_drift_is_not_overwritten_without_force(self):
        self.bootstrap()
        writer = _fake_writer_factory(self.config)
        writer(self.config, "agent.personalities.whalechan", "我自己手改的人设")
        result = self.bootstrap()
        self.assertEqual(result["action"], "drift")
        self.assertEqual(self.read_config()["agent"]["personalities"]["whalechan"], "我自己手改的人设")

    def test_other_display_personality_is_not_stolen(self):
        self.bootstrap()
        writer = _fake_writer_factory(self.config)
        writer(self.config, "display.personality", "kawaii")
        result = self.bootstrap()
        self.assertEqual(result["action"], "unselected")
        self.assertEqual(self.read_config()["display"]["personality"], "kawaii")

    def test_root_level_personality_is_recognised(self):
        # 历史形状：顶层 personalities.whalechan（0.3.x 的 apply.py 写的）
        text = persona.compose(self.persona_dir)
        self.config.write_text(
            yaml.safe_dump({"personalities": {"whalechan": text}, "display": {"personality": "whalechan"}},
                           allow_unicode=True),
            encoding="utf-8",
        )
        result = self.bootstrap()
        self.assertEqual(result["action"], "already")
        self.assertNotIn("agent", self.read_config())

    def test_missing_persona_files_fail_soft(self):
        empty = self.home / "empty"
        empty.mkdir()
        result = self.bootstrap(root=empty)
        self.assertEqual(result["action"], "failed")
        self.assertFalse(self.config.exists())


class StatusTest(Sandbox):
    def test_status_before_and_after(self):
        before = persona.status(self.persona_dir)
        self.assertEqual(before["config_chars"], 0)
        self.assertFalse(before["same"])
        self.assertEqual(before["local_chars"], len(persona.compose(self.persona_dir).strip()))

        self.bootstrap()
        after = persona.status(self.persona_dir)
        self.assertTrue(after["same"])
        self.assertEqual(after["display"], "whalechan")
        self.assertEqual(after["source"], "agent")


class DisplayAndStructuredTest(Sandbox):
    def test_force_does_not_steal_display(self):
        """/whalechan sync 只同步文本，不抢「用哪个人设」的开关。"""
        self.bootstrap()
        writer = _fake_writer_factory(self.config)
        writer(self.config, "display.personality", "kawaii")
        writer(self.config, "agent.personalities.whalechan", None)
        result = self.bootstrap(force=True)
        self.assertIn(result["action"], {"installed", "updated"})
        config = self.read_config()
        self.assertEqual(config["display"]["personality"], "kawaii")
        self.assertEqual(config["agent"]["personalities"]["whalechan"],
                         persona.compose(self.persona_dir))
        self.assertIn("没动 display.personality", result["message"])

    def test_structured_persona_is_never_overwritten(self):
        # 手写的结构化人设（dict）不能被纯文本顶掉，force 也不行
        self.config.write_text(yaml.safe_dump(
            {"agent": {"personalities": {"whalechan": {"text": "别人写的结构"}}},
             "display": {"personality": "whalechan"}}, allow_unicode=True), encoding="utf-8")
        result = self.bootstrap(force=True)
        self.assertEqual(result["action"], "failed")
        self.assertIn("结构化", result["message"])
        self.assertEqual(self.read_config()["agent"]["personalities"]["whalechan"],
                         {"text": "别人写的结构"})


if __name__ == "__main__":
    unittest.main()
