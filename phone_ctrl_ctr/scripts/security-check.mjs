// Reports locations and rule names only. Never prints matched credentials.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const project = dirname(dirname(fileURLToPath(import.meta.url)));
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: project, encoding: 'utf8' }).trim();
const git = (...args) => execFileSync('git', args, { cwd: root, maxBuffer: 64 * 1024 * 1024 });
const findings = [];
const counts = { workingFiles: 0, stagedFiles: 0, historyBlobs: 0, builtFiles: 0 };
const fixtureKey = 'phone_ctrl_ctr/server/fixtures/audio-test-key.pem';
const fixtureCert = 'phone_ctrl_ctr/server/fixtures/audio-test-cert.pem';
const fixtureHash = 'f0abd884ec0f148bc4e58fa02ccf893b3ff8373af265d65d10f4b998943ff4b0';
const knownSecrets = new Set();
for (const path of [join(root, '.env'), join(project, '.env'), join(homedir(), '.phone-control', '.env')]) {
  if (!existsSync(path)) continue;
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^\s*(?:export\s+)?[\w]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*(.*?)\s*$/i.exec(line);
    const value = match?.[1].replace(/^(['"])(.*)\1$/, '$2');
    if (value && value.length >= 16 && !/^(your_|example|placeholder|replace)/i.test(value)) knownSecrets.add(value);
  }
}

function blockedPath(path) {
  const name = path.split('/').at(-1);
  if (name === '.env.example' || path === fixtureKey || path === fixtureCert) return false;
  return /^\.env(?:\.|$)/.test(name) || /\.(?:pem|key|p12|pfx|jks|keystore|safetensors|pt|pth|ckpt|pickle|pkl)$/i.test(name)
    || /(?:^|\/)(?:certs|models|\.venv[^/]*|node_modules|\.aws|\.ssh)\//.test(path)
    || /(?:^|\/)(?:\.npmrc|\.pypirc|\.netrc|id_rsa|id_ed25519)$/.test(path)
    || /(?:credentials|service-account).*\.json$/i.test(name) || /functiongemma.*\.(?:tar\.gz|zip|bin)$/.test(name);
}
const rules = [
  ['credential embedded in URL', /https?:\/\/[^\s/:@]+:[^\s/@]+@/g],
  ['private key', /-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----/g],
  ['GitHub token', /\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/g],
  ['AWS access key', /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/g],
  ['Hugging Face token', /\bhf_[A-Za-z0-9]{30,}\b/g],
  ['OpenAI or Stripe token', /\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}|[sr]k_live_[A-Za-z0-9]{20,})\b/g],
  ['Slack token', /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/g],
  ['credential literal', /\b(?:DEEPGRAM_API_KEY|api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[=:]\s*["']([A-Za-z0-9_\-/+=]{24,})["']/gi],
];
function scan(path, buffer, scope) {
  if (blockedPath(path)) findings.push({ scope, path, rule: 'private or generated file is eligible for Git' });
  if (buffer.length > 10 * 1024 * 1024) { findings.push({ scope, path, rule: 'file exceeds 10 MB; review separately' }); return; }
  const text = buffer.toString('utf8');
  const fixture = path === fixtureKey && createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex') === fixtureHash;
  for (const [rule, pattern] of rules) {
    if (rule === 'private key' && fixture) continue;
    for (const match of text.matchAll(pattern)) findings.push({ scope, path, line: text.slice(0, match.index).split('\n').length, rule });
  }
  for (const secret of knownSecrets) {
    if (text.includes(secret)) findings.push({ scope, path, rule: 'matches a configured local secret' });
  }
}
function scanBlob(path, oid, scope) {
  const size = Number(git('cat-file', '-s', oid).toString().trim());
  if (size > 10 * 1024 * 1024) {
    findings.push({ scope, path, bytes: size, rule: 'large historical or staged artifact; contents not scanned' });
    return;
  }
  scan(path, git('cat-file', 'blob', oid), scope);
}

const files = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').toString().split('\0').filter(Boolean);
for (const path of new Set(files)) {
  const absolute = join(root, path);
  if (!existsSync(absolute) || !statSync(absolute).isFile()) continue;
  counts.workingFiles++;
  if (statSync(absolute).size > 10 * 1024 * 1024) { findings.push({ scope: 'working tree', path, rule: 'file exceeds 10 MB; review separately' }); continue; }
  scan(path, readFileSync(absolute), 'working tree');
}
for (const entry of git('ls-files', '--stage', '-z').toString().split('\0').filter(Boolean)) {
  const [, , oid, , path] = /^(\d+) ([a-f0-9]+) (\d+)\t(.*)$/s.exec(entry);
  counts.stagedFiles++;
  scanBlob(path, oid, 'Git index');
}
if (process.argv.includes('--history')) {
  const refs = process.argv.includes('--all-refs') ? ['--all'] : ['--branches', '--tags', '--remotes'];
  for (const entry of git('rev-list', '--objects', ...refs).toString().split('\n').filter(Boolean)) {
    const [, oid, path] = /^([a-f0-9]+)(?: (.*))?$/.exec(entry);
    if (!path || git('cat-file', '-t', oid).toString().trim() !== 'blob') continue;
    counts.historyBlobs++;
    scanBlob(path, oid, `history ${oid.slice(0, 12)}`);
  }
}
function scanBuilt(dir) {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) scanBuilt(path);
    else if (entry.isFile()) { counts.builtFiles++; scan(relative(root, path).replaceAll('\\', '/'), readFileSync(path), 'built frontend'); }
  }
}
scanBuilt(join(project, 'dist'));
console.log(JSON.stringify({ counts, knownSecretValuesChecked: knownSecrets.size, findings }, null, 2));
process.exitCode = findings.length ? 1 : 0;
