import { useSyncExternalStore } from 'react'

export type Command =
  | { type: 'state' | 'windows' | 'release' }
  | { type: 'launch'; app: string }
  | { type: 'media'; action: 'playPause' | 'next' | 'previous' | 'stop' }
  | { type: 'move' | 'scroll'; dx: number; dy: number }
  | { type: 'click'; button: 'left' | 'right' | 'x1' }
  | { type: 'doubleClick'; button: 'x1' }
  | { type: 'button'; button: 'left' | 'right' | 'x1'; down: boolean }
  | { type: 'gesture'; name: string }
  | { type: 'zoom'; delta: number }
  | { type: 'focus'; id: string }
  | { type: 'volume' | 'brightness'; value: number }
export type RemoteWindow = { id: string; title: string; active: boolean }
export type ComputerState = { volume: number | null; brightness: number | null; windows: RemoteWindow[]; apps: string[] }
type Snapshot = { status: 'checking' | 'unpaired' | 'connecting' | 'online' | 'offline'; state: ComputerState | null; error: string }
let snapshot: Snapshot = { status: 'checking', state: null, error: '' }
const listeners = new Set<() => void>()
const update = (patch: Partial<Snapshot>) => { snapshot = { ...snapshot, ...patch }; listeners.forEach(fn => fn()) }
let socket: WebSocket | null = null
let sequence = 0
let retry: ReturnType<typeof setTimeout> | undefined
let started = false
let reconnectDelay = 600
const pending = new Map<number, { resolve: (data: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
const settingTimers = new Map<string, ReturnType<typeof setTimeout>>()
const settingValues = new Map<'volume' | 'brightness', number>()

export async function api(path: string, data?: unknown) {
  const response = await fetch(path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
  const result = await response.json()
  if (!response.ok) throw new Error(result.error || 'Connection failed.')
  return result
}
function connect() {
  clearTimeout(retry)
  if (document.hidden || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return
  update({ status: 'connecting' })
  const current = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/control`)
  socket = current
  current.onopen = () => { reconnectDelay = 600; update({ status: 'online', error: '' }); remote.send({ type: 'state' }) }
  current.onmessage = event => {
    const packet = JSON.parse(event.data)
    if (packet.type === 'state') update({ state: packet.state })
    const entry = pending.get(packet.id)
    if (entry) { clearTimeout(entry.timer); pending.delete(packet.id); if (packet.type === 'error') entry.reject(new Error(packet.error)); else entry.resolve(packet.result) }
    if (packet.type === 'error') update({ error: packet.error })
  }
  current.onclose = event => {
    if (socket !== current) return
    socket = null
    for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(new Error('Disconnected.')) }
    pending.clear()
    settingTimers.forEach(clearTimeout); settingTimers.clear()
    settingValues.clear()
    if (event.code === 4001) { update({ status: 'unpaired', error: 'Pair again to reconnect.' }); return }
    if (event.code === 4002) { update({ status: 'offline', error: 'Another phone took control. Tap Reconnect to take over.' }); return }
    update({ status: 'offline' })
    if (!document.hidden) retry = setTimeout(async () => {
      try { const session = await api('/api/session'); if (!session.paired) { update({ status: 'unpaired' }); return } } catch { /* Retry while the companion restarts. */ }
      connect()
    }, reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, 6000)
  }
  current.onerror = () => current.close()
}
export const remote = {
  async start() {
    if (started) return
    started = true
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { this.send({ type: 'release' }); socket?.close(); clearTimeout(retry) }
      else if (snapshot.status !== 'unpaired') connect()
    })
    window.addEventListener('pagehide', () => { this.send({ type: 'release' }); socket?.close() })
    window.addEventListener('blur', () => this.send({ type: 'release' }))
    const token = new URLSearchParams(location.hash.slice(1)).get('pair')
    if (token) history.replaceState(null, '', location.pathname)
    try {
      if (token) await api('/api/pair', { token })
      const session = await api('/api/session')
      if (session.paired) connect(); else update({ status: 'unpaired' })
    } catch (error) { update({ status: 'unpaired', error: (error as Error).message }) }
  },
  async pair(code: string) { await api('/api/pair', { code }); update({ error: '' }); connect() },
  reconnect: connect,
  clearError() { update({ error: '' }) },
  request(command: Command): Promise<unknown> {
    if (socket?.readyState !== WebSocket.OPEN) return Promise.reject(new Error('Computer is disconnected.'))
    if (socket.bufferedAmount > 32000 || pending.size > 80) return Promise.reject(new Error('Connection is busy.'))
    const id = ++sequence
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('The computer did not respond.')); }, 16000)
      pending.set(id, { resolve, reject, timer })
      socket!.send(JSON.stringify({ id, command }))
    })
  },
  send(command: Command) { void this.request(command).then(result => { if (command.type === 'state') update({ state: result as ComputerState }) }).catch(error => { if (!['move','scroll','release'].includes(command.type)) update({ error: error.message }) }) },
  setting(type: 'volume' | 'brightness', value: number) {
    settingValues.set(type, Math.round(value))
    if (settingTimers.has(type)) return
    settingTimers.set(type, setTimeout(() => {
      settingTimers.delete(type)
      const latest = settingValues.get(type)
      settingValues.delete(type)
      if (latest !== undefined) this.send({ type, value: latest })
    }, type === 'brightness' ? 180 : 80))
  },
  async logout() { await api('/api/logout', {}); socket?.close(); clearTimeout(retry); update({ status: 'unpaired' }) },
}
export function useRemote() { return useSyncExternalStore(fn => { listeners.add(fn); return () => listeners.delete(fn) }, () => snapshot) }
