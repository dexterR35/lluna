@echo off
setlocal
cd /d "%~dp0"

if not exist "midgardEnv\Scripts\python.exe" (
  echo Midgard environment is missing. Run install.bat first.
  exit /b 2
)

"midgardEnv\Scripts\python.exe" midgard.py %*
exit /b %errorlevel%
