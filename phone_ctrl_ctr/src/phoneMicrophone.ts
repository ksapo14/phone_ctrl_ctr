type Snapshot = { status: 'off' | 'starting' | 'streaming'; error: string }
type Session = { cancelled: boolean; context?: AudioContext; stream?: MediaStream; socket?: WebSocket; node?: AudioWorkletNode }
let snapshot: Snapshot = { status: 'off', error: '' }
let session: Session | null = null
const listeners = new Set<() => void>()
const update = (next: Snapshot) => { snapshot = next; listeners.forEach(listener => listener()) }

function dispose(current: Session) {
  current.cancelled = true
  current.stream?.getTracks().forEach(track => { track.onended = null; track.stop() })
  if (current.node) { current.node.port.onmessage = null; current.node.disconnect() }
  if (current.context) { current.context.onstatechange = null; void current.context.close().catch(() => {}) }
  current.socket?.close()
}

export const phoneMicrophone = {
  subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
  getSnapshot: () => snapshot,
  stop() {
    if (session) { dispose(session); session = null }
    update({ status: 'off', error: '' })
  },
  async start() {
    if (session) return
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      update({ status: 'off', error: 'Phone microphone needs a trusted HTTPS connection. See Phone microphone setup on the computer.' }); return
    }
    const current: Session = { cancelled: false }
    session = current; update({ status: 'starting', error: '' })
    const fail = (message: string) => {
      if (current.cancelled || session !== current) return
      dispose(current); session = null; update({ status: 'off', error: message })
    }
    try {
      // Resume during the tap gesture, before the microphone permission await.
      try { current.context = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' }) }
      catch { current.context = new AudioContext({ latencyHint: 'interactive' }) }
      const context = current.context
      void context.resume().catch(() => fail('Safari could not start audio. Tap Phone microphone again.'))
      const stream = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      }, video: false })
      if (current.cancelled) { stream.getTracks().forEach(track => track.stop()); return }
      current.stream = stream
      stream.getTracks().forEach(track => { track.onended = () => fail('Phone microphone disconnected or permission was removed.') })
      await context.audioWorklet.addModule('/phone-mic-worklet.js')
      if (current.cancelled) return
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/audio`)
      current.socket = socket
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('The computer audio receiver did not respond.')), 20000)
        const rejectWith = (message: string) => { clearTimeout(timeout); reject(new Error(message)); fail(message) }
        socket.onmessage = event => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'ready') { clearTimeout(timeout); resolve() }
            else if (data.type === 'error') rejectWith(data.error)
          } catch { rejectWith('Invalid response from the computer audio receiver.') }
        }
        socket.onerror = () => rejectWith('Cannot connect to the computer audio receiver.')
        socket.onclose = () => rejectWith('Phone microphone connection closed. Tap to reconnect.')
      })
      if (current.cancelled) return
      const source = context.createMediaStreamSource(stream)
      const node = new AudioWorkletNode(context, 'phone-mic', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] })
      current.node = node
      // Worklet outputs silence; connecting it keeps Safari processing without feedback.
      source.connect(node); node.connect(context.destination)
      node.port.onmessage = event => {
        if (current.cancelled || socket.readyState !== WebSocket.OPEN) return
        if (socket.bufferedAmount > 15360) { fail('Network is too slow for live audio. Tap to reconnect.'); return }
        socket.send(event.data as ArrayBuffer)
      }
      node.onprocessorerror = () => fail('Microphone processing stopped. Tap to reconnect.')
      context.onstatechange = () => { if (context.state !== 'running') fail('Safari suspended the microphone. Keep Voice open and the phone unlocked.') }
      if (context.state !== 'running') throw new Error('Safari audio is suspended. Tap Phone microphone again.')
      update({ status: 'streaming', error: '' })
    } catch (error) {
      const e = error as Error
      fail(e.name === 'NotAllowedError' ? 'Allow microphone access in Safari, then tap Phone microphone again.' : e.message)
    }
  },
}
