@echo off
cd /d "%~dp0"
set "PYEXE=py -3"
where py >nul 2>nul || set "PYEXE=python"
%PYEXE% -c "import numpy, scipy, sounddevice" 2>nul || (echo Installing numpy + scipy + sounddevice ... && %PYEXE% -m pip install numpy scipy sounddevice)
echo.
echo P25 OTA GPS Live Decoder - listen to the radio and decode GPS live.
%PYEXE% "System Files\p25_live_decoder.py" %*
echo.
pause
