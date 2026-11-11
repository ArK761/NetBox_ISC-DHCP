from django import template

from ..i18n import t

register = template.Library()


@register.simple_tag
def tr(key):
    return t(key)


@register.filter
def isc_highlight(text):
    """Escape code and mark own-variable lines yellow: USE lines, the marker comment, generated lines."""
    import re

    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    out = []
    for line in (text or "").split("\n"):
        e = escape(line)
        if re.match(r"^\s*USE\s+\S+\s*$", line) or "## VARIABLE ADDED VIA OWN VARIABLES" in line or "## added via own variable" in line:
            e = f'<mark class="isc-var">{e}</mark>'
        out.append(e)
    return mark_safe("\n".join(out))
