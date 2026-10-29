#!/usr/bin/env bash
# خزنتي على السحابة — one-command install on an Ubuntu server (Oracle Cloud Always Free).
#
#   curl -fsSL https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/vault-builds-windows/install-cloud.sh \
#     | sudo bash -s -- <duckdns-name> <duckdns-token>
#
# Installs the same vault server the laptop runs, behind Caddy for HTTPS at
# <duckdns-name>.duckdns.org, keeps the DuckDNS address pointing here, opens
# ports 80/443 in the server's own firewall, asks for the vault password, and
# updates the vault code daily from the published builds.
set -euo pipefail

NAME="${1:-}"
TOKEN="${2:-}"
if [[ -z "$NAME" || -z "$TOKEN" ]]; then
  echo "usage: install-cloud.sh <duckdns-name> <duckdns-token>" >&2
  exit 1
fi
NAME="${NAME%.duckdns.org}"
DOMAIN="$NAME.duckdns.org"
BASE="https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/vault-builds-windows"
APP=/opt/khazanti
DATA=/var/lib/khazanti

if [[ $EUID -ne 0 ]]; then
  echo "run with sudo" >&2
  exit 1
fi

echo "== 1/7 الحزم =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv curl ca-certificates gnupg debian-keyring debian-archive-keyring \
  apt-transport-https iptables-persistent

# Word, PowerPoint and Excel are shown as PDF; these fonts keep their layout,
# Arabic included (Carlito and Caladea stand in for Calibri and Cambria).
OFFICE_PKGS="libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui fonts-liberation fonts-dejavu-core fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea"
apt-get install -y -q --no-install-recommends $OFFICE_PKGS

echo "== 2/7 Caddy (HTTPS) =="
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

echo "== 3/7 عنوان DuckDNS =="
cat > /usr/local/bin/khazanti-duckdns <<DUCK
#!/bin/sh
curl -fsS "https://www.duckdns.org/update?domains=$NAME&token=$TOKEN&ip=" -o /dev/null
DUCK
chmod 700 /usr/local/bin/khazanti-duckdns
/usr/local/bin/khazanti-duckdns || echo "تحذير: تعذر تحديث DuckDNS، تأكد من الاسم والرمز"
echo "*/5 * * * * root /usr/local/bin/khazanti-duckdns" > /etc/cron.d/khazanti-duckdns

echo "== 4/7 خزنتي =="
id khazanti >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin khazanti
mkdir -p "$APP" "$DATA"
chown khazanti:khazanti "$DATA"
chmod 700 "$DATA"
[[ -d "$APP/venv" ]] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pypdf==5.1.0
for f in khazanti.py index.html build_info.json; do
  curl -fsSL "$BASE/$f" -o "$APP/$f"
done

cat > /usr/local/bin/khazanti-update <<UPD
#!/bin/sh
# Daily: take the newest published vault code, restart if it changed.
set -e
command -v soffice >/dev/null || apt-get install -y -q --no-install-recommends $OFFICE_PKGS
latest=\$(curl -fsSL "$BASE/latest.json?t=\$(date +%s)" | python3 -c 'import json,sys;print(json.load(sys.stdin)["build"])')
mine=\$(python3 -c 'import json;print(json.load(open("$APP/build_info.json"))["build"])' 2>/dev/null || echo 0)
[ "\$latest" -gt "\$mine" ] || exit 0
for f in khazanti.py index.html build_info.json; do curl -fsSL "$BASE/\$f" -o "$APP/\$f.new"; done
for f in khazanti.py index.html build_info.json; do mv "$APP/\$f.new" "$APP/\$f"; done
systemctl restart khazanti
UPD
chmod 755 /usr/local/bin/khazanti-update
echo "17 4 * * * root /usr/local/bin/khazanti-update" > /etc/cron.d/khazanti-update

cat > /etc/systemd/system/khazanti.service <<SVC
[Unit]
Description=Khazanti private vault
After=network-online.target

[Service]
User=khazanti
Environment=KHAZANTI_HOME=$DATA
Environment=KHAZANTI_BIND=127.0.0.1
ExecStart=$APP/venv/bin/python $APP/khazanti.py --headless --port 47801
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVC

echo "== 5/7 كلمة سر الخزنة =="
if [[ ! -f "$DATA/config.json" ]] || ! grep -q pw_hash "$DATA/config.json"; then
  PW1="${KHAZANTI_PASSWORD:-}"
  if [[ -z "$PW1" ]] && ! (: </dev/tty) 2>/dev/null; then
    echo "لا توجد شاشة لكتابة كلمة السر؛ شغّل الأمر من نافذة SSH" >&2
    exit 1
  fi
  while [[ -z "$PW1" ]]; do
    read -r -s -p "اختر كلمة سر خزنة السحابة (4 أحرف على الأقل): " PW1 </dev/tty; echo
    read -r -s -p "أعد كتابتها: " PW2 </dev/tty; echo
    if [[ "$PW1" == "$PW2" && ${#PW1} -ge 4 ]]; then break; fi
    echo "غير متطابقتين أو قصيرة، حاول مرة أخرى"
    PW1=""
  done
  printf '%s\n' "$PW1" | sudo -u khazanti env KHAZANTI_HOME="$DATA" "$APP/venv/bin/python" "$APP/khazanti.py" --set-password
else
  echo "كلمة السر موجودة من قبل، تبقى كما هي"
fi

echo "== 6/7 جدار الحماية (80/443) =="
for port in 80 443; do
  iptables -C INPUT -p tcp --dport $port -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport $port -j ACCEPT
done
netfilter-persistent save >/dev/null 2>&1 || true

echo "== 7/7 تشغيل =="
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:47801 {
		flush_interval -1
	}
}
CADDY
systemctl daemon-reload
systemctl enable --now khazanti
systemctl restart caddy

sleep 5
if curl -fsS "http://127.0.0.1:47801/api/status" >/dev/null; then
  echo
  echo "✅ خزنتي جاهزة على: https://$DOMAIN"
  echo "   (الشهادة الآمنة قد تأخذ دقيقة أو اثنتين أول مرة)"
else
  echo "⚠️ خزنتي لم تبدأ، أرسل ناتج: sudo journalctl -u khazanti -n 50"
fi
