import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, remote, useRemote } from './remote'

export function Connection({ children }: { children: ReactNode }) {
  const { status, error } = useRemote()
  const [code, setCode] = useState('')
  const [pairError, setPairError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { void remote.start() }, [])
  useEffect(() => { if (status === 'unpaired') void api('/api/pair/request', {}).catch(() => {}) }, [status])
  if (status === 'unpaired' || status === 'checking') return <main className="pair-screen">
    <h1>Connect to your computer</h1>
    <p>Scan the QR code on your computer, or enter its six-digit code.</p>
    <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setPairError('')
      try { await remote.pair(code) } catch (e) { setPairError((e as Error).message) } finally { setBusy(false) }
    }}>
      <input aria-label="Pairing code" placeholder="000000" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} required />
      <button disabled={busy || status === 'checking'}>{busy ? 'Connecting…' : 'Connect'}</button>
    </form>
    {(pairError || error) && <p role="alert">{pairError || error}</p>}
    <p className="connection-help">Keep the companion running on your PC. Both devices need the same Wi-Fi network.</p>
  </main>
  return <>{children}
    {status !== 'online' && <div className="connection-cover"><p>{status === 'connecting' ? 'Connecting…' : 'Computer disconnected'}</p><button onClick={() => remote.reconnect()}>Reconnect</button></div>}
    {error && <div className="connection-error" role="alert"><span>{error}</span><button onClick={() => remote.clearError()} aria-label="Dismiss error">×</button></div>}
  </>
}

type HostState = { urls: string[]; base: string; qr: string; code: string; expires: number; connected: number; requests: number; nativeError: string | null; ready: boolean; apps: string[] }
export function Companion() {
  const [data, setData] = useState<HostState | null>(null)
  const [error, setError] = useState('')
  const [base, setBase] = useState('')
  useEffect(() => {
    let active = true
    const key = new URLSearchParams(location.hash.slice(1)).get('admin')
    const ready = key ? api('/api/admin/unlock', { key }).then(() => history.replaceState(null, '', '/host')) : Promise.resolve()
    async function refresh() { try { await ready; const status = await api('/api/admin/status' + (base ? `?base=${encodeURIComponent(base)}` : '')); if (active) { setData(status); setError('') } } catch (e) { if (active) setError((e as Error).message) } }
    void refresh(); const timer = setInterval(refresh, 2000)
    return () => { active = false; clearInterval(timer) }
  }, [base])
  return <main className="companion-screen">
    <header><h1>Phone control</h1><p>{data?.connected ? 'Phone connected' : 'Ready to pair'}</p></header>
    {data && <>
      <img className="pair-qr" src={data.qr} alt="Scan with your iPhone camera to connect" />
      <p>Scan with your iPhone camera</p>
      <div className="pair-code">{data.code}</div>
      <p>Or enter this code on your phone. It refreshes every five minutes.</p>
      {data.urls.length > 1 && <select aria-label="Network address" value={data.base} onChange={event => setBase(event.target.value)}>{data.urls.map(url => <option key={url}>{url}</option>)}</select>}
      <a href={data.base} target="_blank" rel="noreferrer">{data.base}</a>
      {data.requests > 0 && <p role="status">A phone is waiting. Enter the code above to approve access.</p>}
      <p>{data.ready ? `${data.apps.length} apps available` : 'Starting the Windows helper…'}</p>
      {data.nativeError && <p role="alert">{data.nativeError}</p>}
      <button onClick={async () => { try { await api('/api/admin/reset', {}); setData(await api('/api/admin/status')) } catch (e) { setError((e as Error).message) } }}>Disconnect phones & reset pairing</button>
    </>}
    {error && <p role="alert">{error}</p>}
    <p className="connection-help">Use the same private Wi-Fi network. Allow Node.js on private networks if Windows Firewall asks. Keep this server running while using the phone.</p>
    <details className="audio-setup"><summary>Phone microphone setup</summary><p>Use HTTPS with a certificate trusted by your iPhone. Install VB-CABLE on Windows and choose CABLE Output as Wispr’s microphone. In Voice, tap Use phone mic, then allow Safari microphone access. Keep Voice open and the phone unlocked. See server/PHONE-MIC.md for setup commands.</p></details>
  </main>
}
