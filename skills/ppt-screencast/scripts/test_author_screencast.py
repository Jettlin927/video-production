import copy
import json
from pathlib import Path
import unittest

from author_screencast import bind_content, text_pages
from build_screencast import compile_plan
from check_screencast_plan import validate


class AuthorTests(unittest.TestCase):
    def setUp(self):
        demo = json.loads((Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8'))
        self.script = {'sentences': [{'id': 's1', 'text_zh': '先看产品能力，条件不变。'},
                                     {'id': 's2', 'text_zh': '再看实际需求。'}]}
        self.timing = {'sentences': [{'id': 's1', 'text_zh': self.script['sentences'][0]['text_zh'], 'start_s': 1, 'end_s': 5},
                                     {'id': 's2', 'text_zh': self.script['sentences'][1]['text_zh'], 'start_s': 6, 'end_s': 10}]}
        page = demo['pages'][0]
        for element in page['elements']:
            element.update(source_ids=['s1', 's2'], takeaway='讲清能力和需求')
        self.content = {'canvas': {k: demo[k] for k in ('width', 'height', 'fps')},
                        'viewport': demo['viewport'], 'pages': [page],
                        'caption_box': {'x': 32, 'y': 736, 'w': 656, 'h': 48},
                        'scenes': [{'page_id': page['id'], 'sentences': ['s1', 's2'], 'cues': [
                            {'target_id': 'demand', 'kind': 'circle', 'reason': '看需求', 'sentences': ['s2']},
                            {'target_id': 'product', 'kind': 'circle', 'reason': '看能力', 'sentences': ['s1']}]}]}

    def test_visual_order_cannot_swap_narration_binding(self):
        original = copy.deepcopy(self.content)
        plan = compile_plan(bind_content(self.content, self.script, self.timing, 12))
        self.assertEqual(self.content, original)
        self.assertEqual([c['narration_id'] for c in plan['scenes'][0]['cues']], ['s1', 's2'])
        self.assertEqual(validate(plan)['status'], 'pass')
        for cue in plan['scenes'][0]['cues']:
            window = plan['narration_windows'][cue['narration_id']]
            self.assertGreaterEqual(cue['start_frame'], window['start_frame'])
            self.assertLessEqual(cue['end_frame'], window['end_frame'])

    def test_impossible_emphasis_rejects_instead_of_borrowing_another_sentence(self):
        self.timing['sentences'][0]['end_s'] = 1.15
        with self.assertRaisesRegex(ValueError, 'cannot fit its own narration'):
            bind_content(self.content, self.script, self.timing, 12)

    def test_checker_catches_post_compile_timing_tampering(self):
        plan = compile_plan(bind_content(self.content, self.script, self.timing, 12))
        plan['scenes'][0]['cues'][0]['narration_ids'] = ['s2']
        plan['scenes'][0]['cues'][0]['narration_id'] = 's2'
        with self.assertRaisesRegex(ValueError, 'own narration'):
            validate(plan)

    def test_source_and_scene_coverage_are_complete(self):
        self.content['scenes'][0]['sentences'] = ['s1']
        with self.assertRaisesRegex(ValueError, 'cover source'):
            bind_content(self.content, self.script, self.timing, 12)

    def test_caption_pagination_preserves_punctuation_and_text(self):
        text = '这是一个很长的句子，条件不能删，数字是100万元，有机会做到而不是保证做到。'
        pages = text_pages(text)
        self.assertEqual(''.join(line for page in pages for line in page), text)
        self.assertTrue(all(len(page) <= 2 for page in pages))
        self.assertTrue(all(len(line) <= 18 for page in pages for line in page))
        self.assertTrue(all(line[0] not in '，。！？；：、,.!?;:' for page in pages for line in page))


if __name__ == '__main__':
    unittest.main()
