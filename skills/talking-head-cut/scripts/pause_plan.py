"""Measure ASR boundary gaps and tighten existing seams on the applied frame grid.

These are ASR-derived intervals, not a breath/silence classifier. Preserve words,
retain at least 10ms of existing margins when available, and require listening.
"""
import argparse
from collections import defaultdict
import copy
import math
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'video-production' / 'scripts'))
from bailian_media import load, save


def stats(values):
    values = [0. if abs(v) < 1e-7 else v for v in values]
    return {'count': len(values), 'mean_ms': statistics.mean(values) if values else None,
            'median_ms': statistics.median(values) if values else None,
            'min_ms': min(values) if values else None, 'max_ms': max(values) if values else None,
            'sum_s': sum(values)/1000}


def tighten(plan, words_doc, target_ms=50):
    if plan['revision'] != words_doc['revision'] or not 0 < target_ms <= 1000:
        raise ValueError('Invalid revision or pause target')
    fps = plan['fps']['num']/plan['fps']['den']
    source_rate = (plan.get('source') or {}).get('fps')
    if not isinstance(source_rate, dict) or type(source_rate.get('num')) is not int or type(source_rate.get('den')) is not int or source_rate['num'] <= 0 or source_rate['den'] <= 0:
        raise ValueError('Plan requires source.fps for source frame calculations')
    source_fps = source_rate['num']/source_rate['den']
    groups = defaultdict(list)
    for w in words_doc['words']: groups[w['instance_id']].append(w)
    segments = copy.deepcopy(plan['segments'])
    records = []
    target = target_ms/1000
    for old_left, old_right, left, right in zip(plan['segments'],plan['segments'][1:],segments,segments[1:]):
        a, b = groups[left['id']][-1], groups[right['id']][0]
        end, start = a['source_end_s'], b['source_start_s']
        lm = old_left['source_out_s']-end
        rm = start-old_right['source_in_s']
        if min(lm,rm) < -1e-6: raise ValueError('Existing segment cuts a retained word')
        before = lm+rm
        # Protect existing small leading/trailing margins; never add artificial silence.
        ln = max(0, math.floor((lm-min(.01,lm))*source_fps+1e-7))
        rn = max(0, math.floor((rm-min(.01,rm))*source_fps+1e-7))
        choices = []
        for dl in range(ln+1):
            for dr in range(rn+1):
                after = before-(dl+dr)/source_fps
                if after < -1e-7 or before <= target+1e-7 and dl+dr: continue
                choices.append((round(abs(after-min(target,before)),9),
                                abs((lm-dl/source_fps)-.03), dl, dr, after))
        _, _, dl, dr, after = min(choices)
        left['source_out_s'] = old_left['source_out_s']-dl/source_fps
        right['source_in_s'] = old_right['source_in_s']+dr/source_fps
        records.append({'left':left['id'],'right':right['id'], 'old_final_time_s':old_right['final_in_s'],
                        'old_gap_ms':round(before*1000,4),'new_gap_ms':round(after*1000,4),
                        'left_trim_frames':dl,'right_trim_frames':dr,'word_tail':a.get('word',a.get('text')),
                        'word_head':b.get('word',b.get('text')), 'review':'not_checked',
                        'asr_left_voice_end_s':end,'asr_right_voice_start_s':start})
    cursor_s = 0.0
    for s in segments:
        s['source_in_frame']=round(s['source_in_s']*source_fps);s['source_out_frame']=round(s['source_out_s']*source_fps)
        if abs(s['source_in_frame']/source_fps-s['source_in_s'])>1e-6 or abs(s['source_out_frame']/source_fps-s['source_out_s'])>1e-6:
            raise ValueError('Input plan is not on its declared frame grid')
        source_duration = s['source_out_s']-s['source_in_s']
        if source_duration <= 0: raise ValueError('Tightening would erase a kept segment')
        final_in_frame = round(cursor_s*fps)
        cursor_s += source_duration
        final_out_frame = round(cursor_s*fps)
        s.update(source_frame_count=s['source_out_frame']-s['source_in_frame'],
                 final_in_frame=final_in_frame,final_in_s=final_in_frame/fps,
                 duration_frames=final_out_frame-final_in_frame,
                 final_out_frame=final_out_frame,final_out_s=final_out_frame/fps)
    lookup={s['id']:s for s in segments}
    for r in records:
        r['final_time_s']=lookup[r['right']]['final_in_s']
        r['retained_gap_s']=r['new_gap_ms']/1000
    deleted=[];prev=0
    for s in segments:
        if s['source_in_s']>prev:
            deleted.append({'source_in_s':prev,'source_out_s':s['source_in_s'],
                            'reason':'Prior editorial deletion plus frame-grid pause tightening; see previous plan and seam records'})
        prev=s['source_out_s']
    if prev<plan['source']['duration_s']:
        deleted.append({'source_in_s':prev,'source_out_s':plan['source']['duration_s'],'reason':'Retain prior editorial end selection'})
    duration_frames = round(cursor_s*fps)
    revised={'revision':plan['revision']+'-pause'+str(target_ms),'previous_revision':plan['revision'],
             'source':plan['source'],'fps':plan['fps'],'duration_frames':duration_frames,'duration_s':duration_frames/fps,
             'segments':segments,'seams':records,'deletions':deleted,
             'pause_target_ms':target_ms,'status':'review_required',
             'mapping':'Same original-speed audio/video boundaries on existing frame grid; no added silence'}
    report={'method':'ASR final word end to next retained first word start, only edited segment joins',
            'before':stats([r['old_gap_ms'] for r in records]),'after':stats([r['new_gap_ms'] for r in records]),
            'changed_seams':sum(r['left_trim_frames']+r['right_trim_frames']>0 for r in records),
            'unchanged_short_seams':sum(r['old_gap_ms'] <= target_ms+1e-6 for r in records),
            'frame_ms':1000/fps,'source_frame_ms':1000/source_fps,'target_ms':target_ms,'rows':records,
            'natural_breath_statistics':'not_checked; ASR gaps can contain breath or quiet phonemes'}
    return revised, report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--words',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--target-ms',type=float,default=50)
    a=p.parse_args(); new,report=tighten(load(a.plan),load(a.words),a.target_ms)
    save(a.out/'edit-plan.json',new);save(a.out/'pause-report.json',report)
    print(report['before'],report['after'])
