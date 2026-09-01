#!/bin/bash
apt update && apt dist-upgrade -y && apt install mosquitto python3 network-manager python3-pip python3-flask python3-paho-mqtt python3-sqlalchemy git
nmcli connection device wifi hotspot ssid timercamnet password microcontroller ifname wlan0
nmcli connection modify Hotspot 802-11-wireless-security.pmf 1 connection.autoconnect yes 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.64.1/29 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "microcontroller"
nmcli connection up Hotspot

git clone https://github.com/arthurrondia/ProjetNichoir.git
mosquitto_passwd -b -c /etc/mosquitto/passwd esp microcontroller
chmod 644 /etc/mosquitto/passwd
touch /etc/mosquitto/conf.d/mosq.conf
printf "listener 1883 192.168.64.1\npassword_file /etc/mosquitto/passwd\n" > /etc/mosquitto/conf.d/mosq.conf
service mosquitto restart
systemctl enable mosquitto
adduser runner --gecos ",,," --disabled-password
su -i -u runner
git clone https://github.com/arthurrondia/ProjetNichoir.git
exit
cp ProjetNichoir/pi/python_nest.service /etc/systemd/system/

systemctl start python_nest
systemctl enable python_nest