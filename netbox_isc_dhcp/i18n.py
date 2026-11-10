"""Tiny translation layer for plugin strings (Slovak default, English)."""
from django.utils.functional import lazy

TR = {
    "menu.base": ("Základný dhcpd.conf", "Base dhcpd.conf"),
    "menu.groups": ("Skupiny tenantov", "Tenant groups"),
    "menu.dns": ("DNS servery", "DNS servers"),
    "menu.settings": ("Nastavenia pluginu", "Plugin settings"),
    "warn.no_dns": (
        "Nie je zvolený žiadny DNS server pre DHCP server. Zvoľte DNS v sekcii „DNS servery“.",
        "No DNS server is selected for the DHCP server. Select one in the “DNS servers” section.",
    ),
    "err.max_dns": ("Naraz môžu byť v použití najviac {n} DNS servery.", "At most {n} DNS servers can be in use at once."),
    "col.name": ("Názov", "Name"),
    "col.in_use": ("Používa sa", "In use"),
    "tip.toggle": ("Prepnúť používanie", "Toggle usage"),
    "tab.preview": ("Náhľad", "Preview"),
    "lbl.name": ("Názov", "Name"),
    "lbl.static": ("Pasívna (statická) časť", "Static (passive) part"),
    "lbl.settings": ("Nastavenia", "Settings"),
    "lbl.table_dir": ("Adresár tabuliek", "Table directory"),
    "lbl.subnet_dir": ("Adresár subnetov", "Subnet directory"),
    "lbl.prefix_by": ("Prefix sa vyberá podľa", "Prefix selected by"),
    "lbl.generated": ("Vygenerovaný", "Generated"),
    "lbl.dns": ("DNS server", "DNS server"),
    "lbl.group": ("DHCP skupina", "DHCP group"),
    "lbl.tenant_group": ("Skupina tenantov", "Tenant group"),
    "lbl.order": ("Poradie", "Order"),
    "lbl.files": ("Súbory", "Files"),
    "lbl.language": ("Jazyk", "Language"),
    "col.export": ("Zahrnúť do configu", "Include in config"),
    "lbl.fields": ("Polia tenanta", "Tenant fields"),
    "lbl.template": ("šablóna", "template"),
    "menu.paths": ("Adresáre", "Directories"),
    "lbl.path": ("Cesta", "Path"),
    "lbl.directory": ("Adresár", "Directory"),
    "col.include": ("Zahrnúť do configu", "Include in config"),
    "lbl.config_path": ("Cesta k dhcpd.conf", "dhcpd.conf path"),
    "lbl.base_path": ("Základná cesta súborov", "Base path of files"),
    "lbl.add_file": ("Pridať súbor", "Add file"),
    "lbl.regenerate": ("Pregenerovať", "Regenerate"),
    "msg.regen_changed": ("Súbor bol pregenerovaný, obsah sa zmenil.", "File regenerated, the content changed."),
    "msg.regen_same": ("Súbor bol pregenerovaný, obsah je rovnaký (bez zmeny).", "File regenerated, content is the same (no change)."),
    "lbl.generated_at": ("Vygenerované (posledná zmena)", "Generated (last change)"),
    "lbl.never": ("ešte nevygenerované", "not generated yet"),
    "lbl.file": ("Súbor", "File"),
    "lbl.subdirs": ("Podadresáre", "Subdirectories"),
    "lbl.add_subdir": ("Pridať podadresár", "Add subdirectory"),
    "lbl.paths": ("Cesty na DHCP serveri", "Paths on the DHCP server"),
    "lbl.not_set": ("nenastavené", "not set"),
    "lbl.no_subdirs": ("Zatiaľ žiadne podadresáre.", "No subdirectories yet."),
    "msg.saved": ("Uložené.", "Saved."),
    "lbl.save": ("Uložiť", "Save"),
    "lbl.click_edit": ("Kliknite pre úpravu", "Click to edit"),
    "lbl.new_subdir": ("názov, napr. TABLE", "name, e.g. TABLE"),
    "warn.no_table_dir": ("{n} súborov nemá podadresár: v Nastaveniach pluginu zvoľte predvolený podadresár pre tabuľky.", "{n} files have no subdirectory: choose the default table subdirectory in plugin settings."),
    "warn.bad_names": ("Súbory s nepovolenými znakmi v názve boli vynechané: {names}", "Files with invalid characters in the name were left out: {names}"),
    "warn.no_base_path": ("Základná cesta nie je nastavená (Nastavenia pluginu).", "Base path is not set (plugin settings)."),
    "warn.no_subnet_dir": ("Podadresár pre subnety nie je zvolený (Nastavenia pluginu): subnety sa nezaradia.", "Subnet subdirectory is not chosen (plugin settings): subnets are left out."),
    "lbl.table_dir": ("Predvolený podadresár pre tabuľky", "Default subdirectory for tables"),
    "lbl.subnet_dir2": ("Podadresár pre subnety", "Subdirectory for subnets"),
    "lbl.file_path": ("Súbor na DHCP serveri", "File on the DHCP server"),
    "lbl.source": ("Zdroj subnetov: objekt", "Subnet source: object"),
    "lbl.src_field": ("Pole objektu", "Object field"),
    "lbl.src_value": ("Hodnota poľa", "Field value"),
    "lbl.none": ("— žiadny —", "— none —"),
    "lbl.conditions": ("Podmienky (všetky musia platiť)", "Conditions (all must match)"),
    "lbl.add_cond": ("Pridať pole", "Add field"),
    "lbl.pick_field": ("— vyberte pole —", "— pick a field —"),
    "lbl.no_conds": ("Zatiaľ žiadne podmienky.", "No conditions yet."),
    "lbl.pick_object_first": ("Najprv zvoľte objekt.", "Pick the object first."),
    "lbl.any_value": ("ľubovoľná (nefiltruje)", "any (no filter)"),
    "lbl.matched": ("Vybrané: {n} objektov", "Selected: {n} objects"),
    "lbl.matched_none": ("Vybrané: nič (nastavte aspoň jednu hodnotu)", "Selected: nothing (set at least one value)"),
    "menu.hosts": ("Hosty a MAC adresy", "Hosts and MAC addresses"),
    "lbl.dynamic": ("Dynamická časť", "Dynamic part"),
    "lbl.dynamic_info": ("Plugin do tejto časti zapisuje výhradne cesty INCLUDE súborov, nie časti konfigurácie DHCP servera (žiadne statické IP, hosty ani subnety).",
                         "The plugin writes only INCLUDE file paths into this part, never parts of the DHCP server configuration (no static IPs, hosts or subnets)."),
    "lbl.no_includes": ("Zatiaľ žiadne INCLUDE súbory.", "No INCLUDE files yet."),
    "menu.plugin": ("CFG pluginu", "Plugin CFG"),
    "menu.dhcp": ("DHCP-CFG", "DHCP-CFG"),
    "hub.base": ("Statická časť a INCLUDE súbory hlavného konfiguračného súboru.", "Static part and INCLUDE files of the main configuration file."),
    "hub.dns": ("DNS servery pre subnety (najviac 2 v použití).", "DNS servers for subnets (at most 2 in use)."),
    "hub.hosts": ("Tenanti: MAC adresy, statické IP a tabuľky tried.", "Tenants: MAC addresses, static IPs and class tables."),
    "lbl.static_info": ("Statickú časť si musí používateľ nastaviť sám: globálne nastavenia DHCP servera (napr. authoritative, lease časy, logovanie, primárny subnet rozhrania). Plugin ju nemení ani nevypĺňa.",
                        "The static part must be set by the user: global DHCP server settings (e.g. authoritative, lease times, logging, the primary interface subnet). The plugin never changes or fills it."),
    "lbl.static_empty": ("Zatiaľ prázdne – kliknite a napíšte vlastnú konfiguráciu.", "Empty – click and write your own configuration."),
    "menu.subnets": ("Subnety", "Subnets"),
    "hub.subnets": ("Objekt a podmienky (ľubovoľné polia a hodnoty), z ktorých sa vyberajú subnety.", "Object and conditions (any fields and values) the subnets are selected from."),
    "lbl.subnet_source": ("Zdroj subnetov", "Subnet source"),
    "lbl.n_selected": ("vybrané: {n}", "selected: {n}"),
    "lbl.all_except": ("všetko okrem {n}", "all except {n}"),
    "lbl.mode_include": ("iba zaškrtnuté", "only ticked"),
    "lbl.mode_exclude": ("všetko okrem zaškrtnutých", "all except ticked"),
    "lbl.select_all": ("Vybrať všetky", "Select all"),
    "lbl.select_none": ("Odškrtnúť všetky", "Untick all"),
    "lbl.search": ("Hľadať…", "Search…"),
    "lbl.pool_key": ("určuje typ poolu", "defines the pool type"),
    "lbl.set_pool_key": ("Nastaviť ako typ poolu", "Use as pool type"),
    "lbl.pools": ("Pooly (podľa typu poolu)", "Pools (by pool type)"),
    "lbl.no_pool_key": ("Pri jednom poli kliknite na „Nastaviť ako typ poolu“ (napr. POOL_TYPE).", "Click “Use as pool type” on one field (e.g. POOL_TYPE)."),
    "lbl.prefixes": ("Rozsahy", "Prefixes"),
    "lbl.generate": ("Generovať", "Generate"),
    "lbl.template_code": ("Kód (šablóna) poolu", "Pool code (template)"),
    "lbl.preview_for": ("Náhľad pre rozsah", "Preview for prefix"),
    "lbl.errors": ("Chyby – súbor by sa nepoužil", "Errors – the file would not be used"),
    "lbl.variables": ("Premenné", "Variables"),
    "lbl.no_prefix": ("Tento pool nemá žiadny rozsah.", "This pool has no prefix."),
    "lbl.all_values": ("všetky ({n}) – aj neskôr pridané", "all ({n}) – also ones added later"),
    "lbl.none_selected": ("nič (všetko vylúčené)", "nothing (all excluded)"),
    "lbl.gateway": ("Brána (GW) pre všetky rozsahy", "Gateway (GW) for all prefixes"),
    "lbl.gw_first": ("prvá voľná (použiteľná) IP", "first free (usable) IP"),
    "lbl.gw_last": ("posledná voľná (použiteľná) IP", "last free (usable) IP"),
    "err.pool_key_many": ("Pole má {n} rôznych hodnôt – typ poolu môže mať najviac {max}. Kliknite na kľúč pri správnom poli (napr. POOL_TYPE).",
                          "The field has {n} different values – a pool type may have at most {max}. Click the key on the right field (e.g. POOL_TYPE)."),
    "menu.vars": ("Vlastné premenné", "Own variables"),
    "hub.vars": ("Voľby ISC (lease, DNS, …) s vlastným popisom; v kóde poolu ich vložíte cez USE <popis> (alebo napíšte ..).",
                 "ISC options (lease, DNS, …) with your own description; insert them in pool code with USE <name> (or type ..)."),
    "lbl.var_factor": ("Násobok max lease (max-lease-time = lease × násobok)", "Max lease factor (max-lease-time = lease × factor)"),
    "lbl.var_desc": ("Popis (použitie v kóde: USE popis)", "Description (use in code: USE name)"),
    "lbl.var_option": ("Voľba ISC", "ISC option"),
    "lbl.var_value": ("Hodnota", "Value"),
    "lbl.var_lines": ("Vloží do kódu", "Inserts into code"),
    "lbl.var_used": ("Používa sa", "Used by"),
    "lbl.var_add": ("Pridať premennú", "Add variable"),
    "lbl.var_pick": ("— vyhľadajte voľbu ISC —", "— find an ISC option —"),
    "lbl.var_none": ("Zatiaľ žiadne premenné.", "No variables yet."),
    "lbl.var_hint": ("V kóde poolu napíšte .. a vyberte premennú, alebo napíšte riadok USE popis.", "In pool code type .. and pick a variable, or write a line USE name."),
    "lbl.var_locked": ("Popis sa nedá meniť, premenná sa používa.", "Description cannot be changed, the variable is in use."),
    "err.var_option": ("Vyberte voľbu ISC.", "Pick an ISC option."),
    "err.var_name": ("Popis môže obsahovať len písmená, číslice, _ . - (bez medzier).", "Description may contain only letters, digits, _ . - (no spaces)."),
    "err.var_exists": ("Premenná {name} už existuje.", "Variable {name} already exists."),
    "err.var_used": ("Premenná {name} sa používa – popis sa nedá meniť ani zmazať.", "Variable {name} is in use – it cannot be renamed or deleted."),
    "err.var_factor": ("Násobok musí byť číslo od 1 do 10.", "Factor must be a number from 1 to 10."),
    "lbl.no_dns_servers": ("Najprv pridajte DNS servery v sekcii DNS servery.", "Add DNS servers in the DNS servers section first."),
    "grp.lease": ("Lease", "Lease"),
    "grp.dns": ("DNS", "DNS"),
    "grp.net": ("Sieť", "Network"),
    "grp.access": ("Prístup", "Access"),
    "grp.pxe": ("PXE / boot", "PXE / boot"),
    "grp.ddns": ("DDNS", "DDNS"),
    "grp.own": ("Vlastné", "Own"),
    "opt.raw": ("Vlastný text (ľubovoľné riadky)", "Own text (any lines)"),
    "hint.gateway": ("globálne, Subnety", "global, Subnets"),
    "hint.ip": ("n>0 od siete, n<0 od broadcastu, -1 = posledná použiteľná", "n>0 from the network, n<0 from the broadcast, -1 = last usable"),
    "ph.lease": ("600 (sekundy)", "600 (seconds)"),
    "lbl.yes": ("áno", "yes"),
    "lbl.no": ("nie", "no"),
}
LANGS = (("sk", "Slovenčina"), ("en", "English"))


def current_language() -> str:
    try:
        from .models import PluginSettings

        obj = PluginSettings.objects.first()
        if obj and obj.language in dict(LANGS):
            return obj.language
    except Exception:  # DB not ready (e.g. before migrate)
        pass
    return "sk"


# Validation messages come from pure code in English; Slovak versions:
_MSG_SK = {
    "lease must be a positive number of seconds": "lease musí byť kladné číslo (sekundy)",
    "pick at least one DNS server": "zvoľte aspoň jeden DNS server",
    "value must be a whole number": "hodnota musí byť celé číslo",
    "value must be an IPv4 address": "hodnota musí byť IPv4 adresa",
    "value must be IPv4 addresses separated by commas": "hodnota musia byť IPv4 adresy oddelené čiarkou",
    "enter at least one address": "zadajte aspoň jednu adresu",
    "enter a text without quotes (they are added automatically)": "zadajte text bez úvodzoviek (doplnia sa samé)",
    "enter texts separated by commas, without quotes": "zadajte texty oddelené čiarkou, bez úvodzoviek",
    "choose allow or deny": "vyberte allow alebo deny",
    "choose true or false": "vyberte true alebo false",
    "choose on or off": "vyberte on alebo off",
    "enter the text": "zadajte text",
}


def tmsg(text: str) -> str:
    """Translate a validation message of the pure code (English) to the current language."""
    return _MSG_SK.get(text, text) if current_language() == "sk" else text


def t(key: str, **kw) -> str:
    if key not in TR:  # a missing translation must never break a page
        return key
    sk, en = TR[key]
    text = en if current_language() == "en" else sk
    return text.format(**kw) if kw else text


t_lazy = lazy(t, str)
