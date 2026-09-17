"""Offline behavioral tests. No real credentials, provider calls, or paid jobs."""
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'video-production' / 'scripts'))
import tempfile
import unittest
import wave
from unittest.mock import patch
import bailian_media as media
from caption_pages import compile_pages
from speech_checks import asr_candidates, sync
from map_words import remap


CFG = {'DASHSCOPE_BASE_URL': 'https://example.cn-beijing.maas.aliyuncs.com/api/v1'}


def plan(kind='video'):
    return {'revision': 'r1', 'fps': {'num': 25, 'den': 1}, 'duration_frames': 250,
            'jobs': [{'id': 'shot1', 'kind': kind, 'prompt': 'A quiet workshop',
                      'start_frame': 25, 'end_frame': 100, 'placement': 'full', 'reason': 'Explain the setting'}]}


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def call(self, *args):
        self.calls.append(args)
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result


def fetched(url, path, kind):
    Path(path).write_bytes(b'offline-fixture-' + kind.encode())


def image_reply():
    return {'output': {'choices': [{'message': {'content': [{'image': 'https://test.oss.aliyuncs.com/i.png'}]}}]}}


PENDING = {'output': {'task_id': 'task-123', 'task_status': 'PENDING'}}
SUCCESS = {'output': {'task_status': 'SUCCEEDED', 'video_url': 'https://test.oss.aliyuncs.com/v.mp4'}}


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

    def test_user_model_contracts(self):
        path, body, async_ = media.request_for(plan('image')['jobs'][0], CFG)
        self.assertEqual(body['model'], 'qwen-image-3.0')
        self.assertEqual(body['input']['messages'][0]['content'][0]['text'], 'A quiet workshop')
        self.assertEqual(body['parameters'], {'prompt_extend': True})
        self.assertFalse(async_)
        path, body, async_ = media.request_for(plan()['jobs'][0], CFG)
        self.assertEqual(body['model'], 'wan3.0-video')
        self.assertEqual(body['parameters'], {'resolution': '480P', 'ratio': 'adaptive', 'duration': 5})
        self.assertTrue(async_)

    def test_dry_run_no_network_or_key(self):
        with tempfile.TemporaryDirectory() as temp:
            result = media.run(plan(), CFG, Path(temp) / 'new')
            self.assertEqual(result['mode'], 'dry_run')
            self.assertFalse((Path(temp) / 'new').exists())

    def test_missing_key_fails_before_state_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'empty'):
                media.run(plan(), CFG, Path(temp) / 'new', True)
            self.assertFalse((Path(temp) / 'new').exists())

    def test_image_sync_download_and_reuse(self):
        c = FakeClient([image_reply()])
        with tempfile.TemporaryDirectory() as temp:
            a = media.run(plan('image'), CFG, temp, True, c, fetched)
            b = media.run(plan('image'), CFG, temp, True, c, fetched)
            self.assertEqual(len(c.calls), 1)
            self.assertFalse(c.calls[0][3])
            self.assertEqual(b['new_jobs'], 0)
            self.assertEqual(media.load(a['manifest'])['jobs'][0]['asset_review'], 'not_checked')

    def test_video_async_polls_then_download(self):
        c = FakeClient([PENDING, PENDING, SUCCESS])
        with tempfile.TemporaryDirectory() as temp:
            media.run(plan(), CFG, temp, True, c, fetched, sleep=lambda _: None)
            self.assertEqual([call[0] for call in c.calls], ['POST', 'GET', 'GET'])
            self.assertEqual(c.calls[1][1], '/tasks/task-123')

    def test_pending_resume_does_not_resubmit(self):
        c = FakeClient([PENDING, PENDING])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                media.run(plan(), CFG, temp, True, c, fetched, max_polls=1)
            resumed = FakeClient([SUCCESS])
            media.run(plan(), CFG, temp, True, resumed, fetched)
            self.assertEqual(resumed.calls[0][0], 'GET')

    def test_ambiguous_submission_never_auto_retries(self):
        c = FakeClient([RuntimeError('timeout')])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):
                media.run(plan('image'), CFG, temp, True, c, fetched)
            with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                media.run(plan('image'), CFG, temp, True, c, fetched)
            self.assertEqual(len(c.calls), 1)

    def test_failed_video_never_auto_retries(self):
        c = FakeClient([PENDING, {'output': {'task_status': 'FAILED'}}])
        with tempfile.TemporaryDirectory() as temp:
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    media.run(plan(), CFG, temp, True, c, fetched)
            self.assertEqual(len(c.calls), 2)

    def test_download_failure_resumes_without_new_charge(self):
        c = FakeClient([image_reply()])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OSError):
                media.run(plan('image'), CFG, temp, True, c,
                          lambda *args: (_ for _ in ()).throw(OSError('download failed')))
            media.run(plan('image'), CFG, temp, True, c, fetched)
            self.assertEqual(len(c.calls), 1)

    def test_changed_prompt_requires_new_asset_id(self):
        c = FakeClient([image_reply()])
        with tempfile.TemporaryDirectory() as temp:
            media.run(plan('image'), CFG, temp, True, c, fetched)
            changed = plan('image'); changed['jobs'][0]['prompt'] = 'Different'
            with self.assertRaisesRegex(ValueError, 'Changed'):
                media.run(changed, CFG, temp, True, c, fetched)
            self.assertEqual(len(c.calls), 1)

    def test_untrusted_api_base_rejected(self):
        with self.assertRaises(ValueError):
            media.api_base({'DASHSCOPE_BASE_URL': 'https://evil.test/api/v1'})

    def test_download_request_has_no_bearer(self):
        class Response:
            def __enter__(self):
                self.done = False; return self
            def __exit__(self, *args):
                pass
            def read(self, n):
                if self.done: return b''
                self.done = True; return b'\x89PNG\r\n\x1a\n' + b'fixture'
        with tempfile.TemporaryDirectory() as temp, patch.object(media, 'build_opener') as opener:
            opener.return_value.open.return_value = Response()
            media.download('https://result.oss.aliyuncs.com/a.png?signed=1', Path(temp)/'a.png', 'image')
            request = opener.return_value.open.call_args.args[0]
            self.assertFalse(request.has_header('Authorization'))

    def test_reject_html_download(self):
        class Response:
            def __enter__(self): self.done = False; return self
            def __exit__(self, *args): pass
            def read(self, n):
                if self.done: return b''
                self.done = True; return b'<html>expired</html>'
        with tempfile.TemporaryDirectory() as temp, patch.object(media, 'build_opener') as opener:
            opener.return_value.open.return_value = Response()
            with self.assertRaisesRegex(RuntimeError, 'download failed'):
                media.download('https://result.oss.aliyuncs.com/a.png', Path(temp)/'a.png', 'image')
            self.assertFalse((Path(temp)/'a.png').exists())

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
