# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2016-10-12 11:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('isubscribe', '0004_auto_20161012_1058'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='email',
            field=models.EmailField(blank=True, max_length=70, null=True, unique=True),
        ),
    ]
