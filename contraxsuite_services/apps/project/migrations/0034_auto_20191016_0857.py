# Generated by Django 2.2.4 on 2019-10-16 08:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('project', '0033_auto_20190916_1356'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectclustering',
            name='reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='projectclustering',
            name='status',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
    ]
