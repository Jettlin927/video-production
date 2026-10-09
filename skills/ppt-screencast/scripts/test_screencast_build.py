import copy
import json
from pathlib import Path
import unittest

from build_screencast import compile_plan
from check_screencast_plan import validate


class ScreencastBuildTests(unittest.TestCase):
    def setUp(self):
        self.author = json.loads((Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8'))
        self.author['script'] = {'sentences': [{'id': 's1', 'text_zh': '先看产品能力和实际需求的关系，再看重点。'}]}
        for element in self.author['pages'][0]['elements']:
            element.update(source_ids=['s1'], takeaway='展示产品能力与实际需求的关系')
        for scene in self.author['scenes']:
            scene.pop('camera')
            for cue in scene['cues']:
                cue.pop('approach_frames')
                cue.pop('draw_frames')

    def test_generates_settled_camera_cues_and_overview_without_mutation(self):
        original = copy.deepcopy(self.author)
        plan = compile_plan(self.author)
        self.assertEqual(validate(plan)['status'], 'pass')
        self.assertEqual(self.author, original)
        self.assertEqual(plan, compile_plan(self.author))
        self.assertEqual(plan['scenes'][0]['camera'][0]['scale'], plan['scenes'][0]['camera'][-1]['scale'])

    def test_revision_changes_when_content_changes(self):
        first = compile_plan(self.author)
        self.author['pages'][0]['elements'][0]['text'] = '新的主题'
        self.assertNotEqual(first['revision'], compile_plan(self.author)['revision'])

    def test_every_content_item_needs_a_real_source_and_visual_intent(self):
        for field, value, error in [('source_ids', ['missing'], 'source_ids'), ('takeaway', '', 'takeaway')]:
            with self.subTest(field=field):
                author = copy.deepcopy(self.author)
                author['pages'][0]['elements'][0][field] = value
                with self.assertRaisesRegex(ValueError, error):
                    compile_plan(author)
        self.author.pop('script')
        with self.assertRaisesRegex(ValueError, 'narration source'):
            compile_plan(self.author)

    def test_source_text_changes_revision_even_if_layout_is_unchanged(self):
        first = compile_plan(self.author)
        self.author['script']['sentences'][0]['text_zh'] = '先看实际需求，再判断产品能力是否匹配。'
        self.assertNotEqual(first['revision'], compile_plan(self.author)['revision'])

    def test_cannot_silently_retime_narration_when_cues_are_too_close(self):
        self.author['scenes'][0]['cues'][1]['start_frame'] = 120
        with self.assertRaisesRegex(ValueError, 'transition'):
            compile_plan(self.author)

    def test_unknown_target_and_kind_fail_before_render(self):
        self.author['scenes'][0]['cues'][0]['target_id'] = 'missing'
        with self.assertRaises(ValueError):
            compile_plan(self.author)

    def test_short_intro_without_cue_does_not_require_a_fake_camera_transition(self):
        intro = {'page_id': 'overview', 'start_frame': 0, 'end_frame': 12, 'cues': []}
        self.author['scenes'][0]['start_frame'] = 12
        self.author['scenes'].insert(0, intro)
        plan = compile_plan(self.author)
        self.assertEqual(len(plan['scenes'][0]['camera']), 2)
        self.assertEqual(validate(plan)['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
