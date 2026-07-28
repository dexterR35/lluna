@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"

rem A py.exe command can exist even when it cannot resolve the classic
rem "-3.12" selector (for example, uv-managed runtimes use a vendor tag).
rem Verify every candidate before trying to launch the installer with it.
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_py_launcher

  rem Newer Python install managers may expose third-party runtimes with a
  rem vendor tag such as -V:Astral/CPython3.12.13 instead of plain -3.12.
  set "MIDGARD_PY_TAG="
  for /f "tokens=1" %%V in ('py -0 2^>nul') do (
    py %%V -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
    if !errorlevel! equ 0 set "MIDGARD_PY_TAG=%%V"
  )
  if defined MIDGARD_PY_TAG goto run_py_tag
)

where python3.12 >nul 2>nul
if %errorlevel% equ 0 (
  python3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python312
)

where python >nul 2>nul
if %errorlevel% equ 0 (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_python
)

rem Reuse an already-installed uv Python 3.12 without downloading anything.
set "MIDGARD_UV_PYTHON="
where uv >nul 2>nul
if %errorlevel% equ 0 (
  for /f "usebackq delims=" %%P in (`uv python find 3.12 2^>nul`) do set "MIDGARD_UV_PYTHON=%%P"
)
if defined MIDGARD_UV_PYTHON (
  "%MIDGARD_UV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_uv_python
)

echo Python 3.12 was not found.
echo Install 64-bit Python 3.12 for the current user or all users, then retry.
echo If Python 3.12 is managed by uv, check that "uv python find 3.12" succeeds.
exit /b 2

:run_py_launcher
py -3.12 install.py %*
exit /b %errorlevel%

:run_py_tag
py %MIDGARD_PY_TAG% install.py %*
exit /b %errorlevel%

:run_python312
python3.12 install.py %*
exit /b %errorlevel%

:run_python
python install.py %*
exit /b %errorlevel%

:run_uv_python
"%MIDGARD_UV_PYTHON%" install.py %*
exit /b %errorlevel%
