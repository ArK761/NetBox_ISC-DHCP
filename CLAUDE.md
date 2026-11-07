# NetBox ISC DHCP plugin: project notes (read first)

Owner: ArK761 (Slovak; answer in Slovak, short, no token waste, no unrequested bash scripts).
Repo: https://github.com/ArK761/NetBox_ISC-DHCP, working branch `claude/skeleton-pool-planner`.
Install on test server (ALWAYS this form, migrations must be committed, never makemigrations on server):
`sudo bash -c 'source /opt/netbox/venv/bin/activate && pip install --upgrade --force-reinstall --no-deps "git+https://github.com/ArK761/NetBox_ISC-DHCP.git@<SHA>" && cd /opt/netbox/netbox && python manage.py migrate netbox_isc_dhcp && systemctl restart netbox netbox-rq'`
Reference plugin for conventions: ArK761/NetBox_UserPIN (Django 6.1, NetBox 4.7+, hand-written migrations).

## Goal
Plugin generates ISC DHCP config from NetBox. A bash script on the DHCP server (written by the owner, NOT by us)
downloads changed files by hash and reloads dhcpd. Pages are unauthenticated but limited by client IP (later).

## Decisions
- dhcpd.conf = passive text (owner writes, verbatim, no template processing) + dynamic includes:
  `<Group>_Table`, `<Group>_StaticTable`, `Netbox_Devices-MAC` (TABLE dir), then `<network>_CFG` per prefix (SUBNET dir).
  Prefix is included when custom field DHCP_POOL = YES (configurable). Only ONE dhcpd.conf object (singleton).
- Tenant Group = DHCP class name. Tenant name = host-name. 1-3 MAC per tenant (owner picks the fields in GUI).
  1 MAC: `host NAME`; 2-3 MAC: `NAME_1`,`NAME_2`,`NAME_3`; `option host-name` always plain NAME.
  Tenant with static IP -> `<Group>_StaticTable` host blocks; without IP -> dynamic `<Group>_Table` (class match + mismatch class).
  Tenant without MAC: skipped silently. Device: only if it has MAC AND static IP -> Netbox_Devices-MAC (no option host-name).
- Pool templates are created by the owner in GUI (name = prefix POOL_TYPE value), Jinja2, one per pool type.
  Gateway/ranges are the template's business; plugin only offers helpers (first_usable/last_usable never network/broadcast)
  and validates rendered ranges (inside prefix, no overlap) so a bad prefix (e.g. /28) can never break dhcpd.
- DNS: table Name + IP + In use (checkbox). MAX 2 in use. Prefix field SUBNET_DNS is NOT used. Active DNS go to every pool template as `dns`.
  Changing DNS regenerates all subnets (not dhcpd.conf). No DNS in use -> error shown everywhere in the plugin.
- Which tenant groups get tables: selected in plugin (model DHCPGroup).
- Languages: Slovak (default) and English, set in plugin settings (model PluginSettings).
- Changes in tenants/devices/prefixes/groups must recompute only affected files (hash per file) and expose a manifest.
- Speed matters: files pre-generated and stored with SHA256, never computed on request.

## Status
Done: base config generator (pure), BaseConfig/DHCPGroup/DNSServer/PluginSettings models + UI.
Version badge (plugin version + git commit from pip direct_url.json) is injected into plugin HTML pages by the middleware (top-right, in page flow); bump `__version__` in netbox_isc_dhcp/__init__.py on every release.
NetBox keeps a menu group expanded only if the menu link URL is a substring of the page URL (sidenav.ts): singleton menu links therefore use the list URL (redirects to the object), never a separate "open" URL.
Next: Pool templates, tables (tenants/devices), generated files + manifest, signals, IP-restricted pages.
Not tested inside NetBox by us: owner tests and reports back.
