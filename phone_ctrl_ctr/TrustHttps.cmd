@echo off
setlocal
if not exist "%~dp0certs\rootCA.pem" goto missing
certutil -user -addstore Root "%~dp0certs\rootCA.pem"
set "trustResult=%errorlevel%"
if not "%trustResult%"=="0" goto failed
echo HTTPS certificate trust is installed for this Windows user.
echo Reload the companion page in your browser.
goto done
:missing
echo Local CA certificate is missing. Run the HTTPS setup first.
set "trustResult=1"
goto done
:failed
echo Windows could not install certificate trust. Accept the Windows certificate dialog if prompted.
:done
if /i not "%~1"=="--quiet" pause
exit /b %trustResult%
