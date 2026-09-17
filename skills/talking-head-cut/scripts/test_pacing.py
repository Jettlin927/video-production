import tempfile
from pathlib import Path
import unittest
from pause_plan import tighten
from rolling_captions import compile_rolling,write_rolling_srt
from map_words import remap

class Tests(unittest.TestCase):
    def test_pause_frame_grid_and_word_margins(self):
        plan={'revision':'r','fps':{'num':25,'den':1},'source':{'duration_s':5},'segments':[
            {'id':'a','source_in_s':1.,'source_out_s':2.,'final_in_s':0.,'final_out_s':1.},
            {'id':'b','source_in_s':3.,'source_out_s':4.,'final_in_s':1.,'final_out_s':2.}]}
        words={'revision':'r','words':[
            {'id':'1','instance_id':'a','source_start_s':1.1,'source_end_s':1.9,'word':'完整'},
            {'id':'2','instance_id':'b','source_start_s':3.06,'source_end_s':3.9,'word':'原声'}]}
        revised,report=tighten(plan,words)
        self.assertAlmostEqual(report['before']['mean_ms'],160)
        self.assertAlmostEqual(report['after']['mean_ms'],40)
        self.assertGreaterEqual(revised['segments'][0]['source_out_s'],1.91-1e-7)
        self.assertLessEqual(revised['segments'][1]['source_in_s'],3.05+1e-7)
        self.assertEqual(len(remap(words,revised)['words']),2)
        words['words'][0]['source_end_s']=1.99;words['words'][1]['source_start_s']=3.01
        _,report=tighten(plan,words)
        self.assertAlmostEqual(report['after']['mean_ms'],20)
        self.assertEqual(report['changed_seams'],0)

    def test_rolling_lifetimes_and_group_reset(self):
        words={'revision':'r','words':[{'id':str(i),'instance_id':'k','text':str(i),
            'final_start_s':i,'final_end_s':i+.8} for i in range(4)]}
        edit={'revision':'r','fps':{'num':25,'den':1},'duration_frames':100,
              'groups':[{'id':'first','takeaway':'前三行','lines':[
                  {'word_keys':['k:0']},{'word_keys':['k:1'],'emphasis':[{'word_keys':['k:1'],'role':'focus','reason':'重点','marker':'underline'}]},
                  {'word_keys':['k:2']}]}, {'id':'second','takeaway':'新句','lines':[{'word_keys':['k:3']}]}]}
        doc=compile_rolling(words,edit)
        self.assertEqual(doc['lines'][0]['display_end_frame'],50)
        self.assertEqual(doc['lines'][1]['emphasis'][0]['start_frame'],25)
        self.assertEqual(doc['lines'][2]['end_frame'],73)
        self.assertEqual(doc['lines'][3]['start_frame'],75)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'out.srt';write_rolling_srt(doc,p);text=p.read_text()
            self.assertIn('0\n1',text);self.assertIn('1\n2',text);self.assertNotIn('2\n3',text)

    def test_zero_duration_requires_explicit_unreliable_anchor(self):
        plan={'revision':'new','fps':{'num':25,'den':1},'source':{'duration_s':2},'duration_frames':50,
              'segments':[{'id':'k','source_in_s':0,'source_out_s':2,'final_in_s':0,'final_out_s':2}]}
        words={'revision':'source','words':[{'id':'z','source_start_s':1,'source_end_s':1}]}
        with self.assertRaises(ValueError):remap(words,plan)
        words['words'][0]['timing_status']='point_only_review_required'
        result=remap(words,plan)
        self.assertEqual(result['words'][0]['final_start_s'],result['words'][0]['final_end_s'])

if __name__=='__main__':unittest.main(verbosity=2)
