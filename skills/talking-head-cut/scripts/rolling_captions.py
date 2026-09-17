"""Compile word-timed phrase lines into a two-line rolling display and matching SRT."""
import argparse
from pathlib import Path
from caption_pages import compile_pages, frame, load, save


def compile_rolling(words, editorial):
    fps=editorial['fps']['num']/editorial['fps']['den']
    flat=[]; group_ids=[]; seen=set()
    for group in editorial['groups']:
        if not group['id'] or group['id'] in seen or not group.get('takeaway') or not group['lines']:
            raise ValueError('Each semantic group requires unique ID, takeaway and phrase lines')
        seen.add(group['id'])
        for line in group['lines']:
            flat.append({'takeaway':group['takeaway'],'lines':[line['word_keys']],
                         'emphasis':line.get('emphasis',[])})
            group_ids.append(group['id'])
    result=compile_pages(words,{**editorial,'pages':flat})
    hold=editorial.get('tail_hold_frames',frame(.12,fps))
    motion=editorial.get('move_frames',max(1,frame(.16,fps)))
    if type(hold) is not int or hold<0 or type(motion) is not int or motion<1:
        raise ValueError('Invalid hold/motion frames')
    lines=result['captions']
    for i,line in enumerate(lines):
        line['group_id']=group_ids[i]; line['text']=line['lines'][0]
        line['speech_end_frame']=line['end_frame']
        next_line=lines[i+1] if i+1<len(lines) else None
        next_start=next_line['start_frame'] if next_line else editorial['duration_frames']
        same_group=next_line is not None and group_ids[i+1]==group_ids[i]
        line['end_frame']=next_start if same_group else min(next_start,line['speech_end_frame']+hold)
        line['move_frames']=min(motion,line['end_frame']-line['start_frame'])
        for span in line['emphasis']:
            marker=span.get('marker','underline')
            if marker not in ['underline','box','none']: raise ValueError('Unsupported emphasis marker')
            span['marker']=marker
    # Display lifetime is longer than speech lifetime: a spoken line remains above the next one.
    for i,line in enumerate(lines):
        next_line=lines[i+1] if i+1<len(lines) else None
        line['display_end_frame']=next_line['end_frame'] if next_line and next_line['group_id']==line['group_id'] else line['end_frame']
    return {'revision':editorial['revision'],'fps':editorial['fps'], 'duration_frames':editorial['duration_frames'],
            'lines':lines,'warnings':result['warnings'],'mode':'rolling-two-lines'}


def write_rolling_srt(doc,path):
    fps=doc['fps']['num']/doc['fps']['den']
    def stamp(f):
        ms=frame(f/fps,1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    cues=[]
    for i,line in enumerate(doc['lines']):
        previous=doc['lines'][i-1] if i else None
        text=(previous['text']+'\n' if previous and previous['group_id']==line['group_id'] else '')+line['text']
        cues.append(f"{i+1}\n{stamp(line['start_frame'])} --> {stamp(line['end_frame'])}\n{text}")
    Path(path).write_text('\n\n'.join(cues)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--words',type=Path,required=True);p.add_argument('--editorial',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=compile_rolling(load(a.words),load(a.editorial));save(a.out,result)
    write_rolling_srt(result,a.out.with_suffix('.srt'))
