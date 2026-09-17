import React, {useEffect, useState} from 'react';
import {cancelRender, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';

export type Font = {family: string; src: string; weight: number|string};
type Page = {id: string; start_frame: number; end_frame: number; lines: string[];
  emphasis: {start_char: number; end_char: number; color_role: string; start_frame: number}[]};

export const useBundledFonts = (fonts: Font[]) => {
  const [handle] = useState(() => delayRender('Load bundled subtitle fonts'));
  const signature = JSON.stringify(fonts);
  useEffect(() => {
    Promise.all((JSON.parse(signature) as Font[]).map(async f => {
      const face = new FontFace(f.family, `url("${staticFile(f.src)}")`, {weight: String(f.weight)});
      await face.load(); document.fonts.add(face);
    })).then(() => document.fonts.ready).then(() => continueRender(handle)).catch(cancelRender);
  }, [handle, signature]);
};

export const CaptionLayer: React.FC<{pages: Page[]; fonts: Font[]; family: string;
  normalWeight?: number; boldWeight?: number; size?: number; bottom?: number; accent?: string}> =
  ({pages, fonts, family, normalWeight=300, boldWeight=700, size=58, bottom=260, accent='#28beb5'}) => {
  const frame = useCurrentFrame();
  useBundledFonts(fonts);
  const page = pages.find(p => frame >= p.start_frame && frame < p.end_frame);
  if (!page) return null;
  return <div style={{position:'absolute', left:'7%', width:'86%', bottom, textAlign:'center',
    fontFamily:JSON.stringify(family), fontWeight:normalWeight, fontSynthesis:'none', fontSize:size,
    color:'#fff', lineHeight:1.35, textShadow:'0 2px 5px #000, 0 0 3px #000', whiteSpace:'pre'}}>
    {page.lines.map((line, li) => {
      const start = Array.from(page.lines.slice(0, li).join('')).length;
      return <div key={li}>{Array.from(line).map((char, i) => {
        // Python stores Unicode codepoint offsets; count codepoints across lines too.
        const pos = start + i;
        const span = page.emphasis.find(s => pos >= s.start_char && pos < s.end_char && frame >= s.start_frame);
        return <span key={i} style={{fontWeight:span ? boldWeight : normalWeight,
          color:span?.color_role === 'accent' ? accent : '#fff'}}>{char}</span>;
      })}</div>;
    })}
  </div>;
};
