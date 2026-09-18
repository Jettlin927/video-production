import copy
import unittest

from check_timeline import validate


def plan(source_fps=50, output_fps=30):
    return {
        'revision': 'r',
        'source': {'duration_s': 10, 'fps': {'num': source_fps, 'den': 1}},
        'fps': {'num': output_fps, 'den': 1},
        'duration_s': 2,
        'duration_frames': 60,
        'segments': [{
            'id': 'k1', 'source_in_s': 7.2, 'source_out_s': 9.2,
            'final_in_s': 0, 'final_out_s': 2,
            'final_in_frame': 0, 'final_out_frame': 60,
            'source_in_frame': round(7.2 * source_fps),
            'source_out_frame': round(9.2 * source_fps),
            'source_frame_count': round(2 * source_fps),
        }],
    }


class TimelineTests(unittest.TestCase):
    def test_distinct_source_and_output_rates_pass(self):
        report = validate(plan())
        self.assertEqual(report['status'], 'pass')

    def test_output_rate_cannot_be_used_for_source_frame(self):
        broken = plan()
        broken['segments'][0]['source_in_frame'] = round(7.2 * 30)
        broken['segments'][0]['source_out_frame'] = round(9.2 * 30)
        broken['segments'][0]['source_frame_count'] = round(2 * 30)
        report = validate(broken)
        self.assertEqual(report['status'], 'fail')
        self.assertTrue(any('source_in_frame' in error for error in report['errors']))

    def test_missing_source_fps_fails(self):
        broken = copy.deepcopy(plan())
        broken['source'].pop('fps')
        with self.assertRaisesRegex(ValueError, 'source.fps'):
            validate(broken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
