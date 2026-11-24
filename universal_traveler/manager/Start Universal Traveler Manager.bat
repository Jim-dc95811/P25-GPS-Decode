@echo off
REM === Universal Traveler Manager ===
setlocal
set "PYEXE=py -3"
where py >nul 2>nul || set "PYEXE=python"
%PYEXE% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install it from python.org and tick "Add to PATH".
  pause ^& exit /b
)
REM Install the helpers best-effort (SSH + image). They are only needed for
REM "Set up a box" and "Make QR card", and the app reports if one is missing,
REM so NEVER block the window from opening on them.
%PYEXE% -c "import paramiko, PIL" >nul 2>nul || (
  echo Installing the helpers this app needs, one time please wait...
  %PYEXE% -m pip install paramiko Pillow
)
start "" %PYEXE% "%~dp0System Files\universal_traveler_manager.py"
endlocal
