#!/bin/bash
# Test VM only: a simulated WPA2 AP with its own QEMU uplink namespace.
set -euo pipefail
modprobe mac80211_hwsim radios=2
ip netns add paimenos-ap
phy=$(iw dev wlan1 info | awk '/wiphy/ {print "phy"$2}')
iw phy "$phy" set netns name paimenos-ap
ip link set ens4 netns paimenos-ap
ip -n paimenos-ap link set lo up
ip -n paimenos-ap link set ens4 up
ip -n paimenos-ap address flush dev ens4
ip -n paimenos-ap address add 10.0.2.15/24 dev ens4
ip -n paimenos-ap route add default via 10.0.2.2
ip -n paimenos-ap address add 192.168.42.1/24 dev wlan1
ip -n paimenos-ap link set wlan1 up
ip netns exec paimenos-ap sysctl -w net.ipv4.ip_forward=1
ip netns exec paimenos-ap iptables -t nat -A POSTROUTING -o ens4 -j MASQUERADE
cat > /run/paimenos-test-ap.conf <<'CONF'
interface=wlan1
driver=nl80211
ssid=PaimenOS-Test
hw_mode=g
channel=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=test-password-only
CONF
ip netns exec paimenos-ap hostapd -B /run/paimenos-test-ap.conf
ip netns exec paimenos-ap dnsmasq --interface=wlan1 --bind-interfaces --except-interface=lo --dhcp-range=192.168.42.10,192.168.42.30,255.255.255.0,1h --dhcp-option=3,192.168.42.1 --dhcp-option=6,192.168.42.1 --server=10.0.2.3 --no-resolv
