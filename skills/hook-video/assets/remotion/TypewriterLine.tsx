import React from 'react';
import {useCurrentFrame} from 'remotion';

type Props = {
  text: string;
  startFrame?: number;    // first character appears at this frame
  perCharFrames?: number; // frames per character
  cursor?: boolean;
  style?: React.CSSProperties;
  cursorStyle?: React.CSSProperties;
};

// Types text one character at a time, driven only by the shared frame clock.
// Template component: calibrate perCharFrames and cursor style after the first real render.
export const TypewriterLine: React.FC<Props> = ({
  text, startFrame = 0, perCharFrames = 2, cursor = true, style, cursorStyle,
}) => {
  const frame = useCurrentFrame();
  const shown = frame < startFrame
    ? 0
    : Math.min(text.length, Math.floor((frame - startFrame) / perCharFrames) + 1);
  const done = shown >= text.length;
  return (
    <span style={style}>
      {text.slice(0, shown)}
      {cursor && !done && (
        <span style={{borderRight: '0.09em solid currentColor', ...cursorStyle}}>{'​'}</span>
      )}
    </span>
  );
};
