import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import wave

import bailian_tts as tts

CFG = {'DASHSCOPE_BASE_URL': 'https://dashscope.aliyuncs.com/api/v1', 'DASHSCOPE_API_KEY': 'offline-fixture'}
RESPONSE = {'request_id': 'test-request', 'output': {'audio': {'url': 'https://result.oss.aliyuncs.com/audio.wav?signature=private'}},
            'usage': {'characters': 10}}


class Client:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = iter(replies) if replies is not None else None

    def call(self, *args):
        self.calls.append(args)
        reply = next(self.replies) if self.replies else RESPONSE
        if isinstance(reply, Exception):
            raise reply
        return reply


def audio_fixture(url, path):
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x01\x00' * 2400)


class TtsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='video-tts-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'copy.txt'
        self.script.write_text('这是原文，保留条件和数字。', encoding='utf-8')
        self.out = self.root / 'voice'
        self.env_patch = patch.dict(os.environ, {'BAILIAN_TTS_MODEL': '', 'BAILIAN_TTS_VOICE': '', 'BAILIAN_TTS_LANGUAGE': ''})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def run_tts(self, client, **kwargs):
        with patch.object(tts, 'download_audio', side_effect=audio_fixture), \
                patch.object(tts, 'normalize_audio', side_effect=lambda _, source, target: shutil.copyfile(source, target)):
            return tts.run(self.script, self.out, CFG, True, ffmpeg='offline-ffmpeg', client=client, **kwargs)

    def test_plain_text_sentences_and_chunks_reconstruct_exact_text(self):
        text = '\n第一句，条件不能删！\n' + '很长的原文' * 260 + '\n最后一句。\n'
        self.script.write_text(text, encoding='utf-8')
        sentences = tts.read_script(self.script)
        self.assertEqual(''.join(s['text_zh'] for s in sentences), text)
        self.assertEqual(sentences[0]['text_zh'], '\n第一句，条件不能删！\n')
        chunks = tts.chunk_text(text)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(0 < len(c) <= 500 for c in chunks))

    def test_json_ids_preserved_and_invalid_ids_rejected(self):
        script = self.root / 'script.json'
        sentences = [{'id': 'argument-1', 'text_zh': '不是所有公司，只有符合条件的公司。'}]
        script.write_text(json.dumps({'sentences': sentences}, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(tts.read_script(script), sentences)
        script.write_text(json.dumps({'sentences': sentences * 2}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unique'):
            tts.read_script(script)

    def test_dry_run_never_calls_provider_or_writes_outputs(self):
        with patch.object(tts, 'Client') as client:
            result = tts.run(self.script, self.out, {}, False)
            self.assertEqual(result['mode'], 'dry_run')
            self.assertFalse(result['key_configured'])
            client.assert_not_called()
        self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(ValueError, 'empty'):
            tts.run(self.script, self.out, {**CFG, 'DASHSCOPE_API_KEY': ''}, True, ffmpeg='ffmpeg')
        self.assertFalse(self.out.exists())

    def test_request_shape_and_completed_audio_are_reused_without_paid_calls(self):
        first = Client()
        result = self.run_tts(first)
        body = first.calls[0][2]
        self.assertEqual(body, {'model': 'qwen3-tts-flash', 'input': {
            'text': self.script.read_text('utf-8'), 'voice': 'Cherry', 'language_type': 'Chinese'}})
        self.assertEqual(result['duration_s'], .1)
        self.assertEqual(result['word_timestamps'], 'not_provided')
        self.assertNotIn('signature=private', json.dumps(result))
        second = Client()
        self.assertTrue(self.run_tts(second)['reused'])
        self.assertEqual(second.calls, [])

    def test_changed_voice_or_source_cannot_reuse_wrong_audio(self):
        self.run_tts(Client())
        voice = Client()
        a = self.run_tts(voice, voice='OtherVoice')
        self.assertEqual(len(voice.calls), 1)
        self.script.write_text('另一份文案。', encoding='utf-8')
        changed = Client()
        b = self.run_tts(changed, voice='OtherVoice')
        self.assertEqual(len(changed.calls), 1)
        self.assertNotEqual(a['signature'], b['signature'])

    def test_resegmentation_updates_script_without_repaying_for_same_audio(self):
        self.script = self.root / 'source.json'
        self.script.write_text(json.dumps({'sentences': [{'id': 'old', 'text_zh': '原文，条件不变。'}]}), encoding='utf-8')
        first = self.run_tts(Client())
        self.script.write_text(json.dumps({'sentences': [{'id': 'new1', 'text_zh': '原文，'},
                                                        {'id': 'new2', 'text_zh': '条件不变。'}]}), encoding='utf-8')
        resumed = Client()
        second = self.run_tts(resumed)
        self.assertEqual(resumed.calls, [])
        self.assertEqual(first['signature'], second['signature'])
        self.assertNotEqual(first['script_revision'], second['script_revision'])
        self.assertEqual(second['sentences'], 2)
        self.assertEqual(json.loads((self.out / 'script-sentences.json').read_text('utf-8'))['sentences'][0]['id'], 'new1')

    def test_completed_chunk_resumes_download_failure_without_resynthesis(self):
        self.script.write_text('内容' * 375, encoding='utf-8')
        client = Client()
        calls = 0

        def fail_second(url, path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('offline download failed')
            audio_fixture(url, path)

        with patch.object(tts, 'download_audio', side_effect=fail_second), \
                patch.object(tts, 'normalize_audio', side_effect=lambda _, source, target: shutil.copyfile(source, target)):
            with self.assertRaises(RuntimeError):
                tts.run(self.script, self.out, CFG, True, ffmpeg='offline', client=client)
        self.assertEqual(len(client.calls), 2)
        resumed = Client()
        result = self.run_tts(resumed)
        self.assertEqual(resumed.calls, [])
        self.assertTrue(result['chunks_detail'][0]['reused'])
        self.assertAlmostEqual(result['duration_s'], .2)

    def test_uncertain_submission_is_not_automatically_retried(self):
        self.script.write_text('内容' * 375, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            self.run_tts(Client([RESPONSE, TimeoutError('sensitive URL must not escape')]))
        resumed = Client()
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            self.run_tts(resumed)
        self.assertEqual(resumed.calls, [])

    def test_rejected_submission_preserves_safe_error_and_does_not_loop(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP 400'):
            self.run_tts(Client([tts.ApiRejected('API rejected request (HTTP 400)')]))
        resumed = Client()
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            self.run_tts(resumed)
        self.assertEqual(resumed.calls, [])

    def test_configured_voice_and_cli_override_are_used(self):
        cfg = {**CFG, 'BAILIAN_TTS_VOICE': 'ConfiguredVoice', 'BAILIAN_TTS_LANGUAGE': 'Auto'}
        result = tts.run(self.script, self.out, cfg)
        self.assertEqual(result['voice'], 'ConfiguredVoice')
        self.assertEqual(result['language_type'], 'Auto')
        result = tts.run(self.script, self.out, cfg, voice='ExplicitVoice')
        self.assertEqual(result['voice'], 'ExplicitVoice')

    def test_corrupt_final_rebuilds_from_valid_cached_chunks(self):
        self.run_tts(Client())
        (self.out / 'voiceover.wav').write_bytes(b'corrupt')
        resumed = Client()
        result = self.run_tts(resumed)
        self.assertEqual(resumed.calls, [])
        self.assertEqual(tts.wav_frames(Path(result['audio'])), 2400)

    def test_input_is_not_overwritten_and_gap_is_validated(self):
        source = self.root / 'script-sentences.json'
        source.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            tts.run(source, self.root, CFG)
        for gap in (-1, float('nan'), 6):
            with self.subTest(gap=gap), self.assertRaisesRegex(ValueError, 'gap_s'):
                tts.run(self.script, self.out, CFG, gap_s=gap)

    def test_pcm_join_has_exact_offsets_gap_and_original_samples(self):
        parts = [self.root / f'{i}.wav' for i in range(2)]
        for part in parts:
            audio_fixture('', part)
        output = self.root / 'joined.wav'
        offsets = tts.join_audio(parts, .05, output)
        self.assertEqual(tts.wav_frames(output), 6000)
        self.assertAlmostEqual(offsets[1]['start_s'], .15)
        with wave.open(str(output), 'rb') as audio:
            self.assertEqual(audio.readframes(6000), b'\x01\x00' * 2400 + b'\0\0' * 1200 + b'\x01\x00' * 2400)

    def test_shared_ffmpeg_normalizes_real_audio_without_network(self):
        media_tools = os.environ.get('VIDEO_PRODUCTION_TOOLS_JSON')
        if not media_tools:
            self.skipTest('Set VIDEO_PRODUCTION_TOOLS_JSON for local media integration')
        ffmpeg = json.loads(Path(media_tools).read_text('utf-8'))['ffmpeg']
        with patch.object(tts, 'download_audio', side_effect=audio_fixture):
            result = tts.run(self.script, self.out, CFG, True, ffmpeg=ffmpeg, client=Client())
        self.assertEqual(tts.wav_frames(Path(result['audio'])), 2400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
