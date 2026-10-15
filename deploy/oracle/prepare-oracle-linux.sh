#!/bin/bash
set -euo pipefail
umask 077
dnf -y install podman-docker git curl
systemctl enable --now podman.socket podman-restart.service
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
if [ ! -d /opt/acr/source/.git ]; then
 git clone --no-checkout https://github.com/ValtteriPSR/acr-daily.git /opt/acr/source
fi
cd /opt/acr/source
git fetch origin rally-club
git checkout --detach 760a085795329d1d2372cb6abb9ac1db7ad56e49
podman build -t localhost/acr-rally-club:0.2.16 -f deploy/Dockerfile .
printf '%s\n' prepared > /opt/acr/prepared
