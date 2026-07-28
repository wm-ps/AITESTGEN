@echo off
setlocal
cd /d "%~dp0.."
set STATUS_FILE=%TEMP%\aitestgen-dev-up-status.txt

rem Web has zero dependency on Postgres/Temporal/Vault, so kick it off before
rem the docker compose wait below instead of after it. (Tried also prewarming
rem `uv sync` for api/discovery-worker/generation-worker here in parallel -
rem measured slower in practice: 3 concurrent syncs + npm install + docker
rem starting at once saturates CPU/disk and slows everything down instead.)
call :check_url http://localhost:5173 WEB_UP
if not "%WEB_UP%"=="200" (
  echo [dev-up] starting web in parallel with docker...
  start "AITestGen Web" cmd /k "cd apps\web && (if not exist node_modules npm install) && npm run dev"
)

echo [dev-up] docker compose up -d --wait ...
docker compose up -d --wait
if errorlevel 1 (
  echo [dev-up] docker compose failed - is Docker running?
  exit /b 1
)

call :check_url http://localhost:8000/openapi.json API_UP
if not "%API_UP%"=="200" (
  echo [dev-up] starting API...
  start "AITestGen API" cmd /k "uv run --env-file .env --package api uvicorn api.main:app --reload --port 8000"
)

tasklist /v /fi "windowtitle eq AITestGen Discovery Worker" 2>nul | findstr /i "cmd.exe" >nul
if errorlevel 1 (
  echo [dev-up] starting discovery worker...
  start "AITestGen Discovery Worker" cmd /k "scripts\run-discovery-worker.cmd"
)

tasklist /v /fi "windowtitle eq AITestGen Generation Worker" 2>nul | findstr /i "cmd.exe" >nul
if errorlevel 1 (
  echo [dev-up] starting generation worker...
  start "AITestGen Generation Worker" cmd /k "scripts\run-generation-worker.cmd"
)

rem Best-effort, backgrounded: refresh generated API types once the API
rem responds. Web is already up by now - this never blocks it.
start /b "" cmd /c "scripts\wait-and-gen-types.cmd" >nul 2>&1

echo.
echo [dev-up] AITestGen is up (or was already running):
echo   Web:      http://localhost:5173
echo   API:      http://localhost:8000/docs
echo   Temporal: http://localhost:8233
echo   Sign-in:  dev@example.com / devpassword123
echo   Each process has its own titled window - close it to stop that process.
exit /b 0

:check_url
curl -s -o nul -w "%%{http_code}" "%~1" > "%STATUS_FILE%" 2>nul
set /p %2=<"%STATUS_FILE%"
exit /b 0
