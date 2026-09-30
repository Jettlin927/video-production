// Uses the prepared workspace runtime; no installation, remote API or browser download.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [toolsFile, entry, output] = process.argv.slice(2);
if (!toolsFile || !entry || !output) throw new Error('Usage: render-demo.mjs <tools.json> <entry.tsx> <sample.mp4>');
const tools = JSON.parse(fs.readFileSync(toolsFile, 'utf8'));
const bundled = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/bundler/dist/index.js')).href);
const renderer = await import(pathToFileURL(path.join(tools.node_modules, '@remotion/renderer/dist/index.js')).href);
const serveUrl = await bundled.bundle({entryPoint: path.resolve(entry),
  publicDir: path.join(path.dirname(path.dirname(entry)), 'public'),
  webpackOverride: (config) => ({...config, resolve: {...config.resolve,
    modules: [tools.node_modules, ...(config.resolve?.modules || [])]}})});
const composition = await renderer.selectComposition({serveUrl, id: 'ScreencastDemo', browserExecutable: tools.browser});
fs.mkdirSync(path.dirname(output), {recursive: true});
await renderer.renderMedia({serveUrl, composition, browserExecutable: tools.browser,
  codec: 'h264', crf: 18, pixelFormat: 'yuv420p', outputLocation: output, concurrency: 2,
  onProgress: ({progress}) => {if (progress === 1) console.log('frames complete');}});
console.log(JSON.stringify({output, duration_frames: composition.durationInFrames, fps: composition.fps}));
