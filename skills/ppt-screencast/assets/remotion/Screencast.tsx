import React from 'react';
import {AbsoluteFill, cancelRender, Composition, continueRender, delayRender, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import plan from './plan.json';
import {CameraStage} from './CameraStage';

const P: any = plan;
const ink = '#1d1d1f';
const soft = '#6b6b73';
const line = '#e6e0d4';
const tint = (color: string, alpha: string) => /^#[0-9a-f]{6}$/i.test(color) ? color + alpha : color;

// Measure natural content after the local font loads, then fit it to the planned box.
// The outer geometry stays canonical, so annotations/camera do not drift from text.
const FitBox: React.FC<{box: any; children: React.ReactNode; background?: React.CSSProperties}> = ({box, children, background}) => {
  const ref = React.useRef<HTMLDivElement>(null);
  const [handle] = React.useState(() => delayRender(`Fit ${box.id || 'screen text'}`));
  const [scale, setScale] = React.useState<number | null>(null);
  React.useLayoutEffect(() => {
    const node = ref.current!;
    const fit = Math.min(1, box.w / node.scrollWidth, box.h / node.scrollHeight);
    if (!Number.isFinite(fit) || fit < .55) {
      cancelRender(new Error(`${box.id}: content too dense; split/reduce page content`));
      return;
    }
    setScale(fit);
  }, []);
  React.useLayoutEffect(() => {if (scale !== null) continueRender(handle);}, [scale, handle]);
  return <div data-element={box.id} data-fit-scale={scale} style={{position: 'absolute', left: box.x, top: box.y,
    width: box.w, height: box.h, display: 'flex', alignItems: 'center', justifyContent: 'center',
    boxSizing: 'border-box', ...background}}>
    <div ref={ref} style={{width: box.w, flexShrink: 0, boxSizing: 'border-box', transform: `scale(${scale ?? 1})`,
      transformOrigin: 'center', color: box.color || ink, fontSize: box.font_size || 40,
      fontWeight: box.weight || 600, lineHeight: box.line_height || 1.35, whiteSpace: 'pre-line'}}>{children}</div>
  </div>;
};

const Element: React.FC<{e: any}> = ({e}) => {
  const color = e.color || ink;
  const centered = {textAlign: 'center' as const};
  let content: React.ReactNode;
  let background: React.CSSProperties = {};
  switch (e.kind || 'text') {
    case 'rule': return <div style={{position: 'absolute', left: e.x, top: e.y, width: e.w, height: e.h, background: color}}/>;
    case 'stat':
      background = {border: `3px solid ${tint(color, '44')}`, borderRadius: 24, background: tint(color, '0d')};
      content = <div style={{...centered, padding: 24}}><div style={{fontSize: 34, color: soft}}>{e.caption}</div>
        <div style={{fontSize: e.value_size || e.font_size, fontWeight: 900, lineHeight: 1.05, marginTop: 10}}>{e.value}</div></div>;
      break;
    case 'panel':
      background = {border: `3px solid ${tint(color, '66')}`, borderRadius: 22, background: tint(color, '10')};
      content = <div style={{padding: '28px 32px'}}>{e.title && <div style={{fontSize: e.title_size || 38, fontWeight: 900, marginBottom: 18}}>{e.title}</div>}
        {(e.lines || []).map((text: string, i: number) => <div key={i} style={{color: ink, marginTop: i ? 18 : 0}}>{text}</div>)}</div>;
      break;
    case 'chips': case 'flow': {
      const columns = Math.max(1, e.cols || e.items.length);
      const rows = Array.from({length: Math.ceil(e.items.length / columns)}, (_, i) => e.items.slice(i * columns, (i + 1) * columns));
      content = <div style={centered}>{rows.map((row: string[], i: number) => <div key={i} style={{display: 'flex', justifyContent: 'center', gap: 14, marginTop: i ? 14 : 0}}>
        {row.map((text, n) => <React.Fragment key={n}><div style={{padding: '12px 20px', border: `3px solid ${color}`,
          borderRadius: e.kind === 'chips' ? 999 : 16, whiteSpace: 'nowrap', background: tint(color, '12')}}>{text}</div>
          {e.kind === 'flow' && n < row.length - 1 && <span style={{alignSelf: 'center'}}>→</span>}</React.Fragment>)}</div>)}</div>;
      break;
    }
    case 'bullets': content = <div>{e.items.map((text: string, i: number) => <div key={i} style={{marginTop: i ? 26 : 0}}>▪ {text}</div>)}</div>; break;
    case 'quote': content = <div style={{borderLeft: `10px solid ${color}`, paddingLeft: 26}}>{e.lines.map((text: string, i: number) => <div key={i} style={{marginTop: i ? 12 : 0}}>{text}</div>)}</div>; break;
    case 'bars': content = <div>{e.items.map((item: any, i: number) => <div key={i} style={{marginTop: i ? 14 : 0}}>
      <div>{item.label}　{item.value}</div><div style={{height: 30, background: line, borderRadius: 20}}>
        <div style={{height: '100%', width: `${item.ratio * 100}%`, background: color, borderRadius: 20}}/></div></div>)}</div>; break;
    case 'text':
      background = e.border ? {border: `2px solid ${color}`, borderRadius: 14} : {};
      content = <div style={{textAlign: e.align || 'center'}}>{e.text}</div>; break;
    default: throw new Error(`Unsupported element kind: ${e.kind}`);
  }
  return <FitBox box={e} background={background}>{content}</FitBox>;
};

const Deck = () => {
  const frame = useCurrentFrame();
  const [handle] = React.useState(() => delayRender('Load local screencast font'));
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    const face = new FontFace('ScreencastFont', `url(${staticFile('font.ttf')})`, {weight: '100 900'});
    face.load().then((font) => {document.fonts.add(font); setReady(true);}).catch(cancelRender);
  }, []);
  React.useLayoutEffect(() => {if (ready) continueRender(handle);}, [ready, handle]);
  if (!ready) return null;
  const scene = P.scenes.find((s: any) => frame >= s.start_frame && frame < s.end_frame);
  const page = scene && P.pages.find((p: any) => p.id === scene.page_id);
  const c = P.chrome;
  const caption = (P.captions || []).find((x: any) => frame >= x.start_frame && frame < x.end_frame);
  return <AbsoluteFill style={{background: P.background || '#efe9dc', fontFamily: 'ScreencastFont'}}>
    <CameraStage plan={P} renderPage={(p) => <React.Fragment key={p.id}>
      <div style={{position: 'absolute', inset: 10, background: '#fff', border: `2px solid ${line}`, borderRadius: 28}}/>
      {p.elements.map((e: any) => <Element key={e.id} e={e}/>)}</React.Fragment>}/>
    {page && c && <>
      <FitBox key={page.id + '-badge'} box={{...c.badge, font_size: 46, color: '#c0392b'}}>{page.badge}</FitBox>
      <FitBox key={page.id + '-title'} box={{...c.title, font_size: 52}}>{page.title}</FitBox>
      <FitBox key={page.id + '-sub'} box={{...c.sub, font_size: 28, color: soft}}>{page.sub}</FitBox>
      <FitBox key={page.id + '-footer'} box={{...c.footer_label, font_size: 28, color: soft}}>{page.footer_label}</FitBox>
      <div style={{position: 'absolute', left: c.progress.x, top: c.progress.y, width: c.progress.w, height: c.progress.h, background: line}}>
        <div style={{height: '100%', width: `${(page.progress || 0) * 100}%`, background: '#c0392b'}}/></div>
    </>}
    {caption && <FitBox key={caption.id || caption.start_frame} box={{...caption, font_size: 48, color: ink}}>
      <div style={{textAlign: 'center'}}>{(caption.lines || [caption.text]).map((text: string, i: number) => <div key={i}>{text}</div>)}</div>
    </FitBox>}
  </AbsoluteFill>;
};

const Root = () => <Composition id="Screencast" component={Deck} width={P.width} height={P.height} fps={P.fps} durationInFrames={P.duration_frames}/>;
registerRoot(Root);
