// Read capabilities and exercise setters using the current values only.
// No apps are launched, no window is activated, and no pointer movement occurs.
import assert from 'node:assert/strict';
import { WindowsBridge } from './bridge.mjs';
const bridge = new WindowsBridge();
try {
  const before = await bridge.request({ type: 'state' });
  await bridge.request({ type: 'move', dx: 0, dy: 0 });
  await bridge.request({ type: 'scroll', dx: 0, dy: 0 });
  await bridge.request({ type: 'release' });
  if (before.volume !== null) await bridge.request({ type: 'volume', value: before.volume });
  if (before.brightness !== null) await bridge.request({ type: 'brightness', value: before.brightness });
  const after = await bridge.request({ type: 'state' });
  assert.equal(after.volume, before.volume);
  assert.ok(after.brightness === null || Math.abs(after.brightness - before.brightness) <= 1);
  console.log(JSON.stringify({ apps: after.apps, windows: after.windows.length, volume: after.volume, brightness: after.brightness, inputInterop: 'passed' }));
} finally { await bridge.close(); }
