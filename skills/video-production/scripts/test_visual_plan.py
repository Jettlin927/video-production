"""Offline contract tests; synthetic media is not generated-image quality evidence."""
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import bailian_media as media
from prepare_broll import stage
from visual_plan import (STYLE_FIELDS, check_preset_consistency, known_style_ids,
                         require_visual_review, style_preset, validate_visual_plan)


CFG = {'DASHSCOPE_BASE_URL': 'https://test.cn-beijing.maas.aliyuncs.com/api/v1'}


def plan():
    return {'schema_version': 2, 'revision': 'cut-1', 'fps': {'num': 25, 'den': 1},
            'duration_frames': 200,
            'visual_style': {'id': 'cartoon-1', 'medium': '二维卡通', 'palette': '米白深蓝',
                             'rendering': '平涂圆润线条', 'composition': '下部留白', 'avoid': '写实摄影'},
            'budget': {'max_total_jobs': 4, 'max_attempts_per_shot': 2,
                       'max_estimated_cost': 2, 'currency': 'CNY'},
            'jobs': [{'id': 'organize-v1', 'shot_id': 'organize', 'kind': 'image',
                      'source_type': 'generated', 'purpose': 'explanation',
                      'source_text': '整理客户资料', 'source_word_ids': ['k1:w1'],
                      'visual_goal': '零散记录汇集成卡片', 'claim_scope': '流程示意，不代表真实交付',
                      'style_id': 'cartoon-1', 'estimated_cost': .5, 'prompt': '空白便签整理成卡片',
                      'start_frame': 25, 'end_frame': 75, 'placement': 'full', 'reason': '解释信息整理'}]}


def png_bytes():
    def chunk(kind, payload):
        return (struct.pack('!I', len(payload)) + kind + payload
                + struct.pack('!I', zlib.crc32(kind + payload)))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 8, 8, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes((40, 80, 120)) * 8) * 8))
            + chunk(b'IEND', b''))


def fetched(url, path, kind):
    Path(path).write_bytes(png_bytes())


class Client:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def call(self, *args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError('submission uncertain')
        return {'output': {'choices': [{'message': {'content': [{'image': 'https://test.invalid/fixture.png'}]}}]}}


def collect(p, out, client=None):
    return media.load(media.run(p, CFG, out, True, client or Client(), fetched)['manifest'])


def reviewed(m):
    anchor = next((j for j in m['jobs'] if j['source_type'] == 'generated'), None)
    if anchor:
        m['style_reference'] = {'path': anchor['path'], 'sha256': anchor['sha256']}
    for j in m['jobs']:
        j.update(asset_review='pass', review_notes='Synthetic test fixture only')
        if j['source_type'] == 'generated':
            j.update(style_review='pass', style_review_notes='Synthetic test fixture only',
                     style_reference_sha256=anchor['sha256'])
    return m


class VisualPlanTests(unittest.TestCase):
    def test_all_requests_receive_identical_art_direction(self):
        p = plan()
        second = {**p['jobs'][0], 'id': 'desk', 'shot_id': 'desk', 'prompt': '职员整理卡片'}
        p['jobs'].append(second)
        with tempfile.TemporaryDirectory() as temp:
            result = media.run(p, CFG, Path(temp) / 'unused')
            prompts = [j['body']['input']['messages'][0]['content'][0]['text'] for j in result['jobs']]
            self.assertEqual(prompts[0].split('本镜头内容')[0], prompts[1].split('本镜头内容')[0])
            self.assertIn('二维卡通', prompts[1])
            self.assertIn(second['prompt'], prompts[1])
            self.assertFalse((Path(temp) / 'unused').exists())

    def test_generated_evidence_rejected_before_provider(self):
        p = plan(); p['jobs'][0]['purpose'] = 'evidence'
        c = Client()
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, 'Evidence requires'):
            collect(p, temp, c)
        self.assertEqual(c.calls, [])

    def test_missing_semantics_and_mixed_styles_rejected(self):
        for field in ('source_text', 'source_word_ids', 'visual_goal', 'claim_scope', 'style_id'):
            with self.subTest(field=field):
                p = plan(); del p['jobs'][0][field]
                with self.assertRaises(ValueError):
                    media.validate_plan(p)
        p = plan(); p['jobs'][0]['style_id'] = 'photo-2'
        with self.assertRaisesRegex(ValueError, 'shared visual style'):
            media.validate_plan(p)

    def test_style_change_cannot_reuse_paid_asset_id(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan(); c = Client(); collect(p, temp, c)
            p['visual_style']['medium'] = '写实摄影'
            with self.assertRaisesRegex(ValueError, 'Changed generation'):
                collect(p, temp, c)
            self.assertEqual(len(c.calls), 1)

    def test_art_direction_locked_across_batches_with_new_asset_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan(); c = Client(); collect(p, temp, c)
            p['jobs'][0]['id'] = 'second-batch'
            p['jobs'][0]['shot_id'] = 'second-shot'
            p['visual_style']['medium'] = '写实摄影'
            with self.assertRaisesRegex(ValueError, 'locked across batches'):
                collect(p, temp, c)
            self.assertEqual(len(c.calls), 1)
            p['visual_style']['id'] = 'photo-2'; p['jobs'][0]['style_id'] = 'photo-2'
            with self.assertRaisesRegex(ValueError, 'locked across batches'):
                collect(p, temp, c)
            p['style_change_reason'] = 'Explicit whole-film restyle test'
            m = collect(p, temp, c)
            self.assertEqual(m['visual_style']['id'], 'photo-2')
            self.assertEqual(len(c.calls), 2)

    def test_style_presets_are_usable_and_self_consistent(self):
        self.assertIn('real-biz-01', known_style_ids())
        self.assertGreaterEqual(len(known_style_ids()), 3)
        for style_id in known_style_ids():
            with self.subTest(style=style_id):
                block = style_preset(style_id)
                self.assertEqual(block['id'], style_id)
                for key in STYLE_FIELDS:
                    self.assertTrue(block.get(key), f'{style_id} missing {key}')
                check_preset_consistency(block)  # must not raise
                p = plan(); p['visual_style'] = block
                p['jobs'][0]['style_id'] = style_id
                validate_visual_plan(p)

    def test_preset_id_cannot_carry_a_different_look(self):
        p = plan()
        p['visual_style'] = style_preset('real-biz-01')
        p['jobs'][0]['style_id'] = 'real-biz-01'
        validate_visual_plan(p)
        p['visual_style']['medium'] = '二维卡通'
        with self.assertRaisesRegex(ValueError, 'does not match preset'):
            validate_visual_plan(p)

    def test_aspect_follows_the_finished_film(self):
        portrait, landscape = style_preset('real-biz-01'), style_preset('real-biz-01', 'landscape')
        self.assertIn('竖幅 9:16', portrait['composition'])
        self.assertIn('横幅 16:9', landscape['composition'])
        self.assertNotEqual(portrait['composition'], landscape['composition'])
        # only composition varies with aspect; the look itself is fixed
        for key in STYLE_FIELDS:
            if key != 'composition':
                self.assertEqual(portrait[key], landscape[key])
        with self.assertRaisesRegex(ValueError, 'Unknown aspect'):
            style_preset('real-biz-01', 'square')
        with self.assertRaisesRegex(ValueError, 'Unknown style preset'):
            style_preset('no-such-style')

    def test_custom_style_id_remains_allowed(self):
        p = plan()  # cartoon-1 is not a preset and must keep working
        validate_visual_plan(p)
        p['visual_style']['id'] = 'my-house-style'
        p['jobs'][0]['style_id'] = 'my-house-style'
        validate_visual_plan(p)

    def test_unchanged_review_preserved_but_new_claim_or_revision_resets_it(self):
        for change in ('claim', 'revision'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                p = plan(); c = Client(); m = reviewed(collect(p, temp, c))
                media.save(Path(temp) / 'media-manifest.json', m)
                self.assertEqual(collect(p, temp, c)['jobs'][0]['style_review'], 'pass')
                if change == 'claim':
                    p['jobs'][0]['claim_scope'] = 'Different interpretation'
                else:
                    p['revision'] = 'cut-2'
                changed = collect(p, temp, c)['jobs'][0]
                self.assertEqual(changed['asset_review'], 'not_checked')
                self.assertEqual(changed['style_review'], 'not_checked')
                self.assertEqual(len(c.calls), 1)

    def test_unchecked_style_or_changed_reference_cannot_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            m = reviewed(collect(plan(), Path(temp) / 'generated'))
            for status in ('not_checked', 'fail'):
                m['jobs'][0]['style_review'] = status
                with self.assertRaisesRegex(ValueError, 'style_review=pass'):
                    stage(m, m, Path(temp) / 'public')
            m['jobs'][0]['style_review'] = 'pass'
            m['style_reference']['sha256'] = 'different'
            with self.assertRaisesRegex(ValueError, 'style_review=pass'):
                stage(m, m, Path(temp) / 'public')

    def test_mutated_manifest_invalidates_review(self):
        with tempfile.TemporaryDirectory() as temp:
            m = reviewed(collect(plan(), temp))
            m['jobs'][0]['purpose'] = 'pacing'
            with self.assertRaisesRegex(ValueError, 'context changed'):
                require_visual_review(m, m['jobs'][0])

    def test_budget_rejects_whole_batch_before_any_submission(self):
        for key, value in [('max_estimated_cost', .4), ('max_total_jobs', 1)]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                p = plan(); p['budget'][key] = value
                p['jobs'].append({**p['jobs'][0], 'id': 'second', 'shot_id': 'second'})
                c = Client()
                with self.assertRaisesRegex(ValueError, 'exceeded'):
                    collect(p, temp, c)
                self.assertEqual(c.calls, [])

    def test_split_batches_and_unknown_submissions_count_toward_budget(self):
        for uncertain in (False, True):
            with self.subTest(uncertain=uncertain), tempfile.TemporaryDirectory() as temp:
                p = plan(); p['budget']['max_total_jobs'] = 1
                c = Client(fail=uncertain)
                if uncertain:
                    with self.assertRaises(RuntimeError): collect(p, temp, c)
                else:
                    collect(p, temp, c)
                p['jobs'][0]['id'] = 'replacement'
                p['jobs'][0]['shot_id'] = 'another-shot'
                with self.assertRaisesRegex(ValueError, 'max_total_jobs'):
                    collect(p, temp, c)
                self.assertEqual(len(c.calls), 1)

    def test_regeneration_limit_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan(); c = Client(); collect(p, temp, c); collect(p, temp, c)
            p['jobs'][0]['id'] = 'organize-v2'; collect(p, temp, c)
            p['jobs'][0]['id'] = 'organize-v3'
            with self.assertRaisesRegex(ValueError, 'regeneration limit'):
                collect(p, temp, c)
            self.assertEqual(len(c.calls), 2)

    def test_new_id_cannot_retry_an_uncertain_shot(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan(); c = Client(fail=True)
            with self.assertRaises(RuntimeError): collect(p, temp, c)
            p['jobs'][0]['id'] = 'organize-v2'
            with self.assertRaisesRegex(ValueError, 'uncertain or pending'):
                collect(p, temp, c)
            self.assertEqual(len(c.calls), 1)

    def test_invalid_cost_and_unknown_schema_rejected(self):
        for cost in (0, -1, float('nan'), float('inf'), True):
            p = plan(); p['jobs'][0]['estimated_cost'] = cost
            with self.assertRaises(ValueError): media.validate_plan(p)
        p = plan(); p['schema_version'] = 3
        with self.assertRaisesRegex(ValueError, 'schema_version'): media.validate_plan(p)

    def test_changed_later_job_rejected_before_new_earlier_submission(self):
        with tempfile.TemporaryDirectory() as temp:
            p = plan(); c = Client(); collect(p, temp, c)
            new = {**p['jobs'][0], 'id': 'new', 'shot_id': 'new'}
            p['jobs'][0]['prompt'] = 'Changed prompt'
            p['jobs'].insert(0, new)
            with self.assertRaisesRegex(ValueError, 'Changed generation'):
                collect(p, temp, c)
            self.assertEqual(len(c.calls), 1)

    def test_real_evidence_requires_basis(self):
        p = plan(); j = p['jobs'][0]
        j.update(source_type='local_real', purpose='evidence', path='unused.png', source_note='课堂原始照片')
        with self.assertRaisesRegex(ValueError, 'evidence_basis'): media.validate_plan(p)

    def test_real_and_template_assets_collect_without_key(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'real.png'; source.write_bytes(png_bytes())
            p = plan(); j = p['jobs'][0]
            j.update(source_type='local_real', purpose='evidence', path=str(source),
                     source_note='Synthetic provenance fixture', evidence_basis='Only this fixture, not a real event')
            del p['visual_style']; del p['budget']
            m = media.load(media.run(p, {}, Path(temp) / 'out', True)['manifest'])
            self.assertEqual(m['jobs'][0]['sha256'], media.file_hash(source))
            self.assertNotIn('model', m['jobs'][0])

    def test_real_staging_keeps_source_labels_and_rejects_reference_mutation(self):
        if not Path(media.tool_path('ffmpeg')).is_file():
            self.skipTest('FFmpeg unavailable: staging not tested')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'; p = plan(); m = reviewed(collect(p, out))
            real = Path(temp) / 'real.png'; real.write_bytes(png_bytes())
            j = {**p['jobs'][0], 'id': 'real', 'source_type': 'local_real', 'purpose': 'evidence',
                 'path': str(real), 'source_note': 'Synthetic fixture', 'evidence_basis': 'Fixture only',
                 'start_frame': 80, 'end_frame': 130}
            p['jobs'].append(j)
            p['jobs'].append({**j, 'id': 'template', 'source_type': 'template', 'purpose': 'explanation',
                              'start_frame': 140, 'end_frame': 190})
            m = reviewed(collect(p, out))
            result = stage(m, m, Path(temp) / 'public', width=64, height=96)
            self.assertEqual([a['label'] for a in result['assets']], ['AI 生成示意', '', '示意图'])
            self.assertEqual(result['assets'][1]['evidence_basis'], 'Fixture only')
            for asset in result['assets']:
                self.assertTrue((Path(temp) / 'public' / asset['src']).is_file())
            anchor = Path(temp) / 'anchor.png'; anchor.write_bytes(b'changed')
            m['style_reference']['path'] = str(anchor)
            with self.assertRaisesRegex(ValueError, 'reference image changed'):
                stage(m, m, Path(temp) / 'rejected', width=64, height=96)


if __name__ == '__main__':
    unittest.main(verbosity=2)
