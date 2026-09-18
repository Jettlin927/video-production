import copy
import unittest
from semantic_pacing import apply,prepare
from map_words import remap


class SemanticPacingTests(unittest.TestCase):
    def fixture(self):
        plan={'revision':'r','fps':{'num':25,'den':1},'source':{'duration_s':5,'fps':{'num':50,'den':1}},'duration_frames':50,
              'segments':[{'id':'a','source_in_s':1.,'source_out_s':2.,'final_in_s':0.,'final_out_s':1.},
                          {'id':'b','source_in_s':3.,'source_out_s':4.,'final_in_s':1.,'final_out_s':2.}]}
        source={'revision':'asr','words':[{'id':'1','source_start_s':1.1,'source_end_s':1.98,'text':'没有难度'},
                                       {'id':'2','source_start_s':3.04,'source_end_s':3.9,'text':'而且'}]}
        words=remap(source,plan);decisions=prepare(words)
        for d in decisions['boundaries']:d.update(category='expansion',reason='同一观点补充')
        return plan,source,words,decisions

    def test_60_to_30_ms_at_25fps_preserves_spoken_durations(self):
        plan,source,words,decisions=self.fixture()
        revised,report=apply(plan,words,decisions)
        actual=remap(source,revised)['words']
        self.assertAlmostEqual(actual[1]['final_start_s']-actual[0]['final_end_s'],.03)
        self.assertEqual(report['rows'][0]['removed_samples'],1440)
        self.assertEqual(revised['audio_samples'],94560)
        for before,after in zip(source['words'],actual):
            self.assertAlmostEqual(before['source_end_s']-before['source_start_s'],after['final_end_s']-after['final_start_s'])
        self.assertEqual(revised['duration_frames'],50)
        for seg in revised['segments']:
            self.assertLessEqual(abs(seg['final_in_frame']/25-seg['final_in_s']),.020001)
            self.assertEqual(seg['source_in_frame'],round(seg['source_in_s']*50))
            self.assertEqual(seg['source_out_frame'],round(seg['source_out_s']*50))

    def test_source_and_output_frame_rates_are_independent(self):
        plan,source,words,decisions=self.fixture()
        revised,_=apply(plan,words,decisions)
        self.assertEqual(revised['fps'],{'num':25,'den':1})
        self.assertEqual(revised['source']['fps'],{'num':50,'den':1})
        for seg in revised['segments']:
            self.assertEqual(seg['source_in_frame'],round(seg['source_in_s']*50))
            self.assertEqual(seg['source_out_frame'],round(seg['source_out_s']*50))
            self.assertEqual(seg['source_frame_count'],seg['source_out_frame']-seg['source_in_frame'])

    def test_missing_source_frame_rate_is_rejected(self):
        plan,source,words,decisions=self.fixture()
        plan['source'].pop('fps')
        with self.assertRaisesRegex(ValueError,'source.fps'):
            apply(plan,words,decisions)

    def test_categories_and_internal_split(self):
        plan,source,words,decisions=self.fixture()
        source['words']=[{'id':str(i),'source_start_s':a,'source_end_s':b,'text':str(i)} for i,(a,b) in enumerate([(1.1,1.3),(1.6,1.98),(3.04,3.9)])]
        words=remap(source,plan);decisions=prepare(words)
        for d in decisions['boundaries']:d.update(category='within_sentence' if d['kind']=='internal' else 'sentence',reason='语义判断')
        revised,report=apply(plan,words,decisions)
        self.assertEqual([r['new_gap_ms'] for r in report['rows']],[20,60])
        self.assertEqual(len(revised['segments']),3)
        self.assertEqual([w['id'] for w in remap(source,revised)['words']],['0','1','2'])
        decisions['boundaries'][0]['category']='topic'
        _,report=apply(plan,words,decisions)
        self.assertEqual(report['rows'][0]['new_gap_ms'],120)

    def test_missing_unknown_duplicate_or_stale_decision_rejected(self):
        plan,source,words,decisions=self.fixture()
        for mutate in [lambda d:d['boundaries'].clear(),lambda d:d['boundaries'].append(copy.deepcopy(d['boundaries'][0])),
                       lambda d:d.update(revision='stale'),lambda d:d['boundaries'][0].update(category=None),
                       lambda d:d['boundaries'][0].update(left_key='unknown')]:
            invalid=copy.deepcopy(decisions);mutate(invalid)
            with self.assertRaises(ValueError):apply(plan,words,invalid)

    def test_preserve_uncertain_and_already_short(self):
        plan,source,words,decisions=self.fixture()
        words['words'][1]['timing_status']='point_only_review_required'
        _,report=apply(plan,words,decisions)
        self.assertEqual(report['rows'][0]['new_gap_ms'],60)
        self.assertTrue(report['rows'][0]['protected'])
        words['words'][1].pop('timing_status')
        decisions['boundaries'][0]['category']='topic'
        _,report=apply(plan,words,decisions)
        self.assertEqual(report['rows'][0]['new_gap_ms'],60)

    def test_saved_preset_is_reused_and_override_wins(self):
        plan,source,words,decisions=self.fixture()
        decisions['preset_targets_ms']['expansion']=40
        self.assertEqual(prepare(words)['preset_targets_ms']['expansion'],30)
        _,report=apply(plan,words,decisions)
        self.assertEqual(report['rows'][0]['target_ms'],40)
        self.assertEqual(report['rows'][0]['new_gap_ms'],40)
        decisions['boundaries'][0]['target_ms']=30
        _,report=apply(plan,words,decisions)
        self.assertEqual(report['rows'][0]['new_gap_ms'],30)


if __name__=='__main__':unittest.main(verbosity=2)
