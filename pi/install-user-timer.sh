#!/usr/bin/env bash
set -Eeuo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
# Avoid accidental ExecStart syntax breakage with non-simple checkout paths.
[[ "$repo" != *' '* && "$repo" != *$'\t'* ]] || { echo 'Clone path cannot contain spaces for this installer' >&2; exit 1; }
units="$HOME/.config/systemd/user"
mkdir -p "$units"
cat > "$units/pi-vpn-builder.service" <<EOF
[Unit]
Description=Locally build and publish VPN and datacenter IP lists to GitHub fork
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$repo
ExecStart=/usr/bin/bash $repo/pi/build-and-publish.sh
TimeoutStartSec=90min
EOF
cat > "$units/pi-vpn-builder.timer" <<'EOF'
[Unit]
Description=Rebuild VPN datasets every 6 hours on Raspberry Pi

[Timer]
OnCalendar=*-*-* 02,08,14,20:15:00
Persistent=true
RandomizedDelaySec=10m
Unit=pi-vpn-builder.service

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now pi-vpn-builder.timer
printf '\nInstalled user timer. For execution while logged out, run: sudo loginctl enable-linger %s\n' "$USER"
