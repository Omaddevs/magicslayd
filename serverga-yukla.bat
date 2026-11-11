@echo off
chcp 65001 >nul
rem MagicSlayd: birinchi marta serverga yuklash (baza bilan)
set /p SERVER=Server IP manzilini kiriting:
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\serverga-yukla.ps1" -Server %SERVER%
echo.
pause
