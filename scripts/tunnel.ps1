# Lokal ishga tushirish: bot + web server + bepul cloudflared tunnel (kompyuter yoniq turganda ishlaydi).
# Ishga tushirish: magicslayd\ishga-tushir.bat ni ikki marta bosing.
# Bepul tunnel har safar YANGI manzil beradi - manzil bot\.env ga yoziladi va bot qayta ishga tushiriladi.
# Doimiy (24/7) ishlash uchun serverga joylang: LAUNCH.md
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$botDir = Join-Path $root 'bot'
$serverDir = Join-Path $root 'web\server'
$logs = Join-Path $root 'logs'
$cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$python = (Get-Command python).Source
$node = (Get-Command node).Source
New-Item -ItemType Directory -Force $logs | Out-Null

# 1) Eski jarayonlar yopiladi (bitta token bilan ikkita bot ishlamaydi)
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'bot\.py' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match 'src[/\\]index\.js' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2

# 2) Tunnel - fonda
Write-Host 'Tunnel ochilmoqda...' -ForegroundColor Yellow
Remove-Item "$logs\tunnel.log" -ErrorAction SilentlyContinue
Start-Process $cloudflared -ArgumentList 'tunnel', '--url', 'http://localhost:3001' `
  -RedirectStandardError "$logs\tunnel.log" -RedirectStandardOutput "$logs\tunnel-out.log" -WindowStyle Hidden | Out-Null
$url = $null
for ($i = 0; $i -lt 40 -and -not $url; $i++) {
  Start-Sleep -Seconds 1
  $match = Select-String -Path "$logs\tunnel.log" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($match) { $url = $match.Matches[0].Value }
}
if (-not $url) { throw "Tunnel manzili chiqmadi. Internetni tekshiring ($logs\tunnel.log)." }

# 3) Manzil bot\.env ga yoziladi
$envFile = Join-Path $botDir '.env'
$lines = [IO.File]::ReadAllLines($envFile, [Text.Encoding]::UTF8)
$found = $false
$lines = foreach ($line in $lines) {
  if ($line -match '^\s*WEBAPP_URL\s*=') { $found = $true; "WEBAPP_URL=$url" } else { $line }
}
if (-not $found) { $lines += "WEBAPP_URL=$url" }
[IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding $false))

# 4) Bot va web server
Start-Process $python -ArgumentList '-u', 'bot.py' -WorkingDirectory $botDir `
  -RedirectStandardOutput "$logs\bot.log" -RedirectStandardError "$logs\bot-error.log" -WindowStyle Hidden | Out-Null
Start-Process $node -ArgumentList '--disable-warning=ExperimentalWarning', 'src/index.js' -WorkingDirectory $serverDir `
  -RedirectStandardOutput "$logs\web.log" -RedirectStandardError "$logs\web-error.log" -WindowStyle Hidden | Out-Null

Write-Host ''
Write-Host "Tayyor! Ilova manzili: $url" -ForegroundColor Green
Write-Host 'Telegram: @MagicSlayd_bot -> /start -> "Ilova" tugmasi yangi manzilni ochadi.'
Write-Host "Loglar: $logs"
Write-Host 'Kompyuter o''chsa yoki uxlasa - ishga-tushir.bat ni qayta bosing.'
