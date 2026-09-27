import type { Command } from './remote'
export type Finger = { id: number; x: number; y: number }
const center = (points: Finger[]) => ({ x: points.reduce((sum, p) => sum + p.x, 0) / points.length, y: points.reduce((sum, p) => sum + p.y, 0) / points.length })
const spread = (points: Finger[]) => points.length < 2 ? 0 : Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)
export class GestureEngine {
  send: (command: Command) => void
  points: Finger[] = []
  maxFingers = 0; startTime = 0; moved = false; dragging = false; fired = false
  totalX = 0; totalY = 0; pinch = 0; lastTap = -Infinity
  twoMode: 'pending' | 'scroll' | 'zoom' = 'pending'
  constructor(send: (command: Command) => void) { this.send = send }
  start(points: Finger[], now: number) {
    if (!this.points.length) {
      this.maxFingers = 0; this.startTime = now; this.moved = false; this.fired = false; this.totalX = 0; this.totalY = 0; this.pinch = 0
      if (points.length === 1 && now - this.lastTap < 300) { this.dragging = true; this.send({ type: 'button', button: 'left', down: true }) }
    }
    if (points.length > 1 && this.dragging) { this.send({ type: 'button', button: 'left', down: false }); this.dragging = false }
    if (points.length > this.maxFingers) { this.totalX = 0; this.totalY = 0; this.pinch = 0; this.twoMode = 'pending' }
    this.maxFingers = Math.max(this.maxFingers, points.length); this.points = points
  }
  move(points: Finger[]) {
    if (!this.points.length || points.length !== this.points.length) { this.points = points; return }
    const before = center(this.points), after = center(points)
    const dx = after.x - before.x, dy = after.y - before.y
    this.totalX += dx; this.totalY += dy
    if (Math.hypot(this.totalX, this.totalY) > 7) this.moved = true
    if (points.length === this.maxFingers) {
      if (points.length === 1 && this.moved) this.send({ type: 'move', dx: Math.max(-500, Math.min(500, Math.round(dx * 1.8))), dy: Math.max(-500, Math.min(500, Math.round(dy * 1.8))) })
      if (points.length === 2) {
        this.pinch += spread(points) - spread(this.points)
        if (this.twoMode === 'pending') {
          if (Math.abs(this.pinch) > 10 && Math.abs(this.pinch) > Math.hypot(this.totalX, this.totalY) * 1.5) this.twoMode = 'zoom'
          else if (this.moved) this.twoMode = 'scroll'
        }
        if (this.twoMode === 'zoom' && Math.abs(this.pinch) > 10) { this.moved = true; this.send({ type: 'zoom', delta: Math.sign(this.pinch) * 120 }); this.pinch = 0 }
        else if (this.twoMode === 'scroll') this.send({ type: 'scroll', dx: Math.round(-dx * 3), dy: Math.round(dy * 3) })
      }
      if (points.length >= 3 && !this.fired && Math.hypot(this.totalX, this.totalY) > 55) {
        this.fired = true; this.moved = true
        const horizontal = Math.abs(this.totalX) > Math.abs(this.totalY)
        const name = horizontal ? (points.length >= 4 ? (this.totalX < 0 ? 'nextDesktop' : 'previousDesktop') : (this.totalX < 0 ? 'nextWindow' : 'previousWindow')) : (this.totalY < 0 ? 'taskView' : 'desktop')
        this.send({ type: 'gesture', name })
      }
    }
    this.points = points
  }
  end(points: Finger[], now: number) {
    if (points.length) { this.points = points; return }
    if (this.dragging) { this.send({ type: 'button', button: 'left', down: false }); this.dragging = false; this.lastTap = -Infinity }
    else if (!this.moved && now - this.startTime < 300) {
      if (this.maxFingers === 1) { this.send({ type: 'click', button: 'left' }); this.lastTap = now }
      else if (this.maxFingers === 2) this.send({ type: 'click', button: 'right' })
      else this.send({ type: 'gesture', name: this.maxFingers >= 4 ? 'notifications' : 'search' })
    }
    this.points = []
  }
  cancel() { if (this.dragging) this.send({ type: 'button', button: 'left', down: false }); this.send({ type: 'release' }); this.dragging = false; this.points = []; this.lastTap = -Infinity }
}
