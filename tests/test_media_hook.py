"""输出侧 MEDIA 行修正的单测：不联网，不碰 Hermes 运行时。

为什么需要这个钩子（2026-11-01 实测）：

模型把 ``MEDIA:<路径>`` 和下一句话写在同一行时，宿主认不出它是附件 ——
``gateway/platforms/base.py`` 的 ``MEDIA_TAG_CLEANUP_RE`` 要求扩展名后面紧跟
空白或标点，紧跟一个汉字就整条不匹配，于是图发不出去、路径当普通文本留在
回复里。人设里写了两遍「前后各空一行」也没用，所以改在输出侧兜底。

跑法：``~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

import whalechan  # noqa: E402

IMG = "/home/ubuntu/.hermes/images/whalechan"


class SplitGluedMediaTest(unittest.TestCase):
    def test_glued_chinese_heading_gets_blank_line(self):
        text = f"MEDIA:{IMG}/ee44.webp进度小结"
        self.assertEqual(
            whalechan._split_glued_media(text),
            f"MEDIA:{IMG}/ee44.webp\n\n进度小结",
        )

    def test_glued_body_text_keeps_all_characters(self):
        text = f"看图\n\nMEDIA:{IMG}/b29c.webp这道题我算完了"
        fixed = whalechan._split_glued_media(text)
        self.assertEqual(fixed, f"看图\n\nMEDIA:{IMG}/b29c.webp\n\n这道题我算完了")

    def test_punctuation_terminator_is_left_alone(self):
        # 全角括号、句号、星号都是宿主认得的终止符，本来就发得出去。
        for tail in ("（内心：算了）", "。", "**进度小结**", "！", "、"):
            text = f"MEDIA:{IMG}/a.webp{tail}"
            self.assertEqual(whalechan._split_glued_media(text), text, tail)

    def test_ascii_terminators_are_left_alone(self):
        for tail in (",", ".", ")", "]", ":", " "):
            text = f"MEDIA:{IMG}/a.webp{tail}算了"
            self.assertEqual(whalechan._split_glued_media(text), text, tail)

    def test_already_clean_line_is_untouched(self):
        text = f"先说一句。\n\nMEDIA:{IMG}/a.webp\n\n**进度小结**\n- 背景：废话"
        self.assertEqual(whalechan._split_glued_media(text), text)

    def test_no_media_tag_is_untouched(self):
        text = "普通回复，没有图，MEDIA 这个词出现了但没冒号"
        self.assertEqual(whalechan._split_glued_media(text), text)

    def test_unknown_extension_is_not_rewritten(self):
        text = "MEDIA:/tmp/report.weirdformat后面还有字"
        self.assertEqual(whalechan._split_glued_media(text), text)

    def test_relative_path_is_not_rewritten(self):
        # 相对路径本来就发不出去，改它只会把文字排版弄乱。
        text = "MEDIA:images/a.png后面还有字"
        self.assertEqual(whalechan._split_glued_media(text), text)

    def test_uppercase_extension_is_handled(self):
        text = f"MEDIA:{IMG}/A.WEBP进度"
        self.assertEqual(whalechan._split_glued_media(text), f"MEDIA:{IMG}/A.WEBP\n\n进度")

    def test_chinese_filename_is_preserved(self):
        text = "MEDIA:/home/ubuntu/.hermes/images/早报.pdf今天早上生成的"
        self.assertEqual(
            whalechan._split_glued_media(text),
            "MEDIA:/home/ubuntu/.hermes/images/早报.pdf\n\n今天早上生成的",
        )

    def test_tilde_path_is_handled(self):
        text = "MEDIA:~/.hermes/images/a.webp喏"
        self.assertEqual(whalechan._split_glued_media(text), "MEDIA:~/.hermes/images/a.webp\n\n喏")

    def test_multiple_glued_lines_in_one_reply(self):
        text = f"MEDIA:{IMG}/a.webp第一张\n正文\nMEDIA:{IMG}/b.webp第二张"
        fixed = whalechan._split_glued_media(text)
        self.assertEqual(fixed, f"MEDIA:{IMG}/a.webp\n\n第一张\n正文\nMEDIA:{IMG}/b.webp\n\n第二张")

    def test_bare_media_line_without_text_is_untouched(self):
        text = f"MEDIA:{IMG}/a.webp"
        self.assertEqual(whalechan._split_glued_media(text), text)

    def test_is_idempotent(self):
        text = f"MEDIA:{IMG}/a.webp进度小结"
        once = whalechan._split_glued_media(text)
        self.assertEqual(whalechan._split_glued_media(once), once)


class TransformHookTest(unittest.TestCase):
    def test_returns_none_when_nothing_to_fix(self):
        self.assertIsNone(
            whalechan._on_transform_llm_output(response_text=f"MEDIA:{IMG}/a.webp\n\n喏")
        )

    def test_returns_none_without_text(self):
        self.assertIsNone(whalechan._on_transform_llm_output())
        self.assertIsNone(whalechan._on_transform_llm_output(response_text=""))
        self.assertIsNone(whalechan._on_transform_llm_output(response_text=None))
        self.assertIsNone(whalechan._on_transform_llm_output(response_text=123))

    def test_returns_repaired_text(self):
        fixed = whalechan._on_transform_llm_output(response_text=f"MEDIA:{IMG}/a.webp进度小结")
        self.assertEqual(fixed, f"MEDIA:{IMG}/a.webp\n\n进度小结")

    def test_does_not_swallow_other_kwargs(self):
        # 宿主会把 session_id / platform / turn_id 一起传进来，不认识就忽略。
        fixed = whalechan._on_transform_llm_output(
            response_text=f"MEDIA:{IMG}/a.webp进度小结",
            session_id="local-x",
            platform="cli",
            turn_id="t1",
        )
        self.assertEqual(fixed, f"MEDIA:{IMG}/a.webp\n\n进度小结")


class RegisterTest(unittest.TestCase):
    def test_transform_hook_is_registered(self):
        """钩子必须真的挂在 ``transform_llm_output`` 上 —— 名字写错是静默失效。"""
        seen = {}

        class FakeCtx:
            def register_hook(self, name, fn, **kwargs):
                seen[name] = fn

            def __getattr__(self, _name):
                def _noop(*_a, **_k):
                    return None

                return _noop

        whalechan.register(FakeCtx())
        self.assertIn("pre_llm_call", seen)
        self.assertIs(seen["transform_llm_output"], whalechan._on_transform_llm_output)


if __name__ == "__main__":
    unittest.main()
