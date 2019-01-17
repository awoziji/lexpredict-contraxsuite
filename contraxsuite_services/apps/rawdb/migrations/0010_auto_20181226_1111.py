# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-12-26 11:11
from __future__ import unicode_literals

from django.db import migrations


def do_migrate(apps, schema_editor):
    AppVar = apps.get_model('common', 'AppVar')
    from apps.rawdb.constants import APP_VAR_DISABLE_RAW_DB_CACHING_NAME
    AppVar.objects.get_or_create(name=APP_VAR_DISABLE_RAW_DB_CACHING_NAME, defaults={
        'name': APP_VAR_DISABLE_RAW_DB_CACHING_NAME,
        'value': False
    })


class Migration(migrations.Migration):
    dependencies = [
        ('rawdb', '0009_auto_20181219_2124'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='documenttypecachingconfig',
            name='document_type',
        ),
        migrations.DeleteModel(
            name='DocumentTypeCachingConfig',
        ),
        migrations.RunPython(do_migrate, reverse_code=migrations.RunPython.noop),
    ]