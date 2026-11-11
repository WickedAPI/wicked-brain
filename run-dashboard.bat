@echo off
rem Double-click launcher for the Wicked Brain dashboard.
rem Set WICKED_BRAIN_VAULT_PATH (or put it in %USERPROFILE%\.config\wicked-brain\.env) first.
rem If a server is already running on the port, this stops it and starts a fresh one.
rem Close the "Wicked Brain Dashboard" window to stop it.

setlocal
set "REPO=%~dp0"
if "%PORT%"=="" set "PORT=8420"

if "%WICKED_BRAIN_VAULT_PATH%"=="" (
  echo WICKED_BRAIN_VAULT_PATH is not set. Set it to the folder of your vault, then run this again.
  pause
  exit /b 1
)

cd /d "%REPO%"

echo Checking for an existing dashboard on port %PORT%...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($c) { $c | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Write-Host ('Stopping existing process ' + $_ + '...'); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500 }"

start "Wicked Brain Dashboard" cmd /k "uv run uvicorn dashboard.server:app --port %PORT%"
timeout /t 2 /nobreak >nul
start "" "http://localhost:%PORT%"
