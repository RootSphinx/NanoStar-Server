from django.contrib import admin
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
    list_display = ('version_id', 'is_tracking_enabled', 'distance_threshold', 'visit_cooldown_minutes', 'max_comments_per_record', 'show_past_comments', 'show_all_history', 'updated_at')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('visitor_record', 'fingerprint', 'content_short', 'created_at')
    search_fields = ('content', 'visitor_record__request_id', 'fingerprint__visitor_fingerprint')

    def content_short(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_short.short_description = '评论内容'


@admin.register(VisitorRecord)
class VisitorRecordAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'fingerprint', 'ip_address', 'distance', 'timestamp', 'is_success', 'module', 'comment_count', 'created_at')
    list_filter = ('is_success', 'module')
    search_fields = ('request_id', 'ip_address', 'fingerprint__visitor_fingerprint')

    def comment_count(self, obj):
        return obj.comments.count()
    comment_count.short_description = '评论数'
