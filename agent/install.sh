#!/usr/bin/env bash
# Installer of isc-dhcp-agent (systemd service).
#   install:    sudo bash install.sh --url https://<netbox>/plugins/isc-dhcp/dhcp/export/agent/
#   from git:   curl -fsSL https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP/<ref>/agent/install.sh | sudo bash -s -- --ref <ref> --url <agent url>
#   uninstall:  sudo bash install.sh --uninstall      (keeps /etc/isc-dhcp-agent.conf and the backups)
set -eu
REPO="https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP"
REF="claude/skeleton-pool-planner"
URL=""
MODE="install"
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --uninstall) MODE="uninstall"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
BIN=/usr/local/sbin/isc-dhcp-agent
UNIT=/etc/systemd/system/isc-dhcp-agent.service
CONF=/etc/isc-dhcp-agent.conf

if [ "$MODE" = uninstall ]; then
  systemctl disable --now isc-dhcp-agent 2>/dev/null || true
  rm -f "$BIN" "$UNIT"; systemctl daemon-reload 2>/dev/null || true
  echo "isc-dhcp-agent removed ($CONF and backups kept)"; exit 0
fi

for c in curl sha256sum flock systemctl; do
  command -v "$c" >/dev/null 2>&1 || { echo "missing command: $c (install it first)" >&2; exit 1; }
done
command -v dhcpd >/dev/null 2>&1 || echo "WARNING: ISC dhcpd is not installed - the agent runs and reports it to NetBox, but gets no CFG"

here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo /nonexistent)"
get() {  # get <file> <dest>: from the checkout next to this script, else from git
  if [ -f "$here/$1" ]; then install -m "$3" "$here/$1" "$2"; else curl -fsSL "$REPO/$REF/agent/$1" -o "$2" && chmod "$3" "$2"; fi
}
get isc-dhcp-agent "$BIN" 755
get isc-dhcp-agent.service "$UNIT" 644
if [ ! -f "$CONF" ]; then
  get isc-dhcp-agent.conf.example "$CONF" 600
  [ -n "$URL" ] && sed -i "s|^NETBOX_URL=.*|NETBOX_URL=\"$URL\"|" "$CONF"
elif [ -n "$URL" ]; then
  sed -i "s|^NETBOX_URL=.*|NETBOX_URL=\"$URL\"|" "$CONF"
fi
grep -q '^NETBOX_URL="https\?://[^"]' "$CONF" || { echo "set NETBOX_URL in $CONF, then: systemctl enable --now isc-dhcp-agent"; exit 0; }
systemctl daemon-reload
systemctl enable --now isc-dhcp-agent
systemctl restart isc-dhcp-agent
echo "isc-dhcp-agent $("$BIN" --version) installed and running (journalctl -u isc-dhcp-agent -f)"
