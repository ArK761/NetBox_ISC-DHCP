"""Which object a config part is built from, its fields (standard + custom) and the accepted values."""
from django.apps import apps
from django.db import models
from django.db.models import Q
from extras.models import CustomField



def source_models() -> list[tuple[str, str, str]]:
    """Every public NetBox object type: (value 'app.model', group label, model label), sorted."""
    from core.models import ObjectType

    out = []
    for ot in ObjectType.objects.public():
        m = ot.model_class()
        if m is None or ot.app_label in _INTERNAL_APPS:
            continue
        app = apps.get_app_config(ot.app_label).verbose_name
        out.append((f"{ot.app_label}.{ot.model}", str(app), str(m._meta.verbose_name).capitalize()))
    return sorted(out, key=lambda o: (o[1].lower(), o[2].lower()))


def source_label(value: str) -> str:
    m = get_model(value)
    if m is None:
        return ""
    return f"{apps.get_app_config(m._meta.app_label).verbose_name} › {str(m._meta.verbose_name).capitalize()}"
_SKIP = {"id", "created", "last_updated", "custom_field_data", "_depth", "_children", "lft", "rght", "tree_id", "level"}
MAX_FK_CHOICES = 500
_INTERNAL_APPS = {"core", "extras", "users", "netbox_isc_dhcp"}  # internal objects (tags, journal, export templates...) are not offered


def get_model(label):
    try:
        return apps.get_model(label) if label else None
    except (LookupError, ValueError):
        return None


def field_options(model) -> list[dict]:
    """All selectable fields of the object: standard fields first, then custom fields (key cf_<name>)."""
    if model is None:
        return []
    out = []
    for f in model._meta.get_fields():
        if f.name in _SKIP or f.name.startswith("_") or not getattr(f, "concrete", False) or f.many_to_many:
            continue
        if isinstance(f, (models.JSONField,)) or getattr(f, "auto_created", False):
            continue
        out.append({"key": f.name, "label": str(getattr(f, "verbose_name", f.name)).capitalize()})
    out.sort(key=lambda o: o["label"].lower())
    for cf in sorted(CustomField.objects.get_for_model(model), key=lambda c: c.name):
        out.append({"key": f"cf_{cf.name}", "label": f"{cf.label or cf.name} (custom field)"})
    return out


def _custom_field(model, key):
    name = key[3:]
    return next((c for c in CustomField.objects.get_for_model(model) if c.name == name), None)


def value_choices(model, key):
    """List of (value, label) when the field has a fixed set of values, otherwise None (free text)."""
    if model is None or not key:
        return None
    if key.startswith("cf_"):
        cf = _custom_field(model, key)
        if cf is None:
            return None
        if cf.type == "boolean":
            return [("true", "true"), ("false", "false")]
        if getattr(cf, "choice_set", None):
            return [(str(v), str(l)) for v, l in cf.choice_set.choices]
        return None
    try:
        f = model._meta.get_field(key)
    except Exception:
        return None
    if isinstance(f, models.BooleanField):
        return [("true", "true"), ("false", "false")]
    if f.choices:
        return [(str(v), str(l)) for v, l in f.flatchoices]
    if f.is_relation and f.related_model is not None:
        qs = f.related_model.objects.all()
        if qs.count() <= MAX_FK_CHOICES:
            return [(str(o.pk), str(o)) for o in qs]
    return None


def value_label(model, key, value) -> str:
    for v, l in value_choices(model, key) or []:
        if v == value:
            return l
    return value


def label_for(model, key) -> str:
    return next((o["label"] for o in field_options(model) if o["key"] == key), key)


def _convert(value, kind):
    if kind == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "ano", "áno")
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def build_q(model, conditions) -> Q:
    """All conditions must match (AND). Conditions without a value are ignored."""
    q = Q()
    for c in conditions or []:
        key, value = c.get("field"), c.get("value", "")
        if not key or value == "":
            continue
        if key.startswith("cf_"):
            cf = _custom_field(model, key)
            kind = "bool" if cf is not None and cf.type == "boolean" else "int" if cf is not None and cf.type == "integer" else "str"
            q &= Q(**{f"custom_field_data__{key[3:]}": _convert(value, kind)})
            continue
        f = model._meta.get_field(key)
        if isinstance(f, models.BooleanField):
            q &= Q(**{key: _convert(value, "bool")})
        elif f.is_relation:
            q &= Q(**{f"{key}_id": _convert(value, "int")}) if str(value).isdigit() else Q(**{f"{key}__name": value})
        else:
            q &= Q(**{key: value})
    return q
