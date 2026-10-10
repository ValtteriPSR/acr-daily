@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ACR Rally Club - kompilacja EXE Windows x64
call "%~dp0find_python.bat"
if errorlevel 1 goto fail
echo Sprawdzam i przygotowuje pliki ACR Daily (jednorazowo, potrzebny Internet)...
%PYRUN% "tools\vendor_acr_daily.py" --download
if errorlevel 1 goto fail
%PYRUN% "tools\export_club_catalog.py"
if errorlevel 1 goto fail
echo Sprawdzam pelne zaleznosci Python launchera...
%PYRUN% "tools\verify_launcher_modules.py"
if errorlevel 1 goto fail
%PYRUN% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
  echo Instalacja PyInstaller - jednorazowo...
  %PYRUN% -m pip install pyinstaller
  if errorlevel 1 goto fail
)
%PYRUN% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ACR-Rally-Club ^
  --paths client ^
  --collect-submodules acr_daily ^
  --hidden-import acr_daily.settings ^
  --add-data "client\club_local\catalog.json;club_local" ^
  "client\run_club.py"
if errorlevel 1 goto fail
echo.
echo GOTOWE: dist\ACR-Rally-Club.exe
pause
exit /b 0
:fail
echo.
echo BUILD FAILED
pause
exit /b 1
