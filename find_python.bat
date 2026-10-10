@echo off
rem Find a working Python >= 3.11 without assuming Python 3.13 is installed.
rem Called from the other .bat files via CALL; sets PYRUN for the caller.
set "PYRUN="
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
  if not errorlevel 1 (
    set "PYRUN="%~dp0.venv\Scripts\python.exe""
    goto :found
  )
)
py -3.13 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 (
  set "PYRUN=py -3.13"
  goto :found
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 (
  set "PYRUN=py -3"
  goto :found
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 (
  set "PYRUN=python"
  goto :found
)
python3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if not errorlevel 1 (
  set "PYRUN=python3"
  goto :found
)
echo.
echo BLAD: Nie wykryto dzialajacego Pythona 3.11 lub nowszego.
echo Sprawdz w CMD: py --list   oraz   python --version
echo Oficjalne pobieranie: https://www.python.org/downloads/windows/
exit /b 1
:found
echo Wykryto: %PYRUN%
%PYRUN% --version
exit /b 0
