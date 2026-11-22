#!/usr/bin/env bash
# Familienplaner – Installation auf Raspberry Pi OS (Bookworm)
# GERÜST: Die Schritte sind beschrieben, aber noch nicht ausimplementiert.
set -euo pipefail

MODE="${1:-lcd}"   # lcd | eink

echo "TODO 1: Pakete installieren (python3-venv, chromium, cage, avahi-daemon, ufw)"
echo "TODO 2: Benutzer 'familienplaner' und 'kiosk' anlegen"
echo "TODO 3: Code nach /opt/familienplaner kopieren, venv anlegen, pip install ./backend[eink?]"
echo "TODO 4: /etc/familienplaner/config.yaml + secret.key erzeugen (chmod 600)"
echo "TODO 5: /var/lib/familienplaner anlegen, Migrationen ausführen"
echo "TODO 6: systemd-Units installieren, je nach MODE kiosk oder eink aktivieren"
echo "TODO 7: Hostname familienplaner + mDNS, ufw: Port 8000 nur im LAN"
echo "TODO 8: SPI aktivieren (nur eink): raspi-config nonint do_spi 0"
