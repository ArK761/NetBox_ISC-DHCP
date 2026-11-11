from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import SubnetOverride, ConfigVariable, PoolTemplate, SubnetConfig, BaseConfig, DHCPPath, DHCPGroup, DHCPFile, DNSServer, PluginSettings


class BaseConfigSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:baseconfig-detail")

    class Meta:
        model = BaseConfig
        fields = ('id', 'url', 'display', 'name', 'static_text', 'tags', 'custom_fields', 'created', 'last_updated')
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



class SubnetConfigSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:subnetconfig-detail")

    class Meta:
        model = SubnetConfig
        fields = ('id', 'url', 'display', 'name', 'source_model', 'conditions', 'gateway_mode', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class PoolTemplateSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:pooltemplate-detail")

    class Meta:
        model = PoolTemplate
        fields = ('id', 'url', 'display', 'name', 'enabled', 'template', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class ConfigVariableSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:configvariable-detail")

    class Meta:
        model = ConfigVariable
        fields = ('id', 'url', 'display', 'name', 'option', 'value', 'dns_servers', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')


class SubnetOverrideSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:netbox_isc_dhcp-api:subnetoverride-detail")

    class Meta:
        model = SubnetOverride
        fields = ('id', 'url', 'display', 'pool', 'prefix_id', 'prefix_text', 'code', 'tags', 'custom_fields', 'created', 'last_updated')
        brief_fields = ('id', 'url', 'display')
