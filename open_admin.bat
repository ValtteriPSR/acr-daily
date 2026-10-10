@echo off
setlocal
if not exist "%~dp0server_local\admin_route.txt" (echo Najpierw uruchom start_local_server.bat & pause & exit /b 1)
set /p ACR_ROUTE=<"%~dp0server_local\admin_route.txt"
if not defined ACR_ROUTE (echo Najpierw uruchom start_local_server.bat & pause & exit /b 1)
start "" "http://127.0.0.1:8790%ACR_ROUTE%"
