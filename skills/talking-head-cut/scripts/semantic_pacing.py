"""Apply explicit semantic pause decisions on the audio sample grid.

ASR gaps are candidates, not measured pure silence. No automatic semantic classifier.
Video uses cumulative frame rounding; audio and word times remain sample accurate.
"""
import argparse
import copy
import math
from pathlib import Path
from pause_plan import load, save, stats

TARGETS = {'within_sentence': 20, 'expansion': 30, 'sentence': 60, 'topic': 120}


def candidates(words):
    result = []
    for a, b in zip(words, words[1:]):
        gap = b['final_start_s'] - a['final_end_s']
        seam = a['instance_id'] != b['instance_id']
        if seam or gap > 1e-7:
            result.append((a, b, gap, seam))
    return result


def prepare(words_doc):
    """Export all candidate IDs and context before the Agent makes semantic decisions."""
    text = lambda w:w.get('corrected_text',w.get('text',w.get('word','')))
    ws=words_doc['words'];positions={id(w):i for i,w in enumerate(ws)}
    rows=[]
    for a,b,gap,seam in candidates(ws):
        i=positions[id(a)]
        rows.append({'left_key':a['instance_id']+':'+a['id'],'right_key':b['instance_id']+':'+b['id'],
                     'left_context':''.join(text(w) for w in ws[max(0,i-9):i+1]),
                     'right_context':''.join(text(w) for w in ws[i+1:i+11]),
                     'source_left_end_s':a['source_end_s'],'source_right_start_s':b['source_start_s'],
                     'old_gap_ms':round(gap*1000,5),'kind':'edited_join' if seam else 'internal',
                     'category':None,'reason':'','review':'not_checked'})
    return {'revision':words_doc['revision'],'preset_targets_ms':dict(TARGETS),'boundaries':rows}


def apply(plan, words_doc, decisions, sample_rate=48000):
    if plan['revision'] != words_doc['revision'] or decisions['revision'] != plan['revision']:
        raise ValueError('Stale pacing revision')
    if sample_rate <= 0:
        raise ValueError('Invalid audio sample rate')
    fps = plan['fps']['num'] / plan['fps']['den']
    segs = {s['id']: s for s in plan['segments']}
    presets = decisions.get('preset_targets_ms', TARGETS)
    if set(presets) != set(TARGETS):
        raise ValueError('Pacing preset must define all four semantic categories')
    choices = {}
    for d in decisions['boundaries']:
        key = (d['left_key'], d['right_key'])
        if key in choices or d['category'] not in TARGETS or not d.get('reason'):
            raise ValueError('Duplicate decision or missing semantic category/reason')
        choices[key] = d
    cuts, rows, used = [], [], set()
    for a, b, gap, seam in candidates(words_doc['words']):
        key = (a['instance_id']+':'+a['id'], b['instance_id']+':'+b['id'])
        if key not in choices:
            raise ValueError('Missing semantic decision: '+str(key))
        used.add(key)
        d = choices[key]
        target = d.get('target_ms', presets[d['category']]) / 1000
        if not math.isfinite(target) or not 0 < target <= 1:
            raise ValueError('Invalid pause target')
        lm = segs[a['instance_id']]['source_out_s']-a['source_end_s'] if seam else gap/2
        rm = b['source_start_s']-segs[b['instance_id']]['source_in_s'] if seam else gap/2
        if min(gap, lm, rm) < -1e-6:
            raise ValueError('Overlapping speech or source word already cut; review first')
        protected = d.get('preserve', False) or any(w.get('timing_status') for w in (a,b))
        after = gap if protected else min(gap, max(target, min(.01,lm)+min(.01,rm)))
        # Split the remaining handle evenly where possible; protect available 10ms edges.
        low,high = max(min(.01,lm),after-rm), min(lm,after-min(.01,rm))
        left_keep = min(high,max(low,after/2))
        start = round((a['final_end_s']+left_keep)*sample_rate)
        stop = round((b['final_start_s']-(after-left_keep))*sample_rate)
        if stop > start:
            cuts.append((start,stop))
        removed = max(0, stop-start)/sample_rate
        rows.append({**d, 'target_ms':target*1000, 'kind':'edited_join' if seam else 'internal',
                     'old_gap_ms':round(gap*1000,5), 'new_gap_ms':round((gap-removed)*1000,5),
                     'removed_samples':max(0,stop-start), 'old_time_s':a['final_end_s'],
                     'protected':bool(protected), 'review':'not_checked'})
    if used != set(choices):
        raise ValueError('Decision names an unknown/non-candidate boundary')
    cuts.sort()
    if any(a[1] > b[0] for a,b in zip(cuts,cuts[1:])):
        raise ValueError('Overlapping deletion intervals')
    result, cursor = [], 0
    for old in plan['segments']:
        old_a, old_b = round(old['final_in_s']*sample_rate), round(old['final_out_s']*sample_rate)
        ranges = [(old_a,old_b)]
        for ca,cb in cuts:
            ranges = [(x,y) for a,b in ranges for x,y in ((a,min(b,ca)),(max(a,cb),b)) if y>x]
        for i,(a,b) in enumerate(ranges):
            s = copy.deepcopy(old)
            sa = old['source_in_s']+(a-old_a)/sample_rate
            sb = old['source_in_s']+(b-old_a)/sample_rate
            fa,fb = cursor/sample_rate,(cursor+b-a)/sample_rate
            vf,ve = round(fa*fps),round(fb*fps)
            s.update(id=old['id']+f'-p{i+1}',parent_instance_id=old['id'],
                     source_in_s=sa,source_out_s=sb,final_in_s=fa,final_out_s=fb,
                     final_in_sample=cursor,final_out_sample=cursor+b-a,
                     old_final_in_s=a/sample_rate,old_final_out_s=b/sample_rate,
                     final_in_frame=vf,final_out_frame=ve,duration_frames=ve-vf,
                     source_in_frame=round((sa+vf/fps-fa)*fps))
            s.pop('source_out_frame',None)
            if ve <= vf:
                raise ValueError('Video segment below one frame; preserve this pause and review')
            result.append(s);cursor += b-a
    frames = math.ceil(cursor/sample_rate*fps-1e-7)
    result[-1]['final_out_frame']=frames
    result[-1]['duration_frames']=frames-result[-1]['final_in_frame']
    new = {**plan,'revision':plan['revision']+'-semantic','previous_revision':plan['revision'],
           'segments':result,'duration_s':frames/fps,'duration_frames':frames,
           'audio_duration_s':cursor/sample_rate,'audio_samples':cursor,'sample_rate':sample_rate,
           'timing_mode':'sample_audio_cumulative_video','status':'review_required',
           'seams':rows,'deletions':[{'old_final_in_s':a/sample_rate,'old_final_out_s':b/sample_rate} for a,b in cuts],
           'mapping':'Audio/words use sample times; video boundaries round cumulative final time, source frame phase error <= half a frame. Tail padding only.'}
    new.pop('pause_target_ms',None)
    report={'method':'ASR word-end to next word-start; includes internal gaps and edited joins; not pure-silence measurement',
            'before':stats([r['old_gap_ms'] for r in rows]),'after':stats([r['new_gap_ms'] for r in rows]),
            'positive_before':stats([r['old_gap_ms'] for r in rows if r['old_gap_ms']>0]),
            'positive_after':stats([r['new_gap_ms'] for r in rows if r['old_gap_ms']>0]),
            'by_category':{c:stats([r['new_gap_ms'] for r in rows if r['category']==c]) for c in TARGETS},
            'rows':rows,'natural_listening':'not_checked'}
    return new,report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--words',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepare',action='store_true')
    p.add_argument('--plan',type=Path);p.add_argument('--decisions',type=Path)
    a=p.parse_args()
    if a.prepare:
        save(a.out/'pause-decisions.json',prepare(load(a.words)))
    else:
        if not a.plan or not a.decisions:p.error('--plan and --decisions are required to apply')
        plan,report=apply(load(a.plan),load(a.words),load(a.decisions))
        save(a.out/'edit-plan.json',plan);save(a.out/'pause-report.json',report)
