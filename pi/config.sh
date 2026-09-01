#!/bin/bash
apt update && apt dist-upgrade -y && apt install mosquitto python3 network-manager python3-pip python3-flask python3-paho-mqtt python3-sqlalchemy
nmcli connection device wifi hotspot ssid timercamnet password microcontroller ifname wlan0
nmcli connection modify Hotspot 802-11-wireless-security.pmf 1 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.64.1/29 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "microcontroller"
nmcli connection up Hotspot

mosquitto_passwd -b -c /etc/mosquitto/passwd esp microcontroller
touch /etc/mosquitto/conf.d/mosq.conf
(echo "listener 1883 192.168.64.1"; echo "password_file /etc/mosquitto/passwd") >> /etc/mosquitto/conf.d/mosq.conf
service mosquitto restart
systemctl enable mosquitto
adduser runner --gecos ",,," --disabled-password
su -i -u runner
git clone https://github.com/arthurrondia/ProjetNichoir.git
exit

touch /etc/systemd/system/python_nest.service
(echo "[Unit]"; echo "Description=Serveur web pour le nichoir connecté"; echo "After=network.target"; echo "[Service]"; echo "Type=simple"; echo "Restart=always"; echo "RestartSec=15"; echo "User=runner"; echo "ExecStart=/usr/bin/env python3 /home/runner/birdsnest/pi/website/app.py"; echo "[Install]"; echo "WantedBy=multi-user.target") >> /etc/systemd/system/python_nest.service
systemctl start python_nest
systemctl enable python_nest