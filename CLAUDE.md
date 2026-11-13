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
- MENU: sidebar has ONLY two items: 'CFG pluginu' (settings) and 'DHCP-CFG' (hub page /plugins/isc-dhcp/dhcp/ with links: dhcpd.conf, DNS, Subnety, Hosty a MAC adresy).
  All DHCP pages live under dhcp/ (dhcp/base-config, dhcp/dns, dhcp/groups, dhcp/groups/files) so DHCP-CFG stays highlighted.
- NEVER ship owner site data (dhcpd.conf text, domains, IPs, MACs, host names) in the repo. Static part default is EMPTY + note that the user must set it.
- dhcpd.conf page: ONLY static part (click-to-edit) + dynamic part (read-only include lines + info that the plugin writes only INCLUDE paths).
  Object/conditions picker lives in SubnetConfig (singleton, page DHCP-CFG > Subnety, URL dhcp/subnets/): source_model + conditions, live 'Vybrané: N objektov'.
  Condition = {field, values[], mode include|exclude, pool_key}. Row expands to a checkbox list of ALL values (search box, Select all / Untick all).
  One row is marked 'určuje typ poolu' (owner: POOL_TYPE). Each pool type value -> PoolTemplate (name, Generate checkbox, Jinja code) at
  dhcp/subnets/pools/<pk>/ with preview on a real prefix of that pool + validation (subnet_render.py: ip(n), first/last_usable, dns, obj, cf).
  Value list is rendered ONLY for the row being edited (?edit=<i>), never all prefixes on the page. All ticked -> {all: true} (also future values).
  Object-type custom fields (owner's POOL_TYPE -> object) store ids: show names, filter by id; pools are named by the object name.
  Pool-type key refused on fields with > 100 values. Global gateway = SubnetConfig.gateway_mode (first/last usable) -> template var `gateway`.
  Subnet directory chosen on the Subnety page (= PluginSettings.subnet_dir).
  OWN VARIABLES (DHCP-CFG > Vlastné premenné, dhcp/variables/): ConfigVariable(name=description, option from CATALOG in variables.py, value, dns_servers).
  Pool code line `USE <name>` is replaced by the variable's ISC lines (indent kept); lease -> default + max (PluginSettings.lease_factor, 1.3).
  Used variables (any USE in pool/file code) cannot be deleted; renaming rewrites all `USE old` lines in pools, files AND subnet overrides (variables.rename_use, atomic). `..` inserts `## VARIABLE ADDED VIA OWN VARIABLES` + USE; USE/comment lines are yellow (editor overlay .isc-ed-back, filter isc_highlight); generated variable lines end with `## added via own variable NAME ##`. Code editors: no spellcheck, no wrap, `..` autocomplete (_code_editor.html).
  All text/code fields are stored with LF (browsers send CRLF) - pre_save signal.
  DONE v0.10.0: PoolTemplate.suitable (sizes /16-/30 the code renders on, lenient = size errors only), min/max_prefixlen ("Používať pre").
  compat.py: incompatible subnets (size outside range or render error) cached (django cache, invalidated by signals on Prefix/pool/config/DNS/vars/files);
  red banner once per page (middleware _error_once), lists on Subnety + pool page. Incompatible subnets must NEVER be exported (use compat in the export step).
  DONE v0.11.0: SubnetOverride (pool, prefix_id, code) = individual code of one subnet, only when PoolTemplate.allow_override; editor at
  dhcp/subnets/pools/<pk>/override/<prefix_pk>/ (check on that subnet only, draft kept); pool code save skips overridden subnets + lists them;
  states active/disabled/orphan. Plugin warnings (no DNS, incompatible, overrides) are a solid bar at the TOP of plugin pages (middleware), not toasts
  (toasts covered buttons). Export must use the override code for overridden subnets.
  DONE v0.12.2: tree bars have a "Zobraziť strom" toggle (no "Subnety ->" link; details.isc-notice display:block, NetBox .alert is flex). Orphan USE names (variable missing, e.g. renamed in old version): red bar + card on Vlastné premenné with remap (views._rewrite_use shared with rename). Updating the plugin never changes stored data.
  DONE v0.12.4: pools table + pool page show code state (PoolTemplate.is_default_code: predvolený/upravený, +N individuálne, _code_state.html); pool page has breadcrumb DHCP-CFG / Subnety + "Späť na Subnety" button.
  DONE v0.12.5: no generic Edit form for singletons (Subnety, dhcpd.conf, settings: no Edit/Delete) and pools (Delete only); their /edit/ URL redirects to the page (_crud singleton / inline_only). Everything is edited inline.
  DONE v0.13.0 (hosts step 1): package netbox_isc_dhcp/hosts/ (models HostConfig singleton, logic, views, urls, texts merged into i18n; templates in templates/netbox_isc_dhcp/hosts/). Page dhcp/hosts/: group source object (fields + count), MAC source object, auto link field, 1-3 MAC fields, IP field, classes overview (dhcp_tables.prepare). Owner wants hosts work ONLY in hosts/ files. Hub link points here; old DHCPGroup pages still exist (replace later).
  DONE v0.13.1: hosts group source = "Zdroj tabuliek": table name field (pills), group_conditions like Subnety (field + values + Accept/Exclude, source_fields.build_q), result chips; host name field; MAC fields with order; IP field pills; migration 0020.
  DONE v0.13.2: hosts page like Subnety: conditions = collapsible rows (?edit=i, checkbox list + search, Accept/Exclude, Save/Select all/Untick), field pickers are click-to-edit drop-downs, two-column layout (label left), muted zeros. Owner wants a nice look (be a designer too).
  DONE v0.14.0: host source is PER GROUP (model HostGroup: group_model+group_pk, name, mac_model, link_field, host_name_field, mac_fields, ip_field; migration 0021 removes them from HostConfig). Hosts page: table source + table subdirectory (PluginSettings.table_dir, full path shown) + optional conditions (none = all groups) + groups table like pools (files with path, source, counts, "Nastaviť"). Group page dhcp/hosts/group/<pk>/: source settings, "Prevziať nastavenie" (copy from other group), both tables (_Table rows, _StaticTable host blocks), warnings.
  DONE v0.14.1: HostGroup.enabled (migration 0022) toggle in groups table + group page; OFF = files still made but WITHOUT MACs (base content only so dhcpd does not fail; content decided later), info bar on group page. Groups table: Objektov column (host source count, else related_count = objects NetBox links to the group).
  DONE v0.15.0: each group = 2 files <name><dynamic_suffix>/<static_suffix> (default _Dynamic/_Static, editable), each built from N HostSource rows (model, conditions like Subnety, host_name_field, mac_fields, ip_field; dynamic: ip_field = leave out objects with IP). Migration 0023 converts old per-group source (link -> condition). No condition = source picks nothing. Warnings incl. MAC in both files.
  DONE v0.15.1: hosts table source WITHOUT conditions (owner: the per-group switch is enough; group_conditions ignored, field kept); order: table subdirectory, object, name field (built-in or custom field). Hosts duplicate MAC/IP = warning only ("detegovaná duplicitná MAC/IP"), never skipped (dhcpd accepts duplicate MAC in class match and in host blocks); static: only a second host block with the same name is skipped (hosts/logic.prepare_hosts).
  DONE v0.15.2: hosts page cards: 1 Umiestnenie tabuliek (subdir, same font), 2 Zdroj tabuliek (green hint, tree Objekt -> Názov z poľa), 3 Skupiny.
  DONE v0.16.0: HostSource is per GROUP (no kind; migration 0024): hosts = rows [{mac, ip, dyn}] max 3, every field once. Row without IP -> _Dynamic; with IP -> _Static host block, dyn=True also MAC into _Dynamic (owner: avoids MismatchClient in another pool). Row with IP field but empty/invalid IP -> always _Dynamic (owner: no IP = cannot be static). Names NAME / NAME_<row>. Static: same host name never twice (dup_name lost). Group page: no on/off toggle (list only), summary "N hostov nepôjde do DHCP" (lost reasons) + warnings collapsible, card Zdroje hostov (tree), card Súbory (host lists collapsible). Test /home/user/hosts7.js (hosts6.js obsolete).
  NEXT hosts: code _Table/_StaticTable per group (like pools), generate + store files, includes in dhcpd.conf, replace old DHCPGroup pages.
  OLD-NEXT hosts: class table with code _Table/_StaticTable per class (like pools), generate files, includes.
  NEXT: store generated <network>_CFG files (sha256) for compatible subnets only (override code where active) + subnet includes in dhcpd.conf.
  DONE v0.9.0: save-time protection of pool code (owner: "kontrola musí prebiehať poriadne"): code is rendered on ALL prefixes of the pool,
  save refused on any error, draft kept in session + shown in editor, errors grouped (count + example prefix), Slovak via tmsg patterns.
  Checks: subnet_render.structure_errors + isc_rules.py (statement/option whitelist, value types, routers/subnet-mask/lease rules,
  classes from tenant tables + static part, log() words incl. `set` vars from the static part, custom `option X code N`). NO dhcpd on NetBox (never).
- (old) dhcpd.conf source: object = any public NetBox object type except core/extras/users/plugin (empty by default) + conditions list [{field, value}] on ANY field of the object (standard + cf_<name>),
  click-to-add / click-to-set value (select for choices/bool/FK, text otherwise), all must match (source_fields.build_q).
- ENGLISH: every UI text through i18n.py (SK + EN); validation messages of pure code are English, translated by tmsg(). Check with /home/user/en.py (EN crawl, 0 Slovak text).
- MANUAL (PDF, owner wants it updated continuously): sources docs/src/manual_sk.html + manual_en.html, build `node docs/src/build_pdf.js v<version>` -> docs/NAVOD_SK.pdf + docs/MANUAL_EN.pdf. Update both on every feature. No site data in it.
- NetBox turns every <select> into a TomSelect widget (ignores `hidden`): add class `no-ts` to selects that must hide/show.
- Every change: run /home/user/links.py (crawls every plugin link/button, bulk delete, forbidden UI words) and /home/user/it3.py before pushing.
  ALWAYS write links.py output to a file and grep it (a piped grep once hid a crash). Every NetBoxModel needs get_absolute_url (delete pages link dependent objects).

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
Paths live in PluginSettings (config_path = dhcpd.conf dir, base_path) and the settings page lists/edits subdirectories (DHCPPath); no separate menu item. URLs: subdirectories under settings/paths/, files under dhcp/groups/files/ so the menu link stays a substring.
dhcpd.conf includes: enabled group files (own dir or settings.table_dir) + <table_dir>/Netbox_Devices-MAC. Subnet includes are OFF until pool templates exist (no file would exist). REST API serializers exist for all models (NetBox needs them for delete/changelog).
Integration test: /home/user/it3.py (run with manage.py shell). Next: Pool templates (per POOL_TYPE, with export yes/no checkbox, Jinja, helpers first_usable/last_usable/ip(n), range validation), Netbox_Devices-MAC, generated files + hashes + manifest, signals, IP-restricted pages.
Not tested inside NetBox by us: owner tests and reports back.
