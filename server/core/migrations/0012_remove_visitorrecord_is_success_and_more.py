# Generated manually for replacing is_success with status enum

from django.db import migrations, models


def migrate_is_success_to_status(apps, schema_editor):
    VisitorRecord = apps.get_model('core', 'VisitorRecord')
    VisitorRecord.objects.filter(is_success=True).update(status='success')
    VisitorRecord.objects.filter(is_success=False).update(status='unknown_error')


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_appconfig_success_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitorrecord',
            name='status',
            field=models.CharField(
                choices=[
                    ('success', '成功'),
                    ('device_offline', '设备未上线'),
                    ('visitor_location_missing', '未获取到访客位置'),
                    ('host_location_missing', '未获取到主机位置'),
                    ('device_too_far', '设备距离过远'),
                    ('unknown_error', '未知错误'),
                ],
                default='unknown_error',
                help_text='验证状态',
                max_length=32,
            ),
        ),
        migrations.RunPython(migrate_is_success_to_status, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='visitorrecord',
            name='is_success',
        ),
    ]
