# Generated migration to make order_id non-nullable

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0019_populate_order_ids'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='order_id',
            field=models.CharField(db_index=True, help_text='Unique order identifier', max_length=20, unique=True),
        ),
    ]