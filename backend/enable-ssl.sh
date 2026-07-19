#!/usr/bin/env bash
# DNS(si.leafeep.com → 노드IP) 전파 후 실행. Let's Encrypt 인증서를 발급하고
# nginx 를 HTTPS 구성(api-ssl.conf)으로 전환한다. 노드에서 backend/ 디렉터리에서 실행.
set -euo pipefail

DOMAIN="si.leafeep.com"
EMAIL="${1:-xhae000@gmail.com}"   # Let's Encrypt 등록 이메일 (만료 알림용)

cd "$(dirname "$0")"

echo "=== 0. DNS 확인 ==="
RESOLVED=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
echo "$DOMAIN → ${RESOLVED:-(해석 안 됨)}"
if [ -z "$RESOLVED" ]; then
  echo "DNS가 아직 해석되지 않습니다. A레코드 추가/전파 후 다시 실행하세요."
  exit 1
fi

echo "=== 1. HTTP 스택 기동 확인 ==="
docker compose up -d backend nginx

echo "=== 2. certbot 인증서 발급 (webroot) ==="
docker compose run --rm --entrypoint "certbot certonly --webroot -w /var/www/certbot \
  -d ${DOMAIN} --email ${EMAIL} --agree-tos --no-eff-email --non-interactive" certbot

echo "=== 3. nginx 를 HTTPS 구성으로 전환 ==="
cp nginx/api-ssl.conf nginx/api.conf
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload

echo "=== 4. 갱신 루프 컨테이너 기동 ==="
docker compose up -d certbot

echo "=== 완료: https://${DOMAIN} ==="
