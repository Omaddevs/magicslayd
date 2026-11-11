@echo off
chcp 65001 >nul
rem MagicSlayd: lokal bot, web server va tunnelni to'xtatadi (serverga ko'chirishdan oldin shart)
powershell -NoProfile -Command "Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force; Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'bot\.py') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'src[/\\]index\.js') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo To'xtatildi.
pause
