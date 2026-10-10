@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "tools\make_demo_event.py"
if errorlevel 1 goto fail
%PYRUN% "server_local\server.py" --import-event "examples\grecja-local-demo.json"
if errorlevel 1 goto fail
echo.
echo Rajd testowy dodany. Uruchom start_local_server.bat
pause
exit /b 0
:fail
echo.
echo BLAD. Nie dodano rajdu.
pause
exit /b 1
