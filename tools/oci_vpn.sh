#!/bin/bash
# SAUDI.TV's own VPN on the owner's Oracle Cloud (Always Free), in ONE paste into Oracle's Cloud Shell:
#     curl -fsSL https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/tools/oci_vpn.sh | bash
# It makes (or finds again) a network "saudi-vpn" with UDP 51820 open, a free VM.Standard.E2.1.Micro Ubuntu
# machine that installs WireGuard by itself (tools/vpn_server.sh), waits for it, and prints one .conf per device.
# Running it again creates nothing new: it prints the same files.
set -euo pipefail
N=${N:-10}
C=${OCI_TENANCY:?run this in Oracle Cloud Shell}
say() { echo -e "\n== $*"; }
q() { "$@" --raw-output 2>/dev/null || true; }

say "network"
V=$(q oci network vcn list -c "$C" --display-name saudi-vpn --lifecycle-state AVAILABLE --query 'data[0].id')
if [ -z "$V" ] || [ "$V" = "null" ]; then
  V=$(oci network vcn create -c "$C" --cidr-blocks '["10.77.0.0/16"]' --display-name saudi-vpn --dns-label saudivpn \
      --wait-for-state AVAILABLE --query data.id --raw-output)
fi
IGW=$(q oci network internet-gateway list -c "$C" --vcn-id "$V" --query 'data[0].id')
if [ -z "$IGW" ] || [ "$IGW" = "null" ]; then
  IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$V" --is-enabled true --display-name saudi-vpn-igw \
      --wait-for-state AVAILABLE --query data.id --raw-output)
fi
RT=$(oci network vcn get --vcn-id "$V" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force \
  --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
SL=$(oci network vcn get --vcn-id "$V" --query 'data."default-security-list-id"' --raw-output)
oci network security-list update --security-list-id "$SL" --force \
  --ingress-security-rules '[{"source":"0.0.0.0/0","protocol":"6","tcpOptions":{"destinationPortRange":{"min":22,"max":22}}},
                             {"source":"0.0.0.0/0","protocol":"17","udpOptions":{"destinationPortRange":{"min":51820,"max":51820}}}]' >/dev/null
SUB=$(q oci network subnet list -c "$C" --vcn-id "$V" --query 'data[0].id')
if [ -z "$SUB" ] || [ "$SUB" = "null" ]; then
  SUB=$(oci network subnet create -c "$C" --vcn-id "$V" --cidr-block 10.77.1.0/24 --display-name saudi-vpn-sub --dns-label vpn \
      --wait-for-state AVAILABLE --query data.id --raw-output)
fi

say "machine"
[ -f ~/.ssh/saudi_vpn ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/saudi_vpn -q
I=$(q oci compute instance list -c "$C" --display-name saudi-vpn --lifecycle-state RUNNING --query 'data[0].id')
if [ -z "$I" ] || [ "$I" = "null" ]; then
  SHAPE=VM.Standard.E2.1.Micro
  IMG=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape $SHAPE \
        --sort-by TIMECREATED --query 'data[0].id' --raw-output)
  printf '#!/bin/bash\ncurl -fsSL https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/tools/vpn_server.sh | bash -s -- %s > /root/vpn.txt 2>&1\n' "$N" > /tmp/saudi_ud.sh
  for AD in $(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]",'); do
    echo "trying $AD"
    I=$(oci compute instance launch -c "$C" --availability-domain "$AD" --shape $SHAPE --image-id "$IMG" --subnet-id "$SUB" \
        --assign-public-ip true --display-name saudi-vpn --ssh-authorized-keys-file ~/.ssh/saudi_vpn.pub \
        --user-data-file /tmp/saudi_ud.sh --wait-for-state RUNNING --query data.id --raw-output 2>/tmp/saudi_err) && break
    I=""; grep -o '"message": "[^"]*"' /tmp/saudi_err | head -1
  done
  [ -n "$I" ] || { echo "Oracle has no free machine right now in any zone — run the same line again later."; exit 1; }
fi
IP=$(oci compute instance list-vnics --instance-id "$I" --query 'data[0]."public-ip"' --raw-output)
echo "machine $IP"

say "waiting for WireGuard (2–6 minutes)"
for t in $(seq 1 60); do
  if ssh -q -o StrictHostKeyChecking=no -o ConnectTimeout=8 -i ~/.ssh/saudi_vpn ubuntu@"$IP" "sudo test -f /etc/wireguard/clients/device$N.conf" 2>/dev/null; then
    say "READY — one file per device: paste each into the admin site (device › ⑤ VPN)"
    ssh -q -o StrictHostKeyChecking=no -i ~/.ssh/saudi_vpn ubuntu@"$IP" 'sudo bash -c "for f in /etc/wireguard/clients/*.conf; do echo; echo ===== \$(basename \$f .conf) =====; cat \$f; done"'
    exit 0
  fi
  sleep 10
done
echo "Not ready yet — run the same line again in a few minutes (nothing is made twice)."
