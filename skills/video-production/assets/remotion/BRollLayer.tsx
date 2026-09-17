import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile} from 'remotion';

type Asset = {
  id: string; kind: string; src: string; start_frame: number; end_frame: number;
  rect: {x: number; y: number; width: number; height: number}; label?: string;
};

// Place after the person's video and before subtitles/title. Speech audio stays untouched.
export const BRollLayer: React.FC<{assets: Asset[]}> = ({assets}) => <AbsoluteFill>
  {assets.map(a => <Sequence key={a.id} from={a.start_frame} durationInFrames={a.end_frame - a.start_frame}>
    <div style={{position: 'absolute', left: `${a.rect.x * 100}%`, top: `${a.rect.y * 100}%`,
      width: `${a.rect.width * 100}%`, height: `${a.rect.height * 100}%`, overflow: 'hidden', background: '#000'}}>
      {a.kind === 'image'
        ? <Img src={staticFile(a.src)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
        : <OffthreadVideo src={staticFile(a.src)} muted style={{width: '100%', height: '100%', objectFit: 'contain'}} />}
      {a.label && <div style={{position: 'absolute', top: 16, right: 20, color: '#fff', background: '#0009',
        padding: '4px 8px', fontSize: 22, fontFamily: 'sans-serif'}}>{a.label}</div>}
    </div>
  </Sequence>)}
</AbsoluteFill>;
