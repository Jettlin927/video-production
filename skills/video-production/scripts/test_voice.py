import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import bailian_voice as voice
from bailian_media import ApiRejected, load
from test_tts import CFG, Client

RESPONSE = {'output': {'voice': 'qwen-tts-vc-test-123', 'target_model': voice.CLONE_MODEL},
            'request_id': 'enroll-test', 'usage': {'count': 1}}


def reference_fixture(source, target, ffmpeg, start, seconds):
    with wave.open(str(target), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\x01\x00' * 24000 * 3)
    return {'duration_s': 3, 'sample_sha256': voice.file_hash(target)}


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / 'source.wav'
        self.audio.write_bytes(b'unchanged source fixture')
        self.out = self.root / 'library' / 'voice-record.json'

    def create(self, client, **kwargs):
        with patch.object(voice, 'prepare_reference', side_effect=reference_fixture):
            return voice.create_voice(self.audio, self.out, CFG, True, True, 'fixture-ffmpeg', client=client, **kwargs)

    def test_dry_run_and_consent_guard_make_no_requests_or_outputs(self):
        client = Client()
        self.assertEqual(voice.create_voice(self.audio, self.out, {}, client=client)['mode'], 'dry_run')
        with self.assertRaisesRegex(ValueError, 'consent'):
            voice.create_voice(self.audio, self.out, CFG, True, client=client)
        self.assertEqual(client.calls, [])
        self.assertFalse(self.out.parent.exists())

    def test_create_request_inline_audio_and_reuse(self):
        client = Client([RESPONSE])
        first = self.create(client)
        self.assertEqual(first['status'], 'ready')
        self.assertEqual(len(client.calls), 1)
        body = client.calls[0][2]
        self.assertEqual(body['model'], voice.ENROLL_MODEL)
        self.assertEqual(body['input']['target_model'], voice.CLONE_MODEL)
        data = body['input']['audio']['data']
        self.assertTrue(base64.b64decode(data.split(',', 1)[1]).startswith(b'RIFF'))
        state = self.out.with_suffix('.state.json').read_text('utf-8')
        self.assertNotIn('base64', state)
        self.assertNotIn(CFG['DASHSCOPE_API_KEY'], state)
        self.assertEqual(self.audio.read_bytes(), b'unchanged source fixture')
        second = Client()
        self.assertTrue(self.create(second)['reused'])
        self.assertEqual(second.calls, [])
        self.assertTrue(self.create(second, start_s=0.0, sample_seconds=15.0)['reused'])
        self.out.unlink()
        self.assertTrue(self.create(second)['reused'])
        self.assertEqual(second.calls, [])

    def test_invalid_reference_options_reject_before_network(self):
        client = Client()
        for kwargs in ({'preferred_name': 'too-long-name-is-bad'}, {'sample_seconds': 2}, {'start_s': float('nan')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.create(client, **kwargs)
        self.assertEqual(client.calls, [])

    def test_uncertain_and_rejected_creation_never_resubmit(self):
        for failure in (TimeoutError('private server data'), ApiRejected('HTTP 403')):
            with self.subTest(failure=type(failure).__name__):
                self.out = self.root / type(failure).__name__ / 'voice.json'
                with self.assertRaises(RuntimeError):
                    self.create(Client([failure]))
                resumed = Client()
                with self.assertRaisesRegex(RuntimeError, 'Prior enrollment'):
                    self.create(resumed)
                self.assertEqual(resumed.calls, [])
                self.assertNotIn('private server', self.out.with_suffix('.state.json').read_text('utf-8'))

    def test_fallback_preserves_created_identity_without_claiming_clone_ready(self):
        response = {**RESPONSE, 'output': {**RESPONSE['output'], 'fallback_mode': True}}
        with self.assertRaisesRegex(RuntimeError, 'degraded'):
            self.create(Client([response]))
        self.assertEqual(load(self.out)['voice'], RESPONSE['output']['voice'])
        self.assertEqual(load(self.out)['status'], 'review_required')
        with self.assertRaisesRegex(ValueError, 'not ready'):
            voice.load_voice_record(self.out, CFG)

    def test_profile_binding_and_changed_input_cannot_overwrite_existing_voice(self):
        self.create(Client([RESPONSE]))
        with self.assertRaisesRegex(ValueError, 'different API endpoint'):
            voice.load_voice_record(self.out, {**CFG, 'DASHSCOPE_BASE_URL': 'https://dashscope-intl.aliyuncs.com/api/v1'})
        self.audio.write_bytes(b'different input')
        resumed = Client()
        with self.assertRaisesRegex(ValueError, 'different inputs'):
            self.create(resumed)
        self.assertEqual(resumed.calls, [])

    def test_list_is_paged_and_never_creates(self):
        client = Client([{'output': {'voice_list': [RESPONSE['output']]}}])
        voice.list_voices({}, client=client)
        self.assertEqual(client.calls, [])
        result = voice.list_voices(CFG, True, 1, 20, client)
        self.assertEqual(result['output']['voice_list'][0]['voice'], RESPONSE['output']['voice'])
        self.assertEqual(client.calls[0][2]['input'], {'action': 'list', 'page_index': 1, 'page_size': 20})

    def test_reference_normalizer_checks_decoded_duration(self):
        target = self.root / 'normalized.wav'
        reference_fixture(None, target, None, None, None)
        with patch.object(voice.subprocess, 'run') as runner:
            runner.return_value.returncode = 0
            self.assertEqual(voice.prepare_reference(self.audio, target, 'ffmpeg', 0, 15)['duration_s'], 3)
            with wave.open(str(target), 'wb') as audio:
                audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                audio.writeframes(b'\0\0' * 24000)
            with self.assertRaisesRegex(ValueError, '3-60'):
                voice.prepare_reference(self.audio, target, 'ffmpeg', 0, 15)


if __name__ == '__main__':
    unittest.main(verbosity=2)
