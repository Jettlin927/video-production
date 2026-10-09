import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

const [toolsFile, entry, output, ...options] = process.argv.slice(2);
if (!toolsFile || !entry || !output) throw new Error('Usage: render-screencast.mjs <tools.json> <entry.tsx> <output.mp4>');
const tools = JSON.parse(fs.readFileSync(toolsFile, 'utf8'));
const {bundle} = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/bundler/dist/index.js')).href);
const {renderMedia, renderStill, selectComposition, openBrowser} = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/renderer/dist/index.js')).href);
const serveUrl = await bundle({entryPoint: path.resolve(entry), outDir: path.join(path.dirname(output), 'bundle'),
  publicDir: path.join(path.dirname(entry), 'public'),
  webpackOverride: (config) => ({...config, resolve: {...config.resolve, modules: [tools.node_modules, ...(config.resolve?.modules || [])]}})});
const browser = await openBrowser('chrome', {browserExecutable: tools.browser});
try {
const composition = await selectComposition({serveUrl, id: 'Screencast', puppeteerInstance: browser});
fs.mkdirSync(path.dirname(output), {recursive: true});
const plan = JSON.parse(fs.readFileSync(path.join(path.dirname(entry), 'plan.json'), 'utf8'));
const preview = path.join(path.dirname(output), 'preflight');
fs.mkdirSync(preview, {recursive: true});
if (!options.includes('--skip-preview')) {
  const frames = new Set();
  for (const scene of plan.scenes) {
    frames.add(scene.start_frame); frames.add(scene.end_frame - 1);
    for (const cue of scene.cues) frames.add(cue.start_frame + cue.approach_frames + Math.floor(cue.draw_frames / 2));
  }
  const selected = options.find((flag) => flag.startsWith('--frames='));
  const ordered = selected ? [...new Set(selected.slice(9).split(',').map(Number))].sort((a, b) => a - b) : [...frames].sort((a, b) => a - b);
  if (ordered.some((frame) => !Number.isInteger(frame) || frame < 0 || frame >= plan.duration_frames)) throw new Error('Invalid preview frame');
  const rows = [];
  for (const frame of ordered) {
    const file = `f${frame}.jpg`;
    await renderStill({serveUrl, composition, puppeteerInstance: browser, frame,
      output: path.join(preview, file), imageFormat: 'jpeg', scale: .5});
    rows.push({frame, file, sha256: createHash('sha256').update(fs.readFileSync(path.join(preview, file))).digest('hex')});
  }
  fs.writeFileSync(path.join(path.dirname(output), 'preflight.json'), JSON.stringify({status: 'rendered', frames: rows}, null, 2));
  console.log(JSON.stringify({stage: 'preflight', scenes: plan.scenes.length, frames: rows.length, status: 'rendered'}));
}
if (!options.includes('--preview-only')) {
await renderMedia({serveUrl, composition, puppeteerInstance: browser, codec: 'h264', crf: 18,
  pixelFormat: 'yuv420p', outputLocation: output, concurrency: 4});
console.log(JSON.stringify({output, frames: composition.durationInFrames, fps: composition.fps}));
}
} finally {
  await browser.close({silent: true});
}
