"""Review packets and revision-bound pre-render gates; no automatic semantic verdict."""
import hashlib

from check_screencast_plan import require


def preview_frames(plan):
    frames = {scene['start_frame'] for scene in plan['scenes']}
    for scene in plan['scenes']:
        frames.add(scene['end_frame'] - 1)
        for cue in scene['cues']:
            frames.add(cue['start_frame'] + cue['approach_frames'] + cue['draw_frames'] // 2)
    return sorted(frames)


def preview_valid(plan, index, out):
    expected = preview_frames(plan)
    rows = index.get('frames', [])
    if [row.get('frame') for row in rows] != expected:
        return False
    for row in rows:
        if row.get('file') != f"f{row['frame']}.jpg":
            return False
        file = out / 'preflight' / row['file']
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != row.get('sha256'):
            return False
    return True


def review_packet(plan, signature):
    sources = {s['id']: s['text_zh'] for s in plan.get('script', {}).get('sentences', [])}
    pages = []
    for page in plan['pages']:
        items = []
        for element in page['elements']:
            if element.get('kind') == 'rule':
                continue
            display = {key: element[key] for key in ('text', 'title', 'lines', 'items', 'caption', 'value') if key in element}
            items.append({'id': element['id'], 'display': display, 'takeaway': element.get('takeaway'),
                          'sources': {sid: sources.get(sid) for sid in element.get('source_ids', [])}})
        scene_frames = []
        for scene in plan['scenes']:
            if scene['page_id'] == page['id']:
                scene_frames.extend([frame for frame in preview_frames({'scenes': [scene]})])
        pages.append({'page_id': page['id'], 'title': page.get('title'), 'sub': page.get('sub'),
                      'badge': page.get('badge'), 'footer_label': page.get('footer_label'),
                      'items': items, 'preview_frames': scene_frames, 'status': 'not_checked', 'notes': ''})
    return {'revision': plan['revision'], 'signature': signature,
            'semantic': 'not_checked', 'visual': 'not_checked', 'pages': pages, 'issues': []}


def require_review(plan, signature, review, preview, out):
    require(review.get('revision') == plan['revision'] and review.get('signature') == signature,
            'Review is stale: plan/audio/font/template changed; preview and review this snapshot')
    require(preview_valid(plan, preview, out), 'Full current preview is missing or changed')
    require(review.get('semantic') == 'pass' and review.get('visual') == 'pass', 'Semantic and visual review must pass before full render')
    pages = review.get('pages', [])
    ids = [page.get('page_id') for page in pages]
    require(len(ids) == len(set(ids)) and set(ids) == {p['id'] for p in plan['pages']}, 'Review must cover every page once')
    require(all(page.get('status') == 'pass' and isinstance(page.get('notes'), str) and page['notes'].strip() for page in pages),
            'Every page needs a reviewed status and evidence note')
    require(isinstance(review.get('issues'), list), 'Review must include issues')
    require(all(isinstance(issue, dict) and issue.get('level') in ('high', 'medium', 'low')
                and issue.get('status') in ('open', 'resolved') for issue in review['issues']),
            'Each review issue needs level high/medium/low and status open/resolved')
    require(not any(issue.get('level') in ('high', 'medium') and issue.get('status') != 'resolved' for issue in review['issues']),
            'Unresolved high/medium review issues block full render')
