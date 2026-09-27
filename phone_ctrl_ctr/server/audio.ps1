param([string]$DeviceName = 'CABLE Input')
$ErrorActionPreference = 'Stop'
try {
  Add-Type -Path (Join-Path $PSScriptRoot 'PhoneAudio.cs')
  [PhoneAudio]::Run($DeviceName)
} catch {
  [Console]::Error.WriteLine($_.Exception.GetBaseException().Message)
  exit 1
}
