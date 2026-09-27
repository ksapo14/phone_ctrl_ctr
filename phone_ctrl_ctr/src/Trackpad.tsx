import { useEffect, useRef } from 'react'
import { GestureEngine } from './gestures'
import { remote } from './remote'
import type { Command } from './remote'

export default function Trackpad() {
  const surface = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const target = surface.current!
    let frame = 0
    let movement = { dx: 0, dy: 0 }, scroll = { dx: 0, dy: 0 }
    function flush() {
      frame = 0
      for (const [type, value] of [['move', movement], ['scroll', scroll]] as const) {
        const limit = type === 'move' ? 500 : 1200
        if (value.dx || value.dy) remote.send({ type, dx: Math.max(-limit, Math.min(limit, value.dx)), dy: Math.max(-limit, Math.min(limit, value.dy)) })
      }
      movement = { dx: 0, dy: 0 }; scroll = { dx: 0, dy: 0 }
    }
    function send(command: Command) {
      if (command.type === 'move' || command.type === 'scroll') {
        const bucket = command.type === 'move' ? movement : scroll
        bucket.dx += command.dx; bucket.dy += command.dy
        if (!frame) frame = requestAnimationFrame(flush)
      } else { if (frame) { cancelAnimationFrame(frame); flush() }; remote.send(command) }
    }
    const engine = new GestureEngine(send)
    const points = (event: TouchEvent) => Array.from(event.targetTouches, t => ({ id: t.identifier, x: t.clientX, y: t.clientY }))
    const start = (event: TouchEvent) => { event.preventDefault(); engine.start(points(event), performance.now()) }
    const move = (event: TouchEvent) => { event.preventDefault(); engine.move(points(event)) }
    const end = (event: TouchEvent) => { event.preventDefault(); engine.end(points(event), performance.now()) }
    const cancel = () => engine.cancel()
    const visibility = () => { if (document.hidden) cancel() }
    const prevent = (event: Event) => event.preventDefault()
    target.addEventListener('touchstart', start, { passive: false }); target.addEventListener('touchmove', move, { passive: false }); target.addEventListener('touchend', end, { passive: false }); target.addEventListener('touchcancel', cancel)
    target.addEventListener('gesturestart', prevent); target.addEventListener('gesturechange', prevent)
    window.addEventListener('blur', cancel)
    document.addEventListener('visibilitychange', visibility)
    return () => { target.removeEventListener('touchstart', start); target.removeEventListener('touchmove', move); target.removeEventListener('touchend', end); target.removeEventListener('touchcancel', cancel); target.removeEventListener('gesturestart', prevent); target.removeEventListener('gesturechange', prevent); window.removeEventListener('blur', cancel); document.removeEventListener('visibilitychange', visibility); cancelAnimationFrame(frame); engine.cancel() }
  }, [])
  return <div className="trackpad-layout">
    <div className="trackpad-surface" ref={surface} aria-label="Trackpad: one finger moves, two fingers scroll, pinch zooms, three fingers switch windows" onContextMenu={event => event.preventDefault()} />
    <div className="trackpad-buttons">{(['left', 'right'] as const).map(button => <button type="button" key={button} aria-label={`${button} click`}
      onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); remote.send({ type: 'button', button, down: true }) }}
      onPointerUp={() => remote.send({ type: 'button', button, down: false })}
      onPointerCancel={() => remote.send({ type: 'button', button, down: false })}
      onLostPointerCapture={() => remote.send({ type: 'button', button, down: false })}
      onClick={event => { if (event.detail === 0) remote.send({ type: 'click', button }) }}
      onContextMenu={event => event.preventDefault()} />)}</div>
  </div>
}
