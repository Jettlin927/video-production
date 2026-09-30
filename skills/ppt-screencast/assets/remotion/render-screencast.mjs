import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [toolsFile, entry, output] = process.argv.slice(2);
if (!toolsFile || !entry || !output) throw new Error('Usage: render-screencast.mjs <tools.json> <entry.tsx> <output.mp4>');
const tools = JSON.parse(fs.readFileSync(toolsFile, 'utf8'));
const {bundle} = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/bundler/dist/index.js')).href);
const {renderMedia, renderStill, selectComposition} = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/renderer/dist/index.js')).href);
const serveUrl = await bundle({entryPoint: path.resolve(entry), publicDir: path.join(path.dirname(entry), 'public'),
  webpackOverride: (config) => ({...config, resolve: {...config.resolve, modules: [tools.node_modules, ...(config.resolve?.modules || [])]}})});
const composition = await selectComposition({serveUrl, id: 'Screencast', browserExecutable: tools.browser});
fs.mkdirSync(path.dirname(output), {recursive: true});
const plan = JSON.parse(fs.readFileSync(path.join(path.dirname(entry), 'plan.json'), 'utf8'));
const preview = path.join(path.dirname(output), 'preflight');
fs.mkdirSync(preview, {recursive: true});
for (const scene of plan.scenes) {
  const cue = scene.cues[0];
  const frames = [scene.start_frame, cue ? cue.start_frame + cue.approach_frames + Math.floor(cue.draw_frames / 2) : scene.start_frame];
  for (const frame of new Set(frames)) {
    await renderStill({serveUrl, composition, browserExecutable: tools.browser, frame,
      output: path.join(preview, `f${frame}.jpg`), imageFormat: 'jpeg', scale: .25});
  }
}
console.log(JSON.stringify({stage: 'preflight', scenes: plan.scenes.length, status: 'rendered'}));
await renderMedia({serveUrl, composition, browserExecutable: tools.browser, codec: 'h264', crf: 18,
  pixelFormat: 'yuv420p', outputLocation: output, concurrency: 4});
console.log(JSON.stringify({output, frames: composition.durationInFrames, fps: composition.fps}));
