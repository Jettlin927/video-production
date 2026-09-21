import copy
from pathlib import Path
import tempfile
import unittest

from authoring import caption_draft, compile_authored, load


class AuthoringTests(unittest.TestCase):
    def fixture(self):
        words = {'revision': 'r', 'words': [
            {'id': str(i), 'instance_id': 'k', 'text': text, 'final_start_s': i * .2,
             'final_end_s': (i + 1) * .2} for i, text in enumerate(['不是', '软件', '不是', '工具', '。'])]}
        plan = {'revision': 'r', 'fps': {'num': 30, 'den': 1}, 'duration_frames': 30}
        return words, plan

    def test_generated_draft_round_trips_without_retyping_words(self):
        words, plan = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'draft.json'
            caption_draft(words, plan, path, 4)
            result, errors = compile_authored(words, plan, load(path))
        self.assertEqual(errors, [])
        self.assertEqual(''.join(''.join(c['lines']) for c in result['captions']), '不是软件不是工具。')

    def test_repeated_phrase_has_unambiguous_emphasis_by_word_range(self):
        words, plan = self.fixture()
        draft = {'revision': 'r', 'pages': [{'lines': [[1, 5]], 'emphasis': [
            {'first': 3, 'last': 3, 'role': 'focus', 'reason': '强调第二个否定'}]}]}
        result, errors = compile_authored(words, plan, draft)
        self.assertFalse(errors)
        self.assertEqual(result['captions'][0]['emphasis'][0]['start_char'], 4)

    def test_all_page_errors_and_missing_words_reported_together(self):
        words, plan = self.fixture()
        draft = {'revision': 'r', 'pages': [{'lines': [[0, 2]]}, {'lines': [[3, 99]]}]}
        result, errors = compile_authored(words, plan, draft)
        self.assertIsNone(result)
        self.assertEqual([x['page'] for x in errors if 'page' in x], [1, 2])
        self.assertEqual(errors[-1]['missing'], [1, 2, 3, 4, 5])

    def test_display_correction_keeps_word_coverage_and_source_immutable(self):
        words, plan = self.fixture(); original = copy.deepcopy(words)
        draft = {'revision': 'r', 'corrections': [{'word': 2, 'text': '系统', 'reason': 'ASR校字'}],
                 'pages': [{'lines': [[1, 5]]}]}
        result, errors = compile_authored(words, plan, draft)
        self.assertFalse(errors)
        self.assertIn('系统', result['captions'][0]['lines'][0])
        self.assertEqual(words, original)

    def test_stale_revision_rejected(self):
        words, plan = self.fixture()
        self.assertTrue(compile_authored(words, plan, {'revision': 'old'})[1])


if __name__ == '__main__':
    unittest.main()
