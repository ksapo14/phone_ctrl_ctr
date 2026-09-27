@echo off
cd /d "%~dp0"
if not exist "certs\server.pem" goto setup
if not exist "certs\server-key.pem" goto setup
if not exist "certs\rootCA.pem" goto setup
set "PHONE_TLS_CERT=%~dp0certs\server.pem"
set "PHONE_TLS_KEY=%~dp0certs\server-key.pem"
set "NODE_EXTRA_CA_CERTS=%~dp0certs\rootCA.pem"
call npm start
pause
exit /b
:setup
echo Phone microphone requires HTTPS certificates and VB-CABLE.
echo Follow server\PHONE-MIC.md, then run this launcher again.
pause
