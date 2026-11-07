from django import template

from ..i18n import t

register = template.Library()


@register.simple_tag
def tr(key):
    return t(key)
