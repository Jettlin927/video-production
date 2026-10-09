import React from 'react';
import {useCurrentFrame} from 'remotion';
import {cameraAt, cueAt, cursorSize, sceneCursorAt} from './motion.mjs';

// The content and annotations share the page transform. The cursor is screen-sized.
export const CameraStage: React.FC<{plan: any; renderPage: (page: any) => React.ReactNode}> = ({plan, renderPage}) => {
  const frame = useCurrentFrame();
  const scene = plan.scenes.find((s: any) => frame >= s.start_frame && frame < s.end_frame);
  if (!scene) return null;
  const page = plan.pages.find((p: any) => p.id === scene.page_id);
  const camera = cameraAt(scene.camera, frame);
  const view = plan.viewport;
  const tip = sceneCursorAt(scene, page, frame, view);
  const toolbar = Math.min(32, view.y * .75);
  const radius = Math.min(24, view.w * .025);
  const marks = scene.cues.filter((c: any) => frame >= c.start_frame + c.approach_frames && c.kind !== 'point');
  return (
    <>
      <div style={{position: 'absolute', left: view.x, top: view.y - toolbar, width: view.w, height: view.h + toolbar,
        background: '#fff', borderRadius: radius, boxShadow: '0 24px 70px #35446930, 0 3px 12px #35446920', overflow: 'hidden'}}>
        <div style={{height: toolbar, display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 14,
          background: '#f7f8fc', borderBottom: '1px solid #e5e9f1', boxSizing: 'border-box'}}>
          {['#fa8379', '#f6c76a', '#7ecb9b'].map((color) => <span key={color} style={{width: 7, height: 7, borderRadius: '50%', background: color}}/>)}
        </div>
      </div>
      <div style={{position: 'absolute', left: view.x, top: view.y, width: view.w, height: view.h,
        background: '#fff', borderRadius: `0 0 ${radius}px ${radius}px`, overflow: 'hidden'}}>
        <div style={{position: 'absolute', width: page.width, height: page.height, transformOrigin: '0 0',
          transform: `translate(${view.w / 2}px, ${view.h / 2}px) scale(${camera.scale}) translate(${-camera.cx}px, ${-camera.cy}px)`}}>
          {renderPage(page)}
          <svg width={page.width} height={page.height} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
            {marks.map((cue: any, i: number) => {
              const target = page.elements.find((e: any) => e.id === cue.target_id);
              const action = cueAt(target, cue, frame);
              return <path key={i} d={action.d} pathLength={1} fill="none" stroke={cue.color || '#c43545'}
                strokeWidth={3.5 / camera.scale} strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - action.progress}/>;
            })}
          </svg>
        </div>
      </div>
      <svg width={cursorSize.w} height={cursorSize.h} viewBox="0 0 25 32" style={{position: 'absolute', left: tip.x, top: tip.y,
        filter: 'drop-shadow(0 2px 2px #00000040)'}}>
        <path d="M1 1 L1 25 L7 19 L12 30 L17 27 L12 17 L23 17 Z" fill="#202633" stroke="white" strokeWidth={1.7} strokeLinejoin="round"/>
      </svg>
    </>
  );
};
