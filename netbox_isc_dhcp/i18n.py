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
    sk, en = TR[key]
    text = en if current_language() == "en" else sk
    return text.format(**kw) if kw else text


t_lazy = lazy(t, str)
