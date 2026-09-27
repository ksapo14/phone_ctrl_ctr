# Phone Control

A minimal black-and-white iPhone remote for a Windows computer. The Node companion serves the React interface and sends authenticated WebSocket commands to one persistent Windows PowerShell helper. No cloud service or .NET SDK is needed.

## Start on the computer

Requirements: Windows 10/11, Node.js 22.17 or newer, and Windows PowerShell 5.1 (included with Windows). Run as your normal desktop user.

```powershell
npm install
npm start
```

After installing dependencies, you can also double-click **StartCompanion.cmd**. It builds the UI, starts the companion on port **8787**, and opens the computer pairing page. Keep the terminal running. Stop it with Ctrl+C. On subsequent runs, `npm run companion` skips the build. Launching again reopens the existing companion instead of starting a second server. If another application owns the port, choose another port with `PORT`.

If Windows Firewall prompts, allow Node.js on **private networks**. The app does not change firewall rules. Connect the phone and PC to the same trusted Wi-Fi network; guest-network isolation and some VPNs can prevent a connection.

## Pair the iPhone

1. Scan the computer page's QR code with the iPhone Camera and tap the link. Pairing finishes automatically and opens the controls.
2. Alternatively, open the address printed on the computer page in Safari. The computer pairing page opens when the phone requests a code. Enter the six-digit code from the computer.
3. If the PC has multiple network adapters, choose the Wi-Fi address on the computer page before scanning.
4. Optionally use Safari's **Share → Add to Home Screen**. Dynamic viewport sizing and safe-area padding accommodate the iPhone 17 Pro's screen, Dynamic Island and home indicator in portrait and landscape.

The QR credential and manual code expire after five minutes and rotate after every successful pairing. A paired session lasts eight hours and is invalidated when the server restarts. **Disconnect phones & reset pairing** immediately revokes all sessions. One phone controls the computer at a time; another paired phone can take over. Pairing from a saved Home Screen app may be needed separately because Safari can use separate storage.

By default the service uses HTTP/WebSocket on a **trusted private LAN** without encryption. Optional HTTPS/WSS is available and required for phone microphone streaming; see [Phone microphone setup](server/PHONE-MIC.md). Do not forward its port or use it on an untrusted/shared network. The computer admin page is restricted to loopback access and a startup secret. Phones receive HttpOnly session cookies. WebSocket upgrades validate the host, origin and session. Phone input is restricted to a fixed command schema and app allowlist; no arbitrary command strings or filesystem paths are accepted.

## Controls

- **App:** Chrome, VS Code, ChatGPT, Spotify, File Explorer and Command Prompt. Installed Store apps are detected through the Start menu. Unavailable apps are dimmed. Each button starts the desktop app on the computer.
- **Window:** swipe or drag between cards containing real open-window titles. Settling on a card activates that window. Dots and arrow keys also work. Window titles update periodically; these are title cards, not screen streaming or live thumbnails.
- **Trackpad:** the blank area is the touch surface. The two bottom buttons support press/hold for left and right mouse buttons. You can hold left click with one finger while moving another finger on the surface.
- **Voice:** hold the microphone for 250ms to hold mouse button 4 (XBUTTON1); releasing releases it. A short tap double-clicks button 4 for Wispr hands-free mode. Blue reflects the requested shortcut state. **Use phone mic** optionally streams your iPhone microphone to Wispr through VB-CABLE. This requires trusted HTTPS and a one-time Windows audio setup: see [Phone microphone setup](server/PHONE-MIC.md), then use `StartPhoneMicrophone.cmd`.
- **Top left:** speaker volume. **Top right:** display brightness. Tap to expand the ticks, then drag inward to increase or outward to decrease. Values clamp to 0–100%. The 10px threshold avoids accidental changes. Wheel and arrow keys work too. Current computer values load on connection and refresh periodically.
- **Bottom center:** a single play/pause media button sends the Windows media toggle key. The microphone gain and haptic corner sliders have been removed.
- **X / Escape:** close the mode and return to the heading selector.

### Trackpad gestures

| Gesture | Computer action |
| --- | --- |
| One finger move | Move pointer |
| One finger tap / double tap | Left click / double click |
| Double tap, hold second tap, drag | Drag with left button held |
| Two finger tap | Right click |
| Two finger slide | Vertical/horizontal scroll |
| Pinch / spread | Ctrl + mouse wheel zoom in apps that support it |
| Three finger swipe left/right | Cycle open windows |
| Three finger swipe up/down | Task View / show desktop |
| Three finger tap | Windows Search |
| Four finger swipe left/right | Change virtual desktop |
| Four finger swipe up/down | Task View / show desktop |
| Four finger tap | Notification center |

These map standard Windows actions, rather than registering a physical Precision Touchpad driver. Windows' custom touchpad mappings are not read. iOS can reserve system gestures (especially three-finger editing gestures), so a Safari page cannot guarantee every physical touchpad gesture. Pointer commands are batched once per animation frame; stale input is discarded after disconnect. Hidden pages, cancelled gestures, connection loss, takeover and revocation release held mouse buttons.

Brightness first uses the built-in display's WMI interface, then tries external displays through DDC/CI. Some monitors, docks and drivers do not support either; the control displays **—** when unavailable. The helper runs at normal user privilege, so Windows can block input to elevated programs, UAC prompts and the lock screen. Do not run as administrator just to bypass those restrictions.

## App detection and development

For the standalone FunctionGemma voice-command dataset, H200 training script, Slurm launcher and evaluator, see [training/README.md](training/README.md). Voice-command model inference and speech recognition are not wired into the app yet.

For a custom install location, copy `server/apps.example.json` to `server/apps.local.json` and edit the absolute executable paths. Only the six predefined app IDs can be overridden. The config is read locally at startup and cannot be edited from the phone.

```powershell
npm run build       # TypeScript + production bundle
npm run lint        # Frontend checks
npm test            # Pairing/authentication/protocol + gesture tests
node server/native-check.mjs # Windows capability check; writes current volume/brightness back unchanged
node server/index.mjs --mock --no-open # Simulated computer for interface testing
```

Use `npm start` for a complete phone connection; Vite's standalone `npm run dev` is only a frontend preview and does not provide the pairing API. Set `$env:PORT = '8787'` to choose a port. Set `$env:PHONE_HOST` to a LAN hostname/IP if automatic address discovery chooses the wrong adapter. Open the full computer link printed in the terminal to recover admin access.

## Implementation references

- [Microsoft: Windows touch gestures](https://support.microsoft.com/en-us/windows/hardware/input-devices/touch-gestures-for-windows)
- [Microsoft: SendInput and privilege restrictions](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- [Microsoft: brightness through WMI](https://devblogs.microsoft.com/scripting/use-powershell-to-report-and-set-monitor-brightness/)
- [Apple: handling touch and gesture events in Safari](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/HandlingEvents/HandlingEvents.html)

Automated checks cover the protocol and gesture recognition. Actual radio latency, iOS gesture interception, monitor support and app behavior still require testing on the paired iPhone and target PC.
