@echo off
setlocal
cd /d "%~dp0"
if not exist "certs\server.pem" goto run
if not exist "certs\rootCA.pem" goto run
set "PHONE_TLS_CERT=%~dp0certs\server.pem"
set "NODE_EXTRA_CA_CERTS=%~dp0certs\rootCA.pem"
if exist "certs\server-key.path" for /f "usebackq delims=" %%K in ("certs\server-key.path") do set "PHONE_TLS_KEY=%%K"
if not defined PHONE_TLS_KEY set "PHONE_TLS_KEY=%USERPROFILE%\.phone-control\server-key.pem"
if not exist "%PHONE_TLS_KEY%" if exist "certs\server-key.pem" set "PHONE_TLS_KEY=%~dp0certs\server-key.pem"
if not exist "%PHONE_TLS_KEY%" goto missing
call "%~dp0TrustHttps.cmd" --quiet
if errorlevel 1 goto trustfailed
:run
call npm start
pause
exit /b
:missing
echo HTTPS key not found: %PHONE_TLS_KEY%
echo Rerun scripts\setup-https.ps1 for your current LAN IP.
pause
exit /b 1
:trustfailed
echo HTTPS trust setup failed. Run TrustHttps.cmd and try again.
pause
exit /b 1
