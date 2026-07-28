@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3.12 install.py %*
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel% neq 0 (
  echo Python 3.12 was not found. Install 64-bit Python 3.12 and retry.
  exit /b 2
)

python install.py %*
exit /b %errorlevel%
