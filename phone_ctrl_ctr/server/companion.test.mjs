import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { startServer, reuseCompanion } from './index.mjs';
import { MockBridge } from './bridge.mjs';
import { validateCommand } from './protocol.mjs';
import { readFileSync } from 'node:fs';
import { parseToolCalls } from './command-router.mjs';

test('pairing, authenticated controls, invalid commands, takeover and revocation', async t => {
  const bridge = new MockBridge();
  const app = await startServer({ port: 0, host: '127.0.0.1', bridge, openBrowser: false });
  t.after(() => app.close());
  const base = `http://127.0.0.1:${app.port}`;
  const post = (path, data, cookie, origin = base) => fetch(base + path, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) }, body: JSON.stringify(data) });
  assert.equal((await fetch(base + '/api/admin/status')).status, 403);
  assert.equal((await post('/api/admin/unlock', { key: app.adminKey }, null, 'http://evil.example')).status, 403);
  const unlocked = await post('/api/admin/unlock', { key: app.adminKey });
  const adminCookie = unlocked.headers.get('set-cookie').split(';')[0];
  const status = await (await fetch(base + '/api/admin/status', { headers: { Cookie: adminCookie } })).json();
  assert.match(status.code, /^\d{6}$/); assert.match(status.qr, /^data:image\/png;base64,/);
  assert.equal((await post('/api/pair', { code: '000000' })).status, 401);
  const pair = await post('/api/pair', { code: status.code }); assert.equal(pair.status, 200);
  const phoneCookie = pair.headers.get('set-cookie').split(';')[0];
  assert.match(pair.headers.get('set-cookie'), /HttpOnly/);
  assert.equal((await post('/api/pair', { code: status.code })).status, 401, 'pairing secret is single-use');
  assert.equal((await (await fetch(base + '/api/session', { headers: { Cookie: phoneCookie } })).json()).paired, true);
  const unauthorized = new WebSocket(`ws://127.0.0.1:${app.port}/control`, { origin: base });
  const [error] = await once(unauthorized, 'error'); assert.match(error.message, /401/);
  const crossOrigin = new WebSocket(`ws://127.0.0.1:${app.port}/control`, { origin: 'http://evil.example', headers: { Cookie: phoneCookie } });
  const [originError] = await once(crossOrigin, 'error'); assert.match(originError.message, /401/);
  const ws = new WebSocket(`ws://127.0.0.1:${app.port}/control`, { origin: base, headers: { Cookie: phoneCookie } });
  await once(ws, 'open');
  const reply = id => new Promise(resolve => { const handler = data => { const packet = JSON.parse(data); if (packet.id === id) { ws.off('message', handler); resolve(packet); } }; ws.on('message', handler); });
  let response = reply(1); ws.send(JSON.stringify({ id: 1, command: { type: 'volume', value: 64 } })); assert.equal((await response).type, 'ack'); assert.equal(bridge.volume, 64);
  response = reply(2); ws.send(JSON.stringify({ id: 2, command: { type: 'launch', app: 'powershell -Command whoami' } })); assert.equal((await response).type, 'error'); assert.equal(bridge.commands.some(c => c.app?.includes('powershell')), false);
  response = reply(3); ws.send(JSON.stringify({ id: 3, command: { type: 'button', button: 'left', down: true } })); await response;
  for (const [id, command] of [[4, { type: 'button', button: 'x1', down: true }], [5, { type: 'button', button: 'x1', down: false }], [6, { type: 'doubleClick', button: 'x1' }], [7, { type: 'media', action: 'playPause' }]]) {
    response = reply(id); ws.send(JSON.stringify({ id, command }));
    assert.equal((await response).type, 'ack'); assert.deepEqual(bridge.commands.at(-1), command);
  }
  const replaced = once(ws, 'close');
  const replacement = new WebSocket(`ws://127.0.0.1:${app.port}/control`, { origin: base, headers: { Cookie: phoneCookie } });
  await once(replacement, 'open'); assert.equal((await replaced)[0], 4002);
  const closed = once(replacement, 'close'); await post('/api/admin/reset', {}, adminCookie); assert.equal((await closed)[0], 4001);
  assert.equal((await (await fetch(base + '/api/session', { headers: { Cookie: phoneCookie } })).json()).paired, false);
  assert.equal(bridge.commands.at(-1).type, 'release');
  let limited;
  for (let i = 0; i < 10; i++) limited = await post('/api/pair', { code: '000000' });
  assert.equal(limited.status, 429);
});

test('strict input bounds reject unsafe or unsupported input', () => {
  for (const command of [null, [], { type: 'shell', command: 'calc' }, { type: 'volume', value: 101 }, { type: 'brightness', value: -1 }, { type: 'move', dx: NaN, dy: 1 }, { type: 'focus', id: '12;cmd' }, { type: 'gesture', name: 'arbitrary' }]) assert.equal(validateCommand(command), false);
  assert.equal(validateCommand({ type: 'launch', app: 'cmd' }), true);
  assert.equal(validateCommand({ type: 'move', dx: -100, dy: 100 }), true);
  assert.equal(validateCommand({ type: 'doubleClick', button: 'x1' }), true);
  assert.equal(validateCommand({ type: 'doubleClick', button: 'left' }), false);
  assert.equal(validateCommand({ type: 'button', button: 'x1', down: 'true' }), false);
  assert.equal(validateCommand({ type: 'button', button: 'x2', down: true }), false);
  assert.equal(validateCommand({ type: 'media', action: 'playPause' }), true);
  assert.equal(validateCommand({ type: 'media', action: 'arbitrary' }), false);
});

test('bundled model smoke outputs map to accepted companion commands', () => {
  const rows = JSON.parse(readFileSync(new URL('./fixtures/functiongemma-smoke-outputs.json', import.meta.url), 'utf8'));
  for (const row of rows) for (const command of parseToolCalls(row.output)) assert.equal(validateCommand(command), true, row.prompt);
});

test('relaunch reuses the companion and cannot expose its admin key to browser requests', async t => {
  const opened = [];
  const app = await startServer({ port: 0, host: '127.0.0.1', bridge: new MockBridge(), openBrowser: false, launchBrowser: url => opened.push(url) });
  t.after(() => app.close());
  assert.equal(await reuseCompanion(app.port), true);
  assert.equal(opened.length, 1);
  assert.equal(opened[0], `http://localhost:${app.port}/host#admin=${app.adminKey}`);
  const response = await fetch(`http://127.0.0.1:${app.port}/api/companion/open`, { method: 'POST', headers: { Origin: `http://127.0.0.1:${app.port}`, 'X-Phone-Control-Launcher': '1' } });
  assert.equal(response.status, 403);
  assert.equal(opened.length, 1);
  let closed = false;
  const duplicateBridge = new MockBridge(); duplicateBridge.close = async () => { closed = true; };
  await assert.rejects(startServer({ port: app.port, host: '127.0.0.1', bridge: duplicateBridge, openBrowser: false }), { code: 'EADDRINUSE' });
  assert.equal(closed, true, 'failed startup cleans up its helper');
});
