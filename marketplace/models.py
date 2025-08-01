# games-bazaar-master/marketplace/models.py

from django.utils import timezone
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from model_utils import FieldTracker
from decimal import Decimal # Import Decimal
from django.core.exceptions import ValidationError
import string
import random

# Custom QuerySet classes for optimized queries
class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_full_details(self):
        return self.select_related(
            'seller__profile', 'game', 'category'
        ).prefetch_related('filter_options__filter', 'images')

    def by_game_category(self, game, category):
        return self.filter(game=game, category=category, is_active=True)

    def recent_first(self):
        return self.order_by('-created_at')

class OrderQuerySet(models.QuerySet):
    def with_full_details(self):
        return self.select_related(
            'buyer__profile', 'seller__profile', 'product__game',
            'product__category', 'game_snapshot', 'category_snapshot'
        ).prefetch_related('filter_options_snapshot__filter')

    def by_status(self, status):
        return self.filter(status=status)

    def recent_first(self):
        return self.order_by('-created_at')

class ReviewQuerySet(models.QuerySet):
    def with_full_details(self):
        return self.select_related(
            'buyer__profile', 'order__product__game', 'order__product__category'
        ).prefetch_related('reply')

    def by_seller(self, seller):
        return self.filter(seller=seller)

    def by_rating(self, rating):
        return self.filter(rating=rating)

    def recent_first(self):
        return self.order_by('-created_at')

class MessageQuerySet(models.QuerySet):
    def with_sender_info(self):
        return self.select_related('sender__profile', 'conversation')

    def unread(self):
        return self.filter(is_read=False)

    def by_timestamp(self):
        return self.order_by('timestamp')

# Custom Managers
class ProductManager(models.Manager):
    def get_queryset(self):
        return ProductQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def with_full_details(self):
        return self.get_queryset().with_full_details()

class OrderManager(models.Manager):
    def get_queryset(self):
        return OrderQuerySet(self.model, using=self._db)

    def with_full_details(self):
        return self.get_queryset().with_full_details()

class ReviewManager(models.Manager):
    def get_queryset(self):
        return ReviewQuerySet(self.model, using=self._db)

    def with_full_details(self):
        return self.get_queryset().with_full_details()

class MessageManager(models.Manager):
    def get_queryset(self):
        return MessageQuerySet(self.model, using=self._db)

    def with_sender_info(self):
        return self.get_queryset().with_sender_info()

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
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    offline_broadcast_at = models.DateTimeField(null=True, blank=True, help_text="Last time offline status was broadcasted")
    image = models.ImageField(upload_to='profile_pics', null=True, blank=True)
    show_listings_on_site = models.BooleanField(default=True, db_index=True)
    is_moderator = models.BooleanField(default=False, help_text="Can join conversations for dispute resolution")
    @property
    def image_url(self):
        if self.image and hasattr(self.image, 'url'): return self.image.url
        else: return '/static/images/default.jpg'
    @property
    def is_online(self):
        if self.last_seen:
            # 5-minute grace period for better user experience
            return timezone.now() < self.last_seen + datetime.timedelta(minutes=5)
        return False

    @property
    def can_moderate(self):
        """Check if user can moderate conversations (admin or moderator)"""
        return self.user.is_staff or self.user.is_superuser or self.is_moderator

    @property
    def balance(self):
        """Calculate user's current balance from completed transactions"""
        from django.db.models import Sum
        balance_data = Transaction.objects.filter(user=self.user, status='COMPLETED').aggregate(balance=Sum('amount'))
        return balance_data.get('balance') or Decimal('0.00')

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
    price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    automatic_delivery = models.BooleanField(default=False, verbose_name="Automatic delivery", db_index=True)
    stock = models.PositiveIntegerField(null=True, blank=True, verbose_name="In Stock")
    stock_details = models.TextField(blank=True)
    post_purchase_message = models.TextField(blank=True, verbose_name="Message to the buyer after payment")
    is_virtual = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    filter_options = models.ManyToManyField('FilterOption', blank=True)

    # Custom manager
    objects = ProductManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stock_count = None

    @property
    def stock_count(self):
        if self._stock_count is None:
            if self.automatic_delivery:
                self._stock_count = len([line for line in self.stock_details.splitlines() if line.strip()])
            else:
                self._stock_count = self.stock
        return self._stock_count

    def clean(self):
        """
        Ensures that stock and stock_details are not populated simultaneously and
        are correctly set based on the automatic_delivery flag.
        """
        super().clean()
        if self.automatic_delivery:
            if self.stock is not None:
                raise ValidationError(
                    "For automatic delivery, 'In Stock' must be empty. Use 'Products for Automatic Delivery' instead."
                )
            if not self.stock_details.strip():
                raise ValidationError(
                    "For automatic delivery, 'Products for Automatic Delivery' cannot be empty."
                )
        else:
            if self.stock_details.strip():
                raise ValidationError(
                    "For manual delivery, 'Products for Automatic Delivery' must be empty. Use 'In Stock' instead."
                )
            # For manual delivery, stock is optional. If provided, it cannot be negative.
            if self.stock is not None and self.stock < 0:
                raise ValidationError(
                    "'In Stock' must not be a negative number."
                )

    def save(self, *args, **kwargs):
        # Clear stock_count cache when saving
        self._stock_count = None
        super().save(*args, **kwargs)

    def __str__(self): return f'{self.game.title} - {self.listing_title}'

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='product_images/')

    def __str__(self):
        return f"Image for {self.product.listing_title}"

def generate_unique_order_id():
    """Generate a unique order ID with format: #AU482ZZ (7 characters: 2 letters + 3 numbers + 2 letters)"""
    while True:
        # Generate 2 letters + 3 numbers + 2 letters for more letters than numbers
        letters1 = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        letters2 = ''.join(random.choices(string.ascii_uppercase, k=2))
        order_id = f"#{letters1}{numbers}{letters2}"
        
        # Check if this ID already exists
        if not Order.objects.filter(order_id=order_id).exists():
            return order_id

class Order(models.Model):
    STATUS_CHOICES = [('PENDING_PAYMENT', 'Pending Payment'), ('PROCESSING', 'Processing'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('DISPUTED', 'Disputed'), ('REFUNDED', 'Refunded'), ('CANCELLED', 'Cancelled')]
    order_id = models.CharField(max_length=20, unique=True, db_index=True, help_text="Unique order identifier")
    buyer = models.ForeignKey(User, related_name='purchases', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sales', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYMENT', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    commission_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Payment split tracking
    amount_paid_from_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Amount paid from user balance")
    amount_paid_via_payment_method = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Amount paid via external payment method")

    # Snapshot fields to preserve data after product deletion
    listing_title_snapshot = models.CharField(max_length=255, null=True, blank=True)
    description_snapshot = models.TextField(null=True, blank=True)
    game_snapshot = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_game_snapshots')
    category_snapshot = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_category_snapshots')
    filter_options_snapshot = models.ManyToManyField('FilterOption', blank=True, related_name='order_filter_options_snapshots')

    tracker = FieldTracker()

    # Custom manager
    objects = OrderManager()

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = generate_unique_order_id()
        super().save(*args, **kwargs)

    def __str__(self):
        title = self.listing_title_snapshot or (self.product.listing_title if self.product else 'a deleted product')
        return f"Order {self.order_id} for {title}"

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
    rating = models.PositiveSmallIntegerField(db_index=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Custom manager
    objects = ReviewManager()

    def __str__(self): return f"Review by {self.buyer.username} for Order {self.order.order_id}"

class ReviewReply(models.Model):
    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name='reply')
    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    reply_text = models.TextField(max_length=1000, help_text="Seller's response to the review")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Review Reply"
        verbose_name_plural = "Review Replies"

    def __str__(self):
        return f"Reply by {self.seller.username} to review #{self.review.id}"

class Conversation(models.Model):
    participant1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations1')
    participant2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations2')
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_conversations', help_text="Admin/moderator who joined for dispute resolution")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_disputed = models.BooleanField(default=False, help_text="Whether this conversation has dispute resolution active")

    class Meta: unique_together = ('participant1', 'participant2')

    def __str__(self):
        if self.moderator:
            return f"Conversation between {self.participant1.username} and {self.participant2.username} (Moderator: {self.moderator.username})"
        return f"Conversation between {self.participant1.username} and {self.participant2.username}"

    def get_participants(self):
        """Returns all participants including moderator"""
        participants = [self.participant1, self.participant2]
        if self.moderator:
            participants.append(self.moderator)
        return participants

    def is_participant(self, user):
        """Check if user is a participant (including moderator)"""
        return user in [self.participant1, self.participant2, self.moderator]

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)
    is_system_message = models.BooleanField(default=False)

    # Custom manager
    objects = MessageManager()

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
    
    USER_TYPE_CHOICES = [
        ('BUYER', 'Buyer'),
        ('SELLER', 'Seller')
    ]
    
    ISSUE_CATEGORY_CHOICES = [
        ('ORDER', 'Issue with an Order'),
        ('ACCOUNT', 'Account Related Issue'),
        ('PAYMENT', 'Payment & Billing'),
        ('TECHNICAL', 'Technical Support'),
        ('GENERAL', 'General Inquiry'),
        ('BUG_REPORT', 'Bug Report'),
        ('FEATURE_REQUEST', 'Feature Request')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='BUYER', help_text="Are you contacting us as a buyer or seller?")
    issue_category = models.CharField(max_length=20, choices=ISSUE_CATEGORY_CHOICES, default='GENERAL', help_text="What type of issue are you experiencing?")
    order_number = models.CharField(max_length=50, blank=True, null=True, help_text="If this is about a specific order, please provide the order number")
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admin_response = models.TextField(blank=True, null=True)
    
    def __str__(self): 
        return f"Ticket #{self.id} by {self.user.username} ({self.get_user_type_display()}) - {self.subject}"
    
    class Meta:
        ordering = ['-created_at']

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