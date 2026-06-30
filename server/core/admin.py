from django.contrib import admin
from .models import Device, AppConfig, VisitorRecord


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'is_online', 'last_seen', 'fcm_token')
    list_filter = ('is_online',)
    search_fields = ('device_id',)


@admin.register(AppConfig)
class AppConfigAdmin(admin.ModelAdmin):
    list_display = ('version_id', 'is_tracking_enabled', 'distance_threshold', 'updated_at')


@admin.register(VisitorRecord)
class VisitorRecordAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'ip_address', 'distance', 'timestamp', 'is_success', 'module', 'created_at')
    list_filter = ('is_success', 'module')
    search_fields = ('request_id', 'ip_address')
