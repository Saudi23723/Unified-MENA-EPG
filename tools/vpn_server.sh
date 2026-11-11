#!/bin/bash
# SAUDI.TV's own VPN server: WireGuard on a small Ubuntu machine the owner has (for example a cloud provider's
# always-free machine). Run once on that machine, as root:
#     curl -fsSL https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/tools/vpn_server.sh | sudo bash -s -- 10
# (10 = how many devices). It installs WireGuard, opens UDP 51820, and prints one .conf per device: paste each
# into the admin site (device → ⑤ VPN). Running it again adds nothing and prints the same files.
set -e
N=${1:-10}; PORT=51820; DIR=/etc/wireguard; NET=10.66.0
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq wireguard iptables curl >/dev/null
IF=$(ip -o -4 route show to default | awk '{print $5}' | head -1)
IP=$(curl -fsS4 https://api.ipify.org || hostname -I | awk '{print $1}')
umask 077; mkdir -p $DIR/clients; cd $DIR
[ -f server.key ] || wg genkey | tee server.key | wg pubkey > server.pub
if [ ! -f wg0.conf ]; then
  cat > wg0.conf <<CONF
[Interface]
Address = $NET.1/24
ListenPort = $PORT
PrivateKey = $(cat server.key)
PostUp = iptables -I INPUT -p udp --dport $PORT -j ACCEPT; iptables -I FORWARD -i wg0 -j ACCEPT; iptables -I FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $IF -j MASQUERADE; iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
PostDown = iptables -D INPUT -p udp --dport $PORT -j ACCEPT; iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $IF -j MASQUERADE; iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
CONF
fi
for i in $(seq 1 "$N"); do
  C=clients/device$i
  [ -f $C.conf ] && continue
  K=$(wg genkey); P=$(echo "$K" | wg pubkey)
  printf '\n[Peer]\n# device%s\nPublicKey = %s\nAllowedIPs = %s.%s/32\n' "$i" "$P" "$NET" "$((i+1))" >> wg0.conf
  cat > $C.conf <<CONF
[Interface]
PrivateKey = $K
Address = $NET.$((i+1))/32
DNS = 1.1.1.1
MTU = 1380

[Peer]
PublicKey = $(cat server.pub)
Endpoint = $IP:$PORT
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
CONF
done
printf 'net.ipv4.ip_forward=1\nnet.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\nnet.core.rmem_max=16777216\nnet.core.wmem_max=16777216\nnet.core.netdev_max_backlog=5000\n' > /etc/sysctl.d/99-saudi1-vpn.conf && sysctl -q --system
systemctl enable -q wg-quick@wg0 && systemctl restart wg-quick@wg0
echo; echo "=== VPN is up on $IP:$PORT (UDP). Also open UDP $PORT in the cloud provider's firewall / security list. ==="
for f in clients/*.conf; do echo; echo "----- $f -----"; cat "$f"; done
