import React from 'react';
import {useCurrentFrame} from 'remotion';

type Chip = {text: string; color?: string};

type Props = {
  chips: Chip[];
  startFrame?: number;
  intervalFrames?: number; // frames between two chips lighting up
  separator?: string;      // e.g. '+' rendered between chips
  lit?: {background: string; color: string};
  dim?: {background: string; color: string};
  style?: React.CSSProperties;
  chipStyle?: React.CSSProperties;
};

// Keyword chips light up one by one. Colors arrive via props from style.json,
// never from a global keyword table inside the component.
export const KeywordChips: React.FC<Props> = ({
  chips, startFrame = 0, intervalFrames = 12, separator,
  lit = {background: '#111111', color: '#ffffff'},
  dim = {background: '#e5e5e5', color: '#999999'},
  style, chipStyle,
}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{display: 'flex', alignItems: 'center', gap: 12, ...style}}>
      {chips.map((chip, i) => {
        const on = frame >= startFrame + i * intervalFrames;
        const palette = on
          ? {...lit, ...(chip.color ? {background: chip.color} : {})}
          : dim;
        return (
          <React.Fragment key={chip.text}>
            {i > 0 && separator && <span>{separator}</span>}
            <span style={{padding: '6px 18px', borderRadius: 10, fontWeight: 700, ...palette, ...chipStyle}}>
              {chip.text}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
};
