#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local PatternLab playback service using FluidSynth and an SF2 SoundFont.

Version: 260810f
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from mido import MidiFile
except ImportError:
    MidiFile = None

SCRIPT_NAME = "play_server.py"
VERSION = "260810f"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"

HOST = "127.0.0.1"
DEFAULT_PORT = 8123
MAX_MIDI_BYTES = 16 * 1024 * 1024
DEFAULT_FLUIDSYNTH = Path(r"C:\Tools\FluidSynth\bin\fluidsynth.exe")
DEFAULT_SOUNDFONT = Path(r"C:\SoundFonts\GeneralUser-GS.sf2")


NO_REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADX Drum MIDI Player</title>
<style>
:root{color-scheme:light dark;--bg:#f4f6f8;--panel:#fff;--ink:#1f2933;--muted:#66717d;--line:#d8dee5;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9aa6b2;--line:#303843;--accent:#60a5fa}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:980px;margin:32px auto;padding:24px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
header{padding:20px 22px 15px;border-bottom:1px solid var(--line)}h1{margin:0 0 5px;font-size:1.5rem}p{margin:0;color:var(--muted)}
.toolbar{display:flex;gap:8px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}
button{border:1px solid var(--line);border-radius:7px;padding:7px 12px;background:var(--panel);color:var(--ink);cursor:pointer;font-weight:700}
button.primary{color:#fff;background:var(--accent);border-color:var(--accent)}button:disabled{opacity:.55;cursor:default}
.location{flex:1;min-width:220px;padding:7px 10px;border:1px solid var(--line);border-radius:7px;background:var(--bg);font:12px ui-monospace,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status{color:var(--muted);font-size:.88rem;white-space:nowrap}
table{width:100%;border-collapse:collapse}th,td{padding:10px 13px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}td.num,th.num{text-align:right}
.entry{cursor:pointer}.entry:hover{background:var(--bg)}.folder-name{font-weight:750}.file-name{font-weight:650}.kind{color:var(--muted);font-size:.82rem}
.playback-row td{padding:0 13px 10px;background:var(--bg)}.inline-player{padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
.inline-player-line{display:flex;justify-content:space-between;gap:12px;font-size:.82rem}.inline-player-state{font-weight:750}.inline-player-time{color:var(--muted);white-space:nowrap}
.progress{height:7px;margin-top:7px;overflow:hidden;border-radius:999px;background:var(--line)}.progress span{display:block;width:0;height:100%;background:var(--accent)}
.empty{padding:30px;text-align:center;color:var(--muted)}footer{padding:11px 16px;color:var(--muted);font-size:.82rem}
</style>
</head>
<body>
<main><section class="panel">
<header><h1>ADX Drum MIDI Player</h1><p>Browse readable folders and play Standard MIDI files with FluidSynth.</p></header>
<div class="toolbar">
<button id="roots">Computer</button><button id="up">Up</button><button id="refresh">Refresh</button><button id="stop">Stop</button>
<div id="location" class="location">Loading…</div><span id="status" class="status"></span>
</div>
<div id="content"></div>
<footer>Read-only browser. Only .MID and .MIDI files can be played; hidden folders are not shown.</footer>
</section></main>
<script>
(()=>{
const content=document.getElementById('content'),status=document.getElementById('status'),locationBox=document.getElementById('location');
const refreshButton=document.getElementById('refresh'),stopButton=document.getElementById('stop'),upButton=document.getElementById('up'),rootsButton=document.getElementById('roots');

let currentId=null,parentId=null;
let playingId=null,playingName='',playDuration=0,playStartedAt=0,elapsedBeforePause=0,playPaused=false,playAnimation=null;

const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes=v=>!Number.isFinite(v)?'—':v<1024?`${v} B`:v<1048576?`${(v/1024).toFixed(1)} KB`:`${(v/1048576).toFixed(1)} MB`;
const duration=v=>{if(!Number.isFinite(v))return '—';const t=Math.max(0,Math.round(v)),m=Math.floor(t/60),s=t%60;return m?`${m}:${String(s).padStart(2,'0')}`:`${s} s`};

function elapsedSeconds(){
 const live=(!playPaused&&playStartedAt)?(performance.now()-playStartedAt)/1000:0;
 return Math.max(0,elapsedBeforePause+live);
}
function stopAnimation(){
 if(playAnimation){cancelAnimationFrame(playAnimation);playAnimation=null}
}
function clearPlaybackState(){
 stopAnimation();
 playingId=null;playingName='';playDuration=0;playStartedAt=0;elapsedBeforePause=0;playPaused=false;
 syncPlaybackUI();
}
function syncPlaybackUI(){
 document.querySelectorAll('.playback-row').forEach(row=>row.remove());
 document.querySelectorAll('.play').forEach(b=>{
   if(b.dataset.id===playingId)b.textContent=playPaused?'▶ Resume':'⏸ Pause';
   else b.textContent='▶ Play';
 });
 if(!playingId)return;
 const button=[...document.querySelectorAll('.play')].find(b=>b.dataset.id===playingId);
 if(!button)return;
 const row=button.closest('tr');if(!row)return;
 const extra=document.createElement('tr');extra.className='playback-row';
 extra.innerHTML=`<td colspan="4"><div class="inline-player"><div class="inline-player-line"><span class="inline-player-state">${playPaused?'Paused':'Playing'}: ${esc(playingName)}</span><span class="inline-player-time">0:00 / ${duration(playDuration)}</span></div><div class="progress"><span></span></div></div></td>`;
 row.insertAdjacentElement('afterend',extra);
 updatePlaybackBar();
}
function updatePlaybackBar(){
 const row=document.querySelector('.playback-row');if(!row)return;
 const time=row.querySelector('.inline-player-time'),bar=row.querySelector('.progress span'),state=row.querySelector('.inline-player-state');
 const elapsed=elapsedSeconds();
 const ratio=playDuration>0?Math.max(0,Math.min(1,elapsed/playDuration)):0;
 if(bar)bar.style.width=`${ratio*100}%`;
 if(time)time.textContent=playDuration>0?`${duration(Math.min(elapsed,playDuration))} / ${duration(playDuration)}`:(playPaused?'Paused':'Playing');
 if(state)state.textContent=`${playPaused?'Paused':'Playing'}: ${playingName}`;
 stopAnimation();
 if(!playPaused&&playingId&&playDuration>0&&ratio<1)playAnimation=requestAnimationFrame(updatePlaybackBar);
 if(!playPaused&&playDuration>0&&ratio>=1){status.textContent=`Finished: ${playingName}`;clearPlaybackState()}
}

function render(data){
 currentId=data.current_id??null;parentId=data.parent_id??null;
 locationBox.textContent=data.display_path||'Computer';locationBox.title=data.display_path||'Computer';upButton.disabled=!parentId;
 const folders=Array.isArray(data.folders)?data.folders:[],files=Array.isArray(data.files)?data.files:[];
 if(!folders.length&&!files.length){content.innerHTML='<div class="empty">No readable folders or MIDI files here.</div>';status.textContent='Empty';return}
 let rows='';
 for(const f of folders)rows+=`<tr class="entry folder" data-id="${esc(f.id)}"><td><span class="folder-name">📁 ${esc(f.name)}</span></td><td class="kind">Folder</td><td></td><td></td></tr>`;
 for(const f of files)rows+=`<tr class="entry midi"><td><span class="file-name">♪ ${esc(f.name)}</span></td><td class="kind">MIDI</td><td class="num">${duration(f.duration_seconds)}</td><td class="num">${bytes(f.size)} &nbsp; <button class="primary play" data-id="${esc(f.id)}">▶ Play</button></td></tr>`;
 content.innerHTML=`<table><thead><tr><th>Name</th><th>Type</th><th class="num">Duration</th><th class="num">Size / Action</th></tr></thead><tbody>${rows}</tbody></table>`;
 content.querySelectorAll('.folder').forEach(row=>row.addEventListener('click',()=>browse(row.dataset.id)));
 content.querySelectorAll('.play').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();togglePlayback(b.dataset.id,b)}));
 syncPlaybackUI();
 status.textContent=`${folders.length} folder${folders.length===1?'':'s'} · ${files.length} MIDI`;
}
async function browse(id){
 refreshButton.disabled=true;status.textContent='Loading…';
 try{const q=id?`?id=${encodeURIComponent(id)}`:'';const r=await fetch('/api/browse'+q,{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);render(d)}
 catch(e){content.innerHTML=`<div class="empty">${esc(String(e))}</div>`;status.textContent='Error'}finally{refreshButton.disabled=false}
}
async function startPlayback(id,b){
 b.disabled=true;status.textContent='Starting playback…';
 try{
   const r=await fetch('/play-file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
   const d=await r.json();if(!r.ok)throw new Error(d.error||'Playback failed');
   stopAnimation();
   playingId=id;playingName=String(d.name||'MIDI');playDuration=Number(d.duration_seconds)||0;
   elapsedBeforePause=0;playStartedAt=performance.now();playPaused=false;
   status.textContent=`Playing: ${playingName}`;syncPlaybackUI();
 }catch(e){status.textContent=`Error: ${e}`}finally{b.disabled=false}
}
async function pausePlayback(){
 try{
   const r=await fetch('/pause',{method:'POST'});if(!r.ok)throw new Error(await r.text());
   elapsedBeforePause=elapsedSeconds();playStartedAt=0;playPaused=true;status.textContent=`Paused: ${playingName}`;syncPlaybackUI();
 }catch(e){status.textContent=`Error: ${e}`}
}
async function resumePlayback(){
 try{
   const r=await fetch('/resume',{method:'POST'});if(!r.ok)throw new Error(await r.text());
   playStartedAt=performance.now();playPaused=false;status.textContent=`Playing: ${playingName}`;syncPlaybackUI();
 }catch(e){status.textContent=`Error: ${e}`}
}
async function togglePlayback(id,b){
 if(id!==playingId){await startPlayback(id,b);return}
 if(playPaused)await resumePlayback();else await pausePlayback();
}
async function stopPlayback(){
 stopButton.disabled=true;
 try{const r=await fetch('/stop',{method:'POST'});if(!r.ok)throw new Error(await r.text());status.textContent='Stopped';clearPlaybackState()}
 catch(e){status.textContent=`Error: ${e}`}finally{stopButton.disabled=false}
}
refreshButton.addEventListener('click',()=>browse(currentId));
upButton.addEventListener('click',()=>parentId&&browse(parentId));
rootsButton.addEventListener('click',()=>browse(null));
stopButton.addEventListener('click',stopPlayback);
browse('start');
})();
</script>
</body>
</html>
"""


class PlayerState:
    def __init__(self, fluidsynth: Path, soundfont: Path, audio_driver: str) -> None:
        self.fluidsynth = fluidsynth
        self.soundfont = soundfont
        self.audio_driver = audio_driver
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.temp_midi: Path | None = None
        self.paused = False

    def _delete_temp(self, path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _process_alive(self) -> subprocess.Popen[bytes]:
        with self.lock:
            process = self.process
        if process is None or process.poll() is not None:
            raise RuntimeError("nothing is playing")
        return process

    def _suspend_windows_process(self, pid: int, suspend: bool) -> None:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            ]

        kernel32 = ctypes.windll.kernel32
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            raise OSError("cannot enumerate FluidSynth threads")
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(THREADENTRY32)
            ok = kernel32.Thread32First(snapshot, ctypes.byref(entry))
            touched = 0
            while ok:
                if entry.th32OwnerProcessID == pid:
                    handle = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                    if handle:
                        try:
                            if suspend:
                                result = kernel32.SuspendThread(handle)
                            else:
                                result = kernel32.ResumeThread(handle)
                            if result != 0xFFFFFFFF:
                                touched += 1
                        finally:
                            kernel32.CloseHandle(handle)
                ok = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
            if touched == 0:
                raise OSError("no FluidSynth thread could be controlled")
        finally:
            kernel32.CloseHandle(snapshot)

    def pause(self) -> None:
        process = self._process_alive()
        with self.lock:
            if self.paused:
                return
        if os.name == "nt":
            self._suspend_windows_process(process.pid, True)
        else:
            import signal
            os.kill(process.pid, signal.SIGSTOP)
        with self.lock:
            if self.process is process:
                self.paused = True

    def resume(self) -> None:
        process = self._process_alive()
        with self.lock:
            if not self.paused:
                return
        if os.name == "nt":
            self._suspend_windows_process(process.pid, False)
        else:
            import signal
            os.kill(process.pid, signal.SIGCONT)
        with self.lock:
            if self.process is process:
                self.paused = False

    def stop(self) -> None:
        with self.lock:
            process = self.process
            midi_path = self.temp_midi
            was_paused = self.paused
            self.process = None
            self.temp_midi = None
            self.paused = False

        if process is not None and process.poll() is None:
            if was_paused:
                try:
                    if os.name == "nt":
                        self._suspend_windows_process(process.pid, False)
                    else:
                        import signal
                        os.kill(process.pid, signal.SIGCONT)
                except Exception:
                    pass
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._delete_temp(midi_path)

    def _cleanup_after_exit(self, process: subprocess.Popen[bytes], midi_path: Path) -> None:
        process.wait()
        with self.lock:
            if self.process is process:
                self.process = None
                self.temp_midi = None
                self.paused = False
        self._delete_temp(midi_path)

    def play(self, midi_bytes: bytes) -> None:
        self.stop()
        with tempfile.NamedTemporaryFile(prefix="adx_compare_", suffix=".mid", delete=False) as fp:
            fp.write(midi_bytes)
            midi_path = Path(fp.name)

        command = [
            str(self.fluidsynth),
            "-a", self.audio_driver,
            "-ni",
            str(self.soundfont),
            str(midi_path),
        ]
        try:
            process = subprocess.Popen(command)
        except Exception:
            self._delete_temp(midi_path)
            raise

        with self.lock:
            self.process = process
            self.temp_midi = midi_path
            self.paused = False

        threading.Thread(
            target=self._cleanup_after_exit,
            args=(process, midi_path),
            daemon=True,
        ).start()

    def play_path(self, midi_path: Path) -> None:
        self.stop()
        command = [
            str(self.fluidsynth),
            "-a", self.audio_driver,
            "-ni",
            str(self.soundfont),
            str(midi_path),
        ]
        process = subprocess.Popen(command)
        with self.lock:
            self.process = process
            self.temp_midi = None
            self.paused = False

        def clear_after_exit() -> None:
            process.wait()
            with self.lock:
                if self.process is process:
                    self.process = None
                    self.paused = False

        threading.Thread(target=clear_after_exit, daemon=True).start()


def midi_duration_seconds(path: Path) -> float | None:
    if MidiFile is None:
        return None
    try:
        return max(0.0, float(MidiFile(path).length))
    except Exception:
        return None


class FileBrowser:
    """Read-only filesystem browser with opaque per-server IDs."""

    MIDI_SUFFIXES = {".mid", ".midi"}

    def __init__(self, start_directory: Path) -> None:
        self.start_directory = start_directory.resolve()
        self.secret = secrets.token_bytes(32)
        self.lock = threading.RLock()
        self.by_id: dict[str, Path] = {}
        self.root_id = "computer"
        self._remember(self.start_directory)

    def _id_for(self, path: Path, prefix: str) -> str:
        material = str(path).encode("utf-8", "surrogatepass")
        digest = hashlib.blake2s(material, key=self.secret, digest_size=12).hexdigest()
        return f"{prefix}-{digest}"

    def _remember(self, path: Path) -> str:
        resolved = path.resolve()
        prefix = "dir" if resolved.is_dir() else "midi"
        item_id = self._id_for(resolved, prefix)
        with self.lock:
            self.by_id[item_id] = resolved
        return item_id

    def _roots(self) -> list[Path]:
        if os.name == "nt":
            # GetLogicalDrives returns one bit per available drive and avoids
            # slow probing of A:..Z:, disconnected network drives, card readers, etc.
            try:
                import ctypes
                mask = int(ctypes.windll.kernel32.GetLogicalDrives())
            except Exception:
                mask = 0
            if mask:
                return [Path(f"{chr(65+i)}:\\") for i in range(26) if mask & (1 << i)]
            return [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
        return [Path("/")]

    def _is_hidden_directory(self, path: Path) -> bool:
        """Return True for OS-hidden directories without entering them."""
        if path.name.startswith("."):
            return True
        if os.name == "nt":
            try:
                import ctypes
                attrs = int(ctypes.windll.kernel32.GetFileAttributesW(str(path)))
                if attrs != -1 and (attrs & 0x2):  # FILE_ATTRIBUTE_HIDDEN
                    return True
            except Exception:
                pass
        return False

    def _safe_children(self, directory: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        folders, files = [], []
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except (PermissionError, OSError) as exc:
            raise PermissionError(f"Cannot read folder: {directory}") from exc
        for path in entries:
            try:
                if path.is_symlink():
                    continue
                if path.is_dir():
                    if self._is_hidden_directory(path):
                        continue
                    folders.append({"id": self._remember(path), "name": path.name or str(path)})
                    continue
                if not path.is_file() or path.suffix.lower() not in self.MIDI_SUFFIXES:
                    continue
                stat = path.stat()
                files.append({
                    "id": self._remember(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "duration_seconds": midi_duration_seconds(path),
                })
            except (PermissionError, OSError):
                continue
        return folders, files

    def browse(self, item_id: str | None) -> dict[str, object]:
        if item_id == "start":
            item_id = self._remember(self.start_directory)
        if not item_id or item_id == self.root_id:
            folders = []
            for root in self._roots():
                try:
                    if root.exists() and root.is_dir():
                        folders.append({"id": self._remember(root), "name": str(root)})
                except OSError:
                    continue
            return {"current_id": self.root_id, "parent_id": None, "display_path": "Computer" if os.name == "nt" else "/", "folders": folders, "files": []}

        with self.lock:
            directory = self.by_id.get(item_id)
        if directory is None or not item_id.startswith("dir-"):
            raise ValueError("unknown or expired folder ID")
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("folder is no longer available")
        folders, files = self._safe_children(directory)
        parent = directory.parent
        parent_id = self.root_id if parent == directory else self._remember(parent)
        return {"current_id": item_id, "parent_id": parent_id, "display_path": str(directory), "folders": folders, "files": files}

    def midi_files_in_start(self) -> list[dict[str, object]]:
        _folders, files = self._safe_children(self.start_directory)
        return files

    def resolve_midi(self, file_id: str) -> Path:
        if not isinstance(file_id, str) or not file_id.startswith("midi-"):
            raise ValueError("invalid MIDI file ID")
        with self.lock:
            path = self.by_id.get(file_id)
        if path is None:
            raise ValueError("unknown or expired MIDI file ID")
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in self.MIDI_SUFFIXES:
            raise ValueError("MIDI file is no longer available")
        return path.resolve()


def make_handler(player: PlayerState, directory: Path, browser: FileBrowser, report_selected: bool):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def _send_cors_headers(self) -> None:
            # PatternLab reports may be opened directly with file://. Browsers
            # represent such documents with the opaque Origin value "null".
            # Allow only that cross-origin case; reports served by this server
            # are same-origin and do not need CORS.
            if self.headers.get("Origin") == "null":
                self.send_header("Access-Control-Allow-Origin", "null")
                self.send_header("Vary", "Origin")

        def _send_text(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            # Preflight for file:// PatternLab -> localhost POST requests.
            path = urlparse(self.path).path
            if path not in {"/play", "/play-file", "/pause", "/resume", "/stop", "/api/midi-files", "/api/browse", "/api/status"}:
                self.send_error(404, "Not found")
                return
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def list_directory(self, path):
            # SimpleHTTPRequestHandler normally exposes a directory index.
            # PatternLab never needs that capability.
            self.send_error(403, "Directory listing is disabled")
            return None

        def send_head(self):
            # The generated report is self-contained. Serve HTML only; do not
            # turn the playback service into a general local-file web server.
            request_path = urlparse(self.path).path
            if request_path == "/" and not report_selected:
                body = NO_REPORT_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return None
            if request_path.endswith("/"):
                return self.list_directory(str(directory))
            suffix = Path(request_path).suffix.lower()
            if suffix not in {".html", ".htm"}:
                self.send_error(403, "Only PatternLab HTML reports are served")
                return None
            return super().send_head()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/status":
                self._send_json(200, {"status": "ready", "version": VERSION})
                return
            if path == "/api/midi-files":
                try:
                    self._send_json(200, {"files": browser.midi_files_in_start()})
                except Exception as exc:
                    self._send_json(500, {"error": str(exc)})
                return
            if path == "/api/browse":
                try:
                    query = parse_qs(urlparse(self.path).query)
                    item_id = query.get("id", [None])[0]
                    self._send_json(200, browser.browse(item_id))
                except PermissionError as exc:
                    self._send_json(403, {"error": str(exc)})
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"error": str(exc)})
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/pause":
                try:
                    player.pause()
                    self._send_text(200, "Paused")
                except Exception as exc:
                    self._send_text(409, f"Pause failed: {exc}")
                return

            if path == "/resume":
                try:
                    player.resume()
                    self._send_text(200, "Resumed")
                except Exception as exc:
                    self._send_text(409, f"Resume failed: {exc}")
                return

            if path == "/stop":
                player.stop()
                self._send_text(200, "Stopped")
                return

            if path == "/play-file":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 65536:
                        raise ValueError("invalid request size")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    file_id = payload.get("id") if isinstance(payload, dict) else None
                    if not isinstance(file_id, str) or not file_id:
                        raise ValueError("missing MIDI file ID")
                    midi_path = browser.resolve_midi(file_id)
                    player.play_path(midi_path)
                    self._send_json(200, {
                        "status": "playing",
                        "id": file_id,
                        "name": midi_path.name,
                        "duration_seconds": midi_duration_seconds(midi_path),
                    })
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"error": f"Playback failed: {exc}"})
                return

            if path != "/play":
                self._send_text(404, "Not found")
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_text(400, "Invalid Content-Length")
                return
            if not 1 <= length <= MAX_MIDI_BYTES:
                self._send_text(400, "Invalid MIDI data size")
                return

            midi_bytes = self.rfile.read(length)
            if len(midi_bytes) != length:
                self._send_text(400, "Incomplete MIDI data")
                return
            if not midi_bytes.startswith(b"MThd"):
                self._send_text(400, "Not a Standard MIDI File")
                return

            try:
                player.play(midi_bytes)
            except Exception as exc:
                self._send_text(500, f"Playback failed: {exc}")
                return
            self._send_text(200, "Playing with FluidSynth")

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[PatternLab] {self.address_string()} - {fmt % args}")

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
    browser_start = directory if report_path is not None else Path.home().resolve()
    browser = FileBrowser(browser_start)
    handler = make_handler(player, directory, browser, report_selected=report_path is not None)
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
