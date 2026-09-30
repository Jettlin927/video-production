import React from 'react';
import {AbsoluteFill, cancelRender, Composition, continueRender, delayRender, registerRoot, staticFile} from 'remotion';
import plan from '../demo-plan.json';
import {CameraStage} from './CameraStage';

const Demo = () => {
  const [handle] = React.useState(() => delayRender('Load shared local font'));
  React.useEffect(() => {
    const font = new FontFace('DemoWenKai', `url(${staticFile('LXGWWenKai-Regular.ttf')})`);
    font.load().then((loaded) => {document.fonts.add(loaded); continueRender(handle);}).catch(cancelRender);
  }, [handle]);
  return <AbsoluteFill style={{background: '#fff', fontFamily: 'DemoWenKai'}}>
    <CameraStage plan={plan} renderPage={(page) => page.elements.map((e: any) =>
      <div key={e.id} style={{position: 'absolute', left: e.x, top: e.y, width: e.w, height: e.h,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: e.font_size,
        color: e.color, border: e.border ? `2px solid ${e.color}` : undefined, borderRadius: 14, boxSizing: 'border-box'}}>{e.text}</div>)}/>
    <div style={{position: 'absolute', left: 32, right: 32, bottom: 30, borderTop: '1px solid #ddd',
      paddingTop: 16, fontSize: 24, textAlign: 'center', color: '#555'}}>无声技术短样 · 非整片验收</div>
  </AbsoluteFill>;
};

const Root = () => <Composition id="ScreencastDemo" component={Demo}
  width={plan.width} height={plan.height} fps={plan.fps} durationInFrames={plan.duration_frames}/>;
registerRoot(Root);
