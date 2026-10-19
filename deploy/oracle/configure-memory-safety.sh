#!/bin/bash
# Give the 2 GiB Oracle VM room to recover from short memory spikes.
# Does not overwrite an existing swap file or alter active swap configuration.
set -euo pipefail
umask 077
if [ "$(id -u)" != 0 ]; then echo 'Run as root' >&2; exit 1; fi
if [ -n "$(swapon --show=NAME --noheadings)" ]; then
  echo 'Existing swap retained; no changes made'
  exit 0
fi
if [ -e /swapfile ]; then echo 'Inactive /swapfile already exists; inspect it first' >&2; exit 1; fi
available=$(df -B1 --output=avail / | tail -n 1 | tr -d ' ')
if [ "$available" -lt 4294967296 ]; then echo 'Insufficient free space for safe swap creation' >&2; exit 1; fi
state=/opt/acr/memory-safety
install -d -m 0700 "$state"
if [ ! -e "$state/fstab.before" ]; then cp -a /etc/fstab "$state/fstab.before"; fi
fallocate -l 2G /swapfile
chmod 0600 /swapfile
restorecon /swapfile
mkswap /swapfile > /dev/null
swapon /swapfile
if ! grep -Eq '^[[:space:]]*/swapfile[[:space:]]' /etc/fstab; then
  printf '\n/swapfile none swap defaults 0 0\n' >> /etc/fstab
fi
printf 'vm.swappiness = 10\n' > /etc/sysctl.d/90-acr-memory-safety.conf
sysctl -w vm.swappiness=10
printf '2 GiB swap activated and configured for boot\n'
swapon --show --bytes --noheadings --output=SIZE,USED
