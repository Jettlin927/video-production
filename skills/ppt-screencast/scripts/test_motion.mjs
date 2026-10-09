import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {cameraAt, cueAt, sceneCursorAt, screenPoint} from '../assets/remotion/motion.mjs';

const target = {x: 100, y: 120, w: 200, h: 80};
const cue = {kind: 'circle', padding: 10, start_frame: 20, end_frame: 80,
  approach_frames: 10, draw_frames: 20};

test('camera center maps to viewport center at every zoom', () => {
  const view = {x: 32, y: 24, w: 656, h: 680};
  for (const scale of [0.5, 1, 2, 3]) {
    assert.deepEqual(screenPoint({x: 200, y: 160}, {cx: 200, cy: 160, scale}, view), {x: 360, y: 364});
  }
});

test('smooth camera interpolation is deterministic and clamps endpoints', () => {
  const keys = [{frame: 0, cx: 0, cy: 0, scale: 1}, {frame: 10, cx: 100, cy: 200, scale: 2}];
  assert.deepEqual(cameraAt(keys, 5), {cx: 50, cy: 100, scale: 1.5});
  assert.equal(cameraAt(keys, -1).scale, 1);
  assert.equal(cameraAt(keys, 20).scale, 2);
  assert.ok(Math.abs(cameraAt(keys, 2).cx - 10.4) < 1e-9);
});

test('circle pen tip follows the ellipse and completes exactly one revolution', () => {
  const start = cueAt(target, cue, 30);
  const quarter = cueAt(target, cue, 35);
  const end = cueAt(target, cue, 50);
  assert.ok(Math.abs(start.tip.x - 200) < 1e-9);
  assert.equal(start.tip.y, 110);
  assert.equal(quarter.tip.x, 310);
  assert.equal(quarter.tip.y, 160);
  assert.ok(Math.abs(end.tip.x - start.tip.x) < 1e-9);
  assert.equal(end.tip.y, start.tip.y);
  assert.equal(end.progress, 1);
});

test('underline cursor tip matches line endpoint at each drawn frame', () => {
  for (let f = 30; f <= 50; f++) {
    const state = cueAt(target, {...cue, kind: 'underline'}, f);
    assert.equal(state.tip.y, 210);
    assert.equal(state.tip.x, 90 + 220 * state.progress);
  }
});

test('pointer arrives before drawing and then stays at the target', () => {
  const arriving = cueAt(target, {...cue, kind: 'point'}, 20);
  const ready = cueAt(target, {...cue, kind: 'point'}, 30);
  const hold = cueAt(target, {...cue, kind: 'point'}, 75);
  assert.notDeepEqual(arriving.tip, ready.tip);
  assert.deepEqual(ready.tip, {x: 310, y: 210});
  assert.deepEqual(hold.tip, ready.tip);
});

const plan = JSON.parse(fs.readFileSync(new URL('../assets/demo-plan.json', import.meta.url), 'utf8'));
test('scene pointer stays present, travels continuously and follows the pen during drawing', () => {
  const scene = plan.scenes[0], page = plan.pages[0], view = plan.viewport;
  const home = sceneCursorAt(scene, page, scene.start_frame, view);
  const end = sceneCursorAt(scene, page, scene.end_frame - 1, view);
  assert.ok(Math.hypot(end.x - home.x, end.y - home.y) < 1e-8);
  let previous = home;
  for (let frame = scene.start_frame; frame < scene.end_frame; frame++) {
    const point = sceneCursorAt(scene, page, frame, view);
    assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y));
    assert.ok(Math.hypot(point.x - previous.x, point.y - previous.y) < 110, `no jump at ${frame}`);
    const active = scene.cues.find((c) => frame >= c.start_frame + c.approach_frames && frame < c.end_frame);
    if (active) assert.deepEqual(point, screenPoint(cueAt(page.elements.find((e) => e.id === active.target_id), active, frame).tip,
      cameraAt(scene.camera, frame), view));
    previous = point;
  }
});

test('geometry checker and renderer use identical whole-scene pointer positions', () => {
  const code = "import json,sys; from check_screencast_plan import scene_cursor_at; p=json.load(sys.stdin); s=p['scenes'][0]; e={x['id']:x for x in p['pages'][0]['elements']}; print(json.dumps([scene_cursor_at(s,e,f,p['viewport']) for f in range(s['end_frame'])]))";
  const points = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-c', code],
    {cwd: new URL('.', import.meta.url), input: JSON.stringify(plan), encoding: 'utf8'}));
  for (let frame = 0; frame < points.length; frame++) {
    const point = sceneCursorAt(plan.scenes[0], plan.pages[0], frame, plan.viewport);
    assert.ok(Math.abs(point.x - plan.viewport.x - points[frame][0]) < 1e-8);
    assert.ok(Math.abs(point.y - plan.viewport.y - points[frame][1]) < 1e-8);
  }
});
