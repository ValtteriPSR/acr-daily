@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
%PYRUN% -m unittest discover -s tests -v
if errorlevel 1 goto fail
echo.
echo WSZYSTKIE TESTY PRZESZLY.
pause
exit /b 0
:fail
echo.
echo TESTY NIE PRZESZLY, zobacz bledy powyzej.
pause
exit /b 1
