@echo off
chcp 65001 >nul
rem MagicSlayd: kod o'zgargandan keyin serverni yangilash (serverdagi baza va balanslar saqlanadi)
set /p SERVER=Server IP manzilini kiriting:
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\serverga-yukla.ps1" -Server %SERVER% -Yangilash
echo.
pause
