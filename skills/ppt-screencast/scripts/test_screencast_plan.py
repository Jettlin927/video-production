import copy
import json
from pathlib import Path
import tempfile
import unittest

from check_screencast_plan import camera_at, main, validate


DEMO = Path(__file__).resolve().parents[1] / 'assets' / 'demo-plan.json'


class ScreencastPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(DEMO.read_text('utf-8'))

    def test_demo_geometry_passes_but_semantic_review_remains_unchecked(self):
        report = validate(self.plan)
        self.assertEqual(report['cues'], 3)
        self.assertEqual(report['semantic_review'], 'not_checked')

    def test_interpolation_preserves_page_center_and_smooths_midpoint(self):
        keys = [{'frame': 0, 'cx': 0, 'cy': 0, 'scale': 1},
                {'frame': 10, 'cx': 100, 'cy': 200, 'scale': 2}]
        self.assertEqual(camera_at(keys, 5), {'cx': 50, 'cy': 100, 'scale': 1.5})
        self.assertAlmostEqual(camera_at(keys, 2)['cx'], 10.4)

    def test_rejects_known_failure_modes(self):
        mutations = {
            'unknown target': lambda p: p['scenes'][0]['cues'][0].update(target_id='missing'),
            'unknown page': lambda p: p['scenes'][0].update(page_id='missing'),
            'cropped target': lambda p: p['scenes'][0]['camera'][2].update(cx=900),
            'invalid scale': lambda p: p['scenes'][0]['camera'][2].update(scale=0),
            'nonfinite scale': lambda p: p['scenes'][0]['camera'][2].update(scale=float('nan')),
            'unsorted keys': lambda p: p['scenes'][0]['camera'][2].update(frame=30),
            'missing first frame': lambda p: p['scenes'][0]['camera'][0].update(frame=1),
            'missing last frame': lambda p: p['scenes'][0]['camera'][-1].update(frame=286),
            'scene gap': lambda p: p['scenes'][0].update(start_frame=1),
            'scene truncated': lambda p: p.update(duration_frames=300),
            'overlapping cues': lambda p: p['scenes'][0]['cues'][1].update(start_frame=100),
            'no hold': lambda p: p['scenes'][0]['cues'][0].update(draw_frames=60),
            'no semantic reason': lambda p: p['scenes'][0]['cues'][0].update(reason=''),
            'unsupported cue': lambda p: p['scenes'][0]['cues'][0].update(kind='random'),
            'fractional frame': lambda p: p['scenes'][0]['cues'][0].update(start_frame=60.5),
            'negative padding': lambda p: p['scenes'][0]['cues'][0].update(padding=-1),
            'no cues': lambda p: p['scenes'][0].update(cues=[]),
            'element outside page': lambda p: p['pages'][0]['elements'][0].update(x=900),
            'viewport outside output': lambda p: p['viewport'].update(x=1000),
            'camera moving during cue': lambda p: p['scenes'][0]['camera'][3].update(cx=195),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                plan = copy.deepcopy(self.plan)
                mutate(plan)
                with self.assertRaises(ValueError):
                    validate(plan)

    def test_duplicate_ids_rejected(self):
        self.plan['pages'][0]['elements'].append(copy.deepcopy(self.plan['pages'][0]['elements'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate(self.plan)

    def test_cursor_icon_cannot_escape_even_when_target_fits(self):
        self.plan['viewport']['w'] = 430
        with self.assertRaisesRegex(ValueError, 'cursor outside viewport'):
            validate(self.plan)

    def test_subtitle_safe_zone(self):
        self.plan['captions'] = [{'start_frame': 0, 'end_frame': 24,
                                 'x': 32, 'y': 736, 'w': 656, 'h': 48}]
        self.assertEqual(validate(self.plan)['status'], 'pass')
        self.plan['captions'][0]['y'] = 680
        with self.assertRaisesRegex(ValueError, 'overlaps content'):
            validate(self.plan)

    def test_cli_failure_writes_readable_report(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bad.json'
            out = Path(temp) / 'report.json'
            source.write_text('{}', encoding='utf-8')
            self.assertEqual(main(['--plan', str(source), '--out', str(out)]), 1)
            self.assertEqual(json.loads(out.read_text('utf-8'))['status'], 'fail')


if __name__ == '__main__':
    unittest.main(verbosity=2)
