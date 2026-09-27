import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { parseToolCalls, FunctionGemmaRouter } from './command-router.mjs';
import { startServer } from './index.mjs';
import { MockBridge } from './bridge.mjs';
import { childEnvironment } from './environment.mjs';

test('child processes do not inherit the Deepgram credential', () => {
  const environment = { DEEPGRAM_API_KEY: 'test-value', deepgram_api_key: 'test-value', Path: 'test-path', PHONE_PYTHON: 'python' };
  assert.deepEqual(childEnvironment(environment), { Path: 'test-path', PHONE_PYTHON: 'python' });
  assert.equal(environment.DEEPGRAM_API_KEY, 'test-value');
});

test('early commands wait for one shared warm-up and later commands reuse it', async () => {
  const router = new FunctionGemmaRouter();
  const requests = [];
  let finishWarmup;
  router.request = text => {
    requests.push(text);
    if (requests.length === 1) return new Promise(resolve => { finishWarmup = resolve; });
    return Promise.resolve('<start_function_call>call:set_volume{level:47}<end_function_call>');
  };
  const ready = router.warmup();
  assert.equal(router.warmup(), ready);
  const early = router.route('Set volume to 47');
  await Promise.resolve();
  assert.deepEqual(requests, ['Set volume to 50']);
  finishWarmup('<start_function_call>call:set_volume{level:50}<end_function_call>');
  assert.deepEqual(await early, [{ type: 'volume', value: 47 }]);
  await router.route('Volume 47');
  assert.deepEqual(requests, ['Set volume to 50', 'Set volume to 47', 'Volume 47']);
});

test('companion primes the router on startup without dispatching a desktop action', async t => {
  const bridge = new MockBridge();
  let warmed = false;
  const app = await startServer({ port: 0, host: '127.0.0.1', bridge, openBrowser: false, warmModel: true,
    commandRouter: { async warmup() { warmed = true; }, close() {} } });
  t.after(() => app.close());
  assert.equal(warmed, true);
  assert.ok(bridge.commands.every(command => command.type === 'state'));
});

test('model calls accept only supported values and ignore generated response noise', () => {
  assert.deepEqual(parseToolCalls('<start_function_call>call:start_app{app:<escape>file_explorer<escape>}<end_function_call><start_function_call>call:open_website{site:<escape>youtube<escape>}<end_function_call><start_function_response>call:set_volume{level:99}<end_function_call>'), [{ type: 'launch', app: 'explorer' }, { type: 'website', site: 'youtube' }]);
  for (const output of ['<start_function_call>call:set_volume{level:101}<end_function_call>', '<start_function_call>call:start_app{app:<escape>powershell<escape>}<end_function_call>', '<start_function_call>call:open_website{site:<escape>evil.example<escape>}<end_function_call>', 'hello']) assert.throws(() => parseToolCalls(output));
});

test('paired controller can run typed and transcribed commands; outsiders cannot', async t => {
  const bridge = new MockBridge();
  const routed = [];
  let finishRoute, markRouteStarted;
  const routeStarted = new Promise(resolve => { markRouteStarted = resolve; });
  const app = await startServer({ port: 0, host: '127.0.0.1', bridge, openBrowser: false,
    commandRouter: { async route(text) {
      routed.push(text);
      if (text === 'delayed') {
        markRouteStarted(); await new Promise(resolve => { finishRoute = resolve; });
        return [{ type: 'volume', value: 90 }];
      }
      return text === 'volume 41' ? [{ type: 'volume', value: 41 }] : [{ type: 'website', site: 'github' }];
    }, close() {} },
    transcribe: async (audio, type) => { assert.equal(type, 'audio/webm'); assert.ok(audio.length > 100); return 'open github'; } });
  t.after(() => app.close());
  const base = `http://127.0.0.1:${app.port}`;
  const post = (path, body, cookie, type = 'application/json', origin = base) => fetch(base + path, { method: 'POST', headers: { Origin: origin, 'Content-Type': type, ...(cookie ? { Cookie: cookie } : {}) }, body });
  const unlock = await post('/api/admin/unlock', JSON.stringify({ key: app.adminKey }));
  const status = await (await fetch(base + '/api/admin/status', { headers: { Cookie: unlock.headers.get('set-cookie').split(';')[0] } })).json();
  const pair = await post('/api/pair', JSON.stringify({ code: status.code }));
  const cookie = pair.headers.get('set-cookie').split(';')[0];
  assert.equal((await post('/api/commands/text', JSON.stringify({ text: 'volume 41' }))).status, 401);
  const ws = new WebSocket(`${base.replace('http', 'ws')}/control`, { origin: base, headers: { Cookie: cookie } });
  await once(ws, 'open'); t.after(() => ws.close());
  assert.equal((await post('/api/commands/text', JSON.stringify({ text: 'volume 41' }), cookie, 'application/json', 'http://evil.example')).status, 403);
  const typed = await post('/api/commands/text', JSON.stringify({ text: 'volume 41' }), cookie);
  assert.equal(typed.status, 200); assert.equal(bridge.volume, 41);
  assert.deepEqual((await typed.json()).commands, [{ type: 'volume', value: 41 }]);
  const audio = await post('/api/commands/audio', Buffer.alloc(256), cookie, 'audio/webm');
  assert.equal(audio.status, 200); assert.equal((await audio.json()).transcript, 'open github');
  assert.deepEqual(routed, ['volume 41', 'open github']);
  assert.deepEqual(bridge.commands.filter(command => command.type === 'website'), [{ type: 'website', site: 'github' }]);
  const delayed = post('/api/commands/text', JSON.stringify({ text: 'delayed' }), cookie);
  await routeStarted;
  const replacement = new WebSocket(`${base.replace('http', 'ws')}/control`, { origin: base, headers: { Cookie: cookie } });
  await once(replacement, 'open'); t.after(() => replacement.close());
  finishRoute();
  assert.equal((await delayed).status, 400);
  assert.equal(bridge.volume, 41, 'takeover cancels pending commands even when the replacement shares the cookie');
});
