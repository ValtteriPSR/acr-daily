@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo ACR RALLY CLUB - LOKALNY SERWER
echo ==========================================
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "server_local\server.py"
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Uruchomienie serwera nie powiodlo sie.
pause
exit /b 1
