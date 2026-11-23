@echo off
cd /d "%~dp0"
set "PYEXE=py -3"
where py >nul 2>nul || set "PYEXE=python"
%PYEXE% -c "import numpy, scipy" 2>nul || (echo Installing numpy + scipy ... && %PYEXE% -m pip install numpy scipy)
echo.
echo P25 OTA GPS Decoder - decode a discriminator-audio recording to NMEA.
%PYEXE% "System Files\p25_ota_decoder.py" %1
echo.
pause
