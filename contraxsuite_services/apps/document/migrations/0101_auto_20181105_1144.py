# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-11-05 11:44
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document', '0100_fix_date_field_serialization'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentfield',
            name='value_detection_strategy',
            field=models.CharField(choices=[('disabled', 'Field detection disabled'), ('use_regexps_only', 'No ML. Use regexp field detectors.'), ('use_formula_only', 'No ML. Use formula only.'), ('regexps_and_text_based_ml', 'Start with regexps, switch to text-based ML when possible.'), ('text_based_ml_only', 'Use pre-trained text-based ML only.'), ('formula_and_fields_based_ml', 'Start with formula, switch to fields-based ML when possible.'), ('fields_based_ml_only', 'Use pre-trained field-based ML only.'), ('python_coded_field', 'Use python class for value detection.')], default='use_regexps_only', max_length=50),
        ),
    ]