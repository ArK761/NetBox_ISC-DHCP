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


def distinct_values(model, key, limit=5000) -> list[tuple[str, str]]:
    """Every value the field has (fixed choices, or the values found in the database), naturally sorted."""
    from .dhcp_tables import natural_key

    fixed = value_choices(model, key)
    if fixed is not None:
        return fixed
    if model is None or not key:
        return []
    if key.startswith("cf_"):
        lookup = f"custom_field_data__{key[3:]}"
        raw = model.objects.exclude(**{f"{lookup}__isnull": True}).values_list(lookup, flat=True).distinct()[:limit]
    else:
        raw = model.objects.exclude(**{f"{key}__isnull": True}).values_list(key, flat=True).distinct()[:limit]
    vals = sorted({str(v) for v in raw if v not in (None, "")}, key=natural_key)
    return [(v, v) for v in vals]


def cond_values(c) -> list[str]:
    """Selected values of a condition (old format had a single 'value')."""
    if "values" in c:
        return [str(v) for v in c.get("values") or []]
    v = c.get("value", "")
    return [str(v)] if v != "" else []


def _convert(value, kind):
    if kind == "bool":
        return str(value).strip().lower() in ("1", "true", "yes", "ano", "áno")
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


def _field_q(model, key, values) -> Q:
    if key.startswith("cf_"):
        cf = _custom_field(model, key)
        kind = "bool" if cf is not None and cf.type == "boolean" else "int" if cf is not None and cf.type == "integer" else "str"
        return Q(**{f"custom_field_data__{key[3:]}__in": [_convert(v, kind) for v in values]})
    f = model._meta.get_field(key)
    if isinstance(f, models.BooleanField):
        return Q(**{f"{key}__in": [_convert(v, "bool") for v in values]})
    if f.is_relation:
        ids = [int(v) for v in values if str(v).isdigit()]
        names = [v for v in values if not str(v).isdigit()]
        return Q(**{f"{key}_id__in": ids}) | Q(**{f"{key}__name__in": names}) if names else Q(**{f"{key}_id__in": ids})
    return Q(**{f"{key}__in": list(values)})


def is_active(c) -> bool:
    return bool(c.get("field")) and bool(cond_values(c))


def build_q(model, conditions) -> Q:
    """All conditions must match (AND). Within one field: any of the ticked values (mode include)
    or none of them (mode exclude). A condition with nothing ticked does not filter."""
    q = Q()
    for c in conditions or []:
        if not is_active(c):
            continue
        fq = _field_q(model, c["field"], cond_values(c))
        q &= ~fq if c.get("mode") == "exclude" else fq
    return q
