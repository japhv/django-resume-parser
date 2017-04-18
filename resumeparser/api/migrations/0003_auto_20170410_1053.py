# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-04-10 10:53
from __future__ import unicode_literals

from django.db import migrations, models
import resumeparser.utils.validator


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_resumearchive'),
    ]

    operations = [
        migrations.AlterField(
            model_name='resumearchive',
            name='datafile',
            field=models.FileField(upload_to='resumes/%Y/%m/%d', validators=[resumeparser.utils.validator.validate_file_extension]),
        ),
    ]