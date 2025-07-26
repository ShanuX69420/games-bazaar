# games-bazaar-master/marketplace/models.py

from django.utils import timezone
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from model_utils import FieldTracker
from decimal import Decimal # Import Decimal

class SiteConfiguration(models.Model):
    default_commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    def __str__(self): return "Site Configuration"

class FlatPage(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.title

class Game(models.Model):
    title = models.CharField(max_length=200, unique=True)
    categories = models.ManyToManyField(
        'Category',
        through='GameCategory',
        related_name='games'
    )
    def __str__(self): return self.title

class GameCategory(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    category = models.ForeignKey('Category', on_delete=models.CASCADE)
    filters = models.ManyToManyField('Filter', blank=True, help_text="Filters specific to this game's category.")

    primary_filter = models.ForeignKey(
        'Filter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='primary_for_game_categories',
        help_text="The main filter to display prominently on the listing page."
    )

    allows_automated_delivery = models.BooleanField(default=False, help_text="Check if listings in this category can be for automated delivery.")

    class Meta:
        unique_together = ('game', 'category')
        verbose_name_plural = "Game-Category Links"

    def __str__(self):
        return f"{self.game.title} - {self.category.name}"

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    def __str__(self): return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    image = models.ImageField(upload_to='profile_pics', null=True, blank=True)
    show_listings_on_site = models.BooleanField(default=True)
    @property
    def image_url(self):
        if self.image and hasattr(self.image, 'url'): return self.image.url
        else: return '/static/images/default.jpg'
    @property
    def is_online(self):
        if self.last_seen: return timezone.now() < self.last_seen + datetime.timedelta(seconds=30)
        return False
    def __str__(self): return f'{self.user.username} Profile'

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created: Profile.objects.create(user=instance)
    else: Profile.objects.get_or_create(user=instance)

class Product(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='listings')
    listing_title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    automatic_delivery = models.BooleanField(default=False, verbose_name="Automatic delivery")
    stock = models.PositiveIntegerField(null=True, blank=True, verbose_name="In Stock")
    stock_details = models.TextField(blank=True)
    post_purchase_message = models.TextField(blank=True, verbose_name="Message to the buyer after payment")
    is_virtual = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    filter_options = models.ManyToManyField('FilterOption', blank=True)

    @property
    def stock_count(self):
        if self.automatic_delivery:
            return len([line for line in self.stock_details.splitlines() if line.strip()])
        return self.stock

    def __str__(self): return f'{self.game.title} - {self.listing_title}'

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='product_images/')

    def __str__(self):
        return f"Image for {self.product.listing_title}"

class Order(models.Model):
    STATUS_CHOICES = [('PENDING_PAYMENT', 'Pending Payment'), ('PROCESSING', 'Processing'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('DISPUTED', 'Disputed'), ('REFUNDED', 'Refunded'), ('CANCELLED', 'Cancelled')]
    buyer = models.ForeignKey(User, related_name='purchases', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sales', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYMENT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    commission_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Snapshot fields to preserve data after product deletion
    listing_title_snapshot = models.CharField(max_length=255, null=True, blank=True)
    description_snapshot = models.TextField(null=True, blank=True)
    game_snapshot = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_game_snapshots')
    category_snapshot = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_category_snapshots')
    filter_options_snapshot = models.ManyToManyField('FilterOption', blank=True, related_name='order_filter_options_snapshots')

    tracker = FieldTracker()
    
    def __str__(self): 
        title = self.listing_title_snapshot or (self.product.listing_title if self.product else 'a deleted product')
        return f"Order #{self.id} for {title}"

    def calculate_commission(self):
        rate = None
        # Priority 1: Seller's custom commission rate
        if self.seller.profile.commission_rate is not None:
            rate = self.seller.profile.commission_rate
        # Priority 2: Category-specific commission rate (use snapshot if product is deleted)
        elif self.category_snapshot and self.category_snapshot.commission_rate is not None:
            rate = self.category_snapshot.commission_rate
        # Fallback to product's category if snapshot isn't populated for some reason (older orders)
        elif self.product and self.product.category and self.product.category.commission_rate is not None:
            rate = self.product.category.commission_rate
        # Priority 3: Site-wide default commission rate
        else:
            config = SiteConfiguration.objects.first()
            rate = config.default_commission_rate if config else Decimal('10.00')

        # Ensure rate is a Decimal before calculation
        return (self.total_price * Decimal(rate)) / 100

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='reviews', on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Review by {self.buyer.username} for Order #{self.order.id}"

class Conversation(models.Model):
    participant1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations1')
    participant2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations2')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: unique_together = ('participant1', 'participant2')
    def __str__(self): return f"Conversation between {self.participant1.username} and {self.participant2.username}"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_system_message = models.BooleanField(default=False)
    def __str__(self): return f"Message from {self.sender.username} at {self.timestamp}"

class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True, null=True)
    def __str__(self): return f"Withdrawal request for {self.user.username} of Rs{self.amount}"

class SupportTicket(models.Model):
    STATUS_CHOICES = [('OPEN', 'Open'), ('IN_PROGRESS', 'In Progress'), ('CLOSED', 'Closed')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admin_response = models.TextField(blank=True, null=True)
    def __str__(self): return f"Ticket #{self.id} by {self.user.username} - {self.subject}"

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [('DEPOSIT', 'Deposit'), ('WITHDRAWAL', 'Withdrawal'), ('ORDER_PURCHASE', 'Order Purchase'), ('ORDER_SALE', 'Order Sale'), ('MISCELLANEOUS', 'Miscellaneous')]
    STATUS_CHOICES = [('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled'), ('REFUNDED', 'Refunded')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    withdrawal = models.ForeignKey(WithdrawalRequest, on_delete=models.SET_NULL, null=True, blank=True)
    def __str__(self): return f"{self.get_transaction_type_display()} of {self.amount} for {self.user.username}"
    class Meta: ordering = ['-created_at']

class Filter(models.Model):
    FILTER_TYPE_CHOICES = [
        ('dropdown', 'Dropdown'),
        ('buttons', 'Buttons')
    ]
    # THIS IS THE CORRECTED PART:
    internal_name = models.CharField(max_length=100, unique=True, null=True, help_text="e.g., Account Filters, Item Properties. Can be blank for existing filters.")
    name = models.CharField(max_length=100, blank=True, help_text="e.g., Platform, Rank, Region")
    filter_type = models.CharField(max_length=50, choices=FILTER_TYPE_CHOICES, default='dropdown')
    order = models.PositiveIntegerField(default=0, help_text="A number to determine the display order. Lower numbers show first.")
    append_to_title = models.BooleanField(default=False, help_text="If checked, this filter's value will be appended to the listing title.")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.internal_name or self.name or f"Filter ID {self.id}"


class FilterOption(models.Model):
    filter = models.ForeignKey(Filter, on_delete=models.CASCADE, related_name='options')
    value = models.CharField(max_length=100)
    class Meta: unique_together = ('filter', 'value')
    def __str__(self): return f"{self.filter.name}: {self.value}"

class UserGameBoost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='boosts')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='boosts')
    boosted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'game')
        ordering = ['-boosted_at']

    def __str__(self):
        return f'{self.user.username} boosted {self.game.title} at {self.boosted_at}'