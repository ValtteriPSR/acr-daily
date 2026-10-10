@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
echo Sprawdzam i przygotowuje pliki ACR Daily (jednorazowo, potrzebny Internet)...
%PYRUN% "tools\vendor_acr_daily.py" --download
if errorlevel 1 goto fail
%PYRUN% "tools\check_weekend_integrity.py"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Ustawienia zgodne.
) else (
  echo Walidacja wykryla niezgodnosc lub blad.
)
pause
exit /b %RC%
:fail
pause
exit /b 1
