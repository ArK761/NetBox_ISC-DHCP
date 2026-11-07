"""Global page addition: version + commit badge at the bottom left of plugin pages."""
import json

from netbox.plugins import PluginTemplateExtension

from .middleware import PLUGIN_PATH
from .version import label

__all__ = ("template_extensions",)


_BADGE_JS = """document.addEventListener("DOMContentLoaded",function(){
if(document.getElementById("isc-dhcp-version"))return;
var d=document.createElement("div");d.id="isc-dhcp-version";
d.innerHTML='<i class="mdi mdi-tag-outline me-1"></i>';
d.appendChild(document.createTextNode(__TEXT__));
d.style.cssText="position:fixed;left:12px;bottom:12px;z-index:1030;padding:2px 10px;border-radius:999px;font-size:12px;background:rgba(108,117,125,.85);color:#fff;pointer-events:none;";
document.body.appendChild(d);});"""

# Keep the plugin's menu group open on every plugin page and highlight the current item.
_MENU_JS = """document.addEventListener("DOMContentLoaded",function(){
var base="/plugins/isc-dhcp/",path=location.pathname,best=null,bestLen=-1;
document.querySelectorAll('a[href*="'+base+'"]').forEach(function(a){
var nav=a.closest("nav,.navbar");var box=a.closest(".collapse");
if(!nav||!box)return;
var h=a.getAttribute("href").replace(base+"open/",base);
if(path.indexOf(h)===0&&h.length>bestLen){best=a;bestLen=h.length;}
});
var items=document.querySelectorAll('nav a[href*="'+base+'"],.navbar a[href*="'+base+'"]');
var target=best||(items.length?items[0]:null);
if(!target)return;
var box=target.closest(".collapse");
while(box){
box.classList.add("show");
var id=box.id;
if(id){document.querySelectorAll('[data-bs-target="#'+id+'"],a[href="#'+id+'"]').forEach(function(t){
t.classList.remove("collapsed");t.setAttribute("aria-expanded","true");});}
box=box.parentElement?box.parentElement.closest(".collapse"):null;
}
if(best){best.classList.add("active");}
});"""


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
        return "<script>" + _BADGE_JS.replace("__TEXT__", text) + _MENU_JS + "</script>"


template_extensions = [VersionBadge]
