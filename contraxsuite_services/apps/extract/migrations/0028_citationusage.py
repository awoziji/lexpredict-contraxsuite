# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-09-26 19:05
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('document', '0003_auto_20170818_0632'),
        ('extract', '0027_auto_20170924_0850'),
    ]

    operations = [
        migrations.CreateModel(
            name='CitationUsage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('count', models.IntegerField(default=0)),
                ('volume', models.PositiveSmallIntegerField()),
                ('reporter', models.CharField(db_index=True, max_length=20)),
                ('reporter_full_name', models.CharField(blank=True, db_index=True, max_length=200, null=True)),
                ('page', models.PositiveSmallIntegerField()),
                ('page2', models.CharField(blank=True, max_length=10, null=True)),
                ('court', models.CharField(blank=True, db_index=True, max_length=20, null=True)),
                ('year', models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ('citation_str', models.CharField(max_length=100)),
                ('text_unit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='document.TextUnit')),
            ],
            options={
                'ordering': ('text_unit', 'reporter', '-count'),
            },
        ),
    ]