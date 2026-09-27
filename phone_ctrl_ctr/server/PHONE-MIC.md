# Use your iPhone as the laptop microphone

Voice now has **Use phone mic** under the microphone button. Audio flows from **iPhone Safari → encrypted companion connection → CABLE Input → CABLE Output → Wispr**. Your Windows speaker output can stay on the monitors. This does not stream laptop audio back to the phone.

## 1. Install a virtual microphone

Install [VB-CABLE from VB-Audio](https://vb-audio.com/Cable/) on Windows and restart if requested. This driver is not bundled or installed automatically by Phone Control.

- **CABLE Input** is the playback endpoint. The companion sends phone audio here.
- **CABLE Output** is the recording endpoint. Choose it as **Wispr's microphone**, under **Show other devices** if needed. See [Wispr's microphone selection guide](https://docs.wisprflow.ai/articles/8884408990).

Keep the Windows default playback device on your monitors/speakers. Do not enable “Listen to this device” for CABLE Output. Other PC apps can use CABLE Output as their microphone too.

The helper only opens a device matching `CABLE Input`; it never falls back to speakers. Advanced setups can set `PHONE_AUDIO_DEVICE` to another virtual cable's playback-device name (substring match).

## 2. Set up trusted HTTPS

Safari requires a secure context for microphone access. A plain `http://192.168...` address cannot capture your phone microphone. Bypassing a certificate warning is not a substitute for a trusted certificate.

Run the project setup script in PowerShell from the project root. It uses OpenSSL to create a local certificate authority, then issues a server certificate for localhost and the current laptop LAN address. The CA and server private keys live in `%USERPROFILE%\.phone-control`, outside the OneDrive project. Only public certificates and the key's location are copied into the gitignored `certs` folder.

Run PowerShell from the project root:

```powershell
# Replace with your laptop's Wi-Fi IPv4 address from the pairing page.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-https.ps1 -LanIp 192.168.1.50
certutil -user -addstore Root certs/rootCA.pem
```

The launchers also call `TrustHttps.cmd` to install the CA for the Windows user running the launcher. If the desktop browser reports an untrusted certificate, run `TrustHttps.cmd` directly, accept the Windows certificate dialog if shown, and reload the page. This can repair trust without restarting the server.

Transfer **only `certs/rootCA.cer`** to your own iPhone, for example through OneDrive. Open it and install its profile in Settings, then enable full trust under **Settings → General → About → Certificate Trust Settings**. This trusts certificates issued by your local CA. Never transfer the private keys in `%USERPROFILE%\.phone-control`. Remove the profile when you no longer need this CA.

The `certs/` directory is gitignored and is not served by the app. Reserve your laptop's IP in the router, or rerun the script when its IP changes. The script reuses the same CA so the iPhone does not need to trust a new CA each time.

## 3. Start the HTTPS companion

Stop the existing companion with Ctrl+C. Double-click **StartCompanion.cmd** or **StartPhoneMicrophone.cmd** after the certificates exist. Both launch HTTPS and open the pairing page.

Equivalent commands:

```powershell
$env:PHONE_TLS_CERT = (Resolve-Path certs/server.pem).Path
$env:PHONE_TLS_KEY = Join-Path $env:USERPROFILE '.phone-control\server-key.pem'
$env:NODE_EXTRA_CA_CERTS = (Resolve-Path certs/rootCA.pem).Path
npm start
```

The extra CA lets Node verify its own HTTPS connection when reusing a companion; verification is not disabled. Scan the new **HTTPS** QR code and pair again. Replace old HTTP bookmarks. Close the old HTTP server before using the same port for HTTPS.

## 4. Use Voice

1. Select **CABLE Output** in Wispr on the laptop.
2. In Voice on the phone, tap **Use phone mic** and allow Safari microphone access.
3. Wait for **Phone mic on / Streaming** before speaking.
4. Hold the large mic button for push-to-talk, or tap for Wispr hands-free, as before.
5. Tap **Phone mic on** to stop streaming.

Audio streams continuously while enabled, even between dictation sessions, so opening the microphone does not clip the start of a sentence. The small label shows streaming; the large blue icon still reflects the requested Wispr shortcut state. No audio is recorded to files or sent to a cloud service by the companion. Wispr's own audio processing is separate.

Closing Voice, hiding Safari, locking the phone, disconnecting, revoking access or another phone taking control stops the stream. Re-enable with a tap when you return. Keep the phone unlocked with Voice visible; iOS can suspend background browser audio. The laptop must stay awake with its lid closed. Both devices must be on the same private Wi-Fi network.

## Troubleshooting

- **HTTPS required:** use the new HTTPS QR code and trust the CA on your iPhone. Do not bypass browser certificate warnings.
- **Virtual microphone not found:** install/restart VB-CABLE; verify CABLE Input exists in Windows playback devices.
- **Streaming but Wispr hears nothing:** explicitly select CABLE Output in Wispr. Check its Windows recording level meter while speaking. Restart Wispr if its device list was cached before driver installation.
- **Windows audio error:** enable the cable and allow mono PCM at 48 kHz; close any app holding it in exclusive mode.
- **Choppy or stopped audio:** keep Voice foregrounded, improve Wi-Fi, then reconnect. Backlogged streams stop rather than playing stale speech.

## Implementation and verification

AudioWorklet emits mono PCM16 at 48 kHz in 20 ms frames (~96 KB/s). A dedicated authenticated WSS connection accepts only the active controller. The Windows helper has eight playback buffers, targets the cable by name, and runs separately from mouse commands. Expiry, revocation, takeover and stalled streams close it.

Tests cover HTTPS pairing/cookies, audio authorization, frame validation/forwarding, takeover/revocation cleanup, PCM conversion and cancellation during microphone permission. The Windows helper compiles. End-to-end iPhone → VB-CABLE → Wispr testing still requires the driver, trusted certificates and phone permission on your devices.
