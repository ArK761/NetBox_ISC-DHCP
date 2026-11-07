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

## UI rules (owner)
- NO import, export, changelog, journal, tags anywhere in the plugin (list actions = Add + Delete selected; table row menu = edit/delete;
  changelog/journal tabs removed from registry in ready(); forms drop tags + changelog_message).
- Values on settings / dhcpd.conf pages are click-to-edit inline (<details> + form, no JS). Layout single column, top to bottom.
- Delete confirmations (single, htmx modal, bulk) use plugin templates without changelog message / background job.
- dhcpd.conf source: object = any public NetBox object type except core/extras/users/plugin (empty by default) + conditions list [{field, value}] on ANY field of the object (standard + cf_<name>),
  click-to-add / click-to-set value (select for choices/bool/FK, text otherwise), all must match (source_fields.build_q).
- Every change: run /home/user/links.py (crawls every plugin link/button, bulk delete, forbidden UI words) and /home/user/it3.py before pushing.

## Status
Done: base config generator (pure), BaseConfig/DHCPGroup/DNSServer/PluginSettings models + UI.
Version badge (plugin version + git commit from pip direct_url.json) is injected into plugin HTML pages by the middleware (top-right, in page flow); bump `__version__` in netbox_isc_dhcp/__init__.py on every release.
NetBox keeps a menu group expanded only if the menu link URL is a substring of the page URL (sidenav.ts): singleton menu links therefore use the list URL (redirects to the object), never a separate "open" URL.
DONE v0.2.0: tenant TABLE generation. DHCPGroup (tenant group) has: tick-box tenant custom fields for MAC, IP field, and TWO editable Jinja templates
(table_template, static_template). Defaults in defaults/*.j2 reproduce the owner's WorkStation_Table byte for byte (golden test, natural sort order).
Template context: class_name, tenants, pairs, static_tenants, hosts (host has _1/_2/_3 suffix for several MACs).
Testing: a real NetBox 4.7.4 is set up in the sandbox (/home/user/nb_ref + /home/user/nbvenv, Postgres 5433, Redis 6380); start PG with pg_ctl as user postgres, then `manage.py shell < /home/user/it.py`.
DONE v0.3.0: BaseConfig has config_path + base_path; DHCPPath = named directories below base_path (TABLE, SUBNET, ...); a DHCPGroup owns many DHCPFile
(own name, directory, include checkbox, MAC fields, IP field, Jinja template). New group gets Name_Table + Name_StaticTable. Generated files are STORED
(content, sha256, generated) and refreshed by signals (tenant/group/file changes) or the regenerate button; pages never generate (only once if never generated).
Paths live in PluginSettings (config_path = dhcpd.conf dir, base_path) and the settings page lists/edits subdirectories (DHCPPath); no separate menu item. URLs: subdirectories under settings/paths/, files under groups/files/ so the menu link stays a substring.
dhcpd.conf includes: enabled group files (own dir or settings.table_dir) + <table_dir>/Netbox_Devices-MAC. Subnet includes are OFF until pool templates exist (no file would exist). REST API serializers exist for all models (NetBox needs them for delete/changelog).
Integration test: /home/user/it3.py (run with manage.py shell). Next: Pool templates (per POOL_TYPE, with export yes/no checkbox, Jinja, helpers first_usable/last_usable/ip(n), range validation), Netbox_Devices-MAC, generated files + hashes + manifest, signals, IP-restricted pages.
Not tested inside NetBox by us: owner tests and reports back.
