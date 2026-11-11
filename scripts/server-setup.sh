#!/usr/bin/env bash
# MagicSlayd: serverda o'rnatish / yangilash. Ishga tushirish: bash /opt/magicslayd/scripts/server-setup.sh
# Bir necha marta ishlatsa bo'ladi — har safar kodni qayta build qiladi, ma'lumotlarga tegmaydi.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "==> 1. Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> 2. Fayllar (Windows qator oxirlari tozalanadi)"
sed -i 's/\r$//' .env bot/.env Caddyfile docker-compose.yml
DOMAIN=$(grep -E '^DOMAIN=' .env | cut -d= -f2- | tr -d '[:space:]')
[ -n "$DOMAIN" ] || { echo "XATO: .env da DOMAIN yozilmagan"; exit 1; }
mkdir -p data
chown -R 1000:1000 data   # bot va web konteynerlari (UID 1000) yoza olsin

echo "==> 3. Firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp
fi

echo "==> 4. DNS tekshiruvi ($DOMAIN)"
SERVER_IP=$(curl -fsS4 https://api.ipify.org || true)
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)
if [ "$SERVER_IP" != "$DNS_IP" ]; then
  echo "DIQQAT: $DOMAIN -> '${DNS_IP:-yoq}', server IP -> '$SERVER_IP'."
  echo "        DNS'da A yozuvini $SERVER_IP ga qarating. HTTPS sertifikat DNS to'g'ri bo'lgach o'zi olinadi."
fi

echo "==> 5. Build va ishga tushirish (birinchi marta 5-10 daqiqa)"
docker compose up -d --build --remove-orphans

echo "==> 6. Kunlik zaxira (04:00, 14 kun saqlanadi)"
command -v sqlite3 >/dev/null || (apt-get update -qq && apt-get install -y -qq sqlite3)
mkdir -p /root/backups
CRON="0 4 * * * sqlite3 $ROOT/data/bot.db \".backup /root/backups/bot-\$(date +\\%F).db\" && find /root/backups -name 'bot-*.db' -mtime +14 -delete"
( crontab -l 2>/dev/null | grep -v '/root/backups' ; echo "$CRON" ) | crontab -

echo "==> 7. Tekshiruv"
for i in $(seq 1 30); do
  if docker compose exec -T web wget -qO- http://127.0.0.1:3001/api/health >/dev/null 2>&1; then
    echo "Web server ishlayapti."
    break
  fi
  sleep 3
done
docker compose ps
echo
echo "Tayyor! Sayt: https://$DOMAIN  |  Loglar: cd $ROOT && docker compose logs -f --tail 50"
