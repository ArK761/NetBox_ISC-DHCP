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
    "col.export": ("Exportovať do configu", "Export to config"),
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


def t(key: str, **kw) -> str:
    if key not in TR:  # a missing translation must never break a page
        return key
    sk, en = TR[key]
    text = en if current_language() == "en" else sk
    return text.format(**kw) if kw else text


t_lazy = lazy(t, str)
