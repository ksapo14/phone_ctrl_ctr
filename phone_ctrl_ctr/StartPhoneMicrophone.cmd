@echo off
setlocal
cd /d "%~dp0"
if not exist "certs\server.pem" goto setup
if not exist "certs\rootCA.pem" goto setup
set "PHONE_TLS_CERT=%~dp0certs\server.pem"
if exist "certs\server-key.path" for /f "usebackq delims=" %%K in ("certs\server-key.path") do set "PHONE_TLS_KEY=%%K"
if not defined PHONE_TLS_KEY set "PHONE_TLS_KEY=%USERPROFILE%\.phone-control\server-key.pem"
if not exist "%PHONE_TLS_KEY%" if exist "certs\server-key.pem" set "PHONE_TLS_KEY=%~dp0certs\server-key.pem"
if not exist "%PHONE_TLS_KEY%" goto setup
set "NODE_EXTRA_CA_CERTS=%~dp0certs\rootCA.pem"
call "%~dp0TrustHttps.cmd" --quiet
if errorlevel 1 goto trustfailed
call npm start
pause
exit /b
:trustfailed
echo HTTPS trust setup failed. Run TrustHttps.cmd and try again.
pause
exit /b 1
:setup
echo Phone microphone requires HTTPS certificates and VB-CABLE.
echo Follow server\PHONE-MIC.md, then run this launcher again.
pause
exit /b 1
