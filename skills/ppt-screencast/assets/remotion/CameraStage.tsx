import React from 'react';
import {useCurrentFrame} from 'remotion';
import {cameraAt, cueAt, screenPoint} from './motion.mjs';

// The content and annotations share the page transform. The cursor is screen-sized.
export const CameraStage: React.FC<{plan: any; renderPage: (page: any) => React.ReactNode}> = ({plan, renderPage}) => {
  const frame = useCurrentFrame();
  const scene = plan.scenes.find((s: any) => frame >= s.start_frame && frame < s.end_frame);
  if (!scene) return null;
  const page = plan.pages.find((p: any) => p.id === scene.page_id);
  const camera = cameraAt(scene.camera, frame);
  const view = plan.viewport;
  const cue = scene.cues.find((c: any) => frame >= c.start_frame && frame < c.end_frame);
  const target = cue && page.elements.find((e: any) => e.id === cue.target_id);
  const action = cue && cueAt(target, cue, frame);
  const tip = action && screenPoint(action.tip, camera, view);
  return (
    <>
      <div style={{position: 'absolute', left: view.x, top: view.y, width: view.w, height: view.h, overflow: 'hidden'}}>
        <div style={{position: 'absolute', width: page.width, height: page.height, transformOrigin: '0 0',
          transform: `translate(${view.w / 2}px, ${view.h / 2}px) scale(${camera.scale}) translate(${-camera.cx}px, ${-camera.cy}px)`}}>
          {renderPage(page)}
          {action && action.d && <svg width={page.width} height={page.height} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
            <path d={action.d} pathLength={1} fill="none" stroke={cue.color || '#c43545'}
              strokeWidth={3.5 / camera.scale} strokeLinecap="round" strokeDasharray="1 1"
              strokeDashoffset={1 - action.progress}/>
          </svg>}
        </div>
      </div>
      {tip && <svg width={25} height={32} viewBox="0 0 25 32" style={{position: 'absolute', left: tip.x, top: tip.y}}>
        <path d="M1 1 L1 25 L7 19 L12 30 L17 27 L12 17 L23 17 Z" fill="white" stroke="#202020" strokeWidth={1.7} strokeLinejoin="round"/>
      </svg>}
    </>
  );
};
