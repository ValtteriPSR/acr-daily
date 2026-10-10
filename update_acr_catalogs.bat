@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo U W A G A: Aktualizacja katalogow ID aut i OS-ow.
echo Zrob kopie katalogu serwera i potwierdz zawartosc upstream.
choice /M "Czy chcesz zaktualizowac katalogi po sprawdzeniu zmian"
if errorlevel 2 exit /b 1
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% "tools\update_acr_catalogs.py" --apply
pause
exit /b 0
:fail
pause
exit /b 1
