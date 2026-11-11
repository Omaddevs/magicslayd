@echo off
chcp 65001 >nul
rem MagicSlayd: bot + web ilova + tunnel (lokal, kompyuterda)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\tunnel.ps1"
echo.
pause
