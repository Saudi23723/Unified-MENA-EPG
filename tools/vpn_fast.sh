#!/bin/bash
# Make SAUDI.TV's VPN faster (owner, 11 Nov 2026: "with the VPN it is very bad"). ONE paste into Oracle's Cloud Shell:
#     curl -fsSL https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/tools/vpn_fast.sh | bash
# On the VPN machine made by oci_vpn.sh (same address, same keys: nothing to change on the devices or the admin site):
#  - TCP MSS clamp: without it big video packets get stuck in the tunnel (stalls, endless loading)
#  - BBR + fq + bigger buffers: steadier speed on long, far streams
# Then it measures the machine's own download speed and shows how busy it is.
set -uo pipefail
C=${OCI_TENANCY:?run this in Oracle Cloud Shell}
I=$(oci compute instance list -c "$C" --display-name saudi-vpn --lifecycle-state RUNNING --query 'data[0].id' --raw-output 2>/dev/null)
[ -n "$I" ] && [ "$I" != "null" ] || { echo "No running saudi-vpn machine found."; exit 1; }
SHAPE=$(oci compute instance get --instance-id "$I" --query 'data.shape' --raw-output)
IP=$(oci compute instance list-vnics --instance-id "$I" --query 'data[0]."public-ip"' --raw-output)
echo "== machine $IP ($SHAPE)"
ssh -q -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i ~/.ssh/saudi_vpn ubuntu@"$IP" 'sudo bash -s' <<'REMOTE'
set -u
printf 'net.ipv4.ip_forward=1\nnet.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\nnet.core.rmem_max=16777216\nnet.core.wmem_max=16777216\nnet.core.netdev_max_backlog=5000\n' > /etc/sysctl.d/99-saudi1-vpn.conf
modprobe tcp_bbr 2>/dev/null; sysctl -q --system
R='iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu'
iptables -t mangle -C FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || $R
grep -q TCPMSS /etc/wireguard/wg0.conf || sed -i "s|^PostUp = .*|&; $R|; s|^PostDown = .*|&; ${R/-A FORWARD/-D FORWARD}|" /etc/wireguard/wg0.conf
echo "== tuned: $(sysctl -n net.ipv4.tcp_congestion_control), MSS clamp $(iptables -t mangle -S FORWARD | grep -c TCPMSS)"
echo "== download speed of the machine itself (100 MB):"
curl -s -o /dev/null -w '%{speed_download}\n' 'https://speed.cloudflare.com/__down?bytes=100000000' | awk '{printf "   %.0f Mbit/s\n", $1*8/1000000}'
echo "== devices connected in the last 3 minutes: $(wg show wg0 latest-handshakes | awk -v n=$(date +%s) '$2>0 && n-$2<180' | wc -l)"
echo "== CPU (steal = what Oracle takes away from this small machine):"
top -bn2 -d1 | grep '^%Cpu' | tail -1
REMOTE
echo "== done"
