@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Najpierw zamknij serwer (Ctrl+C), aby uniewaznic stare sesje.
choice /M "Czy serwer jest zamkniety"
if errorlevel 2 exit /b 1
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "tools\rotate_admin_key.py"
pause
exit /b 0
:fail
pause
exit /b 1
