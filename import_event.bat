@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo Przeciagnij plik JSON na import_event.bat.
  echo Alternatywnie: import_event.bat "C:\sciezka\rajd.json"
  pause
  exit /b 2
)
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "server_local\server.py" --import-event "%~1"
if errorlevel 1 goto fail
echo.
echo Rajd zaimportowany.
pause
exit /b 0
:fail
echo.
echo BLAD importu rajdu.
pause
exit /b 1
