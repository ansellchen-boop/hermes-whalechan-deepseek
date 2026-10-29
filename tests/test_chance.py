"""chance.py 的单测：不联网，不依赖 Hermes 运行时。

跑法：``python3 -m unittest discover -s tests -v``（在仓库根目录）
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "whalechan"))

import chance  # noqa: E402


class ClampTest(unittest.TestCase):
    def test_defaults_on_garbage(self):
        self.assertEqual(chance.clamp_probability("abc"), 66.6)
        self.assertEqual(chance.clamp_probability(None), 66.6)
        self.assertEqual(chance.clamp_probability(float("nan")), 66.6)

    def test_bounds(self):
        self.assertEqual(chance.clamp_probability(-5), 0.0)
        self.assertEqual(chance.clamp_probability(250), 100.0)
        self.assertEqual(chance.clamp_probability(66.66), 66.7)


class RollTest(unittest.TestCase):
    def test_zero_never_fires(self):
        rng = random.Random(1)
        self.assertFalse(any(chance.roll(0, rng) for _ in range(500)))

    def test_hundred_always_fires(self):
        rng = random.Random(1)
        self.assertTrue(all(chance.roll(100, rng) for _ in range(500)))

    def test_roughly_matches_probability(self):
        rng = random.Random(42)
        hits = sum(chance.roll(66.6, rng) for _ in range(20000))
        self.assertAlmostEqual(hits / 20000, 0.666, delta=0.02)


class ConfigTest(unittest.TestCase):
    def test_missing_file_uses_defaults(self):
        config = chance.load_config(Path(tempfile.gettempdir()) / "no-such-whalechan.json")
        self.assertTrue(config["enabled"])
        self.assertEqual(config["probability"], 66.6)
        self.assertEqual(config["sources"], [])

    def test_broken_json_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(chance.load_config(path)["probability"], 66.6)

    def test_partial_config_keeps_other_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"probability": 12.34}), encoding="utf-8")
            config = chance.load_config(path)
            self.assertEqual(config["probability"], 12.3)
            self.assertTrue(config["enabled"])

    def test_disabled_blocks_everything(self):
        config = {"enabled": False, "probability": 100.0, "sources": []}
        self.assertFalse(chance.should_fire(config))

    def test_sources_filter(self):
        config = {"enabled": True, "probability": 100.0, "sources": ["telegram"]}
        self.assertFalse(chance.should_fire(config, platform="cli"))
        self.assertTrue(chance.should_fire(config, platform="telegram"))
        # 没给 platform 时不过滤（避免 platform 名一变就静默停摆）
        self.assertTrue(chance.should_fire(config, platform=""))


class CustomTest(unittest.TestCase):
    def test_normalize_trims_and_caps(self):
        self.assertEqual(chance.normalize_custom("  hi  "), "hi")
        self.assertEqual(len(chance.normalize_custom("字" * 5000)), 2000)
        self.assertEqual(chance.normalize_custom(None), "")
        self.assertEqual(chance.normalize_custom("a\r\nb"), "a\nb")

    def test_save_roundtrip_keeps_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"keep": 1, "probability": 10}), encoding="utf-8")
            config = chance.save_config({"custom": "叫我主人", "probability": 250}, path)
            self.assertEqual(config["custom"], "叫我主人")
            self.assertEqual(config["probability"], 100.0)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["keep"], 1)

    def test_save_creates_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "config.json"
            config = chance.save_config({"enabled": False}, path)
            self.assertFalse(config["enabled"])
            self.assertTrue(path.exists())


class BeatTest(unittest.TestCase):
    """人设节拍骰：独立于表情包开关，0 = 关。"""

    def test_default_beat_is_fifty_five(self):
        config = chance.load_config(Path(tempfile.gettempdir()) / "no-such-whalechan.json")
        self.assertEqual(config["beat_probability"], 55.0)

    def test_zero_beat_never_fires(self):
        config = {"beat_probability": 0.0, "sources": []}
        rng = random.Random(1)
        self.assertFalse(any(chance.should_fire_beat(config, rng=rng) for _ in range(300)))

    def test_beat_ignores_sticker_switch(self):
        # 关表情包的人多半只是不想发图，不该顺带被改成客服腔
        config = {"enabled": False, "probability": 0.0, "beat_probability": 100.0, "sources": []}
        self.assertFalse(chance.should_fire(config))
        self.assertTrue(chance.should_fire_beat(config))

    def test_beat_sources_filter(self):
        config = {"beat_probability": 100.0, "sources": ["telegram"]}
        self.assertFalse(chance.should_fire_beat(config, platform="desktop"))
        self.assertTrue(chance.should_fire_beat(config, platform="telegram"))
        self.assertTrue(chance.should_fire_beat(config, platform=""))

    def test_beat_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = chance.save_config({"beat_probability": 12.34}, path)
            self.assertEqual(config["beat_probability"], 12.3)
            # 表情包那条概率不该被顺手改掉
            self.assertEqual(config["probability"], 66.6)
            config = chance.save_config({"beat_probability": 0}, path)
            self.assertEqual(config["beat_probability"], 0.0)


if __name__ == "__main__":
    unittest.main()
