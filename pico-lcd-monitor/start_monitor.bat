@echo off
title CPU/GPU -^> Pico 1602
cd /d "%~dp0"
echo ==========================================
echo   Sending CPU / GPU stats to Pico
echo   Close this window to stop
echo ==========================================
echo.
rem 串口自动识别（按 2E8A 找 Pico）。要固定端口就改成：
rem python -u pc_stats.py -p COM3
python -u pc_stats.py
echo.
echo Stopped. Press any key to close.
pause >nul
