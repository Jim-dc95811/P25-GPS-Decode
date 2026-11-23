@echo off
cd /d "%~dp0"
set "PYEXE=py -3"
where py >nul 2>nul || set "PYEXE=python"
%PYEXE% -c "import numpy, scipy, sounddevice" 2>nul || (echo Installing numpy + scipy + sounddevice ... && %PYEXE% -m pip install numpy scipy sounddevice)
echo.
echo Starting the Universal Traveler ...
start "P25 OTA decoder (listening to the radio)" cmd /k %PYEXE% "System Files\p25_live_decoder.py" --serve
timeout /t 2 >nul
start "Traveler map server" cmd /k %PYEXE% "System Files\units_kml.py"
timeout /t 3 >nul
start "" http://localhost:8080
echo.
echo Two windows opened: the decoder (listening) and the Traveler map server.
echo The browser should open the live split-screen map at http://localhost:8080
echo Close those two windows to stop everything.
echo.
pause
