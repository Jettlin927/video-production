// Shared deterministic math for the renderer and Node tests. Coordinates are page pixels.
export const smooth = (t) => {
  const p = Math.max(0, Math.min(1, t));
  return p * p * (3 - 2 * p);
};

export function cameraAt(keys, frame) {
  if (frame <= keys[0].frame) return keys[0];
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (frame <= b.frame) {
      const p = smooth((frame - a.frame) / (b.frame - a.frame));
      return Object.fromEntries(['cx', 'cy', 'scale'].map((k) => [k, a[k] + (b[k] - a[k]) * p]));
    }
  }
  return keys[keys.length - 1];
}

export function screenPoint(point, camera, viewport) {
  return {
    x: viewport.x + viewport.w / 2 + (point.x - camera.cx) * camera.scale,
    y: viewport.y + viewport.h / 2 + (point.y - camera.cy) * camera.scale,
  };
}

export function cueShape(target, cue) {
  const pad = cue.padding;
  const cx = target.x + target.w / 2, cy = target.y + target.h / 2;
  const rx = target.w / 2 + pad, ry = target.h / 2 + pad;
  const left = target.x - pad, right = target.x + target.w + pad;
  const bottom = target.y + target.h + pad;
  if (cue.kind === 'circle') {
    return {
      d: `M ${cx} ${cy - ry} A ${rx} ${ry} 0 1 1 ${cx} ${cy + ry} A ${rx} ${ry} 0 1 1 ${cx} ${cy - ry}`,
      point: (p) => ({x: cx + rx * Math.cos(-Math.PI / 2 + p * Math.PI * 2),
                      y: cy + ry * Math.sin(-Math.PI / 2 + p * Math.PI * 2)}),
    };
  }
  if (cue.kind === 'underline') {
    return {d: `M ${left} ${bottom} L ${right} ${bottom}`,
      point: (p) => ({x: left + (right - left) * p, y: bottom})};
  }
  return {d: '', point: () => ({x: right, y: bottom})};
}

export function cueAt(target, cue, frame) {
  const shape = cueShape(target, cue);
  const local = frame - cue.start_frame;
  const approach = smooth(local / cue.approach_frames);
  const progress = Math.max(0, Math.min(1, (local - cue.approach_frames) / cue.draw_frames));
  const tip = shape.point(progress);
  const start = shape.point(0);
  return {d: shape.d, progress,
    tip: local < cue.approach_frames
      ? {x: start.x + (1 - approach) * 32, y: start.y - (1 - approach) * 24}
      : tip};
}
