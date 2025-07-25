# Generated by Django 5.2.4 on 2025-07-19 23:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0005_filter_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamecategory',
            name='primary_filter',
            field=models.ForeignKey(blank=True, help_text='The main filter to display prominently on the listing page.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='primary_for_game_categories', to='marketplace.filter'),
        ),
    ]
