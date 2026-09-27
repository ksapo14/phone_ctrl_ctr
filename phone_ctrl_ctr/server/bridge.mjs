import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

export class WindowsBridge {
  constructor() {
    this.pending = new Map(); this.serial = 0;
    this.process = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', fileURLToPath(new URL('./bridge.ps1', import.meta.url))], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    this.failure = null;
    createInterface({ input: this.process.stdout }).on('line', line => {
      try { const response = JSON.parse(line); const entry = this.pending.get(response.id);
        if (!entry) return; clearTimeout(entry.timer); this.pending.delete(response.id);
        if (response.ok) entry.resolve(response.result); else entry.reject(new Error(response.error));
      } catch { /* PowerShell compilation diagnostics are on stderr. */ }
    });
    this.process.stderr.on('data', data => { this.diagnostic = String(data).slice(-2000); });
    this.process.on('error', error => this.fail(error));
    this.process.on('exit', () => this.fail(new Error(this.diagnostic || 'The Windows helper stopped. Restart the companion.')));
    this.process.stdin.on('error', error => this.fail(error));
  }
  fail(error) { this.failure = error; for (const entry of this.pending.values()) { clearTimeout(entry.timer); entry.reject(error); } this.pending.clear(); }
  request(command) {
    if (this.failure) return Promise.reject(this.failure);
    if (this.pending.size > 120) return Promise.reject(new Error('Input queue is full.'));
    const id = ++this.serial;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('Windows helper timed out.')); }, 15000);
      this.pending.set(id, { resolve, reject, timer });
      this.process.stdin.write(JSON.stringify({ id, command }) + '\n');
    });
  }
  async close() { await this.request({ type: 'release' }).catch(() => {}); this.process.stdin.end(); }
}

export class MockBridge {
  constructor() { this.volume = 35; this.brightness = 60; this.commands = []; }
  async request(c) {
    this.commands.push(c);
    if (c.type === 'volume' || c.type === 'brightness') this[c.type] = c.value;
    const windows = [{ id: '101', title: 'Test window', active: true }, { id: '102', title: 'Second window', active: false }];
    if (c.type === 'windows') return windows;
    if (c.type === 'state') return { volume: this.volume, brightness: this.brightness, windows, apps: ['chrome','vscode','chatgpt','spotify','explorer','cmd'] };
    return null;
  }
  async close() {}
}
