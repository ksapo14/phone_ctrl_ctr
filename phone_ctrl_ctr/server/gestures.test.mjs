import test from 'node:test';
import assert from 'node:assert/strict';
import { GestureEngine } from '../src/gestures.ts';
const points = (count, x = 0, y = 0, gap = 30) => Array.from({ length: count }, (_, id) => ({ id, x: x + id * gap, y }));
const setup = () => { const commands = []; return { commands, engine: new GestureEngine(c => commands.push(c)) }; };
test('one-finger tap, two-finger right click and double tap drag release', () => {
  const { engine, commands } = setup();
  engine.start(points(1), 100); engine.end([], 180); assert.deepEqual(commands.pop(), { type: 'click', button: 'left' });
  engine.start(points(1), 230); engine.move(points(1, 30)); engine.end([], 500);
  assert.deepEqual(commands[0], { type: 'button', button: 'left', down: true }); assert.equal(commands[1].type, 'move'); assert.deepEqual(commands.at(-1), { type: 'button', button: 'left', down: false });
  engine.start(points(2), 1000); engine.end([], 1100); assert.deepEqual(commands.at(-1), { type: 'click', button: 'right' });
});
test('scroll, pinch, three-finger windows, four-finger desktops', () => {
  const { engine, commands } = setup();
  engine.start(points(2), 0); engine.move(points(2, 0, 20)); assert.equal(commands.at(-1).type, 'scroll'); engine.end([], 200);
  engine.start(points(2), 1000); engine.move(points(2, 0, 0, 55)); assert.equal(commands.at(-1).type, 'zoom'); engine.end([], 1200);
  engine.start(points(3), 2000); engine.move(points(3, -80)); assert.deepEqual(commands.at(-1), { type: 'gesture', name: 'nextWindow' }); engine.end([], 2200);
  engine.start(points(4), 3000); engine.move(points(4, 80)); assert.deepEqual(commands.at(-1), { type: 'gesture', name: 'previousDesktop' }); engine.end([], 3200);
});
test('finger-count changes do not jump pointer or cause an accidental click; cancellation releases drag', () => {
  const { engine, commands } = setup();
  engine.start(points(3), 0); engine.move(points(3, -90)); engine.end(points(1), 100); engine.move(points(1, -120)); engine.end([], 200);
  assert.equal(commands.length, 1);
  engine.start(points(1), 1000); engine.end([], 1080); engine.start(points(1), 1120); engine.cancel();
  assert.equal(commands.at(-1).type, 'release'); assert.deepEqual(commands.at(-2), { type: 'button', button: 'left', down: false });
});
