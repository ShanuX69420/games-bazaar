# Generated migration to update order ID format

from django.db import migrations
import string
import random


def generate_new_order_id_migration(existing_ids):
    """Generate a unique order ID for migration with new format #AU482ZZ"""
    while True:
        # Generate 2 letters + 3 numbers + 2 letters for more letters than numbers
        letters1 = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        letters2 = ''.join(random.choices(string.ascii_uppercase, k=2))
        order_id = f"#{letters1}{numbers}{letters2}"
        
        if order_id not in existing_ids:
            existing_ids.add(order_id)
            return order_id


def update_order_id_format(apps, schema_editor):
    """Update all existing order IDs to new format"""
    Order = apps.get_model('marketplace', 'Order')
    existing_ids = set()
    
    for order in Order.objects.all():
        old_id = order.order_id
        new_id = generate_new_order_id_migration(existing_ids)
        order.order_id = new_id
        order.save()
        print(f"Updated order {order.pk}: {old_id} -> {new_id}")


def reverse_update_order_id_format(apps, schema_editor):
    """Cannot reverse this migration - would lose data"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0020_make_order_id_non_nullable'),
    ]

    operations = [
        migrations.RunPython(update_order_id_format, reverse_update_order_id_format),
    ]