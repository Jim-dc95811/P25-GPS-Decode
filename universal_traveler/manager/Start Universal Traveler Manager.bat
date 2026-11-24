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
%PYEXE% -c "import paramiko, PIL" >nul 2>nul
if errorlevel 1 (
  echo Installing the helpers this app needs (SSH + image), one time please wait...
  %PYEXE% -m pip install paramiko Pillow
)
%PYEXE% -c "import paramiko, PIL" >nul 2>nul
if errorlevel 1 (
  echo Could not install the helpers automatically. Run this once:  %PYEXE% -m pip install paramiko Pillow
  pause ^& exit /b
)
start "" %PYEXE% "%~dp0System Files\universal_traveler_manager.py"
endlocal
