import React from 'react';
import {useCurrentFrame} from 'remotion';

type Line = {zh: string; en?: string; startFrame: number; endFrame: number};

type Props = {
  lines: Line[];
  dividerColor?: string;
  bottom?: string;      // distance of the subtitle block from the bottom edge
  zhStyle?: React.CSSProperties;
  enStyle?: React.CSSProperties;
};

// Bottom subtitle strip with a divider above it: zh line bold, en line smaller,
// one entry per script sentence. Subtitles transcribe the voiceover; on-screen
// typography is a separate layer and does not repeat this text verbatim.
export const BilingualSubtitleBar: React.FC<Props> = ({
  lines, dividerColor = '#000000', bottom = '4%', zhStyle, enStyle,
}) => {
  const frame = useCurrentFrame();
  const line = lines.find(l => frame >= l.startFrame && frame < l.endFrame);
  return (
    <>
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: '18%', height: 2,
        background: dividerColor,
      }} />
      <div style={{position: 'absolute', left: '6%', right: '6%', bottom, textAlign: 'center'}}>
        {line && (
          <>
            <div style={{fontSize: 40, fontWeight: 700, color: '#111111', ...zhStyle}}>{line.zh}</div>
            {line.en && (
              <div style={{fontSize: 26, color: '#333333', marginTop: 8, ...enStyle}}>{line.en}</div>
            )}
          </>
        )}
      </div>
    </>
  );
};
