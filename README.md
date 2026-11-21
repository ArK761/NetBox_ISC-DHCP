# NetBox ISC DHCP

NetBox 4.7 plugin that generates the **ISC DHCP (dhcpd 4.4)** configuration from NetBox data, plus **isc-dhcp-agent**,
a small bash daemon that keeps every DHCP server in sync with NetBox (download → backup → test → restart → report).

*Slovenský popis je nižšie. Full manual (PDF): [docs/NAVOD_SK.pdf](docs/NAVOD_SK.pdf) · [docs/MANUAL_EN.pdf](docs/MANUAL_EN.pdf), also linked on every plugin page.*

## What it does
- **dhcpd.conf** = your own static text + include lines written by the plugin.
- **Subnets**: one `<network>_CFG` file per selected prefix, built from pool templates (Jinja2), checked before saving
  (ranges inside the prefix, no overlap, ISC syntax rules). Incompatible subnets are never exported.
- **Hosts and MAC addresses**: per group `_Dynamic` (class + subclass) and `_Static` (host blocks) files.
- **Own variables, DNS servers, classes** with usage tracking and safe rename.
- Generated files are stored with **SHA256** and only changed parts are recomputed.
- **DHCP servers + agent**: staged rollout (next server only after the previous one reported OK), CFG number `dd.mm.yy_NNN`,
  Start / Stop / Restart / Update from NetBox, real dhcpd state, PID, crash/manual stop detection.
- **Audit**: who changed what (diff), downloads, agent reports; colours OK / INFO / WARNING.
- Slovak and English UI.

## Requirements
- NetBox 4.7+ (Django 6.1), Python 3.10+
- DHCP server: Debian/Ubuntu with `isc-dhcp-server` 4.4, bash, curl (7.55+ recommended), sha256sum, flock, systemd

## 1. Install the plugin (NetBox server)
```bash
sudo bash -c 'source /opt/netbox/venv/bin/activate && pip install "git+https://github.com/ArK761/NetBox_ISC-DHCP.git@v1.0.0" && cd /opt/netbox/netbox && python manage.py migrate netbox_isc_dhcp && systemctl restart netbox netbox-rq'
```
`/opt/netbox/netbox/netbox/configuration.py`:
```python
PLUGINS = ["netbox_isc_dhcp"]
```
Then in NetBox: **CFG pluginu** (language, base path, subdirectories) → **DHCP-CFG** (dhcpd.conf, DNS, Subnets, Hosts).

Upgrade: the same command with `--upgrade --force-reinstall --no-deps` and the new tag. Migrations are part of the package
(never run `makemigrations` on the server). Updating the plugin never changes your stored data.

## 2. Install the agent (each DHCP server)
1. NetBox → **CFG pluginu → DHCP servery**: add the server (name + IP/FQDN), press **Vygenerovať kľúč / Generate key**.
   The page shows the agent API address and a ready install command.
2. On the DHCP server:
```bash
curl -fsSL https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP/v1.0.0/agent/install.sh | sudo bash -s -- --ref v1.0.0 --url https://<netbox>/api/plugins/isc-dhcp/agent/ --token <key>
```
3. Check: `sudo isc-dhcp-agent --show`, `sudo systemctl status isc-dhcp-agent`, log `/var/log/isc-dhcp-agent.log`.
   The server turns *online* in NetBox within one interval.

Later agent updates come from NetBox (button **Aktualizovať agenta / Update agent**), no reinstall needed.
Uninstall: `sudo bash install.sh --uninstall` (keeps the config and the backups).

**Server that already runs DHCP:** back up the original configuration yourself first (`/etc/dhcp`, include files, `/var/lib/dhcp`).
If the agent finds a dhcpd.conf that does not come from NetBox, NetBox sends nothing until you confirm the backup and the overwrite
at the server (CFG pluginu → DHCP servery → *Allow overwrite*). Switch off any other tool that manages the DHCP CFG (Ansible, scripts…),
otherwise it collides with the agent.
On the first run the agent copies the original leases (`<backup dir>/leases/original_<time>/`); on the takeover it stops dhcpd,
copies the current leases, deploys and tests the CFG and starts dhcpd with the same leases (shown at the server: leases kept N → N IP).
**Recommended: a test DHCP server** set as *First* with staged rollout – every new CFG and every takeover is tried there first.
Mark it as **Test server** in NetBox (it becomes First; nothing to set on the server): the **Test** button then
simulates the first run of the agent (original leases copy, consent, dhcpd stop → leases copy → CFG → start → leases check). `TEST_SERVER=no` in `/etc/isc-dhcp-agent.conf` forbids it for good on a production server.

## 3. Agent settings
Set in NetBox (CFG pluginu → DHCP servery): interval (10 s – 30 min), test and restart command, backup directory
(**only below `/opt/`**, default `/opt/BCK`), staged rollout, bundle size, keep failed CFG.

Local settings on the DHCP server, `/etc/isc-dhcp-agent.conf` (root only, 600), change with `sudo isc-dhcp-agent --set NAME value`:

| Setting | Default | Meaning |
|---|---|---|
| `NETBOX_URL` | – | agent API address (`--set-url`) |
| `NETBOX_TOKEN` | – | agent API key (`--set-token`) |
| `ALLOWED_TEST_CMDS` | `dhcpd -t -cf /etc/dhcp/dhcpd.conf` | the only test commands the agent runs |
| `ALLOWED_RESTART_CMDS` | `systemctl restart isc-dhcp-server` | the only restart commands the agent runs |
| `DHCP_CONF_DIR` | `/etc/dhcp` | dhcpd.conf directory, NetBox cannot change it |
| `ALLOWED_BASE` | first one from NetBox | base path of the CFG files (pinned on first contact) |
| `ALLOW_HTTP` | `yes` | `no` = never plain http (key + CFG unencrypted) |
| `CURL_OPTS` | – | e.g. `(--cacert /etc/ssl/certs/netbox-ca.pem)` |
| `DEFAULT_FIX` | `yes` | fixes `/etc/default/isc-dhcp-server` (IPv4 interfaces, IPv6 off) |
| `APPARMOR_FIX` | `yes` | lets dhcpd read the base path under AppArmor |
| `KEEP_BACKUPS` | `10` | backups kept |
| `TEST_SERVER` | `netbox` | `netbox` = the NetBox *Test server* switch decides, `no` = never simulate the first run here, `yes` = always allowed |
| `LEASES_FILE` | `/var/lib/dhcp/dhcpd.leases` | copied into every CFG backup (`_leases/`) and periodically (interval + copies set in NetBox, default 1 h / 72) to `<backup dir>/leases/<date-time>/` (date format set in NetBox, the agent renames old dirs); never restored |
| `START_WAIT` | `5` | seconds after restart before checking dhcpd |

Commands: `--setup`, `--once`, `--show`, `--set-url`, `--set-token`, `--set NAME value`, `--version`, `--help`.

## Security
- The agent runs **only** the commands in a fixed list, identical in the plugin and the agent (shown read-only in
  CFG pluginu → DHCP servery → *Commands NetBox can send to the agent*). Anything else is ignored and logged as SECURITY.
- Test/restart: only locally allowed commands. Paths: dhcpd.conf dir fixed, base path pinned, system directories refused.
- Deletes: only CFG files below the base path; `rm -rf` only on the agent's own backups below `/opt/`.
- All URLs from NetBox are used on the agent's own NetBox address; the key is read by curl from a root-only file.
- Use **https** in production (`ALLOW_HTTP=no`). `dhcpd -t` on the server is always the final check; a failing CFG is rolled back.

---

# NetBox ISC DHCP (SK)

Plugin pre NetBox 4.7, ktorý z dát NetBoxu generuje konfiguráciu **ISC DHCP (dhcpd 4.4)**, a **isc-dhcp-agent**, bash
služba na DHCP serveri, ktorá ho drží v súlade s NetBoxom (stiahnutie → záloha → test → reštart → hlásenie).

## Inštalácia pluginu
```bash
sudo bash -c 'source /opt/netbox/venv/bin/activate && pip install "git+https://github.com/ArK761/NetBox_ISC-DHCP.git@v1.0.0" && cd /opt/netbox/netbox && python manage.py migrate netbox_isc_dhcp && systemctl restart netbox netbox-rq'
```
Do `configuration.py` pridaj `PLUGINS = ["netbox_isc_dhcp"]`. Potom v NetBoxe **CFG pluginu** (jazyk, základná cesta,
podadresáre) → **DHCP-CFG** (dhcpd.conf, DNS, Subnety, Hosty). Aktualizácia = ten istý príkaz s
`--upgrade --force-reinstall --no-deps` a novou verziou; migrácie sú v balíku (nikdy `makemigrations` na serveri).

## Inštalácia agenta (každý DHCP server)
1. NetBox → **CFG pluginu → DHCP servery**: pridaj server (názov + IP/FQDN), stlač **Vygenerovať kľúč**. Stránka ukáže
   API adresu agenta a hotový inštalačný príkaz.
2. Na DHCP serveri:
```bash
curl -fsSL https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP/v1.0.0/agent/install.sh | sudo bash -s -- --ref v1.0.0 --url https://<netbox>/api/plugins/isc-dhcp/agent/ --token <kľúč>
```
3. Kontrola: `sudo isc-dhcp-agent --show`, `sudo systemctl status isc-dhcp-agent`, log `/var/log/isc-dhcp-agent.log`.
   Server je v NetBoxe *online* do jedného intervalu. Ďalšie verzie agenta nainštaluješ z NetBoxu tlačidlom **Aktualizovať agenta**.

## Nastavenie agenta
V NetBoxe (CFG pluginu → DHCP servery): interval, príkaz testu a reštartu, adresár záloh (**len pod `/opt/`**,
predvolene `/opt/BCK`), postupné nasadenie, balík, ponechanie chybného CFG.
Lokálne na serveri v `/etc/isc-dhcp-agent.conf` (len root, 600), zmena `sudo isc-dhcp-agent --set NAZOV hodnota`
(tabuľka nastavení je vyššie v anglickej časti). Úplný popis: [docs/NAVOD_SK.pdf](docs/NAVOD_SK.pdf).

## Bezpečnosť
Agent vykoná **len** príkazy z pevného zoznamu, rovnakého v plugine aj v agente (v NetBoxe rozbaľovacie, nedá sa meniť);
ostatné ignoruje a zapíše SECURITY. Test a reštart len lokálne povolené príkazy. Maže len CFG súbory pod základnou cestou,
`rm -rf` len na vlastné zálohy pod `/opt/`. V produkcii používaj **https** (`ALLOW_HTTP=no`).
