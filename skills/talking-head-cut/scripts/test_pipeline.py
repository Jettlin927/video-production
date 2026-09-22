"""Offline behavioral tests. No real credentials, provider calls, or paid jobs."""
import copy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'video-production' / 'scripts'))
import tempfile
import unittest
import wave
import bailian_media as media
from caption_pages import compile_pages
from speech_checks import asr_candidates, sync
from map_words import remap


class PipelineTests(unittest.TestCase):
    def test_source_words_map_to_final_without_interpolation(self):
        doc = {'revision': 'source', 'words': [
            {'id': 'a', 'source_start_s': 6.2, 'source_end_s': 6.5, 'text': '不要'},
            {'id': 'b', 'source_start_s': 10.2, 'source_end_s': 10.5, 'text': '重拍'}]}
        plan_ = {'revision': 'cut', 'source': {'duration_s': 12}, 'fps': {'num': 25, 'den': 1},
                 'duration_frames': 175, 'segments': [
                     {'id': 'k1', 'source_in_s': 1, 'source_out_s': 4, 'final_in_s': 0, 'final_out_s': 3},
                     {'id': 'k2', 'source_in_s': 6, 'source_out_s': 10, 'final_in_s': 3, 'final_out_s': 7}]}
        result = remap(doc, plan_)
        self.assertAlmostEqual(result['words'][0]['final_start_s'], 3.2)
        self.assertEqual(result['words'][0]['instance_id'], 'k2')
        self.assertEqual(result['excluded_word_ids'], ['b'])
        doc['words'][0]['source_start_s'] = 5.9
        with self.assertRaisesRegex(ValueError, 'crosses cut'):
            remap(doc, plan_)

    def test_untrusted_api_base_rejected(self):
        with self.assertRaises(ValueError):
            media.api_base({'DASHSCOPE_BASE_URL': 'https://evil.test/api/v1'})

    def test_high_probability_long_word_is_flagged(self):
        result = asr_candidates({'words': [{'id': 'a', 'word': '现在', 'start': 11.15, 'end': 16.11, 'probability': .99}]})
        self.assertIn('long_word_may_hide_prompt_or_retake', result['findings'][0]['reasons'])

    def test_caption_negation_and_amount_remain_complete(self):
        words, edit = caption_fixture()
        result = compile_pages(words, edit)
        span = result['captions'][0]['emphasis'][0]
        self.assertEqual(span['text'], '千万不要')
        self.assertEqual(span['color_role'], 'white')
        self.assertEqual(result['captions'][1]['lines'], ['三五十万'])

    def test_lost_word_and_stale_revision_rejected(self):
        words, edit = caption_fixture()
        wrong = copy.deepcopy(edit); wrong['pages'].pop()
        with self.assertRaisesRegex(ValueError, 'cover every'):
            compile_pages(words, wrong)
        edit['revision'] = 'old'
        with self.assertRaisesRegex(ValueError, 'Stale'):
            compile_pages(words, edit)

    def test_protected_amount_split_rejected(self):
        words, edit = caption_fixture()
        edit['pages'][1:] = [{'takeaway': '金额', 'lines': [['k:a']]}, {'takeaway': '金额', 'lines': [['k:b']]}]
        with self.assertRaisesRegex(ValueError, 'Protected phrase'):
            compile_pages(words, edit)

    def test_waveform_delay_and_zero_delay(self):
        import numpy as np
        rng = np.random.default_rng(88)
        signal = (rng.normal(0, 2500, 16000*4)).astype('<i2')
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp)/s for s in ['ref.wav', 'zero.wav', 'late.wav']]
            for path, data in zip(paths, [signal, signal, np.r_[np.zeros(683, dtype='<i2'), signal][:(len(signal))]]):
                with wave.open(str(path), 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(data.astype('<i2').tobytes())
            good = sync(paths[0], paths[1], [.5, 1.5, 2.5])
            late = sync(paths[0], paths[2], [.5, 1.5, 2.5])
            self.assertEqual(good['status'], 'pass')
            self.assertEqual(late['status'], 'fail')
            self.assertAlmostEqual(late['windows'][0]['lag_ms'], 42.6875)

    def test_sync_normalizes_louder_neighbor(self):
        import numpy as np
        rng = np.random.default_rng(31)
        signal = rng.normal(0, 50, 32000)
        signal[15800:17600] *= 180
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'same.wav'
            with wave.open(str(p), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(signal.astype('<i2').tobytes())
            result = sync(p, p, [.48])
            self.assertEqual(result['status'], 'pass')
            self.assertEqual(result['windows'][0]['lag_ms'], 0)


def caption_fixture():
    tokens = [('w1', '千万', .2, .5), ('w2', '不要', .5, .9), ('w3', '碰FDE', .9, 1.4),
              ('a', '三五', 1.6, 2), ('b', '十万', 2, 2.4)]
    words = {'revision': 'r1', 'words': [{'id': i, 'instance_id': 'k', 'text': t, 'final_start_s': a, 'final_end_s': b} for i, t, a, b in tokens]}
    edit = {'revision': 'r1', 'fps': {'num': 25, 'den': 1}, 'duration_frames': 75,
            'protected_phrases': ['三五十万'], 'pages': [
                {'takeaway': '不要接这类业务', 'lines': [['k:w1', 'k:w2'], ['k:w3']],
                 'emphasis': [{'word_keys': ['k:w1', 'k:w2'], 'role': 'focus', 'reason': '否定决定句意'}]},
                {'takeaway': '金额范围', 'lines': [['k:a', 'k:b']]}]}
    return words, edit


if __name__ == '__main__':
    unittest.main(verbosity=2)
