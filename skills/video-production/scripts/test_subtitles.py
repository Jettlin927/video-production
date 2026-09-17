"""Speaker filtering, role repairs and source/final SRT timestamp contracts."""
import tempfile
from pathlib import Path
import unittest
from bailian_asr import normalize
from export_subtitles import export
from bailian_media import load

RAW = {'transcripts': [{'channel_id': 0, 'sentences': [
    {'speaker_id': 4, 'text': '提示', 'words': [{'text': '提示', 'begin_time': 0, 'end_time': 1000}]},
    {'speaker_id': 7, 'text': '数字高管', 'words': [{'text': '数字', 'begin_time': 5000, 'end_time': 5300}, {'text': '高管', 'begin_time': 5300, 'end_time': 6000}]},
    {'speaker_id': 4, 'text': '下一句', 'words': [{'text': '下一句', 'begin_time': 7000, 'end_time': 8000}]},
    {'speaker_id': 7, 'text': '继续', 'words': [{'text': '继续', 'begin_time': 10000, 'end_time': 11000}]}
]}]}


class Tests(unittest.TestCase):
    def test_speaker_ids_and_source_gaps_are_preserved(self):
        d = normalize(RAW)
        self.assertEqual([w['speaker_id'] for w in d['words']], [4, 7, 7, 4, 7])
        with tempfile.TemporaryDirectory() as t:
            r = export(d, t, speaker=7)
            srt = Path(r['srt']).read_text(encoding='utf-8')
            self.assertIn('00:00:05,000 --> 00:00:06,000', srt)
            self.assertIn('00:00:10,000 --> 00:00:11,000', srt)
            self.assertNotIn('提示', srt)
            self.assertEqual(r['words'], 3)
            self.assertEqual(len(load(Path(t)/'speakers.json')['speakers']), 2)

    def test_final_timestamps_and_repeated_instances(self):
        w = normalize(RAW)['words'][1]
        d = {'revision': 'cut-test', 'words': [{**w, 'instance_id': 'k1', 'final_start_s': .2, 'final_end_s': .5},
                                              {**w, 'instance_id': 'k2', 'final_start_s': 2.2, 'final_end_s': 2.5}]}
        with tempfile.TemporaryDirectory() as t:
            r = export(d, t)
            self.assertIn('subtitles.final.srt', r['srt'])
            self.assertEqual(r['cues'], 2)
            self.assertIn('00:00:02,200 --> 00:00:02,500', Path(r['srt']).read_text(encoding='utf-8'))

    def test_explicit_word_role_repair_keeps_provider_label(self):
        d = normalize(RAW); d['words'][2]['effective_speaker_id'] = 4
        with tempfile.TemporaryDirectory() as t:
            r = export(d, t, speaker=4)
            self.assertIn('高管', Path(r['srt']).read_text(encoding='utf-8'))
            self.assertEqual(d['words'][2]['speaker_id'], 7)

    def test_unknown_speaker_is_not_actor_zero(self):
        d = normalize(RAW)
        for w in d['words']: w['speaker_id'] = None
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, 'no labelled words'): export(d, t, speaker=0)

    def test_word_boundary_pagination_and_coverage(self):
        d = normalize(RAW)
        with tempfile.TemporaryDirectory() as t:
            export(d, t, max_chars=2)
            r = load(Path(t)/'subtitles.source.json')
            self.assertEqual([k for c in r['cues'] for k in c['word_ids']], [w['id'] for w in d['words']])
            self.assertEqual(r['cues'][1]['end_s'], 5.3)
            self.assertEqual(r['cues'][2]['start_s'], 5.3)

    def test_partial_final_mapping_rejected(self):
        d = normalize(RAW); d['words'][0]['final_start_s'] = 0
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, 'invalid word timestamps'): export(d, t)


if __name__ == '__main__': unittest.main(verbosity=2)
