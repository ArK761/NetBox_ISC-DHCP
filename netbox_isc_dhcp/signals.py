"""Regenerate the stored files when the data they are built from changes."""
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from tenancy.models import Tenant, TenantGroup

from .models import DHCPFile, DHCPGroup


def _regenerate(**filters):
    from .services import regenerate_file

    for f in DHCPFile.objects.filter(**filters).select_related("group__group", "directory"):
        regenerate_file(f)


@receiver(post_save, sender=DHCPFile, dispatch_uid="isc_dhcp_file_saved")
def file_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(lambda: _regenerate(pk=instance.pk))


@receiver(post_save, sender=DHCPGroup, dispatch_uid="isc_dhcp_group_saved")
def group_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(lambda: _regenerate(group_id=instance.pk))


@receiver(post_save, sender=TenantGroup, dispatch_uid="isc_dhcp_tenantgroup_saved")
def tenantgroup_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(lambda: _regenerate(group__group_id=instance.pk))


@receiver(pre_save, sender=Tenant, dispatch_uid="isc_dhcp_tenant_pre")
def tenant_pre_save(sender, instance, **kwargs):
    instance._isc_old_group_id = (
        Tenant.objects.filter(pk=instance.pk).values_list("group_id", flat=True).first() if instance.pk else None
    )


@receiver(post_save, sender=Tenant, dispatch_uid="isc_dhcp_tenant_saved")
def tenant_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    ids = {i for i in (instance.group_id, getattr(instance, "_isc_old_group_id", None)) if i}
    if ids:
        transaction.on_commit(lambda: _regenerate(group__group_id__in=ids))


@receiver(post_delete, sender=Tenant, dispatch_uid="isc_dhcp_tenant_deleted")
def tenant_deleted(sender, instance, **kwargs):
    if instance.group_id:
        transaction.on_commit(lambda: _regenerate(group__group_id=instance.group_id))
