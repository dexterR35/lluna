@echo off
setlocal
cd /d "%~dp0"
if not exist "midgardEnv\Scripts\python.exe" (
  echo Midgard environment is missing. Run install.bat first.
  exit /b 2
)
"midgardEnv\Scripts\python.exe" -c "import struct,sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
if errorlevel 1 (
  echo Midgard requires a 64-bit Python 3.12 environment. Run install.bat to repair it.
  exit /b 3
)
"midgardEnv\Scripts\python.exe" midgard.py %*
exit /b %errorlevel%
