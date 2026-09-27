$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -Path (Join-Path $PSScriptRoot 'WindowsControl.cs')
$appMap = @{}
$candidates = @{
  chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
  vscode = @("$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe", "$env:ProgramFiles\Microsoft VS Code\Code.exe")
  spotify = @("$env:APPDATA\Spotify\Spotify.exe")
  chatgpt = @()
  explorer = @("$env:WINDIR\explorer.exe")
  cmd = @("$env:WINDIR\System32\cmd.exe")
}
foreach ($name in $candidates.Keys) {
  foreach ($candidate in $candidates[$name]) { if (Test-Path -LiteralPath $candidate) { $appMap[$name] = @{path=$candidate}; break } }
}
try {
  $startApps = @(Get-StartApps)
  foreach ($entry in @(@{key='chatgpt';pattern='^ChatGPT$'}, @{key='spotify';pattern='^Spotify'}, @{key='chrome';pattern='^Google Chrome$'}, @{key='vscode';pattern='^Visual Studio Code$'})) {
    if (!$appMap.ContainsKey($entry.key)) {
      $match = $startApps | Where-Object { $_.Name -match $entry.pattern -and $_.AppID -like '*!*' } | Select-Object -First 1
      if ($match) { $appMap[$entry.key] = @{appId=$match.AppID} }
    }
  }
} catch {}
# Optional local-only overrides. Nothing from a phone becomes a path or command.
$configPath = Join-Path $PSScriptRoot 'apps.local.json'
if (Test-Path -LiteralPath $configPath) {
  $overrides = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
  foreach ($property in $overrides.PSObject.Properties) {
    if ($candidates.ContainsKey($property.Name) -and (Test-Path -LiteralPath $property.Value -PathType Leaf)) { $appMap[$property.Name] = @{path=[string]$property.Value} }
  }
}
function Get-Brightness {
  try { $screen = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop | Where-Object Active | Select-Object -First 1; if ($screen) { return [int]$screen.CurrentBrightness } } catch {}
  return [WindowsControl]::MonitorBrightness(-1)
}
function Set-Brightness([int]$level) {
  try {
    $screens = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop | Where-Object Active)
    if ($screens.Count) { foreach ($screen in $screens) { $result = Invoke-CimMethod -InputObject $screen -MethodName WmiSetBrightness -Arguments @{Timeout=[uint32]0;Brightness=[byte]$level}; if ($result.ReturnValue -ne 0) { throw 'Brightness change failed' } }; return }
  } catch {}
  if ([WindowsControl]::MonitorBrightness($level) -lt 0) { throw 'This display does not expose brightness control. Enable DDC/CI on an external monitor if supported.' }
}
while ($null -ne ($line = [Console]::ReadLine())) {
  $request = $null
  try {
    $request = $line | ConvertFrom-Json
    $command = $request.command
    $result = $null
    switch ($command.type) {
      'state' {
        $volume = $null; try { $volume = [WindowsControl]::Volume() } catch {}
        $brightness = Get-Brightness
        $result = @{volume=$volume;brightness=$(if($brightness -ge 0){$brightness}else{$null});windows=@([WindowsControl]::Windows());apps=@($appMap.Keys)}
      }
      'windows' { $result = @([WindowsControl]::Windows()) }
      'launch' {
        $app = $appMap[[string]$command.app]
        if (!$app) { throw 'This app is not installed or was not found. Set its path in server/apps.local.json.' }
        if ($app.path) { Start-Process -FilePath $app.path | Out-Null } else { Start-Process -FilePath "$env:WINDIR\explorer.exe" -ArgumentList "shell:AppsFolder\$($app.appId)" | Out-Null }
      }
      'move' { [WindowsControl]::Move([int]$command.dx,[int]$command.dy) }
      'scroll' { [WindowsControl]::Scroll([int]$command.dx,[int]$command.dy) }
      'click' { [WindowsControl]::Click([string]$command.button) }
      'doubleClick' { [WindowsControl]::DoubleClick([string]$command.button) }
      'button' { [WindowsControl]::Button([string]$command.button,[bool]$command.down) }
      'release' { [WindowsControl]::Release() }
      'gesture' { [WindowsControl]::Gesture([string]$command.name) }
      'media' { [WindowsControl]::Media([string]$command.action) }
      'zoom' { [WindowsControl]::Zoom([int]$command.delta) }
      'focus' { [WindowsControl]::Focus([string]$command.id) }
      'volume' { [WindowsControl]::SetVolume([int]$command.value) }
      'brightness' { Set-Brightness ([int]$command.value) }
      default { throw 'Unsupported command' }
    }
    [Console]::WriteLine((@{id=$request.id;ok=$true;result=$result} | ConvertTo-Json -Compress -Depth 6))
  } catch { [Console]::WriteLine((@{id=$request.id;ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress -Depth 6)) }
}
[WindowsControl]::Release()
