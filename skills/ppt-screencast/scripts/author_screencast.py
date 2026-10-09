"""Bind semantic page/cue authorship to measured sentence timings and paginate captions."""
import copy

from check_screencast_plan import require, number, validate_content_sources


def text_pages(text, line_chars=18):
    text = text.replace('\r', '').replace('\n', '')
    lines = []
    while text:
        end = min(line_chars, len(text))
        # Closing punctuation stays with its preceding text, not at a line's start.
        while end < len(text) and text[end] in '，。！？；：、,.!?;:)]）】”：':
            if end > 1:
                end -= 1
                break
            end += 1
        lines.append(text[:end]); text = text[end:]
    return [lines[i:i + 2] for i in range(0, len(lines), 2)]


def bind_content(content, script, timing, duration_s):
    plan = copy.deepcopy(content)
    canvas = plan.pop('canvas')
    plan.update(canvas)
    fps = number(plan['fps'], 'fps', positive=True, integer=True)
    plan['duration_frames'] = round(number(duration_s, 'audio duration', positive=True) * fps)
    plan['script'] = copy.deepcopy(script)
    validate_content_sources(plan)
    sentences = script['sentences']
    ordered = [sentence['id'] for sentence in sentences]
    times = {row['id']: row for row in timing['sentences']}
    require(len(times) == len(timing['sentences']) and set(times) == set(ordered), 'timing must cover every source sentence exactly once')
    windows, previous_end = {}, 0
    for sentence in sentences:
        row = times[sentence['id']]
        a = number(row['start_s'], 'sentence.start_s')
        b = number(row['end_s'], 'sentence.end_s', positive=True)
        require(previous_end <= a < b <= duration_s + 1 / fps, 'sentence timing is unordered or outside audio')
        require(row.get('text_zh', sentence['text_zh']) == sentence['text_zh'], 'timing text differs from source')
        previous_end = b
        windows[sentence['id']] = {'start_frame': max(0, round(a * fps)),
                                   'end_frame': min(plan['duration_frames'], max(round(a * fps) + 1, round(b * fps)))}
    plan['narration_windows'] = windows
    require([sid for scene in plan['scenes'] for sid in scene['sentences']] == ordered,
            'scenes must cover source sentence IDs once, in narration order')
    page_map = {page['id']: page for page in plan['pages']}
    transition, hold = max(3, round(fps / 3)), max(3, round(fps / 4))
    gap, minimum = transition - 1, max(6, round(fps * .4))
    boundaries = [0]
    for before, after in zip(plan['scenes'], plan['scenes'][1:]):
        boundaries.append(round((windows[before['sentences'][-1]]['end_frame'] + windows[after['sentences'][0]]['start_frame']) / 2))
    boundaries.append(plan['duration_frames'])
    for index, scene in enumerate(plan['scenes']):
        start, end = boundaries[index:index + 2]
        scene.update(start_frame=start, end_frame=end)
        require(scene['page_id'] in page_map, 'unknown page_id')
        targets = {e['id']: e for e in page_map[scene['page_id']]['elements']}
        authored = scene['cues']
        specs = []
        for cue in authored:
            ids = cue['sentences']
            require(ids and all(sid in scene['sentences'] for sid in ids), 'cue sentence must belong to its scene')
            require([ordered.index(sid) for sid in ids] == sorted(set(ordered.index(sid) for sid in ids)), 'cue sentence IDs must be unique and ordered')
            indexes = [ordered.index(sid) for sid in ids]
            require(indexes == list(range(indexes[0], indexes[-1] + 1)), 'cue sentence IDs must form a contiguous narration window')
            require(cue['target_id'] in targets, 'unknown target_id')
            require(set(ids) <= set(targets[cue['target_id']].get('source_ids', [])), 'cue target does not cite its narration sentences')
            a = max(windows[ids[0]]['start_frame'], start + hold + transition)
            b = min(windows[ids[-1]]['end_frame'], end - 1 - hold - transition)
            specs.append((a, b, cue))
        # Order by narration, not the visual top/bottom order in the authored array.
        specs.sort(key=lambda spec: spec[0])
        latest = [b - minimum for a, b, cue in specs]
        for i in range(len(specs) - 2, -1, -1):
            latest[i] = min(latest[i], latest[i + 1] - gap - minimum)
        cues, previous = [], start + hold
        for i, (a, b, cue) in enumerate(specs):
            a = max(a, previous + gap)
            require(a <= latest[i], f"{scene['page_id']}/{cue['target_id']}: emphasis cannot fit its own narration; merge targets or reduce cues")
            if i + 1 < len(specs):
                b = min(b, latest[i + 1] - gap)
                if specs[i + 1][0] <= a + minimum + gap:
                    # Shared sentence: split the valid window rather than borrowing another sentence.
                    b = min(b, max(a + minimum, (a + specs[i + 1][1] - gap) // 2))
            require(b - a >= minimum, 'cue lacks drawing/read time')
            entry = {k: v for k, v in cue.items() if k != 'sentences'}
            entry.update(narration_id=cue['sentences'][0], narration_ids=cue['sentences'], start_frame=a, end_frame=b)
            cues.append(entry)
            previous = b
        scene['cues'] = cues
        scene.pop('sentences')

    view = plan['viewport']
    margin = max(12, round(plan['width'] * .025))
    available = plan['height'] - view['y'] - view['h'] - 2 * margin
    require(available > 0 or 'caption_box' in plan, 'viewport must leave room for captions')
    caption_box = plan.pop('caption_box', {'x': margin, 'y': plan['height'] - margin - min(available, plan['width'] * .14),
                                          'w': plan['width'] - 2 * margin, 'h': min(available, plan['width'] * .14)})
    captions = []
    for sentence in sentences:
        pages = text_pages(sentence['text_zh'])
        window = windows[sentence['id']]
        start, end = window['start_frame'], window['end_frame']
        chars = sum(len(line) for page in pages for line in page)
        offset = 0
        for page in pages:
            count = sum(map(len, page))
            a = start + round((end - start) * offset / chars)
            b = start + round((end - start) * (offset + count) / chars)
            require(a < b, f"{sentence['id']}: narration too short for caption pagination")
            captions.append({'id': f'c{len(captions) + 1:04d}', 'source_id': sentence['id'],
                             'start_frame': a, 'end_frame': b, 'lines': page, **caption_box})
            offset += count
    require(''.join(line for caption in captions for line in caption['lines']) ==
            ''.join(s['text_zh'] for s in sentences).replace('\r', '').replace('\n', ''), 'caption text coverage differs from source')
    plan['captions'] = captions
    plan['caption_timing_source'] = 'measured_sentence_windows; proportional within each sentence'
    return plan
