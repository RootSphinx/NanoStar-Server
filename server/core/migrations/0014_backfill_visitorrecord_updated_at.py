# 0014: Backfill updated_at = timestamp for existing VisitorRecords

from django.db import migrations, models


def backfill_updated_at(apps, schema_editor):
    VisitorRecord = apps.get_model('core', 'VisitorRecord')
    VisitorRecord.objects.filter(updated_at__isnull=True).update(updated_at=models.F('timestamp'))


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0013_visitorrecord_updated_at'),
    ]

    operations = [
        migrations.RunPython(backfill_updated_at, migrations.RunPython.noop),
    ]