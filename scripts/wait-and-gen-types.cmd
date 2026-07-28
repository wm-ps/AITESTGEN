@echo off
cd /d "%~dp0.."
set STATUS_FILE=%TEMP%\aitestgen-typegen-status.txt
set RETRIES=0
:waitapi
curl -s -o nul -w "%%{http_code}" http://localhost:8000/openapi.json > "%STATUS_FILE%" 2>nul
set /p API_UP=<"%STATUS_FILE%"
if "%API_UP%"=="200" goto apiready
set /a RETRIES+=1
if %RETRIES% GEQ 30 exit /b 0
timeout /t 1 /nobreak >nul
goto waitapi
:apiready
if not exist apps\web\node_modules exit /b 0
pushd apps\web
call npm run generate:api-types
popd
