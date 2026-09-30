import copy
import json
from pathlib import Path
import unittest

from build_screencast import compile_plan
from check_screencast_plan import validate


class ScreencastBuildTests(unittest.TestCase):
    def setUp(self):
        self.author = json.loads((Path(__file__).resolve().parents[1] / 'assets/demo-plan.json').read_text('utf-8'))
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
