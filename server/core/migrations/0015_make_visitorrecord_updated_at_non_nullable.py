# 0015: Make updated_at non-nullable

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0014_backfill_visitorrecord_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='visitorrecord',
            name='updated_at',
            field=models.BigIntegerField(
                db_index=True,
                help_text='毫秒级时间戳，记录创建时=timestamp，后续更新时刷新',
            ),
        ),
    ]