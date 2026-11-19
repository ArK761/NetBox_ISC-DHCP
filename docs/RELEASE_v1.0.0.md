## NetBox ISC DHCP 1.0.0 (agent 1.15.0)

First stable release. NetBox 4.7 plugin that generates the ISC DHCP (dhcpd 4.4) configuration from NetBox, plus **isc-dhcp-agent** that keeps every DHCP server in sync (download → backup → test → restart → report).

### Highlights
- dhcpd.conf (own static part + plugin includes), subnets from pool templates with full checks, hosts/MAC tables, own variables, DNS, classes
- Stored files with SHA256, only changed parts recomputed
- DHCP servers: staged rollout, CFG number, Start / Stop / Restart / Update from NetBox, real dhcpd state, PID, crash and manual stop detection
- Audit with diffs and colours (OK / INFO / WARNING), SK + EN UI, PDF manual linked in the plugin

### Security in this release
- Agent runs **only** a fixed command list, identical (1:1) in the plugin and the agent, visible read-only in *CFG pluginu → DHCP servery*; anything else is ignored and logged as SECURITY
- Backup directory only below `/opt/` (default `/opt/BCK`); `rm -rf` only on the agent's own backups; other deletes only CFG files below the base path
- Test / restart only locally allowed commands; dhcpd.conf dir fixed; base path pinned; system directories refused
- API key read by curl from a root-only file (not visible in `ps`); all URLs used on the agent's own NetBox address

### Install the plugin
```bash
sudo bash -c 'source /opt/netbox/venv/bin/activate && pip install "git+https://github.com/ArK761/NetBox_ISC-DHCP.git@v1.0.0" && cd /opt/netbox/netbox && python manage.py migrate netbox_isc_dhcp && systemctl restart netbox netbox-rq'
```
Add `PLUGINS = ["netbox_isc_dhcp"]` to `configuration.py`.

### Install the agent (each DHCP server)
1. NetBox → **CFG pluginu → DHCP servery**: add the server, press **Generate key** (the page shows the API address and the install command).
2. On the DHCP server:
```bash
curl -fsSL https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP/v1.0.0/agent/install.sh | sudo bash -s -- --ref v1.0.0 --url https://<netbox>/api/plugins/isc-dhcp/agent/ --token <key>
```
3. Check: `sudo isc-dhcp-agent --show`, `systemctl status isc-dhcp-agent`, `/var/log/isc-dhcp-agent.log`.

Settings: in NetBox (interval, test/restart command, backup dir, staged rollout) and locally in `/etc/isc-dhcp-agent.conf` (`sudo isc-dhcp-agent --set NAME value`) — see the README table and the manual.

---

## SK – NetBox ISC DHCP 1.0.0 (agent 1.15.0)

Prvá stabilná verzia. Plugin generuje konfiguráciu ISC DHCP z NetBoxu, agent ju drží na DHCP serveroch (stiahnutie → záloha → test → reštart → hlásenie).

**Bezpečnosť:** agent vykoná len príkazy z pevného zoznamu, rovnakého v plugine aj v agente (v NetBoxe rozbaľovacie, nedá sa meniť). Zálohy len pod `/opt/`, `rm -rf` len na vlastné zálohy, inak maže len CFG súbory pod základnou cestou. Kľúč nevidno v `ps`.

**Inštalácia pluginu a agenta:** príkazy vyššie. Agent: v NetBoxe CFG pluginu → DHCP servery → pridať server → Vygenerovať kľúč → na DHCP serveri spustiť inštalačný príkaz. Ďalšie verzie agenta sa inštalujú z NetBoxu tlačidlom **Aktualizovať agenta**.

Návod: **NAVOD_SK.pdf** / **MANUAL_EN.pdf** (prílohy nižšie, aj v plugine vpravo hore).
