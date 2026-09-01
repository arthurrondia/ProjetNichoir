#!/bin/bash
apt update && apt dist-upgrade -y && apt install mosquitto python3 network-manager
nmcli connection device wifi hotspot ssid timercamnet password microcontroller ifname wlan0
nmcli connection modify Hotspot 802-11-wireless-security.pmf 1 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.64.1/29 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "microcontroller"
nmcli connection up Hotspot

mosquitto_passwd -b -c /etc/mosquitto/passwd esp microcontroller
touch /etc/mosquitto/conf.d/mosq.conf
(echo "listener 1883 192.168.64.1"; echo "password_file /etc/mosquitto/passwd") >> /etc/mosquitto/conf.d/mosq.conf