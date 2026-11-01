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


class BeatVariantTest(unittest.TestCase):
    """节拍措辞：几套说法换着来 + 前两轮强制命中。"""

    def test_variants_are_distinct_and_constrained(self):
        contexts = chance.BEAT_CONTEXTS
        self.assertGreaterEqual(len(contexts), 3)
        self.assertEqual(len(set(contexts)), len(contexts))
        for text in contexts:
            self.assertTrue("口癖" in text or "语气词" in text, text)
            self.assertTrue("内心" in text or "动作" in text, text)
            self.assertTrue(text.startswith("🎭 人设节拍"), text)
        # 兼容别名指向第一条，老调用方不会炸
        self.assertIs(chance.BEAT_CONTEXT, contexts[0])

    def test_pick_beat_only_returns_known_variants(self):
        rng = random.Random(7)
        picked = {chance.pick_beat(rng) for _ in range(300)}
        self.assertEqual(picked, set(chance.BEAT_CONTEXTS))

    def test_early_context_is_its_own_thing(self):
        self.assertNotIn(chance.BEAT_EARLY_CONTEXT, chance.BEAT_CONTEXTS)
        self.assertIn("口癖", chance.BEAT_EARLY_CONTEXT)
        self.assertIn("内心", chance.BEAT_EARLY_CONTEXT)

    def test_early_forces_hit_even_when_dice_miss(self):
        config = {"beat_probability": 55.0, "sources": []}
        rng = random.Random(1)
        self.assertTrue(all(chance.should_fire_beat(config, rng=rng, early=True) for _ in range(200)))

    def test_early_does_not_override_zero_or_sources(self):
        # 用户明确关掉（0）就得尊重，前两轮也不硬塞
        self.assertFalse(chance.should_fire_beat({"beat_probability": 0.0, "sources": []}, early=True))
        blocked = {"beat_probability": 55.0, "sources": ["telegram"]}
        self.assertFalse(chance.should_fire_beat(blocked, platform="desktop", early=True))
        self.assertTrue(chance.should_fire_beat(blocked, platform="telegram", early=True))

    def test_describe_sources(self):
        self.assertEqual(chance.describe_sources({"sources": []}), "")
        self.assertEqual(chance.describe_sources({"sources": ["desktop", "telegram"]}),
                         "只在 desktop、telegram 上掷骰")


class RhythmTest(unittest.TestCase):
    """节奏骰：报进度 + 三段小结。三条骰子里最独立的一条。"""

    def test_default_rhythm_is_eighty_five(self):
        config = chance.load_config(Path(tempfile.gettempdir()) / "no-such-whalechan.json")
        self.assertEqual(config["rhythm_probability"], 85.0)

    def test_zero_rhythm_never_fires(self):
        config = {"rhythm_probability": 0.0, "sources": []}
        rng = random.Random(1)
        self.assertFalse(any(chance.should_fire_rhythm(config, rng=rng) for _ in range(300)))

    def test_rhythm_ignores_other_switches(self):
        # 关表情包、关节拍，都不该顺带把结构提醒也关掉
        config = {"enabled": False, "probability": 0.0, "beat_probability": 0.0,
                  "rhythm_probability": 100.0, "sources": []}
        self.assertFalse(chance.should_fire(config))
        self.assertFalse(chance.should_fire_beat(config))
        self.assertTrue(chance.should_fire_rhythm(config))

    def test_rhythm_sources_filter(self):
        config = {"rhythm_probability": 100.0, "sources": ["telegram"]}
        self.assertFalse(chance.should_fire_rhythm(config, platform="desktop"))
        self.assertTrue(chance.should_fire_rhythm(config, platform="telegram"))
        self.assertTrue(chance.should_fire_rhythm(config, platform=""))

    def test_rhythm_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = chance.save_config({"rhythm_probability": 12.34}, path)
            self.assertEqual(config["rhythm_probability"], 12.3)
            # 另两条概率不该被顺手改掉
            self.assertEqual(config["probability"], 66.6)
            self.assertEqual(config["beat_probability"], 55.0)
            config = chance.save_config({"rhythm_probability": 0}, path)
            self.assertEqual(config["rhythm_probability"], 0.0)


class RhythmVariantTest(unittest.TestCase):
    """节奏措辞：换说法、前几轮必中、内容必须真的点到要点。"""

    def test_variants_are_distinct_and_constrained(self):
        contexts = chance.RHYTHM_CONTEXTS
        self.assertGreaterEqual(len(contexts), 3)
        self.assertEqual(len(set(contexts)), len(contexts))
        for text in contexts:
            self.assertIn("[进度]", text, text)
            self.assertIn("**进度小结**", text, text)
            # 三段必须写全，否则模型会自己发明小标题
            for section in ("背景", "当前", "下一步"):
                self.assertIn(section, text, text)

    def test_header_marks_itself_as_host_generated(self):
        # 不标清楚，模型会去接「你」的话头当成用户在说话
        self.assertIn("🧭", chance.RHYTHM_HEADER)
        self.assertIn("不是老板说的话", chance.RHYTHM_HEADER)

    def test_pick_rhythm_only_returns_known_variants(self):
        rng = random.Random(7)
        picked = {chance.pick_rhythm(rng=rng) for _ in range(300)}
        self.assertEqual(picked, set(chance.RHYTHM_CONTEXTS))

    def test_early_context_is_its_own_thing(self):
        self.assertNotIn(chance.RHYTHM_EARLY_CONTEXT, chance.RHYTHM_CONTEXTS)
        self.assertIn("`[进度]`", chance.RHYTHM_EARLY_CONTEXT)
        self.assertIn("**进度小结**", chance.RHYTHM_EARLY_CONTEXT)
        self.assertIs(chance.pick_rhythm(early=True), chance.RHYTHM_EARLY_CONTEXT)

    def test_early_forces_hit_even_when_dice_miss(self):
        config = {"rhythm_probability": 85.0, "sources": []}
        rng = random.Random(1)
        self.assertTrue(all(chance.should_fire_rhythm(config, rng=rng, early=True) for _ in range(200)))

    def test_early_does_not_override_zero_or_sources(self):
        self.assertFalse(chance.should_fire_rhythm({"rhythm_probability": 0.0, "sources": []}, early=True))
        blocked = {"rhythm_probability": 85.0, "sources": ["telegram"]}
        self.assertFalse(chance.should_fire_rhythm(blocked, platform="desktop", early=True))
        self.assertTrue(chance.should_fire_rhythm(blocked, platform="telegram", early=True))


if __name__ == "__main__":
    unittest.main()
