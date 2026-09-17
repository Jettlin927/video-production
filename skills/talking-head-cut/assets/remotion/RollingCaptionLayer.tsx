import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Font, useBundledFonts} from './CaptionLayer';

type Emphasis = {start_char:number; end_char:number; start_frame:number; color_role:string; marker?:string};
type Line = {id:string; group_id:string; text:string; start_frame:number; end_frame:number;
  move_frames:number; emphasis:Emphasis[]};

// Exactly two visual row slots. The outgoing upper line fades within its slot.
export const RollingCaptionLayer:React.FC<{lines:Line[]; fonts:Font[]; family:string;
  emphasisFamily?:string; normalWeight?:number; boldWeight?:number; size?:number; bottom?:number; accent?:string}> =
  ({lines,fonts,family,emphasisFamily=family,normalWeight=300,boldWeight=700,size=52,bottom=440,accent='#53C8C0'}) => {
  useBundledFonts(fonts);
  const frame=useCurrentFrame();
  const index=lines.findIndex(l=>frame>=l.start_frame && frame<l.end_frame);
  if(index<0)return null;
  const current=lines[index];
  const prev=index>0 && lines[index-1].group_id===current.group_id ? lines[index-1] : null;
  const old=prev && index>1 && lines[index-2].group_id===current.group_id ? lines[index-2] : null;
  const t=Math.min(1,Math.max(0,(frame-current.start_frame+1)/current.move_frames));
  const ease=1-Math.pow(1-t,3);const row=size*1.48;
  const text=(line:Line,history=false)=>Array.from(line.text).map((char,pos)=>{
    const hit=line.emphasis.find(e=>pos>=e.start_char && pos<e.end_char && frame>=e.start_frame);
    return <span key={pos} style={{fontFamily:JSON.stringify(hit?emphasisFamily:family),
      fontWeight:hit?boldWeight:normalWeight,color:hit?.color_role==='accent'?accent:'#fff',
      borderBottom:hit?.marker==='underline'?`${Math.max(2,size*.045)}px solid ${accent}`:undefined,
      background:hit?.marker==='box'?'#136b66c9':undefined,
      opacity:history ? .8:1}}>{char}</span>;
  });
  const rowStyle:React.CSSProperties={position:'absolute',left:0,right:0,textAlign:'center',
    height:row,fontSize:size,lineHeight:`${row}px`,whiteSpace:'pre',fontSynthesis:'none',
    textShadow:'0 2px 5px #000, 0 0 3px #000'};
  return <div data-rolling-captions style={{position:'absolute',left:'7%',width:'86%',bottom,height:row*2,overflow:'hidden'}}>
    {old && t<1 && <div style={{...rowStyle,top:-ease*row*.2,opacity:1-ease}}>{text(old,true)}</div>}
    {prev && <div style={{...rowStyle,top:row*(1-ease)}}>{text(prev,true)}</div>}
    <div style={{...rowStyle,top:row+(1-ease)*size*.2,opacity:ease}}>{text(current)}</div>
  </div>;
};
