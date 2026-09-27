import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFileSync } from 'node:fs';
import https from 'node:https';
import vm from 'node:vm';
import { WebSocket } from 'ws';
import { startServer } from './index.mjs';
import { MockBridge } from './bridge.mjs';

test('HTTPS microphone: pairing, authorization, PCM forwarding, takeover and revocation', async t => {
  // Public test-only key/cert. Never trusted system-wide or used by the real companion.
  const cert = readFileSync(new URL('./fixtures/audio-test-cert.pem', import.meta.url));
  const key = readFileSync(new URL('./fixtures/audio-test-key.pem', import.meta.url));
  const sinks = [];
  const app = await startServer({ port: 0, host: '127.0.0.1', bridge: new MockBridge(), openBrowser: false, tls: { cert, key },
    audioSinkFactory: () => { const sink = { ready: Promise.resolve(), frames: [], closed: false, write(frame) { this.frames.push(frame); }, close() { this.closed = true; } }; sinks.push(sink); return sink; } });
  t.after(() => app.close());
  const base = `https://127.0.0.1:${app.port}`;
  const request = (path, body, cookie) => new Promise((resolve, reject) => {
    const req = https.request(base + path, { ca: cert, method: body ? 'POST' : 'GET', headers: { Origin: base, 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) } }, res => {
      let data = ''; res.on('data', chunk => { data += chunk; }); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, data: JSON.parse(data) }));
    }); req.on('error', reject); req.end(body ? JSON.stringify(body) : undefined);
  });
  const unlock = await request('/api/admin/unlock', { key: app.adminKey });
  assert.match(unlock.headers['set-cookie'][0], /Secure/);
  const admin = unlock.headers['set-cookie'][0].split(';')[0];
  const status = await request('/api/admin/status', undefined, admin);
  assert.ok(status.data.urls.every(url => url.startsWith('https:')));
  const paired = await request('/api/pair', { code: status.data.code });
  const cookie = paired.headers['set-cookie'][0].split(';')[0];
  assert.match(paired.headers['set-cookie'][0], /Secure/);
  const open = (path, options = {}) => new WebSocket(`wss://127.0.0.1:${app.port}${path}`, { ca: cert, origin: base, headers: { Cookie: cookie }, ...options });
  const unowned = open('/audio'); assert.match((await once(unowned, 'error'))[0].message, /401/);
  const control = open('/control'); await once(control, 'open');
  const foreign = open('/audio', { origin: 'https://evil.example' }); assert.match((await once(foreign, 'error'))[0].message, /401/);
  const audio = open('/audio'); const ready = once(audio, 'message'); await once(audio, 'open');
  assert.equal(JSON.parse((await ready)[0]).type, 'ready');
  audio.send(Buffer.alloc(1920, 12));
  // A ping is processed after the preceding data frame.
  const pong = once(audio, 'pong'); audio.ping(); await pong;
  assert.equal(sinks[0].frames.length, 1); assert.equal(sinks[0].frames[0].length, 1920);
  const ended = once(audio, 'close'); const replaced = once(control, 'close');
  const replacement = open('/control'); await once(replacement, 'open'); await ended; await replaced;
  assert.equal(sinks[0].closed, true);
  const invalid = open('/audio'); const invalidReady = once(invalid, 'message'); await invalidReady;
  const invalidClose = once(invalid, 'close'); invalid.send(Buffer.alloc(8)); await invalidClose;
  assert.equal(sinks[1].closed, true);
  const revoked = open('/audio'); await once(revoked, 'message');
  const revokedClose = once(revoked, 'close'); await request('/api/admin/reset', {}, admin); await revokedClose;
  assert.equal(sinks[2].closed, true);
});

test('worklet produces bounded little-endian mono PCM frames at 48k and 44.1k', () => {
  for (const rate of [48000, 44100]) {
    let Processor; const frames = [];
    const context = { AudioWorkletProcessor: class { constructor() { this.port = { postMessage: frame => frames.push(frame) }; } }, sampleRate: rate,
      registerProcessor: (_name, ctor) => { Processor = ctor; } };
    vm.runInNewContext(readFileSync(new URL('../public/phone-mic-worklet.js', import.meta.url), 'utf8'), context);
    const processor = new Processor();
    for (let i = 0; i < rate; i += 128) processor.process([[new Float32Array(Math.min(128, rate - i)).fill(-1)]]);
    assert.ok(frames.length >= 49 && frames.length <= 50);
    for (const frame of frames) { assert.equal(frame.byteLength, 1920); assert.equal(new DataView(frame).getInt16(0, true), -32768); }
  }
});
