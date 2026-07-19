# 0013: Add updated_at (nullable) to VisitorRecord

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0012_remove_visitorrecord_is_success_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitorrecord',
            name='updated_at',
            field=models.BigIntegerField(
                db_index=True,
                help_text='毫秒级时间戳，记录创建时=timestamp，后续更新时刷新',
                null=True,
            ),
        ),
    ]