const apps = new Set(['chrome', 'vscode', 'chatgpt', 'spotify', 'explorer', 'cmd', 'notion', 'settings']);
const sites = new Set(['google_drive', 'github', 'google_docs', 'youtube']);
const gestures = new Set(['taskView', 'desktop', 'nextWindow', 'previousWindow', 'nextDesktop', 'previousDesktop', 'search', 'notifications']);
const number = (v, min, max) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
export function validateCommand(c) {
  if (!c || typeof c !== 'object' || Array.isArray(c)) return false;
  switch (c.type) {
    case 'state': case 'windows': case 'release': return true;
    case 'launch': return apps.has(c.app);
    case 'website': return sites.has(c.site);
    case 'media': return ['playPause', 'next', 'previous', 'stop'].includes(c.action);
    case 'move': return number(c.dx, -500, 500) && number(c.dy, -500, 500);
    case 'scroll': return number(c.dx, -1200, 1200) && number(c.dy, -1200, 1200);
    case 'click': return ['left', 'right', 'x1'].includes(c.button);
    case 'doubleClick': return c.button === 'x1';
    case 'button': return ['left', 'right', 'x1'].includes(c.button) && typeof c.down === 'boolean';
    case 'gesture': return gestures.has(c.name);
    case 'zoom': return number(c.delta, -240, 240);
    case 'focus': return typeof c.id === 'string' && /^\d{1,18}$/.test(c.id);
    case 'volume': case 'brightness': return number(c.value, 0, 100) && Number.isInteger(c.value);
    default: return false;
  }
}
