# marketplace/models.py

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save # Import post_save signal
from django.dispatch import receiver


class SiteConfiguration(models.Model):
    default_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        help_text="Default site-wide commission rate in % (e.g., 10.00)."
    )

    def __str__(self):
        return "Site Configuration"

# --- CATEGORY MODEL (UPDATED) ---
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # This field holds a custom commission rate for this specific category
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, 
        help_text="Custom commission rate in % (e.g., 15.00). Leave blank to use seller's or site default."
    )

    def __str__(self):
        return self.name

# --- NEW PROFILE MODEL ---
# This model extends the built-in User model to store our custom fields
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # This field holds a custom commission rate for this specific seller
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, 
        help_text="Custom commission for this seller in % (e.g., 7.00). Leave blank to use category or site default."
    )

    def __str__(self):
        return f'{self.user.username} Profile'

# --- NEW SIGNAL ---
# This signal ensures a Profile is created automatically for each new User
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


# --- All other models (Product, Order, etc.) remain the same ---
# (You can copy them from your existing file if they are not here)

class Product(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    is_virtual = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING_PAYMENT', 'Pending Payment'),
        ('PROCESSING', 'Processing'),
        ('DELIVERED', 'Delivered'),
        ('COMPLETED', 'Completed'),
        ('DISPUTED', 'Disputed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]

    buyer = models.ForeignKey(User, related_name='purchases', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sales', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYMENT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    commission_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def calculate_commission(self):
        """
        Calculates commission based on the hierarchy:
        1. Seller's custom rate
        2. Category's custom rate
        3. Site's default rate
        """
        # Import inside the method to avoid circular import
        from .models import SiteConfiguration

        # 1. Check for a seller-specific rate
        if self.seller.profile.commission_rate is not None:
            rate = self.seller.profile.commission_rate
        # 2. Check for a category-specific rate
        elif self.product.category and self.product.category.commission_rate is not None:
            rate = self.product.category.commission_rate
        # 3. Use the site-wide default
        else:
            config = SiteConfiguration.objects.first()
            rate = config.default_commission_rate if config else 10.00

        commission_amount = (self.total_price * rate) / 100
        return commission_amount

    def __str__(self):
        return f"Order #{self.id} for {self.product.title}"

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='reviews', on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review by {self.buyer.username} for Order #{self.order.id}"

class ChatMessage(models.Model):
    order = models.ForeignKey(Order, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.sender.username} on Order #{self.order.id}"