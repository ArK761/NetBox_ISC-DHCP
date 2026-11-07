"""Global page addition: version + commit badge at the bottom left of plugin pages."""
import json

from netbox.plugins import PluginTemplateExtension

from .middleware import PLUGIN_PATH
from .version import label

__all__ = ("template_extensions",)


class VersionBadge(PluginTemplateExtension):
    """No models = global: head() is rendered on every NetBox page."""

    def head(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or PLUGIN_PATH not in request.path:
            return ""
        try:
            text = json.dumps(label())
        except Exception:
            return ""
        return (
            '<script>document.addEventListener("DOMContentLoaded",function(){'
            "if(document.getElementById('isc-dhcp-version'))return;"
            "var d=document.createElement('div');d.id='isc-dhcp-version';"
            "d.innerHTML='<i class=\"mdi mdi-tag-outline me-1\"></i>';"
            f"d.appendChild(document.createTextNode({text}));"
            "d.style.cssText='position:fixed;left:12px;bottom:12px;z-index:1030;padding:2px 10px;"
            "border-radius:999px;font-size:12px;background:rgba(108,117,125,.85);color:#fff;"
            "pointer-events:none;';document.body.appendChild(d);});</script>"
        )


template_extensions = [VersionBadge]
