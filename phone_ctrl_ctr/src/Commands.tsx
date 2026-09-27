import { useEffect, useRef, useState } from 'react'
import { useRemote } from './remote'

type ExecutedCommand = { type: string; app?: string; site?: string; value?: number; action?: string }
type Result = { transcript: string; commands: ExecutedCommand[] }

function describe(command: ExecutedCommand) {
  if (command.type === 'launch') return `Open ${command.app}`
  if (command.type === 'website') return `Open ${command.site?.replaceAll('_', ' ')}`
  if (command.type === 'volume' || command.type === 'brightness') return `Set ${command.type} to ${command.value}%`
  if (command.type === 'media') return command.action === 'next' ? 'Next track' : 'Play/pause media'
  return command.type
}

export default function Commands() {
  const { status } = useRemote()
  const [text, setText] = useState('')
  const [phase, setPhase] = useState<'idle' | 'recording' | 'working'>('idle')
  const [error, setError] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const active = useRef(true)

  useEffect(() => {
    active.current = true
    const cancel = () => { if (document.hidden) stopRecording(true) }
    document.addEventListener('visibilitychange', cancel)
    return () => { active.current = false; stopRecording(true); document.removeEventListener('visibilitychange', cancel) }
  }, [])

  function stopRecording(discard = false) {
    clearTimeout(timer.current)
    if (recorder.current) {
      if (discard) recorder.current.onstop = null
      if (recorder.current.state !== 'inactive') recorder.current.stop()
      recorder.current = null
    }
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
    if (discard && active.current) setPhase('idle')
  }

  async function run(path: string, body: BodyInit, contentType: string) {
    setPhase('working'); setError(''); setResult(null)
    try {
      const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': contentType }, body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || 'Command failed.')
      if (active.current) { setResult(data); setText(data.transcript) }
    } catch (reason) { if (active.current) setError(reason instanceof Error ? reason.message : 'Command failed.') }
    finally { if (active.current) setPhase('idle') }
  }

  async function startRecording() {
    if (phase !== 'idle' || status !== 'online') return
    setError(''); setResult(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Microphone recording requires HTTPS and a supported browser.'); return }
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!active.current) { media.getTracks().forEach(track => track.stop()); return }
      stream.current = media
      const mimeType = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type))
      const capture = new MediaRecorder(media, mimeType ? { mimeType } : undefined)
      recorder.current = capture
      const chunks: Blob[] = []
      capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      capture.onstop = () => {
        media.getTracks().forEach(track => track.stop())
        stream.current = null; recorder.current = null
        if (!active.current || !chunks.length) { if (active.current) { setPhase('idle'); setError('No audio was recorded.') } return }
        const type = capture.mimeType.split(';')[0] || mimeType || 'audio/webm'
        void run('/api/commands/audio', new Blob(chunks, { type }), type)
      }
      capture.start()
      setPhase('recording')
      timer.current = setTimeout(() => stopRecording(), 12000)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Microphone access failed.'); stopRecording(true) }
  }

  return <div className="commands-layout">
    <button type="button" className={`voice-button${phase === 'recording' ? ' is-active' : ''}`} aria-label={phase === 'recording' ? 'Stop recording command' : 'Record command'} aria-pressed={phase === 'recording'} disabled={status !== 'online' || phase === 'working'} onClick={() => phase === 'recording' ? stopRecording() : void startRecording()}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><rect x="11" y="3" width="10" height="18" rx="5"/><path d="M7 15v2a9 9 0 0 0 18 0v-2M16 26v4M11 30h10"/></svg>
    </button>
    <p className="commands-hint">{phase === 'recording' ? 'Listening… tap to send' : phase === 'working' ? 'Processing command…' : 'Tap to speak a command'}</p>
    <form className="commands-form" onSubmit={event => { event.preventDefault(); if (text.trim()) void run('/api/commands/text', JSON.stringify({ text: text.trim() }), 'application/json') }}>
      <label htmlFor="command-text">Or type a command</label>
      <div className="commands-entry"><input id="command-text" value={text} maxLength={240} onChange={event => setText(event.target.value)} placeholder="Open GitHub, set volume to 40…" disabled={status !== 'online' || phase !== 'idle'} /><button type="submit" disabled={status !== 'online' || phase !== 'idle' || !text.trim()}>Run</button></div>
    </form>
    {result && <div className="commands-result" role="status"><p>“{result.transcript}”</p><ul>{result.commands.map((command, index) => <li key={index}>{describe(command)}</li>)}</ul></div>}
    {error && <p className="commands-error" role="alert">{error}</p>}
  </div>
}
