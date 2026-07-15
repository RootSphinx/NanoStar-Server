from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import Device, AppConfig, VisitorRecord, Fingerprint, Comment


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'is_online', 'last_seen', 'fcm_token')
    list_filter = ('is_online',)
    search_fields = ('device_id',)


@admin.register(Fingerprint)
class FingerprintAdmin(admin.ModelAdmin):
    list_display = ('visitor_fingerprint', 'first_seen', 'last_seen')
    search_fields = ('visitor_fingerprint',)


@admin.register(AppConfig)
class AppConfigAdmin(admin.ModelAdmin):
    list_display = ('version_id', 'is_tracking_enabled', 'distance_threshold', 'visit_cooldown_minutes', 'max_comments_per_record', 'show_past_comments', 'show_all_history', 'show_total_visitors', 'show_first_comments', 'show_distance_on_failure', 'updated_at')
    fields = (
        'is_tracking_enabled',
        'distance_threshold',
        'visit_cooldown_minutes',
        'max_comments_per_record',
        'show_past_comments',
        'show_all_history',
        'show_total_visitors',
        'show_first_comments',
        'show_distance_on_failure',
        'success_message',
    )

    def has_add_permission(self, request):
        """如果已经存在配置，则禁止添加"""
        return not AppConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除配置"""
        return False

    def changelist_view(self, request, extra_context=None):
        """列表页直接跳转到编辑页面"""
        obj = AppConfig.objects.first()
        if obj:
            return HttpResponseRedirect(
                reverse('admin:core_appconfig_change', args=[obj.pk])
            )
        return HttpResponseRedirect(
            reverse('admin:core_appconfig_add')
        )

    def save_model(self, request, obj, form, change):
        """保存设置时清除缓存"""
        super().save_model(request, obj, form, change)
        self.message_user(request, '设置已保存，缓存已清除')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('visitor_record', 'fingerprint', 'content_short', 'created_at')
    search_fields = ('content', 'visitor_record__request_id', 'fingerprint__visitor_fingerprint')

    def content_short(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_short.short_description = '评论内容'


@admin.register(VisitorRecord)
class VisitorRecordAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'fingerprint', 'ip_address', 'distance', 'timestamp', 'status', 'module', 'comment_count', 'created_at')
    list_filter = ('status', 'module')
    search_fields = ('request_id', 'ip_address', 'fingerprint__visitor_fingerprint')

    def comment_count(self, obj):
        return obj.comments.count()
    comment_count.short_description = '评论数'
