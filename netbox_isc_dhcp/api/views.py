from netbox.api.viewsets import NetBoxModelViewSet

from .. import models
from . import serializers


class BaseConfigViewSet(NetBoxModelViewSet):
    queryset = models.BaseConfig.objects.all()
    serializer_class = serializers.BaseConfigSerializer


class DHCPPathViewSet(NetBoxModelViewSet):
    queryset = models.DHCPPath.objects.all()
    serializer_class = serializers.DHCPPathSerializer


class DHCPGroupViewSet(NetBoxModelViewSet):
    queryset = models.DHCPGroup.objects.all()
    serializer_class = serializers.DHCPGroupSerializer


class DHCPFileViewSet(NetBoxModelViewSet):
    queryset = models.DHCPFile.objects.all()
    serializer_class = serializers.DHCPFileSerializer


class DNSServerViewSet(NetBoxModelViewSet):
    queryset = models.DNSServer.objects.all()
    serializer_class = serializers.DNSServerSerializer


class PluginSettingsViewSet(NetBoxModelViewSet):
    queryset = models.PluginSettings.objects.order_by("pk")
    serializer_class = serializers.PluginSettingsSerializer

