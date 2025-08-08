# Generated migration to populate order IDs

from django.db import migrations
import string
import random


def generate_unique_order_id_migration(existing_ids):
    """Generate a unique order ID for migration"""
    while True:
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        order_id = f"GM-{random_part}"
        if order_id not in existing_ids:
            existing_ids.add(order_id)
            return order_id


def populate_order_ids(apps, schema_editor):
    """Populate order_id field for existing orders"""
    Order = apps.get_model('marketplace', 'Order')
    existing_ids = set()
    
    for order in Order.objects.all():
        if not order.order_id:
            order.order_id = generate_unique_order_id_migration(existing_ids)
            order.save()


def reverse_populate_order_ids(apps, schema_editor):
    """Remove order_id values"""
    Order = apps.get_model('marketplace', 'Order')
    Order.objects.update(order_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0018_add_order_id_field'),
    ]

    operations = [
        migrations.RunPython(populate_order_ids, reverse_populate_order_ids),
    ]