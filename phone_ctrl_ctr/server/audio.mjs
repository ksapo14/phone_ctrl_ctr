import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';
import { childEnvironment } from './environment.mjs';

export class WindowsAudioSink {
  constructor() {
    this.closed = false;
    this.child = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
      fileURLToPath(new URL('./audio.ps1', import.meta.url)), '-DeviceName', process.env.PHONE_AUDIO_DEVICE || 'CABLE Input'],
    { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: childEnvironment() });
    this.ready = new Promise((resolve, reject) => {
      let output = '', errors = '';
      const fail = error => { clearTimeout(timer); reject(error); this.onError?.(error); };
      const timer = setTimeout(() => { fail(new Error('Audio helper took too long to start.')); this.close(); }, 15000);
      this.child.stdout.on('data', chunk => { output = (output + chunk).slice(-1024); if (output.includes('READY')) { clearTimeout(timer); resolve(); } });
      this.child.stderr.on('data', chunk => { errors = (errors + chunk).slice(-2048); });
      this.child.on('error', fail);
      this.child.stdin.on('error', error => { if (!this.closed) fail(error); });
      this.child.on('exit', () => { clearTimeout(timer); if (!this.closed) fail(new Error(errors.trim() || 'The Windows audio device disconnected.')); else reject(new Error('Audio stopped.')); });
    });
  }
  write(frame) {
    if (this.closed || this.child.stdin.writableLength > 7680) throw new Error('Audio connection is too slow. Reconnect the phone microphone.');
    this.child.stdin.write(frame);
  }
  close() {
    if (this.closed) return;
    this.closed = true; this.child.stdin.end();
    const timer = setTimeout(() => this.child.kill(), 1000); timer.unref();
    this.child.once('exit', () => clearTimeout(timer));
  }
}

export function createAudioRelay({ authorize, sinkFactory = () => new WindowsAudioSink() }) {
  const wss = new WebSocketServer({ noServer: true, maxPayload: 1920, perMessageDeflate: false });
  let active = null;
  const stop = () => { if (active) { active.cleanup(); active.ws.close(4000, 'Audio stopped'); active = null; } };
  wss.on('connection', (ws, req, owner) => {
    stop();
    let sink, ready = false, stopped = false, lastFrame = Date.now(), count = 0, windowStart = Date.now();
    const cleanup = () => { if (stopped) return; stopped = true; clearInterval(timer); sink?.close(); };
    const fail = message => { if (stopped) return; ws.send(JSON.stringify({ type: 'error', error: message })); cleanup(); ws.close(4000, 'Audio stopped'); };
    const timer = setInterval(() => { if (authorize(req) !== owner || (ready && Date.now() - lastFrame > 5000)) fail('Microphone connection expired or stopped sending audio.'); }, 1000);
    active = { ws, cleanup };
    ws.on('close', () => { cleanup(); if (active?.ws === ws) active = null; });
    ws.on('error', cleanup);
    ws.on('message', (bytes, binary) => {
      if (!ready || stopped) return;
      if (authorize(req) !== owner) return fail('Phone control session ended.');
      if (Date.now() - windowStart > 1000) { count = 0; windowStart = Date.now(); }
      if (!binary || bytes.length !== 1920 || ++count > 100) return fail('Invalid microphone audio format or rate.');
      lastFrame = Date.now();
      try { sink.write(bytes); } catch (error) { fail(error.message); }
    });
    try {
      sink = sinkFactory(); sink.onError = error => fail(error.message);
      Promise.resolve(sink.ready).then(() => { if (stopped) return; ready = true; lastFrame = Date.now(); ws.send(JSON.stringify({ type: 'ready', sampleRate: 48000 })); }).catch(error => fail(error.message));
    } catch (error) { fail(error.message); }
  });
  return { stop, upgrade(req, socket, head) {
    const owner = authorize(req);
    if (!owner) { socket.end('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n'); return; }
    wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws, req, owner));
  }, close() { stop(); for (const ws of wss.clients) ws.terminate(); wss.close(); } };
}
