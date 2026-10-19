@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-win\Scripts\python.exe" (
  ".venv-win\Scripts\python.exe" scripts\start_web.py %*
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\start_web.py %*
) else (
  python scripts\start_web.py %*
)
if errorlevel 1 (
  echo.
  echo Startup failed. Read the diagnostic above and the README installation steps.
  pause
)
endlocal
