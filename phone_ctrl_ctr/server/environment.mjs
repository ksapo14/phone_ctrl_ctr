import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export function loadLocalEnvironment() {
  // Prefer the user-profile file outside the OneDrive checkout. Explicit process
  // environment values win; the project .env remains a compatibility fallback.
  for (const path of [join(homedir(), '.phone-control', '.env'), new URL('../.env', import.meta.url)]) {
    try {
      for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
        const match = /^\s*(?:export\s+)?(DEEPGRAM_API_KEY|PHONE_PYTHON)\s*=\s*(.*)\s*$/.exec(line);
        if (match && !process.env[match[1]]) process.env[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
      }
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

export function childEnvironment(environment = process.env) {
  return Object.fromEntries(Object.entries(environment).filter(([name]) => name.toUpperCase() !== 'DEEPGRAM_API_KEY'));
}
