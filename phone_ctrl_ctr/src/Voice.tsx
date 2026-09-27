import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { remote, useRemote } from './remote'
import { phoneMicrophone } from './phoneMicrophone'

export default function Voice({ handsFree, onHandsFree }: { handsFree: boolean; onHandsFree: (active: boolean) => void }) {
  const { status } = useRemote()
  const phoneMic = useSyncExternalStore(phoneMicrophone.subscribe, phoneMicrophone.getSnapshot)
  useEffect(() => {
    const hide = () => { if (document.hidden) phoneMicrophone.stop() }
    document.addEventListener('visibilitychange', hide)
    window.addEventListener('pagehide', phoneMicrophone.stop)
    return () => { phoneMicrophone.stop(); document.removeEventListener('visibilitychange', hide); window.removeEventListener('pagehide', phoneMicrophone.stop) }
  }, [])
  useEffect(() => { if (status !== 'online') phoneMicrophone.stop() }, [status])
  const [holding, setHolding] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pressed = useRef(false)
  const held = useRef(false)
  const pointer = useRef<number | null>(null)
  const generation = useRef(0)
  const busy = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    const cancel = () => {
      clearTimeout(timer.current); pressed.current = false; pointer.current = null; generation.current++
      if (held.current) remote.send({ type: 'button', button: 'x1', down: false })
      held.current = false; setHolding(false)
    }
    const visibility = () => { if (document.hidden) cancel() }
    window.addEventListener('blur', cancel); document.addEventListener('visibilitychange', visibility)
    return () => { mounted.current = false; cancel(); window.removeEventListener('blur', cancel); document.removeEventListener('visibilitychange', visibility) }
  }, [])

  function begin() {
    if (pressed.current || busy.current || status !== 'online') return
    pressed.current = true
    const current = ++generation.current
    timer.current = setTimeout(() => {
      if (!pressed.current) return
      held.current = true
      void remote.request({ type: 'button', button: 'x1', down: true }).then(() => {
        if (mounted.current && generation.current === current && pressed.current) { setHolding(true); onHandsFree(false) }
      }).catch(() => { if (mounted.current && generation.current === current) setHolding(false) })
    }, 250)
  }
  function finish(cancel = false) {
    if (!pressed.current) return
    clearTimeout(timer.current); pressed.current = false; generation.current++
    if (held.current) {
      held.current = false; setHolding(false)
      remote.send({ type: 'button', button: 'x1', down: false })
    } else if (!cancel) tap()
  }
  function tap() {
    if (busy.current || status !== 'online') return
    busy.current = true
    void remote.request({ type: 'doubleClick', button: 'x1' }).then(() => {
      // This reflects our shortcut toggle; Wispr does not report its recording
      // state to the companion. Keep it across mode changes.
      onHandsFree(!handsFree)
    }).catch(() => {}).finally(() => { busy.current = false })
  }
  const active = status === 'online' && (holding || handsFree)
  return <div className="voice-layout"><div className="voice-controls">
    <button type="button" className={`voice-button${active ? ' is-active' : ''}`} aria-label="Voice: hold to dictate, tap for hands-free" aria-pressed={active}
      onPointerDown={event => { if (pointer.current !== null) return; event.preventDefault(); pointer.current = event.pointerId; event.currentTarget.setPointerCapture(event.pointerId); begin() }}
      onPointerUp={event => { if (pointer.current !== event.pointerId) return; pointer.current = null; finish() }}
      onPointerCancel={() => { pointer.current = null; finish(true) }}
      onLostPointerCapture={() => { pointer.current = null; finish(true) }}
      onContextMenu={event => event.preventDefault()}
      onKeyDown={event => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); begin() } }}
      onKeyUp={event => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); finish() } }}
      onBlur={() => finish(true)}
      onClick={event => { if (event.detail === 0 && !pressed.current) tap() }}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><rect x="11" y="3" width="10" height="18" rx="5"/><path d="M7 15v2a9 9 0 0 0 18 0v-2M16 26v4M11 30h10"/></svg>
    </button>
    <button type="button" className="phone-mic-toggle" aria-pressed={phoneMic.status !== 'off'} disabled={status !== 'online'}
      onClick={() => { if (phoneMic.status === 'off') void phoneMicrophone.start(); else phoneMicrophone.stop() }}>
      {phoneMic.status === 'starting' ? 'Connecting mic…' : phoneMic.status === 'streaming' ? 'Phone mic on' : 'Use phone mic'}
    </button>
    {phoneMic.status === 'streaming' && <p className="phone-mic-hint" role="status">Streaming · keep Voice open</p>}
    {phoneMic.error && <p className="phone-mic-error" role="alert">{phoneMic.error}</p>}
  </div></div>
}
