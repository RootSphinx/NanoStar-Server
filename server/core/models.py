# core/models.py
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models


class Device(models.Model):
    """手机设备表"""
    device_id = models.CharField(max_length=64, primary_key=True, help_text="设备唯一标识")
    fcm_token = models.CharField(max_length=255, null=True, blank=True, help_text="Firebase推送令牌")
    is_online = models.BooleanField(default=False, help_text="当前WS是否在线")
    last_seen = models.DateTimeField(auto_now=True, help_text="最后活跃时间")
    active_modules = models.JSONField(default=list, help_text="设备支持的能力清单")

    def __str__(self):
        return self.device_id

class Fingerprint(models.Model):
    """访客指纹表"""
    visitor_fingerprint = models.CharField(max_length=64, unique=True, db_index=True, help_text="FingerprintJS 访客指纹")
    first_seen = models.DateTimeField(auto_now_add=True, help_text="首次出现时间")
    last_seen = models.DateTimeField(auto_now=True, help_text="最近出现时间")

    def __str__(self):
        return self.visitor_fingerprint

class AppConfig(models.Model):
    """客户端云端配置表"""
    version_id = models.BigAutoField(primary_key=True)
    is_tracking_enabled = models.BooleanField(default=True)
    distance_threshold = models.FloatField(default=500.0, help_text="拒绝访客的距离阈值(米)")
    visit_cooldown_minutes = models.PositiveIntegerField(default=30, help_text="同一指纹访问冷却时间(分钟)")
    max_comments_per_record = models.PositiveIntegerField(default=3, help_text="同一访问记录最大评论数")
    show_past_comments = models.BooleanField(default=True, help_text="评论页是否展示历史评论列表")
    show_all_history = models.BooleanField(default=False, help_text="历史评论是否显示该指纹全部记录下的留言")
    show_total_visitors = models.BooleanField(default=False, help_text="成功页是否显示累计成功访客人数")
    show_first_comments = models.BooleanField(default=False, help_text="首次成功访问时是否展示过去的留言")
    show_distance_on_failure = models.BooleanField(default=True, help_text="匹配失败时是否向客户端显示距离信息")
    success_message = models.TextField(blank=True, default="", help_text="验证成功时在前端显示的自定义信息，支持HTML")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "应用配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"应用配置 #{self.version_id}"

    def clean(self):
        if AppConfig.objects.exclude(version_id=self.version_id).count():
            raise ValidationError("应用配置只能存在一个")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.clear()

    @property
    def updated_at_ms(self) -> int:
        """返回 updated_at 的 Unix 毫秒时间戳，用于与客户端 last_modified 比对"""
        import datetime
        epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        return int((self.updated_at - epoch).total_seconds() * 1000)

class VisitorRecordStatus(models.TextChoices):
    SUCCESS = 'success', '成功'
    DEVICE_OFFLINE = 'device_offline', '设备未上线'
    VISITOR_LOCATION_MISSING = 'visitor_location_missing', '未获取到访客位置'
    HOST_LOCATION_MISSING = 'host_location_missing', '未获取到主机位置'
    DEVICE_TOO_FAR = 'device_too_far', '设备距离过远'
    UNKNOWN_ERROR = 'unknown_error', '未知错误'


class VisitorRecord(models.Model):
    """访客验证记录表"""
    fingerprint = models.ForeignKey(Fingerprint, null=True, blank=True, on_delete=models.SET_NULL, related_name='records')
    request_id = models.CharField(max_length=64, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    distance = models.FloatField(null=True, blank=True, help_text="计算出的距离(米)")
    timestamp = models.BigIntegerField(help_text="毫秒级时间戳")
    status = models.CharField(
        max_length=32,
        choices=VisitorRecordStatus.choices,
        default=VisitorRecordStatus.UNKNOWN_ERROR,
        help_text="验证状态",
    )
    module = models.CharField(max_length=64, default="tracking", help_text="模块名称，用于历史数据筛选")

    # 双方坐标
    visitor_latitude = models.FloatField(null=True, blank=True, help_text="访客纬度")
    visitor_longitude = models.FloatField(null=True, blank=True, help_text="访客经度")
    device_latitude = models.FloatField(null=True, blank=True, help_text="设备纬度")
    device_longitude = models.FloatField(null=True, blank=True, help_text="设备经度")
    device_address = models.TextField(blank=True, default="", help_text="设备坐标逆地理编码地址")
    visitor_address = models.TextField(blank=True, default="", help_text="访客坐标逆地理编码地址")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.request_id} - {self.status}"

class Comment(models.Model):
    """访客评论表"""
    visitor_record = models.ForeignKey(VisitorRecord, on_delete=models.CASCADE, related_name='comments')
    fingerprint = models.ForeignKey(Fingerprint, null=True, blank=True, on_delete=models.SET_NULL, related_name='comments')
    content = models.TextField(help_text="评论内容")
    timestamp = models.BigIntegerField(help_text="毫秒级时间戳")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment on {self.visitor_record.request_id}"
