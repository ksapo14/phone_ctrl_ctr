param(
  [Parameter(Mandatory=$true)][ValidatePattern('^\d{1,3}(\.\d{1,3}){3}$')][string]$LanIp
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$certs = Join-Path $project 'certs'
$private = Join-Path $env:USERPROFILE '.phone-control'
New-Item -ItemType Directory -Force -Path $certs, $private | Out-Null
$caKey = Join-Path $private 'rootCA-key.pem'
$caCert = Join-Path $private 'rootCA.pem'
$serverKey = Join-Path $private 'server-key.pem'
$serverCert = Join-Path $certs 'server.pem'
$request = Join-Path $certs 'server.csr'
$extensions = Join-Path $certs 'server.ext'

if ((Test-Path $caKey) -xor (Test-Path $caCert)) { throw 'The local CA is incomplete. Restore both CA files before regenerating the certificate.' }
if (!(Test-Path $caKey)) {
  & openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes -keyout $caKey -out $caCert -subj '/CN=Phone Control Local CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
  if ($LASTEXITCODE -ne 0) { throw 'Could not create the local certificate authority.' }
}

& openssl req -new -newkey rsa:2048 -nodes -keyout $serverKey -out $request -subj "/CN=$LanIp"
if ($LASTEXITCODE -ne 0) { throw 'Could not create the server key.' }
@(
  'basicConstraints=critical,CA:FALSE'
  'keyUsage=critical,digitalSignature,keyEncipherment'
  'extendedKeyUsage=serverAuth'
  "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:$LanIp"
) | Set-Content -LiteralPath $extensions -Encoding ascii
& openssl x509 -req -in $request -CA $caCert -CAkey $caKey -CAcreateserial -out $serverCert -days 365 -sha256 -extfile $extensions
if ($LASTEXITCODE -ne 0) { throw 'Could not sign the server certificate.' }
Copy-Item -LiteralPath $caCert -Destination (Join-Path $certs 'rootCA.pem') -Force
Set-Content -LiteralPath (Join-Path $certs 'server-key.path') -Value $serverKey -Encoding ascii
& openssl x509 -in $caCert -outform DER -out (Join-Path $certs 'rootCA.cer')
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the iPhone certificate.' }
Remove-Item -LiteralPath $request, $extensions -Force
& openssl verify -CAfile (Join-Path $certs 'rootCA.pem') $serverCert
if ($LASTEXITCODE -ne 0) { throw 'Server certificate verification failed.' }
Write-Host "HTTPS certificate covers localhost, 127.0.0.1, and $LanIp."
Write-Host "Public iPhone CA: $(Join-Path $certs 'rootCA.cer')"
Write-Host "Private keys: $private"
