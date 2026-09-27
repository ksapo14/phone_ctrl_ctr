import test from 'node:test';
import assert from 'node:assert/strict';
import { phoneMicrophone } from '../src/phoneMicrophone.ts';

test('phone microphone rejects insecure capture and releases late permission results after cancel', async t => {
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const originalWindow = globalThis.window;
  const originalContext = globalThis.AudioContext;
  t.after(() => {
    phoneMicrophone.stop();
    if (originalNavigator) Object.defineProperty(globalThis, 'navigator', originalNavigator); else delete globalThis.navigator;
    if (originalWindow) globalThis.window = originalWindow; else delete globalThis.window;
    if (originalContext) globalThis.AudioContext = originalContext; else delete globalThis.AudioContext;
  });
  let allow, stopped = 0, closed = 0;
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia: () => new Promise(resolve => { allow = resolve; }) } } });
  globalThis.window = { isSecureContext: false };
  await phoneMicrophone.start(); assert.match(phoneMicrophone.getSnapshot().error, /HTTPS/);
  globalThis.window.isSecureContext = true;
  globalThis.AudioContext = class { resume() { return Promise.resolve(); } close() { closed++; return Promise.resolve(); } };
  const starting = phoneMicrophone.start(); assert.equal(phoneMicrophone.getSnapshot().status, 'starting');
  phoneMicrophone.stop();
  allow({ getTracks: () => [{ stop() { stopped++; } }] }); await starting;
  assert.equal(stopped, 1); assert.equal(closed, 1); assert.equal(phoneMicrophone.getSnapshot().status, 'off');
});
