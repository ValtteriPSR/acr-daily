@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "tools\update_acr_catalogs.py" --check
pause
exit /b 0
:fail
pause
exit /b 1
