@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
echo Sprawdzam i przygotowuje pliki ACR Daily (jednorazowo, potrzebny Internet)...
%PYRUN% "tools\vendor_acr_daily.py" --download
if errorlevel 1 goto fail
%PYRUN% "client\run_club.py"
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Uruchomienie klienta nie powiodlo sie.
pause
exit /b 1
