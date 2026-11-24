@echo off
cd /d "%~dp0"
set "PYEXE=py -3"
where py >nul 2>nul || set "PYEXE=python"
%PYEXE% -c "import numpy, scipy, sounddevice" 2>nul || (echo Installing numpy + scipy + sounddevice ... && %PYEXE% -m pip install numpy scipy sounddevice)
if not exist "%~dp0Maps" mkdir "%~dp0Maps"
set "LOOKOUT_MAP_ROOTS=%~dp0Maps"
echo.
echo ============================================================
echo   THE TRAVELER PC   -   Radio  -^>  Live Map
echo   P25 GPS off the air . your own offline maps . no cloud
echo   built by Claude McNally
echo ============================================================
echo.
echo Starting The Traveler PC ...
start "The Traveler PC - OTA decoder (listening to the radio)" cmd /k %PYEXE% "System Files\traveler_pc.py" --serve --self-gps
timeout /t 2 >nul
start "The Traveler PC - map server" cmd /k %PYEXE% "System Files\units_kml.py"
timeout /t 3 >nul
start "" http://localhost:8080
echo.
echo Two windows opened: the decoder (listening) and the map server.
echo Your browser should open The Traveler PC at http://localhost:8080
echo.
echo   - Wire the USB sound card to the radio's detector / discriminator audio.
echo   - Plug the Garmin USB in for your own position (MY POSITION).
echo   - Put your offline maps (.tpkx / .mbtiles) in the "Maps" folder beside this file.
echo.
echo Close those two windows to stop everything.
echo.
pause
