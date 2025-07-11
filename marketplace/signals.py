# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order, Review

@receiver(post_save, sender=Order)
def auto_delete_review_on_refund(sender, instance, created, **kwargs):
    """
    Deletes the associated review if an existing order's status is saved as 'Refunded'.
    """
    # We only care about updates to existing orders, not new ones.
    # And we only care if the final status is 'REFUNDED'.
    if not created and instance.status == 'REFUNDED':
        Review.objects.filter(order=instance).delete()