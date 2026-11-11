# MagicSlayd: loyihani serverga yuklaydi va ishga tushiradi.
#   Birinchi marta (baza va loyihalar bilan):  .\scripts\serverga-yukla.ps1 -Server 1.2.3.4
#   Kod yangilanganda (serverdagi ma'lumotlarga tegmaydi):  .\scripts\serverga-yukla.ps1 -Server 1.2.3.4 -Yangilash
param(
  [Parameter(Mandatory = $true)][string]$Server,
  [string]$User = 'root',
  [switch]$Yangilash
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$parent = Split-Path $root -Parent
$name = Split-Path $root -Leaf
$archive = Join-Path $env:TEMP 'magicslayd.tgz'
$target = "$User@$Server"

$excludes = @('--exclude=node_modules', '--exclude=logs', '--exclude=__pycache__', '--exclude=.libreoffice',
  '--exclude=client/dist', '--exclude=*.db-wal', '--exclude=*.db-shm')

if ($Yangilash) {
  # Serverdagi data/ (userlar, balanslar) va .env (DOMAIN) saqlanib qoladi
  $excludes += @("--exclude=$name/data", "--exclude=$name/.env")
} else {
  # Birinchi yuklash: baza ham ketadi. Lokal bot to'xtatiladi - bitta token bilan ikkita bot ishlamaydi
  Write-Host 'Lokal bot, web va tunnel toxtatilmoqda...' -ForegroundColor Yellow
  Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
  Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'bot\.py') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'src[/\\]index\.js')
  } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep -Seconds 2
  $db = Join-Path $root 'data\bot.db'
  python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); print('Baza tayyor:', c.execute('PRAGMA integrity_check').fetchone()[0])" $db
}

Write-Host 'Arxiv tayyorlanmoqda...' -ForegroundColor Yellow
Remove-Item $archive -ErrorAction SilentlyContinue
& tar -czf $archive -C $parent @excludes $name
if ($LASTEXITCODE -ne 0) { throw 'Arxiv yaratilmadi' }
Write-Host ("Arxiv: {0:N1} MB" -f ((Get-Item $archive).Length / 1MB))

Write-Host "Serverga yuklanmoqda ($target)... parol so'ralsa - server paroli" -ForegroundColor Yellow
scp $archive "${target}:/opt/magicslayd.tgz"
if ($LASTEXITCODE -ne 0) { throw 'Yuklab bolmadi (IP, parol yoki internetni tekshiring)' }

Write-Host 'Serverda ornatilmoqda (birinchi marta 5-10 daqiqa)...' -ForegroundColor Yellow
ssh $target "cd /opt && tar -xzf magicslayd.tgz && rm magicslayd.tgz && bash /opt/magicslayd/scripts/server-setup.sh"
if ($LASTEXITCODE -ne 0) { throw 'Serverda xato. Yuqoridagi xabarni oqing.' }

Write-Host ''
Write-Host 'Tayyor! https://magicslayd.uz' -ForegroundColor Green
