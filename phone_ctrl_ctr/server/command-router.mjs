import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { validateCommand } from './protocol.mjs';
import { childEnvironment } from './environment.mjs';

const appNames = { chrome: 'chrome', chatgpt: 'chatgpt', spotify: 'spotify', vscode: 'vscode', command_prompt: 'cmd', file_explorer: 'explorer', notion: 'notion', settings: 'settings' };
const siteNames = new Set(['google_drive', 'github', 'google_docs', 'youtube']);
const field = (body, name) => {
  const match = new RegExp(`^\\s*${name}\\s*:\\s*(?:<escape>([^<]*)<escape>|"([^"]*)"|([a-zA-Z0-9_]+))\\s*$`).exec(body);
  return match?.[1] ?? match?.[2] ?? match?.[3];
};

export function parseToolCalls(output) {
  if (typeof output !== 'string') throw new Error('The command model returned an invalid response.');
  const proposal = output.split('<start_function_response>')[0];
  const calls = [...proposal.matchAll(/<start_function_call>\s*call:([a-z_]+)\{([^{}]*)\}\s*<end_function_call>/g)];
  if (!calls.length || calls.length > 4 || proposal.replace(/<start_function_call>\s*call:[a-z_]+\{[^{}]*\}\s*<end_function_call>/g, '').trim()) throw new Error('No supported command was recognized.');
  const commands = calls.map(([, name, args]) => {
    if (name === 'start_app') return { type: 'launch', app: appNames[field(args, 'app')] };
    if (name === 'open_website') return { type: 'website', site: field(args, 'site') };
    if (name === 'set_volume' || name === 'set_brightness') {
      const raw = field(args, 'level');
      return { type: name === 'set_volume' ? 'volume' : 'brightness', value: /^\d+$/.test(raw ?? '') ? Number(raw) : NaN };
    }
    if (args.trim() !== '') throw new Error('The command model returned unexpected arguments.');
    if (name === 'pause_media' || name === 'play_media') return { type: 'media', action: 'playPause' };
    if (name === 'skip_media') return { type: 'media', action: 'next' };
    throw new Error('The command model selected an unsupported action.');
  });
  if (commands.some(command => !validateCommand(command) || (command.type === 'website' && !siteNames.has(command.site)))) throw new Error('The command model returned an unsupported value.');
  return commands;
}

export class FunctionGemmaRouter {
  constructor({ python = process.env.PHONE_PYTHON || (existsSync(fileURLToPath(new URL('../.venv-commands/Scripts/python.exe', import.meta.url))) ? fileURLToPath(new URL('../.venv-commands/Scripts/python.exe', import.meta.url)) : 'python'), script = fileURLToPath(new URL('../scripts/inference.py', import.meta.url)) } = {}) {
    this.python = python; this.script = script; this.pending = new Map(); this.sequence = 0;
  }
  start() {
    if (this.process) return;
    this.diagnostic = '';
    const child = spawn(this.python, [this.script, '--serve'], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: childEnvironment() });
    this.process = child;
    createInterface({ input: child.stdout }).on('line', line => {
      try {
        const packet = JSON.parse(line); const entry = this.pending.get(packet.id);
        if (!entry) return;
        clearTimeout(entry.timer); this.pending.delete(packet.id);
        if (packet.error) entry.reject(new Error(packet.error)); else entry.resolve(packet.output);
      } catch { /* Ignore diagnostics that are not protocol messages. */ }
    });
    child.stderr.on('data', bytes => { this.diagnostic = ((this.diagnostic || '') + bytes).slice(-1500); });
    child.on('error', error => { if (this.process === child) this.fail(error); });
    child.on('exit', () => { if (this.process === child) this.fail(new Error(this.diagnostic || 'FunctionGemma stopped. Check Python dependencies and the model path.')); });
  }
  fail(error) {
    this.process = null;
    this.warmupPromise = null;
    for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error); }
    this.pending.clear();
  }
  warmup() {
    if (!this.warmupPromise) {
      // Exercise generation as well as loading weights. This result is discarded;
      // only the HTTP command handler dispatches actions to the Windows bridge.
      const warming = Promise.resolve().then(() => this.request('Set volume to 50')).then(parseToolCalls);
      this.warmupPromise = warming;
      void warming.catch(() => { if (this.warmupPromise === warming) this.warmupPromise = null; });
    }
    return this.warmupPromise;
  }
  async route(text) {
    await this.warmup();
    return parseToolCalls(await this.request(text));
  }
  request(text) {
    if (this.closed) return Promise.reject(new Error('The companion stopped.'));
    this.start();
    if (this.pending.size) return Promise.reject(new Error('The command model is busy. Try again in a moment.'));
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('FunctionGemma timed out.')); this.process?.kill(); }, 120000);
      this.pending.set(id, { resolve, reject, timer });
      this.process.stdin.write(JSON.stringify({ id, text }) + '\n', error => { if (error) { clearTimeout(timer); this.pending.delete(id); reject(error); } });
    });
  }
  close() { this.closed = true; this.process?.kill(); this.process = null; this.fail(new Error('The companion stopped.')); }
}
