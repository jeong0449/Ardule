#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local PatternLab playback service using FluidSynth and an SF2 SoundFont.

Version: 260811o
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import struct
import re
import tempfile
import threading
import webbrowser
from collections import defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from mido import MidiFile, MidiTrack, Message, MetaMessage
except ImportError:
    MidiFile = MidiTrack = Message = MetaMessage = None

SCRIPT_NAME = "play_server.py"
VERSION = "260818o"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"

HOST = "127.0.0.1"
DEFAULT_PORT = 8123
MAX_MIDI_BYTES = 16 * 1024 * 1024
DEFAULT_FLUIDSYNTH = Path(r"C:\Tools\FluidSynth\bin\fluidsynth.exe")
DEFAULT_SOUNDFONT = Path(r"C:\SoundFonts\GeneralUser-GS.sf2")


NO_REPORT_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADX Drum Player 260818o</title><style>
:root{color-scheme:light dark;--bg:#f4f6f8;--panel:#fff;--ink:#1f2933;--muted:#66717d;--line:#d8dee5;--accent:#2563eb;--playing:#dbeafe;--playing-line:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9aa6b2;--line:#303843;--accent:#60a5fa;--playing:#18324f;--playing-line:#60a5fa}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}main{max-width:1100px;margin:28px auto;padding:22px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}header{padding:19px 22px 13px;border-bottom:1px solid var(--line)}h1{margin:0 0 5px;font-size:1.5rem}p{margin:0;color:var(--muted)}.toolbar,.modebar,.filterbar{display:flex;gap:8px;align-items:center;padding:10px 15px;border-bottom:1px solid var(--line);flex-wrap:wrap}button{border:1px solid var(--line);border-radius:7px;padding:7px 11px;background:var(--panel);color:var(--ink);cursor:pointer;font-weight:700}button.primary,button.active{color:#fff;background:var(--accent);border-color:var(--accent)}button:disabled{opacity:.55;cursor:default}.location{flex:1;min-width:260px;padding:7px 10px;border:1px solid var(--line);border-radius:7px;background:var(--bg);font:12px ui-monospace,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.status{color:var(--muted);font-size:.88rem}.spacer{flex:1}.genre{font-size:.82rem;padding:5px 9px}.sort{min-width:86px}table{width:100%;border-collapse:collapse}th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}td.num,th.num{text-align:right}.entry{cursor:pointer}.entry:hover{background:var(--bg)}.playing-row{background:var(--playing);box-shadow:inset 4px 0 0 var(--playing-line)}.playing-row td{background:var(--playing)}.folder-name{font-weight:750}.file-name{font-weight:650}.kind,.ornflag{color:var(--muted);font-size:.82rem}.ornflag.yes{font-weight:800;color:var(--ink)}.detail-row td{background:var(--bg);padding:10px 16px}.detail-box{border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:10px;overflow:auto}.pattern-grid{border-collapse:collapse;width:auto;min-width:100%}.pattern-grid th,.pattern-grid td{padding:0;border:1px solid var(--line);height:18px;min-width:12px;text-align:center}.pattern-grid td{position:relative}.pattern-grid td.beat-start::before,.pattern-grid td.bar-start::before{content:"";position:absolute;left:-2px;top:-1px;bottom:-1px;z-index:4;pointer-events:none}.pattern-grid td.beat-start::before{border-left:2px dashed var(--muted)}.pattern-grid td.bar-start::before{border-left:3px solid var(--ink)}.pattern-grid th.slot{padding:2px 6px;min-width:36px;font-size:10px;position:sticky;left:0;background:var(--panel);z-index:1}.hit{width:100%;height:100%;min-height:17px}.orntext{margin:0;font:12px/1.4 ui-monospace,Consolas,monospace;white-space:pre}.playback-row td{padding:0 13px 10px;background:var(--bg)}.inline-player{padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.midi-status-line{display:flex;justify-content:space-between;gap:12px;font-size:.82rem}.midi-status-state{font-weight:750}.midi-status-time{color:var(--muted);white-space:nowrap}.midi-progress{height:7px;margin-top:7px;overflow:hidden;border-radius:999px;background:var(--line)}.midi-progress span{display:block;width:0;height:100%;background:var(--accent)}.global-transport{display:none;padding:10px 15px;border-top:1px solid var(--line);background:var(--panel)}.global-transport.show{display:block}.global-transport-line{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.global-title{font-weight:800}.global-meta{color:var(--muted);font-size:.85rem}.global-actions{margin-left:auto;display:flex;gap:8px}.global-progress{height:7px;margin-top:8px;overflow:hidden;border-radius:999px;background:var(--line)}.global-progress span{display:block;width:0;height:100%;background:var(--accent)}.empty{padding:30px;text-align:center;color:var(--muted)}.midi-roll-wrap{max-height:520px;overflow:auto}.midi-roll-svg{display:block;width:100%;height:auto;min-width:720px}.roll-system-label{font-size:12px;font-weight:800;fill:var(--ink)}.roll-instrument{font-size:10px;fill:var(--ink)}.roll-bar-number{font-size:11px;font-weight:800;fill:var(--ink)}.roll-meter{font-size:9px;fill:var(--muted)}.roll-staff{stroke:var(--line);stroke-width:.7}.roll-bar-line{stroke:var(--ink);stroke-width:1}.roll-beat-line{stroke:var(--muted);stroke-width:.7}.roll-grid-line{stroke:var(--line);stroke-width:.55;stroke-dasharray:2 3}.roll-note{fill:var(--ink)}.roll-note-duration{stroke:var(--ink);stroke-width:1.1;opacity:.65}.roll-bar-bg{fill:transparent}.roll-bar-bg.playing{fill:var(--playing)}footer{padding:11px 16px;color:var(--muted);font-size:.82rem}
</style></head><body><main><section class="panel">
<header><h1>ADX Drum Player <span class="status">260818o</span></h1><p>Browse MIDI files or audition ADT/ADP drum patterns with FluidSynth.</p></header>
<div class="modebar"><button id="modeMidi" class="active">MIDI</button><button id="modePattern">ADT / ADP</button><span class="spacer"></span><span id="modeHint" class="status">Standard MIDI playback</span></div>
<div class="toolbar"><button id="roots">Computer</button><button id="up">Up</button><button id="refresh">Refresh</button><button id="stop">Stop</button><div id="location" class="location">Loading…</div><span id="status" class="status"></span></div>
<div id="filters" class="filterbar" style="display:none"></div><div id="content"></div><div id="globalTransport" class="global-transport"></div>
<footer>Read-only browser · play_server.py 260818o. ADP is preferred when same-basename ADT and ADP both exist. Same-basename ORN is applied automatically.</footer>
</section></main><script>
(()=>{
const $=id=>document.getElementById(id),content=$('content'),status=$('status'),locationBox=$('location'),filters=$('filters'),globalTransport=$('globalTransport');
const refreshButton=$('refresh'),stopButton=$('stop'),upButton=$('up'),rootsButton=$('roots'),modeMidi=$('modeMidi'),modePattern=$('modePattern'),modeHint=$('modeHint');
let mode='midi',currentId=null,parentId=null,lastData=null,genre='ALL',descending=false,playingId=null,playingName='',playPaused=false,playDuration=0,playStartedAt=0,elapsedBeforePause=0,playAnimation=null,detailId=null,detailKind=null,midiDetailId=null,midiRollData=null,lastFollowSystem=null;
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes=v=>!Number.isFinite(v)?'—':v<1024?`${v} B`:v<1048576?`${(v/1024).toFixed(1)} KB`:`${(v/1048576).toFixed(1)} MB`;
const duration=v=>{if(!Number.isFinite(v))return '—';const t=Math.max(0,Math.round(v)),m=Math.floor(t/60),s=t%60;return m?`${m}:${String(s).padStart(2,'0')}`:`${s} s`};
function elapsedSeconds(){const live=(!playPaused&&playStartedAt)?(performance.now()-playStartedAt)/1000:0;return Math.max(0,elapsedBeforePause+live)}
function stopProgressAnimation(){if(playAnimation){cancelAnimationFrame(playAnimation);playAnimation=null}}
function updateMidiProgress(){
 const elapsed=elapsedSeconds(),ratio=playDuration>0?Math.max(0,Math.min(1,elapsed/playDuration)):0;
 const local=row=>{if(!row)return;const time=row.querySelector('.midi-status-time'),bar=row.querySelector('.midi-progress span'),state=row.querySelector('.midi-status-state');if(time)time.textContent=playDuration>0?`${duration(Math.min(elapsed,playDuration))} / ${duration(playDuration)}`:(playPaused?'Paused':'Playing');if(bar)bar.style.width=`${ratio*100}%`;if(state)state.textContent=`${playPaused?'Paused':'Playing'}: ${playingName}`;updateRollPlayback(elapsed)};
 local(document.querySelector('.playback-row'));
 const gt=$('globalTransport');
 if(gt&&gt.classList.contains('show')){const time=gt.querySelector('.global-time'),bar=gt.querySelector('.global-progress span'),state=gt.querySelector('.global-state');if(time)time.textContent=playDuration>0?`${duration(Math.min(elapsed,playDuration))} / ${duration(playDuration)}`:(playPaused?'Paused':'Playing');if(bar)bar.style.width=`${ratio*100}%`;if(state)state.textContent=playPaused?'Paused':'Playing'}
 stopProgressAnimation();
 if(!playPaused&&playingId&&playDuration>0&&ratio<1)playAnimation=requestAnimationFrame(updateMidiProgress);
 if(!playPaused&&playDuration>0&&ratio>=1){playingId=null;playingName='';playDuration=0;playStartedAt=0;elapsedBeforePause=0;status.textContent='Finished';render(lastData)}
}
function currentRollBar(elapsed){if(!midiRollData||!Array.isArray(midiRollData.bars))return null;for(const b of midiRollData.bars){if(elapsed>=b.start_seconds&&elapsed<b.end_seconds)return b.measure}return midiRollData.bars.length&&elapsed>=midiRollData.bars[midiRollData.bars.length-1].end_seconds?midiRollData.bars[midiRollData.bars.length-1].measure:null}
let rollScrollAnimation=null;
function smoothRollScroll(wrap,target){
 if(rollScrollAnimation){cancelAnimationFrame(rollScrollAnimation);rollScrollAnimation=null}
 const start=wrap.scrollTop,distance=target-start;
 if(Math.abs(distance)<2){wrap.scrollTop=target;return}
 const duration=420,startTime=performance.now();
 const ease=t=>1-Math.pow(1-t,3);
 const step=now=>{const t=Math.min(1,(now-startTime)/duration);wrap.scrollTop=start+distance*ease(t);if(t<1)rollScrollAnimation=requestAnimationFrame(step);else rollScrollAnimation=null};
 rollScrollAnimation=requestAnimationFrame(step)
}
function updateRollPlayback(elapsed){const svg=document.querySelector('.midi-roll-svg');if(!svg)return;const measure=currentRollBar(elapsed);let active=null;svg.querySelectorAll('.roll-bar-bg').forEach(x=>{const on=Number(x.dataset.measure)===measure;x.classList.toggle('playing',on);if(on)active=x});const label=document.querySelector('.roll-position');if(label)label.textContent=measure?`Bar ${measure}`:'—';if(!active)return;const system=Number(active.dataset.system);if(system===lastFollowSystem)return;const wrap=svg.closest('.midi-roll-wrap');if(!wrap)return;const first=svg.querySelector(`.roll-bar-bg[data-system="${system}"]`)||active;requestAnimationFrame(()=>{try{const vb=svg.viewBox&&svg.viewBox.baseVal?svg.viewBox.baseVal:null;const scale=vb&&vb.height>0?svg.clientHeight/vb.height:1;const y=Number(first.getAttribute('y'))||0;const target=Math.max(0,y*scale-36);smoothRollScroll(wrap,target);lastFollowSystem=system}catch(_e){lastFollowSystem=null}})}
function renderMidiRoll(d){const box=$('detailBox');if(!box)return;midiRollData=d;lastFollowSystem=null;if(!d.notes||!d.notes.length){box.textContent='No CH10 drum notes.';return}const escA=v=>esc(v),barsPerRow=4,labelW=150,barW=112,rowH=18,headerH=42,gap=24;const systems=[];for(let i=0;i<d.bars.length;i+=barsPerRow)systems.push(d.bars.slice(i,i+barsPerRow));let y=12,totalH=20;const layouts=[];for(const bs of systems){const start=bs[0].start_tick,end=bs[bs.length-1].end_tick;const used=[...new Set(d.notes.filter(n=>n.start_tick>=start&&n.start_tick<end).map(n=>n.note))];const rows=d.note_order.filter(n=>used.includes(n));const rr=rows.length?rows:d.note_order.slice(0,1);const h=headerH+rr.length*rowH+12;layouts.push({bars:bs,rows:rr,y,h});y+=h+gap;totalH=y}const width=labelW+barsPerRow*barW+20;let h=`<div class="midi-status-line"><span><b>Drum Roll</b> · ${escA(d.ppqn_label)} · ${d.notes.length} notes</span><span class="roll-position">—</span></div><div class="midi-roll-wrap"><svg class="midi-roll-svg" viewBox="0 0 ${width} ${totalH}" role="img">`;for(const L of layouts){const plotTop=L.y+headerH,plotH=L.rows.length*rowH;h+=`<text x="8" y="${L.y+15}" class="roll-system-label">Bars ${L.bars[0].measure}–${L.bars[L.bars.length-1].measure}</text>`;const idx=new Map(L.rows.map((n,i)=>[n,i]));for(let ri=0;ri<L.rows.length;ri++){const note=L.rows[ri],yy=plotTop+ri*rowH+rowH/2;h+=`<text x="${labelW-8}" y="${yy+3}" text-anchor="end" class="roll-instrument">${escA(d.note_names[String(note)]||('GM '+note))}</text><line x1="${labelW}" y1="${yy+rowH/2}" x2="${labelW+L.bars.length*barW}" y2="${yy+rowH/2}" class="roll-staff"/>`}for(let bi=0;bi<L.bars.length;bi++){const b=L.bars[bi],x0=labelW+bi*barW,dur=Math.max(1,b.end_tick-b.start_tick);h+=`<rect x="${x0}" y="${plotTop-8}" width="${barW}" height="${plotH+8}" class="roll-bar-bg" data-measure="${b.measure}" data-system="${Math.floor((b.measure-1)/barsPerRow)}"/><line x1="${x0}" y1="${plotTop-8}" x2="${x0}" y2="${plotTop+plotH}" class="roll-bar-line"/><text x="${x0+5}" y="${plotTop-14}" class="roll-bar-number">${b.measure}</text><text x="${x0+barW-5}" y="${plotTop-14}" text-anchor="end" class="roll-meter">${b.numerator}/${b.denominator}</text>`;const beatTicks=d.ppqn*4/b.denominator;for(let beat=1;beat<b.numerator;beat++){const bx=x0+beat*beatTicks/dur*barW;h+=`<line x1="${bx}" y1="${plotTop}" x2="${bx}" y2="${plotTop+plotH}" class="roll-beat-line"/>`}const gridTicks=d.ppqn/4;for(let t=b.start_tick+gridTicks;t<b.end_tick;t+=gridTicks){const mul=(t-b.start_tick)/beatTicks;if(Math.abs(mul-Math.round(mul))<1e-8)continue;const gx=x0+(t-b.start_tick)/dur*barW;h+=`<line x1="${gx}" y1="${plotTop}" x2="${gx}" y2="${plotTop+plotH}" class="roll-grid-line"/>`}for(const n of d.notes){if(n.start_tick<b.start_tick||n.start_tick>=b.end_tick||!idx.has(n.note))continue;const xx=x0+(n.start_tick-b.start_tick)/dur*barW,yy=plotTop+idx.get(n.note)*rowH+rowH/2,x2=Math.min(x0+barW,Math.max(xx+1.5,xx+n.duration/dur*barW)),r=1.7+1.7*n.velocity/127;h+=`<line x1="${xx}" y1="${yy}" x2="${x2}" y2="${yy}" class="roll-note-duration"><title>${escA(n.position)} · ${escA(d.note_names[String(n.note)]||('GM '+n.note))} · velocity ${n.velocity}</title></line><circle cx="${xx}" cy="${yy}" r="${r}" class="roll-note"><title>${escA(n.position)} · ${escA(d.note_names[String(n.note)]||('GM '+n.note))} · velocity ${n.velocity}</title></circle>`} }const rx=labelW+L.bars.length*barW;h+=`<line x1="${rx}" y1="${plotTop-8}" x2="${rx}" y2="${plotTop+plotH}" class="roll-bar-line"/>`}h+='</svg></div>';box.innerHTML=h;updateRollPlayback(elapsedSeconds())}
async function loadMidiRoll(id){const box=$('detailBox');if(!box)return;try{const r=await fetch(`/api/midi-roll?id=${encodeURIComponent(id)}`,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);renderMidiRoll(d)}catch(e){box.textContent=String(e)}}
function renderGlobalTransport(){
 if(mode!=='midi'||!playingId){
   globalTransport.classList.remove('show');
   globalTransport.innerHTML='';
   return
 }
 const visibleHere=[...document.querySelectorAll('.play')].some(b=>b.dataset.id===playingId);
 if(visibleHere){
   globalTransport.classList.remove('show');
   globalTransport.innerHTML='';
   return
 }
 globalTransport.classList.add('show');
 globalTransport.innerHTML=`<div class="global-transport-line"><span class="global-state">${playPaused?'Paused':'Playing'}</span><span class="global-title">${esc(playingName)}</span><span class="global-meta global-time"></span><span class="global-actions"><button id="globalPause" class="primary">${playPaused?'▶ Resume':'⏸ Pause'}</button><button id="globalStop">■ Stop</button></span></div><div class="global-progress"><span></span></div>`;
 $('globalPause').onclick=()=>togglePlayback(playingId);
 $('globalStop').onclick=stopPlayback;
 updateMidiProgress();
}
function setMode(next){if(mode===next)return;mode=next;genre='ALL';detailId=detailKind=null;midiDetailId=null;midiRollData=null;modeMidi.classList.toggle('active',mode==='midi');modePattern.classList.toggle('active',mode==='pattern');modeHint.textContent=mode==='midi'?'Standard MIDI playback':'Looping ADT/ADP pattern playback';browse(currentId||'start')}
function renderFilters(data){if(mode!=='pattern'){filters.style.display='none';filters.innerHTML='';return}filters.style.display='flex';const total=(data.patterns||[]).length;let h=`<button class="genre ${genre==='ALL'?'active':''}" data-g="ALL">Show all ${total}</button>`;for(const [g,n] of Object.entries(data.genres||{}))h+=`<button class="genre ${genre===g?'active':''}" data-g="${esc(g)}">${esc(g)} ${n}</button>`;h+=`<span class="spacer"></span><button id="sortToggle" class="sort">${descending?'Z → A':'A → Z'}</button>`;filters.innerHTML=h;filters.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{genre=b.dataset.g;render(data)});$('sortToggle').onclick=()=>{descending=!descending;render(data)}}
function rowsFor(data){if(mode==='midi')return data.files||[];let xs=[...(data.patterns||[])];if(genre!=='ALL')xs=xs.filter(x=>x.genre===genre);xs.sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'}));if(descending)xs.reverse();return xs}
function render(data){lastData=data;currentId=data.current_id??null;parentId=data.parent_id??null;locationBox.textContent=data.display_path||'Computer';locationBox.title=locationBox.textContent;upButton.disabled=!parentId;renderFilters(data);const folders=data.folders||[],items=rowsFor(data);if(!folders.length&&!items.length){content.innerHTML='<div class="empty">No matching files here.</div>';status.textContent='Empty';return}let rows='';for(const f of folders)rows+=`<tr class="entry folder" data-id="${esc(f.id)}"><td><span class="folder-name">📁 ${esc(f.name)}</span></td><td class="kind">Folder</td><td></td><td></td></tr>`;if(mode==='midi'){for(const f of items){const active=f.id===playingId;rows+=`<tr><td><span class="file-name">♪ ${esc(f.name)}</span></td><td class="kind">MIDI</td><td class="num">${duration(f.duration_seconds)}</td><td class="num">${bytes(f.size)} &nbsp; <button class="primary play" data-id="${esc(f.id)}">${active?(playPaused?'▶ Resume':'⏸ Pause'):'▶ Play'}</button>${active?' <button class="midi-stop">■ Stop</button>':''} <button class="showroll" data-id="${esc(f.id)}">${midiDetailId===f.id?'Hide Roll':'Show Roll'}</button></td></tr>`;if(active)rows+=`<tr class="playback-row"><td colspan="4"><div class="inline-player"><div class="midi-status-line"><span class="midi-status-state">${playPaused?'Paused':'Playing'}: ${esc(playingName)}</span><span class="midi-status-time"></span></div><div class="midi-progress"><span></span></div></div></td></tr>`;if(midiDetailId===f.id)rows+=`<tr class="detail-row"><td colspan="4"><div id="detailBox" class="detail-box">Loading…</div></td></tr>`}content.innerHTML=`<table><thead><tr><th>Name</th><th>Type</th><th class="num">Duration</th><th class="num">Size / Action</th></tr></thead><tbody>${rows}</tbody></table>`;if(midiDetailId)loadMidiRoll(midiDetailId);if(playingId)updateMidiProgress()}else{for(const f of items){rows+=`<tr class="${f.id===playingId?'playing-row':''}"><td><span class="file-name">▦ ${esc(f.name)}</span></td><td class="kind">${esc(f.type)}</td><td class="ornflag ${f.has_orn?'yes':''}">${f.has_orn?'ORN ●':'—'}</td><td class="num"><button class="primary play" data-id="${esc(f.id)}">${f.id===playingId?'■ Stop':'▶ Play'}</button> <button class="showpat" data-id="${esc(f.id)}">${detailId===f.id&&detailKind==='pattern'?'Hide Pattern':'Show Pattern'}</button>${f.has_orn?` <button class="showorn" data-id="${esc(f.id)}">${detailId===f.id&&detailKind==='orn'?'Hide ORN':'Show ORN'}</button>`:''}</td></tr>`;if(detailId===f.id)rows+=`<tr class="detail-row"><td colspan="4"><div id="detailBox" class="detail-box">Loading…</div></td></tr>`}content.innerHTML=`<table><thead><tr><th>Name</th><th>Type</th><th>ORN</th><th class="num">Action</th></tr></thead><tbody>${rows}</tbody></table>`;if(detailId)loadDetail(detailId,detailKind)}
content.querySelectorAll('.folder').forEach(r=>r.onclick=()=>browse(r.dataset.id));content.querySelectorAll('.play').forEach(b=>b.onclick=e=>{e.stopPropagation();togglePlayback(b.dataset.id)});content.querySelectorAll('.showroll').forEach(b=>b.onclick=()=>{midiDetailId=midiDetailId===b.dataset.id?null:b.dataset.id;midiRollData=null;render(lastData)});content.querySelectorAll('.midi-stop').forEach(b=>b.onclick=e=>{e.stopPropagation();stopPlayback()});content.querySelectorAll('.showpat').forEach(b=>b.onclick=()=>toggleDetail(b.dataset.id,'pattern'));content.querySelectorAll('.showorn').forEach(b=>b.onclick=()=>toggleDetail(b.dataset.id,'orn'));renderGlobalTransport();status.textContent=mode==='midi'?`${folders.length} folder(s) · ${items.length} MIDI`:`${folders.length} folder(s) · ${items.length} pattern(s)`}
async function browse(id){refreshButton.disabled=true;status.textContent='Loading…';try{const q=new URLSearchParams();if(id)q.set('id',id);q.set('mode',mode);const r=await fetch('/api/browse?'+q,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);render(d)}catch(e){content.innerHTML=`<div class="empty">${esc(String(e))}</div>`;status.textContent='Error'}finally{refreshButton.disabled=false}}
function toggleDetail(id,kind){if(detailId===id&&detailKind===kind){detailId=detailKind=null}else{detailId=id;detailKind=kind}render(lastData)}
async function loadDetail(id,kind){const box=$('detailBox');if(!box)return;try{const r=await fetch(`/api/pattern?id=${encodeURIComponent(id)}`,{cache:'no-store'}),d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);if(kind==='orn'){box.innerHTML=d.orn_text?`<pre class="orntext">${esc(d.orn_text)}</pre>`:'No ORN file.';return}const spq=({16:4,32:8,'8T':3,'16T':6})[d.subdiv]||4;const tm=String(d.time_sig||'4/4').match(/^(\d+)\/(\d+)$/);const beats=tm?Number(tm[1]):4,den=tm?Number(tm[2]):4;const barSteps=Math.max(1,Math.round(beats*spq*4/den));let h='<table class="pattern-grid"><tbody>';for(let ri=d.slots.length-1;ri>=0;ri--){h+=`<tr><th class="slot">${esc(d.slots[ri])}</th>`;for(let si=0;si<d.length;si++){const a=d.steps[si][ri]||0,c=d.colors[String(a)]||'transparent';const cls=si>0&&si%barSteps===0?'bar-start':(si>0&&si%spq===0?'beat-start':'');h+=`<td class="${cls}"><div class="hit" title="step ${si}, accent ${a}" style="background:${esc(c)}"></div></td>`}h+='</tr>'}h+='</tbody></table>';box.innerHTML=h}catch(e){box.textContent=String(e)}}
async function togglePlayback(id){
 if(mode==='pattern'&&id===playingId){await stopPlayback();return}
 if(mode==='midi'&&id===playingId){try{const wasPaused=playPaused,ep=wasPaused?'/resume':'/pause';const r=await fetch(ep,{method:'POST'});if(!r.ok)throw new Error(await r.text());if(wasPaused){playStartedAt=performance.now();playPaused=false}else{elapsedBeforePause=elapsedSeconds();playStartedAt=0;playPaused=true}status.textContent=playPaused?'Paused':'Playing';render(lastData)}catch(e){status.textContent=`Error: ${e}`}return}
 try{status.textContent='Starting playback…';const ep=mode==='midi'?'/play-file':'/play-pattern';const r=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})}),d=await r.json();if(!r.ok)throw new Error(d.error||'Playback failed');stopProgressAnimation();playingId=id;playingName=d.name||'';playPaused=false;if(mode==='midi'){midiDetailId=id;midiRollData=null;playDuration=Number(d.duration_seconds)||0;elapsedBeforePause=0;playStartedAt=performance.now()}else{playDuration=0;elapsedBeforePause=0;playStartedAt=0}status.textContent=`Playing: ${playingName}${mode==='pattern'?' · Loop':''}`;render(lastData)}catch(e){status.textContent=`Error: ${e}`}
}
async function stopPlayback(){try{await fetch('/stop',{method:'POST'});stopProgressAnimation();playingId=null;playingName='';playPaused=false;playDuration=0;playStartedAt=0;elapsedBeforePause=0;status.textContent='Stopped';render(lastData)}catch(e){status.textContent=`Error: ${e}`}}
refreshButton.onclick=()=>browse(currentId);upButton.onclick=()=>parentId&&browse(parentId);rootsButton.onclick=()=>browse(null);stopButton.onclick=stopPlayback;modeMidi.onclick=()=>setMode('midi');modePattern.onclick=()=>setMode('pattern');browse('start');
})();</script></body></html>"""



class PlayerState:
    def __init__(self, fluidsynth: Path, soundfont: Path, audio_driver: str) -> None:
        self.fluidsynth=fluidsynth; self.soundfont=soundfont; self.audio_driver=audio_driver
        self.lock=threading.RLock(); self.process=None; self.temp_midi=None; self.paused=False
        self.loop=False; self.loop_path=None; self.generation=0

    def _suspend_windows_process(self,pid:int,suspend:bool)->None:
        import ctypes
        from ctypes import wintypes
        TH32CS_SNAPTHREAD=0x4; THREAD_SUSPEND_RESUME=0x2; INVALID_HANDLE_VALUE=ctypes.c_void_p(-1).value
        class THREADENTRY32(ctypes.Structure):
            _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ThreadID',wintypes.DWORD),('th32OwnerProcessID',wintypes.DWORD),('tpBasePri',wintypes.LONG),('tpDeltaPri',wintypes.LONG),('dwFlags',wintypes.DWORD)]
        k=ctypes.windll.kernel32; snap=k.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0)
        if snap==INVALID_HANDLE_VALUE: raise OSError('cannot enumerate FluidSynth threads')
        try:
            e=THREADENTRY32(); e.dwSize=ctypes.sizeof(THREADENTRY32); ok=k.Thread32First(snap,ctypes.byref(e)); touched=0
            while ok:
                if e.th32OwnerProcessID==pid:
                    h=k.OpenThread(THREAD_SUSPEND_RESUME,False,e.th32ThreadID)
                    if h:
                        try:
                            r=k.SuspendThread(h) if suspend else k.ResumeThread(h)
                            if r!=0xFFFFFFFF: touched+=1
                        finally: k.CloseHandle(h)
                ok=k.Thread32Next(snap,ctypes.byref(e))
            if not touched: raise OSError('no FluidSynth thread could be controlled')
        finally: k.CloseHandle(snap)

    def _launch(self,path:Path,generation:int,loop:bool=False)->None:
        # Normal MIDI playback uses -i so FluidSynth exits when the file ends.
        # Pattern playback keeps the shell input open and asks FluidSynth's own
        # MIDI player to loop forever. This avoids process restarts at every
        # pattern boundary and gives seamless looping.
        if loop:
            # Keep FluidSynth's shell alive, but let the normal command-line MIDI
            # player load and start the file.  The shell cannot add a MIDI file
            # to the player playlist itself, so do NOT stop/restart the player
            # with shell commands here.  Once startup has completed, only set
            # the already-loaded player to loop forever.
            cmd=[str(self.fluidsynth),'-a',self.audio_driver,'-n',str(self.soundfont),str(path)]
            proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,text=True)

            def enable_infinite_loop() -> None:
                # Popen returns before FluidSynth has necessarily finished
                # creating/loading its MIDI player.  A short delay avoids racing
                # the command-line file loader.  The pattern itself is already
                # playing by then; changing the loop count does not restart it.
                import time
                time.sleep(0.20)
                try:
                    if proc.poll() is None and proc.stdin is not None:
                        proc.stdin.write('player_loop -1\n')
                        proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass

            threading.Thread(target=enable_infinite_loop,daemon=True).start()
        else:
            cmd=[str(self.fluidsynth),'-a',self.audio_driver,'-ni',str(self.soundfont),str(path)]
            proc=subprocess.Popen(cmd)
        with self.lock:
            if generation!=self.generation:
                proc.terminate(); return
            self.process=proc; self.paused=False
        threading.Thread(target=self._after_exit,args=(proc,path,generation),daemon=True).start()

    def _after_exit(self,proc:subprocess.Popen,path:Path,generation:int)->None:
        proc.wait()
        with self.lock:
            if generation!=self.generation or self.process is not proc: return
            self.process=None; self.paused=False; self.loop=False; self.loop_path=None
            owned=self.temp_midi if self.temp_midi==path else None
            if owned: self.temp_midi=None
        if owned:
            try: owned.unlink(missing_ok=True)
            except OSError: pass

    def pause(self)->None:
        with self.lock: proc=self.process
        if proc is None or proc.poll() is not None: raise RuntimeError('nothing is playing')
        if self.paused: return
        if os.name=='nt': self._suspend_windows_process(proc.pid,True)
        else:
            import signal; os.kill(proc.pid,signal.SIGSTOP)
        with self.lock:
            if self.process is proc: self.paused=True

    def resume(self)->None:
        with self.lock: proc=self.process
        if proc is None or proc.poll() is not None: raise RuntimeError('nothing is playing')
        if not self.paused: return
        if os.name=='nt': self._suspend_windows_process(proc.pid,False)
        else:
            import signal; os.kill(proc.pid,signal.SIGCONT)
        with self.lock:
            if self.process is proc: self.paused=False

    def stop(self)->None:
        with self.lock:
            self.generation+=1; proc=self.process; temp=self.temp_midi; paused=self.paused
            self.process=None; self.temp_midi=None; self.paused=False; self.loop=False; self.loop_path=None
        if proc is not None and proc.poll() is None:
            if paused:
                try:
                    if os.name=='nt': self._suspend_windows_process(proc.pid,False)
                    else:
                        import signal; os.kill(proc.pid,signal.SIGCONT)
                except Exception: pass
            proc.terminate()
            try: proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=2)
        if temp:
            try: temp.unlink(missing_ok=True)
            except OSError: pass

    def play_path(self,path:Path,loop:bool=False,temp_owned:bool=False)->None:
        self.stop()
        with self.lock:
            generation=self.generation; self.loop=loop; self.loop_path=path if loop else None; self.temp_midi=path if temp_owned else None
        self._launch(path,generation,loop=loop)

    def play(self,midi_bytes:bytes,loop:bool=False)->None:
        with tempfile.NamedTemporaryFile(prefix='adx_play_',suffix='.mid',delete=False) as fp:
            fp.write(midi_bytes); path=Path(fp.name)
        self.play_path(path,loop=loop,temp_owned=True)


GM_DRUM_NAMES={35:'Acoustic Bass Drum',36:'Bass Drum 1',37:'Side Stick',38:'Acoustic Snare',39:'Hand Clap',40:'Electric Snare',41:'Low Floor Tom',42:'Closed Hi-Hat',43:'High Floor Tom',44:'Pedal Hi-Hat',45:'Low Tom',46:'Open Hi-Hat',47:'Low-Mid Tom',48:'Hi-Mid Tom',49:'Crash Cymbal 1',50:'High Tom',51:'Ride Cymbal 1',52:'Chinese Cymbal',53:'Ride Bell',54:'Tambourine',55:'Splash Cymbal',56:'Cowbell',57:'Crash Cymbal 2',58:'Vibraslap',59:'Ride Cymbal 2',60:'Hi Bongo',61:'Low Bongo',62:'Mute Hi Conga',63:'Open Hi Conga',64:'Low Conga',65:'High Timbale',66:'Low Timbale',67:'High Agogo',68:'Low Agogo',69:'Cabasa',70:'Maracas',71:'Short Whistle',72:'Long Whistle',73:'Short Guiro',74:'Long Guiro',75:'Claves',76:'Hi Wood Block',77:'Low Wood Block',78:'Mute Cuica',79:'Open Cuica',80:'Mute Triangle',81:'Open Triangle'}

def _collect_midi_events(mid):
    rows=[]; order=0
    for ti,tr in enumerate(mid.tracks):
        tick=0
        for msg in tr:
            tick+=int(msg.time); rows.append((tick,ti,order,msg)); order+=1
    rows.sort(key=lambda x:(x[0],x[1],x[2])); return rows

def _time_signature_points(rows,tpq):
    merged={0:(4,4)}
    for tick,_ti,_o,msg in rows:
        if isinstance(msg,MetaMessage) and msg.type=='time_signature': merged[tick]=(int(msg.numerator),int(msg.denominator))
    ordered=sorted((t,n,d) for t,(n,d) in merged.items()); out=[]; measure=1; pt,pn,pd=ordered[0]; out.append((pt,pn,pd,measure))
    for tick,num,den in ordered[1:]:
        bt=max(1,round(tpq*pn*4/pd)); elapsed=max(0,tick-pt); measure+=elapsed//bt+(1 if elapsed%bt else 0); out.append((tick,num,den,measure)); pt,pn,pd=tick,num,den
    return out

def _bar_spans(max_tick,tpq,points):
    spans=[]; measure=1; tick=0; idx=0; cur=points[0]
    while tick<=max_tick:
        while idx+1<len(points) and points[idx+1][0]<=tick: idx+=1; cur=points[idx]; measure=cur[3]
        bt=max(1,round(tpq*cur[1]*4/cur[2])); nxt=points[idx+1][0] if idx+1<len(points) else None; end=tick+bt
        if nxt is not None and tick<nxt<end: end=nxt
        spans.append((measure,tick,end,cur[1],cur[2])); tick=end; measure+=1
    return spans

def _tick_to_seconds_builder(rows,tpq):
    tempos={0:500000}
    for tick,_ti,_o,msg in rows:
        if isinstance(msg,MetaMessage) and msg.type=='set_tempo': tempos[tick]=int(msg.tempo)
    pts=sorted(tempos.items()); seg=[]; elapsed=0.0
    for i,(tick,tempo) in enumerate(pts):
        if i: prev_tick,prev_tempo=pts[i-1]; elapsed+=(tick-prev_tick)*prev_tempo/1_000_000/tpq
        seg.append((tick,tempo,elapsed))
    def conv(tick):
        cur=seg[0]
        for x in seg:
            if x[0]<=tick: cur=x
            else: break
        return cur[2]+(tick-cur[0])*cur[1]/1_000_000/tpq
    return conv

def midi_roll_data(path:Path)->dict:
    if MidiFile is None: raise RuntimeError('mido is required for drum-roll preview')
    mid=MidiFile(path)
    if mid.ticks_per_beat<=0: raise ValueError('SMPTE timing is not supported')
    rows=_collect_midi_events(mid); active=defaultdict(list); notes=[]
    for tick,track,_order,msg in rows:
        if not isinstance(msg,Message) or not hasattr(msg,'channel') or msg.channel!=9 or msg.type not in {'note_on','note_off'}: continue
        key=(track,msg.note)
        if msg.type=='note_on' and msg.velocity>0: active[key].append((tick,int(msg.velocity)))
        elif msg.type=='note_off' or (msg.type=='note_on' and msg.velocity==0):
            if active[key]:
                start,vel=active[key].pop(0); notes.append({'start_tick':start,'duration':max(0,tick-start),'note':int(msg.note),'velocity':vel})
    for (track,note),starts in active.items():
        for start,vel in starts: notes.append({'start_tick':start,'duration':0,'note':int(note),'velocity':vel})
    notes.sort(key=lambda n:(n['start_tick'],n['note']))
    if not notes: return {'notes':[],'bars':[],'note_order':[],'note_names':{},'ppqn':mid.ticks_per_beat,'ppqn_label':f'PPQN {mid.ticks_per_beat}'}
    points=_time_signature_points(rows,mid.ticks_per_beat); max_tick=max(n['start_tick']+n['duration'] for n in notes); spans=_bar_spans(max_tick,mid.ticks_per_beat,points); to_sec=_tick_to_seconds_builder(rows,mid.ticks_per_beat)
    def pos(t):
        point=points[0]
        for c in points:
            if c[0]<=t: point=c
            else: break
        beat_ticks=mid.ticks_per_beat*4/point[2]; bar_ticks=beat_ticks*point[1]; rel=max(0,t-point[0]); bo=int(rel//bar_ticks); wb=rel-bo*bar_ticks; bi=int(wb//beat_ticks); tib=int(round(wb-bi*beat_ticks)); return f'{point[3]+bo}:{bi+1}:{tib:03d}'
    for n in notes: n['position']=pos(n['start_tick'])
    bars=[{'measure':m,'start_tick':a,'end_tick':b,'numerator':num,'denominator':den,'start_seconds':to_sec(a),'end_seconds':to_sec(b)} for m,a,b,num,den in spans]
    used=sorted({n['note'] for n in notes},reverse=True)
    return {'notes':notes,'bars':bars,'note_order':used,'note_names':{str(n):GM_DRUM_NAMES.get(n,f'Unknown drum note {n}') for n in used},'ppqn':mid.ticks_per_beat,'ppqn_label':f'PPQN {mid.ticks_per_beat}'}

def midi_duration_seconds(path: Path) -> float | None:
    if MidiFile is None: return None
    try: return max(0.0,float(MidiFile(path).length))
    except Exception: return None

ADP3_HEADER_FMT='<4sBBBBHH'; ADP3_HEADER_SIZE=struct.calcsize(ADP3_HEADER_FMT)
SUBDIV_CODE_TO_STR={0:'16',1:'32',2:'8T',3:'16T'}; STEPS_PER_QUARTER={'16':4,'32':8,'8T':3,'16T':6}

def _load_json(path:Path): return json.loads(path.read_text(encoding='utf-8'))

def load_pattern_config(script_dir:Path):
    maps=_load_json(script_dir/'slot_map_definitions.json'); accents=_load_json(script_dir/'accent_levels.json')
    by_name={}; by_id={}
    for m in maps:
        slots=[]
        for s in m['slots']:
            slots.append({'abbrev':s['abbrev'].upper(),'note':int(s['representative_midi'])})
        item={'name':m['name'].upper(),'id':int(m['slot_map_id']),'slots':slots}; by_name[item['name']]=item; by_id[item['id']]=item
    scheme=(accents.get('schemes') or {}).get('6-accent') or {}
    levels=scheme.get('levels') or []
    velocities={int(x['index']):int(x['representative_velocity']) for x in levels}
    colors={str(int(x['index'])):'rgb(%d,%d,%d)'%tuple(x['color']) for x in levels}
    symbols={str(x['symbol']).lower():int(x['index']) for x in levels}
    return {'by_name':by_name,'by_id':by_id,'velocities':velocities,'colors':colors,'symbols':symbols}

def parse_inline_slot(value:str):
    m=re.fullmatch(r'\s*([^@,\s]+)\s*@\s*([0-9]{1,3})\s*(?:,\s*(.+?)\s*)?',value)
    if not m: raise ValueError(f'invalid inline slot: {value!r}')
    return {'abbrev':m.group(1).upper(),'note':int(m.group(2))}

def parse_adt(path:Path,cfg:dict)->dict:
    lines=path.read_text(encoding='utf-8-sig').splitlines(); meta={}; inline={}; data=[]; in_data=False
    if not lines or lines[0].strip()!='; ADT v2.3': raise ValueError('not ADT v2.3')
    for raw in lines[1:]:
        line=raw.split(';',1)[0].strip()
        if not line: continue
        if line.upper()=='[DATA]': in_data=True; continue
        if in_data: data.append(''.join(c for c in line if not c.isspace())); continue
        if '=' not in line: continue
        k,v=line.split('=',1); k=k.strip().upper(); v=v.strip()
        sm=re.fullmatch(r'SLOT([0-9]+)',k)
        if sm: inline[int(sm.group(1))]=v
        else: meta[k]=v
    length=int(meta['LENGTH']); subdiv=meta['SUBDIV'].upper(); smap=meta.get('SLOT_MAP_ID','LEGACY').upper()
    if smap=='INLINE': slots=[parse_inline_slot(inline[i]) for i in sorted(inline)]
    else: slots=cfg['by_name'][smap]['slots']
    orient=meta.get('ORIENTATION','STEP').upper(); symbols=cfg['symbols']
    if orient=='STEP': steps=[[symbols.get(c.lower(),0) for c in row] for row in data]
    else:
        steps=[[0]*len(slots) for _ in range(length)]
        for si,row in enumerate(data):
            for st,c in enumerate(row): steps[st][si]=symbols.get(c.lower(),0)
    return {'path':path,'name':meta.get('NAME',path.stem).upper(),'length':length,'subdiv':subdiv,'steps':steps,'slots':slots,'ppqn':int(meta.get('PPQN','240')),'time_sig':meta.get('TIME_SIG'),'source':meta.get('SOURCE')}

def decode_adp(path:Path,cfg:dict)->dict:
    data=path.read_bytes();
    if len(data)<ADP3_HEADER_SIZE: raise ValueError('ADP3 header too short')
    magic,ver,subcode,length,mapid,pbytes,_crc=struct.unpack(ADP3_HEADER_FMT,data[:ADP3_HEADER_SIZE])
    if magic!=b'ADP3' or ver!=23: raise ValueError('not ADP v2.3')
    companion=path.with_suffix('.ADT')
    if not companion.exists(): companion=path.with_suffix('.adt')
    adt=parse_adt(companion,cfg) if companion.exists() else None
    if mapid==255:
        if not adt: raise ValueError('INLINE ADP needs companion ADT')
        slots=adt['slots']
    else: slots=cfg['by_id'][mapid]['slots']
    payload=data[ADP3_HEADER_SIZE:ADP3_HEADER_SIZE+pbytes]; steps=[[0]*len(slots) for _ in range(length)]; o=0
    for st in range(length):
        n=payload[o]; o+=1
        for _ in range(n):
            hit=payload[o]; o+=1; slot=(hit>>3)&0x0f; accent=hit&7
            if slot<len(slots): steps[st][slot]=max(steps[st][slot],accent)
    subdiv=SUBDIV_CODE_TO_STR[subcode]
    return {'path':path,'name':path.stem.upper(),'length':length,'subdiv':subdiv,'steps':steps,'slots':slots,'ppqn':adt['ppqn'] if adt else 240,'time_sig':adt['time_sig'] if adt else None,'source':adt['source'] if adt else None}

def load_pattern(path:Path,cfg:dict)->dict:
    return parse_adt(path,cfg) if path.suffix.lower()=='.adt' else decode_adp(path,cfg)

def load_orn_text(path:Path)->str|None:
    for suffix in ('.ORN','.orn'):
        p=path.with_suffix(suffix)
        if p.is_file(): return p.read_text(encoding='utf-8-sig')
    return None

def parse_orn_events(text:str|None,pattern:dict)->list[dict]:
    if not text: return []
    out=[]; in_events=False
    abbrev={s['abbrev'].upper():i for i,s in enumerate(pattern['slots'])}
    for raw in text.splitlines():
        line=raw.split(';',1)[0].strip()
        if not line: continue
        if line.upper()=='[EVENTS]': in_events=True; continue
        if not in_events: continue
        parts=line.split(); kind=parts[0].upper(); fields={}
        for token in parts[1:]:
            if '=' in token:
                k,v=token.split('=',1); fields[k.upper()]=v
        if kind not in {'FLAM','NOTE'}: continue
        slot_token=fields.get('SLOT','0'); slot=int(slot_token) if slot_token.isdigit() else abbrev.get(slot_token.upper(),-1)
        if slot<0: continue
        out.append({'kind':kind,'target_step':int(fields['TARGET_STEP']),'slot':slot,'offset_ticks':int(fields.get('OFFSET_TICKS','0')),'velocity':int(fields.get('VELOCITY','80'))})
    return out

def pattern_to_midi_bytes(pattern:dict,cfg:dict,orn_text:str|None)->bytes:
    if MidiFile is None: raise RuntimeError('mido is required for ADT/ADP playback')
    ppqn=int(pattern['ppqn']); step_ticks=ppqn//STEPS_PER_QUARTER[pattern['subdiv']]; loop_ticks=pattern['length']*step_ticks
    events=[]; note_len=max(1,ppqn//16); timing_overrides={}
    orn=parse_orn_events(orn_text,pattern)
    for e in orn:
        if e['kind']=='NOTE': timing_overrides[(e['target_step'],e['slot'])]=e
    for st,row in enumerate(pattern['steps']):
        for si,accent in enumerate(row):
            if not accent: continue
            e=timing_overrides.get((st,si)); tick=st*step_ticks+(e['offset_ticks'] if e else 0); tick%=loop_ticks
            vel=e['velocity'] if e else cfg['velocities'].get(int(accent),96); note=pattern['slots'][si]['note']; events.append((tick,1,note,vel)); events.append((min(loop_ticks-1,tick+note_len),0,note,0))
    for e in orn:
        if e['kind']!='FLAM': continue
        tick=(e['target_step']*step_ticks+e['offset_ticks'])%loop_ticks; note=pattern['slots'][e['slot']]['note']; events.append((tick,1,note,e['velocity'])); events.append((min(loop_ticks-1,tick+note_len),0,note,0))
    # Avoid wrapped note-offs sorting before their note-ons by clipping at loop end.
    clean=[]
    for tick,on,note,vel in events:
        if tick<0: tick=0
        clean.append((tick,on,note,vel))
    clean.sort(key=lambda x:(x[0],x[1]))
    mid=MidiFile(type=0,ticks_per_beat=ppqn); tr=MidiTrack(); mid.tracks.append(tr); tr.append(MetaMessage('set_tempo',tempo=500000,time=0))
    ts=pattern.get('time_sig') or '4/4'; m=re.fullmatch(r'(\d+)\s*/\s*(\d+)',ts)
    if m: tr.append(MetaMessage('time_signature',numerator=int(m.group(1)),denominator=int(m.group(2)),time=0))
    last=0
    for tick,on,note,vel in clean:
        if tick>=loop_ticks: continue
        tr.append(Message('note_on' if on else 'note_off',channel=9,note=note,velocity=vel,time=max(0,tick-last))); last=tick
    tr.append(MetaMessage('end_of_track',time=max(1,loop_ticks-last)))
    import io; bio=io.BytesIO(); mid.save(file=bio); return bio.getvalue()


class FileBrowser:
    """Read-only filesystem browser for MIDI plus grouped ADT/ADP patterns."""
    MIDI_SUFFIXES={'.mid','.midi'}; PATTERN_SUFFIXES={'.adt','.adp'}
    def __init__(self,start_directory:Path):
        self.start_directory=start_directory.resolve(); self.secret=secrets.token_bytes(32); self.lock=threading.RLock(); self.by_id={}; self.root_id='computer'; self._remember(self.start_directory,'dir')
    def _id_for(self,path:Path,prefix:str)->str:
        digest=hashlib.blake2s(str(path.resolve()).encode('utf-8','surrogatepass'),key=self.secret,digest_size=12).hexdigest(); return f'{prefix}-{digest}'
    def _remember(self,path:Path,prefix:str|None=None)->str:
        resolved=path.resolve(); prefix=prefix or ('dir' if resolved.is_dir() else 'file'); item_id=self._id_for(resolved,prefix)
        with self.lock: self.by_id[item_id]=resolved
        return item_id
    def _roots(self):
        if os.name=='nt':
            try:
                import ctypes; mask=int(ctypes.windll.kernel32.GetLogicalDrives())
                if mask: return [Path(f'{chr(65+i)}:\\') for i in range(26) if mask&(1<<i)]
            except Exception: pass
            return [Path(f'{x}:\\') for x in 'CDEFGHIJKLMNOPQRSTUVWXYZ']
        return [Path('/')]
    def _is_hidden_directory(self,path:Path)->bool:
        if path.name.startswith('.'): return True
        if os.name=='nt':
            try:
                import ctypes; attrs=int(ctypes.windll.kernel32.GetFileAttributesW(str(path))); return attrs!=-1 and bool(attrs&0x2)
            except Exception: pass
        return False
    def _folders(self,directory:Path):
        out=[]
        try: entries=sorted(directory.iterdir(),key=lambda p:p.name.casefold())
        except (PermissionError,OSError) as exc: raise PermissionError(f'Cannot read folder: {directory}') from exc
        for p in entries:
            try:
                if p.is_symlink() or not p.is_dir() or self._is_hidden_directory(p): continue
                out.append({'id':self._remember(p,'dir'),'name':p.name or str(p)})
            except (PermissionError,OSError): pass
        return out
    def _midi_files(self,directory:Path):
        out=[]
        try: entries=sorted(directory.iterdir(),key=lambda p:p.name.casefold())
        except (PermissionError,OSError): return out
        for p in entries:
            try:
                if p.is_file() and p.suffix.lower() in self.MIDI_SUFFIXES:
                    st=p.stat(); out.append({'id':self._remember(p,'midi'),'name':p.name,'size':st.st_size,'duration_seconds':midi_duration_seconds(p)})
            except (PermissionError,OSError): pass
        return out
    def _patterns(self,directory:Path):
        grouped={}
        try: entries=list(directory.iterdir())
        except (PermissionError,OSError): return [],{}
        for p in entries:
            try:
                if not p.is_file() or p.suffix.lower() not in self.PATTERN_SUFFIXES: continue
                key=p.stem.casefold(); prev=grouped.get(key)
                if prev is None or (prev.suffix.lower()=='.adt' and p.suffix.lower()=='.adp'): grouped[key]=p
            except OSError: pass
        pats=[]; genres={}
        for p in sorted(grouped.values(),key=lambda x:x.stem.casefold()):
            name=p.stem.upper(); m=re.match(r'^([A-Z0-9]{2,5})_',name); genre=m.group(1) if m else 'OTHER'; has_orn=any(p.with_suffix(s).is_file() for s in ('.ORN','.orn'))
            pats.append({'id':self._remember(p,'pat'),'name':name,'type':p.suffix[1:].upper(),'genre':genre,'has_orn':has_orn}); genres[genre]=genres.get(genre,0)+1
        return pats,dict(sorted(genres.items()))
    def browse(self,item_id:str|None,mode:str='midi'):
        if item_id=='start': item_id=self._remember(self.start_directory,'dir')
        if not item_id or item_id==self.root_id:
            folders=[]
            for r in self._roots():
                try:
                    if r.exists() and r.is_dir(): folders.append({'id':self._remember(r,'dir'),'name':str(r)})
                except OSError: pass
            return {'current_id':self.root_id,'parent_id':None,'display_path':'Computer' if os.name=='nt' else '/','folders':folders,'files':[],'patterns':[],'genres':{}}
        with self.lock: directory=self.by_id.get(item_id)
        if directory is None or not item_id.startswith('dir-') or not directory.is_dir(): raise ValueError('unknown or expired folder ID')
        parent=directory.parent; parent_id=self.root_id if parent==directory else self._remember(parent,'dir'); folders=self._folders(directory)
        pats,genres=self._patterns(directory) if mode=='pattern' else ([],{})
        return {'current_id':item_id,'parent_id':parent_id,'display_path':str(directory),'folders':folders,'files':self._midi_files(directory) if mode=='midi' else [],'patterns':pats,'genres':genres}
    def midi_files_in_start(self): return self._midi_files(self.start_directory)
    def _resolve(self,file_id:str,prefix:str,suffixes:set[str]):
        if not isinstance(file_id,str) or not file_id.startswith(prefix+'-'): raise ValueError(f'invalid {prefix} file ID')
        with self.lock: path=self.by_id.get(file_id)
        if path is None or path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes: raise ValueError(f'unknown or expired {prefix} file ID')
        return path.resolve()
    def resolve_midi(self,file_id:str)->Path: return self._resolve(file_id,'midi',self.MIDI_SUFFIXES)
    def resolve_pattern(self,file_id:str)->Path: return self._resolve(file_id,'pat',self.PATTERN_SUFFIXES)


def make_handler(player: PlayerState, directory: Path, browser: FileBrowser, report_selected: bool, pattern_cfg: dict):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(directory),**kwargs)
        def _send_cors_headers(self):
            if self.headers.get('Origin')=='null': self.send_header('Access-Control-Allow-Origin','null'); self.send_header('Vary','Origin')
        def _send_text(self,status:int,message:str):
            body=message.encode('utf-8'); self.send_response(status); self.send_header('Content-Type','text/plain; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self._send_cors_headers(); self.end_headers(); self.wfile.write(body)
        def _send_json(self,status:int,value:object):
            body=json.dumps(value,ensure_ascii=False).encode('utf-8'); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self._send_cors_headers(); self.end_headers(); self.wfile.write(body)
        def do_OPTIONS(self):
            self.send_response(204); self._send_cors_headers(); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.send_header('Access-Control-Max-Age','600'); self.end_headers()
        def list_directory(self,path): self.send_error(403,'Directory listing is disabled'); return None
        def send_head(self):
            request_path=urlparse(self.path).path
            if request_path=='/' and not report_selected:
                body=NO_REPORT_HTML.encode('utf-8'); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body); return None
            if request_path.endswith('/'): return self.list_directory(str(directory))
            if Path(request_path).suffix.lower() not in {'.html','.htm'}: self.send_error(403,'Only PatternLab HTML reports are served'); return None
            return super().send_head()
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/api/status': self._send_json(200,{'status':'ready','version':VERSION}); return
            if path=='/api/midi-files':
                try: self._send_json(200,{'files':browser.midi_files_in_start()})
                except Exception as exc: self._send_json(500,{'error':str(exc)})
                return
            if path=='/api/browse':
                try:
                    q=parse_qs(urlparse(self.path).query); item=q.get('id',[None])[0]; mode=q.get('mode',['midi'])[0]
                    if mode not in {'midi','pattern'}: raise ValueError('invalid browse mode')
                    self._send_json(200,browser.browse(item,mode))
                except PermissionError as exc: self._send_json(403,{'error':str(exc)})
                except ValueError as exc: self._send_json(400,{'error':str(exc)})
                except Exception as exc: self._send_json(500,{'error':str(exc)})
                return
            if path=='/api/midi-roll':
                try:
                    q=parse_qs(urlparse(self.path).query); file_id=q.get('id',[None])[0]; p=browser.resolve_midi(file_id); self._send_json(200,midi_roll_data(p))
                except ValueError as exc: self._send_json(400,{'error':str(exc)})
                except Exception as exc: self._send_json(500,{'error':f'Drum roll failed: {exc}'})
                return
            if path=='/api/pattern':
                try:
                    q=parse_qs(urlparse(self.path).query); file_id=q.get('id',[None])[0]; p=browser.resolve_pattern(file_id); pat=load_pattern(p,pattern_cfg); orn=load_orn_text(p)
                    self._send_json(200,{'name':pat['name'],'length':pat['length'],'subdiv':pat['subdiv'],'time_sig':pat.get('time_sig') or '4/4','slots':[s['abbrev'] for s in pat['slots']],'steps':pat['steps'],'colors':pattern_cfg['colors'],'orn_text':orn})
                except ValueError as exc: self._send_json(400,{'error':str(exc)})
                except Exception as exc: self._send_json(500,{'error':f'Pattern load failed: {exc}'})
                return
            super().do_GET()
        def _json_payload(self):
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=65536: raise ValueError('invalid request size')
            return json.loads(self.rfile.read(length).decode('utf-8'))
        def do_POST(self):
            path=urlparse(self.path).path
            if path=='/pause':
                try: player.pause(); self._send_text(200,'Paused')
                except Exception as exc: self._send_text(409,f'Pause failed: {exc}')
                return
            if path=='/resume':
                try: player.resume(); self._send_text(200,'Resumed')
                except Exception as exc: self._send_text(409,f'Resume failed: {exc}')
                return
            if path=='/stop': player.stop(); self._send_text(200,'Stopped'); return
            if path=='/play-file':
                try:
                    payload=self._json_payload(); file_id=payload.get('id') if isinstance(payload,dict) else None; midi_path=browser.resolve_midi(file_id); player.play_path(midi_path,loop=False); self._send_json(200,{'status':'playing','id':file_id,'name':midi_path.name,'duration_seconds':midi_duration_seconds(midi_path)})
                except (ValueError,json.JSONDecodeError) as exc: self._send_json(400,{'error':str(exc)})
                except Exception as exc: self._send_json(500,{'error':f'Playback failed: {exc}'})
                return
            if path=='/play-pattern':
                try:
                    payload=self._json_payload(); file_id=payload.get('id') if isinstance(payload,dict) else None; pat_path=browser.resolve_pattern(file_id); pat=load_pattern(pat_path,pattern_cfg); orn=load_orn_text(pat_path); midi_bytes=pattern_to_midi_bytes(pat,pattern_cfg,orn); player.play(midi_bytes,loop=True); self._send_json(200,{'status':'playing','id':file_id,'name':pat['name'],'loop':True,'orn':bool(orn)})
                except (ValueError,json.JSONDecodeError) as exc: self._send_json(400,{'error':str(exc)})
                except Exception as exc: self._send_json(500,{'error':f'Pattern playback failed: {exc}'})
                return
            if path!='/play': self._send_text(404,'Not found'); return
            try: length=int(self.headers.get('Content-Length','0'))
            except ValueError: self._send_text(400,'Invalid Content-Length'); return
            if not 1<=length<=MAX_MIDI_BYTES: self._send_text(400,'Invalid MIDI data size'); return
            midi_bytes=self.rfile.read(length)
            if len(midi_bytes)!=length or not midi_bytes.startswith(b'MThd'): self._send_text(400,'Not a Standard MIDI File'); return
            try: player.play(midi_bytes,loop=False); self._send_text(200,'Playing with FluidSynth')
            except Exception as exc: self._send_text(500,f'Playback failed: {exc}')
        def log_message(self,fmt,*args): print(f'[PatternLab] {self.address_string()} - {fmt % args}')
    return Handler


def existing_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"file not found: {path}")
    return path


def resolve_fluidsynth(explicit: Path | None, parser: argparse.ArgumentParser) -> tuple[Path, str]:
    """Resolve FluidSynth with priority: CLI override, PATH, embedded default."""
    if explicit is not None:
        return explicit, "command-line override"

    found = shutil.which("fluidsynth.exe") or shutil.which("fluidsynth")
    if found:
        path = Path(found).resolve()
        if path.is_file():
            return path, "PATH"

    fallback = DEFAULT_FLUIDSYNTH.expanduser()
    if fallback.is_file():
        return fallback.resolve(), "embedded default"

    parser.error(
        "FluidSynth was not found. Supply --fluidsynth PATH, add fluidsynth.exe "
        f"to PATH, or install it at the embedded default:\n  {DEFAULT_FLUIDSYNTH}"
    )
    raise AssertionError("unreachable")


def resolve_soundfont(explicit: Path | None, parser: argparse.ArgumentParser) -> tuple[Path, str]:
    """Resolve SoundFont with priority: CLI override, embedded default."""
    if explicit is not None:
        return explicit, "command-line override"

    fallback = DEFAULT_SOUNDFONT.expanduser()
    if fallback.is_file():
        return fallback.resolve(), "embedded default"

    parser.error(
        "SoundFont was not found. Supply --sf2 PATH or place it at the embedded default:\n"
        f"  {DEFAULT_SOUNDFONT}"
    )
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve a PatternLab HTML report or browse/play readable MIDI files.",
        epilog=(
            "Examples:\n"
            "  python play_server.py\n"
            "  python play_server.py --report COOL_PatternLab.html\n"
            "  python play_server.py --report .\\reports\\COOL_PatternLab.html\n"
            "  python play_server.py --report E:\\Hobbies\\ADX\\reports\\COOL_PatternLab.html"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=VERSION_TEXT,
    )
    parser.add_argument(
        "--fluidsynth",
        type=existing_file,
        default=None,
        help=(
            "override path to fluidsynth.exe; when omitted, search PATH first, "
            f"then use {DEFAULT_FLUIDSYNTH}"
        ),
    )
    parser.add_argument(
        "--sf2",
        type=existing_file,
        default=None,
        help=f"override SoundFont path; default: {DEFAULT_SOUNDFONT}",
    )
    parser.add_argument(
        "--report",
        metavar="HTML",
        required=False,
        help="optional PatternLab HTML report path; omit to open the filesystem MIDI browser",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--audio-driver", default="dsound", help="FluidSynth audio driver (default: dsound)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    args = parser.parse_args()

    fluidsynth, fluidsynth_source = resolve_fluidsynth(args.fluidsynth, parser)
    soundfont, soundfont_source = resolve_soundfont(args.sf2, parser)

    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")

    report_path: Path | None = None
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        if not report_path.is_file():
            parser.error(f"report not found: {report_path}")
        if report_path.suffix.lower() not in {".html", ".htm"}:
            parser.error(f"--report must be an HTML file: {report_path}")
        directory = report_path.parent
    else:
        directory = Path.cwd().resolve()

    player = PlayerState(fluidsynth, soundfont, args.audio_driver)
    browser_start = directory if report_path is not None else Path.cwd().resolve()
    browser = FileBrowser(browser_start)
    try:
        pattern_cfg = load_pattern_config(Path(__file__).resolve().parent)
    except Exception as exc:
        parser.error(f"cannot load pattern definitions beside script: {exc}")
    handler = make_handler(player, directory, browser, report_selected=report_path is not None, pattern_cfg=pattern_cfg)
    server = ThreadingHTTPServer((HOST, args.port), handler)
    base_url = f"http://{HOST}:{args.port}/"

    if report_path is not None:
        from urllib.parse import quote
        report_url_path = quote(report_path.name, safe="/")
        open_url = base_url + report_url_path
    else:
        open_url = base_url

    print(f"PatternLab FluidSynth service ({VERSION_TEXT})")
    print(f"  URL        : {base_url}")
    print(f"  Directory  : {directory}")
    if report_path is None:
        print(f"  MIDI Home  : {browser_start}")
    print(f"  FluidSynth : {fluidsynth} ({fluidsynth_source})")
    print(f"  SoundFont  : {soundfont} ({soundfont_source})")
    print("  Stop server: Ctrl+C")

    if not args.no_browser:
        webbrowser.open(open_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        player.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
