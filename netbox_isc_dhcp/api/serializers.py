from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import BaseConfig, DHCPPath, DHCPGroup, DHCPFile, DNSServer, PluginSettings


class BaseConfigSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:baseconfig-detail")

    class Meta:
        model = BaseConfig
        fields = ('id', 'url', 'display', 'name', 'source_model', 'conditions', 'static_text', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class DHCPPathSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:dhcppath-detail")

    class Meta:
        model = DHCPPath
        fields = ('id', 'url', 'display', 'name', 'order', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class DHCPGroupSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:dhcpgroup-detail")

    class Meta:
        model = DHCPGroup
        fields = ('id', 'url', 'display', 'group', 'enabled', 'order', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class DHCPFileSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:dhcpfile-detail")

    class Meta:
        model = DHCPFile
        fields = ('id', 'url', 'display', 'group', 'name', 'directory', 'enabled', 'order', 'mac_fields', 'ip_field', 'template', 'sha256', 'generated', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class DNSServerSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:dnsserver-detail")

    class Meta:
        model = DNSServer
        fields = ('id', 'url', 'display', 'name', 'ip', 'active', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class PluginSettingsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:pluginsettings-detail")

    class Meta:
        model = PluginSettings
        fields = ('id', 'url', 'display', 'language', 'config_path', 'base_path', 'table_dir', 'subnet_dir', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')

