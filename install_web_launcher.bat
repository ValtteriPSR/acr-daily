@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "dist\ACR-Club-Launcher.exe" (
  echo Brak dist\ACR-Club-Launcher.exe
  echo Najpierw uruchom build_web_launcher_exe.bat
  pause
  exit /b 1
)
echo Instalacja dla biezacego uzytkownika Windows...
"dist\ACR-Club-Launcher.exe" --install
if errorlevel 1 (
  echo Instalacja nieudana.
  pause
  exit /b 1
)
echo Launcher zainstalowany. Wejdz na http://127.0.0.1:8790/
pause
