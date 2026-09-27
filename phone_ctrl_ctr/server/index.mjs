import http from 'node:http';
import https from 'node:https';
import { randomBytes, randomInt, timingSafeEqual } from 'node:crypto';
import { networkInterfaces } from 'node:os';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { WebSocketServer } from 'ws';
import QRCode from 'qrcode';
import { WindowsBridge, MockBridge } from './bridge.mjs';
import { validateCommand } from './protocol.mjs';
import { createAudioRelay } from './audio.mjs';
import { FunctionGemmaRouter } from './command-router.mjs';
import { transcribeDeepgram } from './deepgram.mjs';
import { loadLocalEnvironment, childEnvironment } from './environment.mjs';

loadLocalEnvironment();

const secret = () => randomBytes(32).toString('hex');
const equal = (a, b) => typeof a === 'string' && typeof b === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));
const loopback = address => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address);
const cookie = (req, name) => (req.headers.cookie || '').split(';').map(v => v.trim()).find(v => v.startsWith(name + '='))?.slice(name.length + 1);
const root = fileURLToPath(new URL('../dist', import.meta.url));

export async function startServer({ port = Number(process.env.PORT || 8787), host = '0.0.0.0', bridge, openBrowser = true, launchBrowser, tls, audioSinkFactory, commandRouter = new FunctionGemmaRouter(), transcribe = transcribeDeepgram, warmModel = !(bridge instanceof MockBridge) } = {}) {
  if (!tls && (process.env.PHONE_TLS_CERT || process.env.PHONE_TLS_KEY)) {
    if (!process.env.PHONE_TLS_CERT || !process.env.PHONE_TLS_KEY) throw new Error('Set both PHONE_TLS_CERT and PHONE_TLS_KEY.');
    tls = { cert: await readFile(process.env.PHONE_TLS_CERT), key: await readFile(process.env.PHONE_TLS_KEY) };
  }
  const scheme = tls ? 'https' : 'http';
  const secureCookie = tls ? '; Secure' : '';
  const adminKey = secret(); const adminSession = secret(); let pairing;
  let requests = 0; let lastOpen = 0; let controller = null; let state = null; let nativeError = null;
  const sessions = new Map(); const attempts = new Map(); const sockets = new Set();
  const commandAttempts = new Map(); let commandBusy = false;
  const addresses = Object.values(networkInterfaces()).flat().filter(n => n && n.family === 'IPv4' && !n.internal).map(n => n.address);
  if (process.env.PHONE_HOST && /^[a-zA-Z0-9.:-]+$/.test(process.env.PHONE_HOST)) addresses.unshift(process.env.PHONE_HOST);
  const hosts = new Set(['localhost', '127.0.0.1', '[::1]', ...addresses]);
  let actualPort = port;
  function rotatePairing() { pairing = { token: secret(), code: String(randomInt(100000, 1000000)), expires: Date.now() + 300000 }; }
  rotatePairing();
  function originAllowed(req) {
    try { const url = new URL(req.headers.origin); return url.protocol === scheme + ':' && hosts.has(url.hostname) && Number(url.port || (tls ? 443 : 80)) === actualPort; } catch { return false; }
  }
  function hostAllowed(req) {
    try { const url = new URL(scheme + '://' + req.headers.host); return hosts.has(url.hostname) && Number(url.port || (tls ? 443 : 80)) === actualPort; } catch { return false; }
  }
  function isAdmin(req) { return loopback(req.socket.remoteAddress) && equal(cookie(req, 'pc_admin'), adminSession); }
  function authenticated(req) { const id = cookie(req, 'pc_phone'); const expiry = sessions.get(id); return expiry && expiry > Date.now() ? id : null; }
  function rateLimit(req, limit = 8) {
    const now = Date.now(); const key = req.socket.remoteAddress;
    let entry = attempts.get(key); if (!entry || now > entry.until) { entry = { count: 0, until: now + 60000 }; attempts.set(key, entry); }
    return ++entry.count <= limit;
  }
  async function body(req) { let text = ''; for await (const chunk of req) { text += chunk; if (text.length > 4096) throw new Error('Request too large'); } return JSON.parse(text || '{}'); }
  async function audioBody(req) {
    const chunks = []; let size = 0;
    for await (const chunk of req) { size += chunk.length; if (size > 5 * 1024 * 1024) throw new Error('Recording is too large. Keep commands under 15 seconds.'); chunks.push(chunk); }
    if (size < 100) throw new Error('No microphone audio was recorded.');
    return Buffer.concat(chunks);
  }
  function json(res, status, data, cookies) { res.writeHead(status, { 'Content-Type': 'application/json', ...(cookies ? { 'Set-Cookie': cookies } : {}) }); res.end(JSON.stringify(data)); }
  function openHost(force = false) {
    if (!force && (!openBrowser || Date.now() - lastOpen < 60000)) return;
    lastOpen = Date.now();
    const url = `${scheme}://localhost:${actualPort}/host#admin=${adminKey}`;
    if (launchBrowser) { launchBrowser(url); return; }
    const child = spawn('explorer.exe', [url], { windowsHide: true, stdio: 'ignore', env: childEnvironment() }); child.on('error', () => {}); child.unref();
  }
  function broadcast(message) { const data = JSON.stringify(message); for (const ws of sockets) if (ws.readyState === 1) ws.send(data); }
  async function refresh() {
    try { state = await bridge.request({ type: 'state' }); nativeError = null; broadcast({ type: 'state', state }); }
    catch (e) { nativeError = e.message; broadcast({ type: 'error', error: nativeError }); }
  }
  const handler = async (req, res) => {
    res.setHeader('Cache-Control', 'no-store'); res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Permissions-Policy', 'microphone=(self), camera=()');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    try {
      if (!hostAllowed(req)) return json(res, 403, { error: 'Unrecognized host' });
      const path = new URL(req.url, 'http://localhost').pathname;
      if (path === '/api/companion' && req.method === 'GET') {
        if (!loopback(req.socket.remoteAddress)) return json(res, 403, { error: 'Local launcher only' });
        return json(res, 200, { service: 'phone-control-companion', version: 1 });
      }
      if (path === '/api/companion/open' && req.method === 'POST') {
        // Only a local, non-browser launcher may ask us to open the existing
        // dashboard. No pairing or admin secrets are returned over this API.
        if (!loopback(req.socket.remoteAddress) || req.headers.origin || req.headers['sec-fetch-site'] || req.headers['x-phone-control-launcher'] !== '1') return json(res, 403, { error: 'Local launcher only' });
        openHost(true);
        return json(res, 200, { ok: true });
      }
      if (req.method !== 'GET' && !originAllowed(req)) return json(res, 403, { error: 'Invalid origin' });
      if (path === '/api/admin/unlock' && req.method === 'POST') {
        if (!loopback(req.socket.remoteAddress) || !equal((await body(req)).key, adminKey)) return json(res, 403, { error: 'Open the companion link on the computer.' });
        return json(res, 200, { ok: true }, `pc_admin=${adminSession}; HttpOnly; SameSite=Strict; Path=/api/admin${secureCookie}`);
      }
      if (path.startsWith('/api/admin/')) {
        if (!isAdmin(req)) return json(res, 403, { error: 'Open the companion link printed in the server terminal.' });
        if (path === '/api/admin/reset' && req.method === 'POST') {
          sessions.clear(); audio.stop(); for (const ws of sockets) ws.close(4001, 'Access revoked'); rotatePairing(); requests = 0;
          await bridge.request({ type: 'release' }); return json(res, 200, { ok: true });
        }
        if (path === '/api/admin/status' && req.method === 'GET') {
          if (Date.now() > pairing.expires) rotatePairing();
          const urls = [...new Set(addresses)].map(ip => `${scheme}://${ip}:${actualPort}`);
          if (!urls.length) urls.push(`${scheme}://localhost:${actualPort}`);
          const requested = new URL(req.url, 'http://localhost').searchParams.get('base');
          const base = urls.includes(requested) ? requested : urls[0];
          return json(res, 200, { urls, base, qr: await QRCode.toDataURL(`${base}/#pair=${pairing.token}`, { margin: 2, width: 300 }), code: pairing.code, expires: pairing.expires, connected: sockets.size, requests, nativeError, ready: Boolean(state), apps: state?.apps || [] });
        }
        return json(res, 404, { error: 'Not found' });
      }
      if (path === '/api/pair/request' && req.method === 'POST') {
        if (!rateLimit(req, 12)) return json(res, 429, { error: 'Wait a minute before trying again.' });
        requests++; openHost(); return json(res, 200, { ok: true });
      }
      if (path === '/api/pair' && req.method === 'POST') {
        if (!rateLimit(req)) return json(res, 429, { error: 'Too many attempts. Wait a minute.' });
        const data = await body(req);
        if (Date.now() > pairing.expires || !(equal(data.token, pairing.token) || equal(data.code, pairing.code))) return json(res, 401, { error: 'The pairing code expired or is incorrect. Check the computer.' });
        const id = secret(); sessions.set(id, Date.now() + 8 * 60 * 60 * 1000); rotatePairing(); requests = 0;
        return json(res, 200, { ok: true }, `pc_phone=${id}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800${secureCookie}`);
      }
      if (path === '/api/session' && req.method === 'GET') return json(res, 200, { paired: Boolean(authenticated(req)) });
      if (path === '/api/logout' && req.method === 'POST') {
        const id = authenticated(req); sessions.delete(id); if (controller?.session === id) audio.stop(); for (const ws of sockets) if (ws.session === id) ws.close(4001, 'Unpaired');
        return json(res, 200, { ok: true }, 'pc_phone=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' + secureCookie);
      }
      if ((path === '/api/commands/text' || path === '/api/commands/audio') && req.method === 'POST') {
        const session = authenticated(req);
        if (!session || controller?.session !== session || controller.readyState !== 1) return json(res, 401, { error: 'Connect the paired phone before sending commands.' });
        const requestingController = controller;
        const now = Date.now(); const attempt = commandAttempts.get(session) || { count: 0, until: now + 60000 };
        if (now > attempt.until) { attempt.count = 0; attempt.until = now + 60000; }
        commandAttempts.set(session, attempt);
        if (++attempt.count > 12) return json(res, 429, { error: 'Too many commands. Wait a minute.' });
        if (commandBusy) return json(res, 429, { error: 'A command is already being processed.' });
        commandBusy = true;
        try {
          let text;
          if (path.endsWith('/text')) text = (await body(req)).text;
          else {
            const type = req.headers['content-type']?.split(';')[0]?.toLowerCase();
            if (!['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav'].includes(type)) throw new Error('Unsupported microphone recording format.');
            text = await transcribe(await audioBody(req), type);
          }
          if (typeof text !== 'string' || !text.trim() || text.length > 240) throw new Error('Enter or speak a short command.');
          text = text.trim();
          const commands = await commandRouter.route(text);
          if (!Array.isArray(commands) || !commands.length || commands.length > 4 || commands.some(command => !validateCommand(command))) throw new Error('The command model returned an unsupported action.');
          for (const command of commands) {
            if (authenticated(req) !== session || controller !== requestingController || controller.readyState !== 1) throw new Error('The phone disconnected before the command ran.');
            await bridge.request(command);
          }
          await refresh();
          return json(res, 200, { transcript: text, commands });
        } catch (error) { return json(res, 400, { error: error.message || 'Command failed.' }); }
        finally { commandBusy = false; }
      }
      if (path.startsWith('/api/')) return json(res, 404, { error: 'Not found' });
      if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed' });
      const filename = path === '/' || path === '/host' ? 'index.html' : decodeURIComponent(path).slice(1);
      const file = resolve(root, filename);
      if (!file.startsWith(root + sep)) return json(res, 404, { error: 'Not found' });
      if (!(await stat(file)).isFile()) return json(res, 404, { error: 'Not found' });
      const contentTypes = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };
      res.setHeader('Content-Type', contentTypes[extname(file)] || 'application/octet-stream'); res.end(await readFile(file));
    } catch (e) { if (!res.headersSent) json(res, e.code === 'ENOENT' ? 404 : 400, { error: e.code === 'ENOENT' ? 'Build the phone UI with npm run build.' : 'Invalid request.' }); else res.end(); }
  };
  const server = tls ? https.createServer(tls, handler) : http.createServer(handler);
  const audio = createAudioRelay({ sinkFactory: audioSinkFactory, authorize: req => {
    const session = authenticated(req);
    return hostAllowed(req) && originAllowed(req) && (tls || loopback(req.socket.remoteAddress)) && session && controller?.session === session && controller.readyState === 1 ? controller : null;
  } });
  const wss = new WebSocketServer({ noServer: true, maxPayload: 4096, perMessageDeflate: false });
  server.on('upgrade', (req, socket, head) => {
    if (req.url === '/audio') { audio.upgrade(req, socket, head); return; }
    const session = authenticated(req);
    if (req.url !== '/control' || !hostAllowed(req) || !originAllowed(req) || !session) { socket.end('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n'); return; }
    wss.handleUpgrade(req, socket, head, ws => { ws.session = session; wss.emit('connection', ws); });
  });
  wss.on('connection', ws => {
    audio.stop();
    if (controller) controller.close(4002, 'Another controller connected');
    controller = ws; sockets.add(ws); ws.alive = true;
    void bridge.request({ type: 'release' }).catch(() => {});
    if (state) ws.send(JSON.stringify({ type: 'state', state }));
    if (nativeError) ws.send(JSON.stringify({ type: 'error', error: nativeError }));
    let count = 0, windowStart = Date.now(), pending = 0;
    ws.on('pong', () => { ws.alive = true; });
    ws.on('message', async bytes => {
      let packet;
      try {
        if (controller !== ws || (sessions.get(ws.session) || 0) < Date.now()) { ws.close(4001, 'Session expired'); return; }
        if (Date.now() - windowStart > 1000) { count = 0; windowStart = Date.now(); }
        if (++count > 150 || pending > 80) throw new Error('Too much input.');
        packet = JSON.parse(bytes.toString());
        if (!Number.isSafeInteger(packet.id) || !validateCommand(packet.command)) throw new Error('Invalid command.');
        pending++;
        const result = await bridge.request(packet.command);
        if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'ack', id: packet.id, result }));
      } catch (e) { if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'error', id: packet?.id, error: e.message })); }
      finally { pending = Math.max(0, pending - 1); }
    });
    ws.on('close', () => { sockets.delete(ws); if (controller === ws) { audio.stop(); controller = null; void bridge.request({ type: 'release' }).catch(() => {}); } });
    ws.on('error', () => {});
  });
  try {
    await new Promise((resolveListen, reject) => { server.once('error', reject); server.listen(port, host, resolveListen); });
  } catch (error) {
    audio.close(); wss.close();
    if (bridge) await bridge.close().catch(() => {});
    throw error;
  }
  // Start the native helper only after owning the port. A duplicate launcher
  // must not leave another PowerShell process running.
  try { bridge ??= new WindowsBridge(); }
  catch (error) { audio.close(); wss.close(); await new Promise(done => server.close(done)); throw error; }
  actualPort = server.address().port;
  if (warmModel && commandRouter.warmup) {
    console.log('FunctionGemma: loading and warming up…');
    void Promise.resolve().then(() => commandRouter.warmup()).then(
      () => console.log('FunctionGemma: ready.'),
      error => console.error(`FunctionGemma warm-up failed: ${error.message}`),
    );
  }
  const heartbeat = setInterval(() => {
    for (const ws of sockets) { if (!ws.alive || (sessions.get(ws.session) || 0) < Date.now()) ws.terminate(); else { ws.alive = false; ws.ping(); } }
    for (const [key, value] of attempts) if (value.until < Date.now()) attempts.delete(key);
    for (const [key, value] of sessions) if (value < Date.now()) sessions.delete(key);
  }, 5000);
  let refreshing = false;
  const poll = setInterval(async () => { if (refreshing || !sockets.size) return; refreshing = true; try { await refresh(); } finally { refreshing = false; } }, 4000);
  void refresh(); openHost();
  return { port: actualPort, scheme, adminKey, bridge, server, async close() { clearInterval(heartbeat); clearInterval(poll); audio.close(); commandRouter.close?.(); for (const ws of sockets) ws.terminate(); wss.close(); await bridge.close(); await new Promise(resolveClose => server.close(resolveClose)); } };
}

export async function reuseCompanion(port, { openBrowser = true, scheme = process.env.PHONE_TLS_CERT ? 'https' : 'http' } = {}) {
  const base = `${scheme}://127.0.0.1:${port}`;
  try {
    const response = await fetch(`${base}/api/companion`, { signal: AbortSignal.timeout(2000) });
    if (!response.ok || (await response.json()).service !== 'phone-control-companion') return false;
    if (openBrowser) {
      const opened = await fetch(`${base}/api/companion/open`, { method: 'POST', headers: { 'X-Phone-Control-Launcher': '1' }, signal: AbortSignal.timeout(2000) });
      if (!opened.ok) return false;
    }
    return true;
  } catch { return false; }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const mock = process.argv.includes('--mock');
  const port = Number(process.env.PORT || 8787);
  const openBrowser = !process.argv.includes('--no-open');
  try {
    if (process.platform !== 'win32' && !mock) throw new Error('The companion must run on Windows.');
    if (await reuseCompanion(port, { openBrowser })) {
      console.log(`Phone Control is already running on port ${port}.${openBrowser ? ' Opened its pairing page.' : ''}`);
    } else {
      try {
        const app = await startServer({ port, bridge: mock ? new MockBridge() : undefined, openBrowser });
        console.log(`Companion: ${app.scheme}://localhost:${app.port}/host#admin=${app.adminKey}`);
        console.log('Keep this process running. The phone and computer must share a private network.');
        for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await app.close(); process.exit(0); });
      } catch (error) {
        if (error.code !== 'EADDRINUSE') throw error;
        if (await reuseCompanion(port, { openBrowser })) console.log(`Phone Control is already running on port ${port}.`);
        else throw new Error(`Port ${port} is occupied by another program or an older companion. Close that instance, or choose a different port (PowerShell: $env:PORT='8788'; npm start).`);
      }
    }
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
