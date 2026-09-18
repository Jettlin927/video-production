# -*- coding: utf-8 -*-
"""Offline regression tests for align_script.py.

Every case here is a real failure observed while producing hook videos, so the
tests exist to stop the aligner from silently regressing. They are pure functions
over synthetic timings: no network, no API key, no media.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from align_script import (align_one, chars_from_words, norm,  # noqa: E402
                          target_units)


def stream(text, char_s=0.2, gap_s=0.0):
    """Build a word list from a plain string, one word per character."""
    toks, t = [], 0.0
    for ch in text:
        toks.append({"text": ch, "start": t, "end": t + char_s})
        t += char_s + gap_s
    return toks


class AlignTests(unittest.TestCase):
    def chars(self, text, **kw):
        return chars_from_words(stream(text, **kw))

    def units(self, text):
        return len(target_units(norm(text)))

    def test_exact_match(self):
        chars = self.chars("下一个风口就是培训机构")
        res = align_one(norm("下一个风口就是培训机构"), chars, 0)
        self.assertIsNotNone(res)
        start, end, cursor = res
        self.assertAlmostEqual(start, 0.0, places=3)
        self.assertEqual(cursor, 11)

    def test_numeral_rewrite_does_not_shift(self):
        """7天 is spoken 七天: it must stay in place and consume the whole sentence."""
        spoken = "只做了一场活动结果七天时间招了一百四十多个学生"
        script = "只做了一场活动，结果7天时间，招了140多个学生。"
        chars = self.chars(spoken)
        res = align_one(norm(script), chars, 0)
        self.assertIsNotNone(res)
        # the sentence must consume the stream it actually heard, unit for unit
        self.assertEqual(res[2], len(chars))

    def test_ten_becomes_shi(self):
        """The voiceover says 十 where the script writes 10: compare by value, not glyph."""
        spoken = "平均每天都有十个以上家长报名"
        script = "平均每天都有10个以上家长报名。"
        chars = self.chars(spoken)
        res = align_one(norm(script), chars, 0)
        self.assertIsNotNone(res)
        self.assertEqual(res[2], len(chars))

    def test_homophone_confusion(self):
        spoken = "让家长主动尽校"
        script = "让家长主动进校。"
        chars = self.chars(spoken)
        res = align_one(norm(script), chars, 0)
        self.assertIsNotNone(res, "进/尽 must be tolerated as a known mishearing")

    def test_swallowed_characters(self):
        """已经 heard as 已: the alignment absorbs it without shifting the tail."""
        spoken = "活动方案我已把流程整理好了"
        script = "活动方案，我已经把流程整理好了。"
        chars = self.chars(spoken)
        res = align_one(norm(script), chars, 0)
        self.assertIsNotNone(res)
        self.assertEqual(res[2], len(chars))

    def test_trailing_sentence_can_be_short(self):
        """The final short sentence may be heard only partly."""
        chars = self.chars("分享给你")
        res = align_one(norm("分享给你。"), chars, 0)
        self.assertIsNotNone(res)
        self.assertEqual(res[2], 4)

    def test_sequential_sentences_stay_monotonic(self):
        """Two sentences in a row must not overlap or drift."""
        chars = self.chars("思路一换招生真的会不一样有一位95后女老师")
        first = align_one(norm("思路一换，招生真的会不一样。"), chars, 0)
        self.assertIsNotNone(first)
        second = align_one(norm("有一位95后女老师"), chars, first[2])
        self.assertIsNotNone(second)
        self.assertGreaterEqual(second[0], first[1] - 1e-6)

    def test_does_not_slide_to_later_lookalike(self):
        """A repeated phrase must match locally, not jump to its second occurrence."""
        # "与你同行" appears twice; the first sentence must claim the first one.
        chars = self.chars("与你同行活动方案与你同行活动方案")
        res = align_one(norm("与你同行活动方案"), chars, 0)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res[0], 0.0, places=3)

    def test_far_shift_is_not_silently_accepted(self):
        """When the stream starts somewhere else entirely, the aligner returns None."""
        chars = self.chars("完全不同的另外一段内容")
        res = align_one(norm("下一个风口就是培训机构"), chars, 0)
        self.assertIsNone(res, "a non-matching stream must be rejected, not aligned")

    def test_skipped_ratio_recorded(self):
        """A spoken filler the script does not contain is skipped and reported."""
        findings = []
        chars = self.chars("今天天气不错呀然后我们开始")
        res = align_one(norm("今天天气不错然后我们开始"), chars, 0, findings=findings, label="s1")
        self.assertIsNotNone(res)
        kinds = {f["kind"] for f in findings}
        self.assertIn("stream_chars_skipped", kinds)
        skipped = [f for f in findings if f["kind"] == "stream_chars_skipped"][0]
        self.assertEqual(skipped["count"], 1)

    def test_filler_run_does_not_cause_drops(self):
        """Two fillers must be skipped, not turned into dropped script characters."""
        findings = []
        chars = self.chars("今天天气不错呀嗯然后我们开始")
        res = align_one(norm("今天天气不错然后我们开始"), chars, 0, findings=findings, label="s1")
        self.assertIsNotNone(res)
        kinds = [f["kind"] for f in findings]
        self.assertIn("stream_chars_skipped", kinds)
        self.assertNotIn("target_chars_dropped", kinds)

    def test_dropped_script_characters_reported(self):
        findings = []
        chars = self.chars("活动方案我已把流程整理好了")
        align_one(norm("活动方案，我已经把流程整理好了。"), chars, 0,
                  findings=findings, label="s1")
        kinds = {f["kind"] for f in findings}
        self.assertTrue(kinds & {"target_chars_dropped", "asr_rewrite"})


if __name__ == "__main__":
    unittest.main(verbosity=2)