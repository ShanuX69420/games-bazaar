# games-bazaar-master/marketplace/models.py

from django.utils import timezone
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from model_utils import FieldTracker
from decimal import Decimal, ROUND_HALF_UP # Import Decimal helpers
from django.core.exceptions import ValidationError, NON_FIELD_ERRORS
from django.conf import settings
import string
import random
# Import simple Google Cloud Storage
from .simple_storage import google_cloud_chat_storage, google_cloud_profile_storage, google_cloud_product_storage

# Money helpers
MONEY_QUANTIZER = Decimal('0.01')


def quantize_money(value):
    """Round monetary values to 2 decimal places using bankers rounding."""
    if value is None:
        return Decimal('0.00')
    return Decimal(value).quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


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


def get_effective_commission_rate_for_listing(seller, category=None):
    """
    Determine the commission rate for a seller/category combination.
    Priority: seller-specific override, category override, then site default.
    """
    profile = getattr(seller, 'profile', None)
    if profile and profile.commission_rate is not None:
        return Decimal(profile.commission_rate)

    if category and category.commission_rate is not None:
        return Decimal(category.commission_rate)

    config = SiteConfiguration.objects.first()
    if config and config.default_commission_rate is not None:
        return Decimal(config.default_commission_rate)

    return Decimal('10.00')


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
    requires_special_approval = models.BooleanField(
        default=False,
        help_text="Only approved sellers can create listings when enabled."
    )
    approved_sellers = models.ManyToManyField(
        User,
        blank=True,
        related_name='approved_game_categories',
        help_text="Sellers allowed to create listings when special approval is required."
    )

    class Meta:
        unique_together = ('game', 'category')
        verbose_name_plural = "Game-Category Links"

    def __str__(self):
        return f"{self.game.title} - {self.category.name}"

    def seller_can_list(self, user):
        """
        Determine if a seller is allowed to create listings in this game/category.
        Staff bypass the restriction to simplify internal moderation tasks.
        """
        if not self.requires_special_approval:
            return True

        if not getattr(user, 'is_authenticated', False):
            return False

        if user.is_staff or user.is_superuser:
            return True

        return self.approved_sellers.filter(pk=user.pk).exists()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete(f'game_category_{self.game_id}_{self.category_id}')

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        cache.delete(f'game_category_{self.game_id}_{self.category_id}')
        super().delete(*args, **kwargs)

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    def __str__(self): return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    offline_broadcast_at = models.DateTimeField(null=True, blank=True, help_text="Last time offline status was broadcasted")
    image = models.ImageField(storage=google_cloud_profile_storage, upload_to='profile_pics', null=True, blank=True)
    show_listings_on_site = models.BooleanField(default=True, db_index=True)
    is_moderator = models.BooleanField(default=False, help_text="Can join conversations for dispute resolution")
    is_verified_seller = models.BooleanField(default=False, help_text="Verified sellers can withdraw funds immediately")
    @property
    def image_url(self):
        if self.image and hasattr(self.image, 'url'): 
            # The storage backend will handle CDN URL generation
            return self.image.url
        else: 
            return '/static/images/default.jpg'
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
        """Calculate user's current balance from completed transactions with caching"""
        from django.db.models import Sum
        from django.core.cache import cache
        
        cache_key = f'user_balance_{self.user.id}'
        cached_balance = cache.get(cache_key)
        
        if cached_balance is not None:
            return Decimal(str(cached_balance))
            
        balance_data = Transaction.objects.filter(user=self.user, status='COMPLETED').aggregate(balance=Sum('amount'))
        balance = balance_data.get('balance') or Decimal('0.00')
        
        # Cache for 5 minutes - balance changes are not ultra-frequent
        cache.set(cache_key, str(balance), 300)
        return balance

    @property
    def available_balance(self):
        """Calculate user's available balance (total balance minus held funds)"""
        # Auto-release eligible funds first
        self._auto_release_funds()
        return self.balance - self._get_held_balance()

    @property
    def held_balance(self):
        """Calculate total amount currently held for 72-hour delay"""
        return self._get_held_balance()
    
    def _get_held_balance(self):
        """Get held balance without auto-release to avoid circular calls with caching"""
        from django.db.models import Sum
        from django.core.cache import cache
        
        cache_key = f'user_held_balance_{self.user.id}'
        cached_held_balance = cache.get(cache_key)
        
        if cached_held_balance is not None:
            return Decimal(str(cached_held_balance))
            
        held_data = HeldFund.objects.filter(
            user=self.user, 
            is_released=False
        ).aggregate(total_held=Sum('amount'))
        held_balance = held_data.get('total_held') or Decimal('0.00')
        
        # Cache for 2 minutes - held funds change less frequently
        cache.set(cache_key, str(held_balance), 120)
        return held_balance
    
    def _auto_release_funds(self):
        """Automatically release funds that have passed the 72-hour period"""
        eligible_funds = HeldFund.objects.filter(
            user=self.user,
            is_released=False,
            release_at__lte=timezone.now()
        )
        
        for held_fund in eligible_funds:
            held_fund.release_fund()
    
    def get_held_funds_details(self):
        """Get detailed breakdown of held funds with individual release times"""
        return HeldFund.objects.filter(
            user=self.user,
            is_released=False
        ).select_related('order').order_by('release_at')
    
    def get_held_funds_summary(self):
        """Get summary of held funds grouped by release timeframe"""
        from django.db.models import Sum, Count
        from django.utils import timezone
        import datetime
        
        now = timezone.now()
        
        # Define time ranges
        ranges = [
            ('available_now', now - datetime.timedelta(minutes=1), now),
            ('next_24h', now, now + datetime.timedelta(hours=24)),
            ('next_48h', now + datetime.timedelta(hours=24), now + datetime.timedelta(hours=48)),
            ('later', now + datetime.timedelta(hours=48), now + datetime.timedelta(days=365))
        ]
        
        summary = []
        for label, start, end in ranges:
            if label == 'available_now':
                funds = HeldFund.objects.filter(
                    user=self.user,
                    is_released=False,
                    release_at__lte=now
                )
            else:
                funds = HeldFund.objects.filter(
                    user=self.user,
                    is_released=False,
                    release_at__gt=start,
                    release_at__lte=end
                )
            
            if funds.exists():
                stats = funds.aggregate(
                    total_amount=Sum('amount'),
                    count=Count('id')
                )
                summary.append({
                    'label': label,
                    'count': stats['count'],
                    'total_amount': stats['total_amount'] or 0,
                    'start': start,
                    'end': end
                })
        
        return summary

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
        errors = {}
        non_field_errors = []

        title = (self.listing_title or '').strip()
        if len(title) < 20:
            errors['listing_title'] = 'Title must be at least 20 characters long.'

        description = (self.description or '').strip()
        if len(description) < 20:
            errors['description'] = 'Description must be at least 20 characters long.'

        if self.price is not None and self.price < Decimal('300'):
            errors['price'] = 'Minimum listing price is 300.'

        if self.automatic_delivery:
            if self.stock is not None:
                non_field_errors.append(
                    "For automatic delivery, 'In Stock' must be empty. Use 'Products for Automatic Delivery' instead."
                )
            if not (self.stock_details or '').strip():
                non_field_errors.append(
                    "For automatic delivery, 'Products for Automatic Delivery' cannot be empty."
                )
        else:
            if (self.stock_details or '').strip():
                non_field_errors.append(
                    "For manual delivery, 'Products for Automatic Delivery' must be empty. Use 'In Stock' instead."
                )
            # For manual delivery, stock is optional. If provided, it cannot be negative.
            if self.stock is not None and self.stock < 0:
                non_field_errors.append(
                    "'In Stock' must not be a negative number."
                )

        if non_field_errors:
            errors[NON_FIELD_ERRORS] = non_field_errors

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Clear stock_count cache when saving
        self._stock_count = None
        super().save(*args, **kwargs)

    def __str__(self): return f'{self.game.title} - {self.listing_title}'

    def get_commission_rate(self):
        return get_effective_commission_rate_for_listing(self.seller, self.category)

    def get_net_total(self, quantity=1):
        return quantize_money(Decimal(self.price or 0) * Decimal(quantity))

    def get_buyer_total(self, quantity=1):
        net_total = self.get_net_total(quantity)
        rate = self.get_commission_rate()
        multiplier = Decimal('1.00') + (Decimal(rate) / Decimal('100'))
        return quantize_money(net_total * multiplier)

    def get_buyer_price(self):
        return self.get_buyer_total(quantity=1)

    def get_commission_amount(self, quantity=1):
        return self.get_buyer_total(quantity) - self.get_net_total(quantity)

    @property
    def buyer_price(self):
        return self.get_buyer_price()

    @property
    def commission_amount(self):
        return self.get_commission_amount()

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(storage=google_cloud_product_storage, upload_to='product_images/')

    @property
    def image_url(self):
        """Return CDN URL with fallback for missing images"""
        if self.image and hasattr(self.image, 'url'): 
            try:
                return self.image.url
            except Exception as e:
                print(f"Error generating URL for image {self.image.name}: {e}")
                return '/static/images/default.jpg'
        else: 
            return '/static/images/default.jpg'

    def __str__(self):
        return f"Image for {self.product.listing_title}"

def generate_unique_order_id():
    """Generate a unique order ID using UUID for enhanced security against enumeration attacks"""
    import uuid
    while True:
        # Generate a UUID and use first 12 characters (much more secure than sequential/predictable IDs)
        unique_part = str(uuid.uuid4()).replace('-', '').upper()[:12]
        order_id = f"#{unique_part[:4]}-{unique_part[4:8]}-{unique_part[8:12]}"
        
        # Check if this ID already exists (extremely unlikely with UUID)
        if not Order.objects.filter(order_id=order_id).exists():
            return order_id

class Order(models.Model):
    STATUS_CHOICES = [('PENDING_PAYMENT', 'Pending Payment'), ('PROCESSING', 'Processing'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('DISPUTED', 'Disputed'), ('REFUNDED', 'Refunded'), ('CANCELLED', 'Cancelled')]
    order_id = models.CharField(max_length=30, unique=True, db_index=True, help_text="Unique order identifier")
    buyer = models.ForeignKey(User, related_name='purchases', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sales', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    seller_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROCESSING', db_index=True)
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
    
    @property
    def clean_order_id(self):
        """Return order_id without the # symbol for use in URLs"""
        return self.order_id.lstrip('#') if self.order_id else ''

    def calculate_commission(self):
        seller_amount = getattr(self, 'seller_amount', None)
        if seller_amount and Decimal(seller_amount) > Decimal('0.00'):
            return quantize_money(Decimal(self.total_price) - Decimal(seller_amount))

        rate = get_effective_commission_rate_for_listing(
            self.seller,
            self.category_snapshot or (self.product.category if self.product else None)
        )
        return quantize_money((Decimal(self.total_price) * Decimal(rate)) / Decimal('100'))

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='reviews', on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(db_index=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Custom manager
    objects = ReviewManager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate review stats cache when new review is created/updated
        from django.core.cache import cache
        cache.delete(f'review_stats_{self.seller.id}')

    def delete(self, *args, **kwargs):
        seller_id = self.seller.id
        super().delete(*args, **kwargs)
        # Invalidate review stats cache when review is deleted
        from django.core.cache import cache
        cache.delete(f'review_stats_{seller_id}')

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
    image = models.ImageField(storage=google_cloud_chat_storage, upload_to='chat_images/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True)
    is_system_message = models.BooleanField(default=False)
    is_auto_reply = models.BooleanField(default=False)

    # Custom manager
    objects = MessageManager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate message count cache when new message is created
        from django.core.cache import cache
        cache.delete(f'conversation_message_count_{self.conversation.id}')

    def __str__(self): return f"Message from {self.sender.username} at {self.timestamp}"

class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('easypaisa', 'Easypaisa'),
        ('jazzcash', 'JazzCash'),
        ('sadapay', 'SadaPay'),
        ('nayapay', 'NayaPay'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer')
    account_title = models.CharField(max_length=100, default='Not specified')
    account_number = models.CharField(max_length=50, blank=True, null=True)
    iban = models.CharField(max_length=24, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True, null=True)
    def __str__(self): return f"Withdrawal request for {self.user.username} of Rs{self.amount} via {self.get_payment_method_display()}"

class DepositRequest(models.Model):
    """Manual deposit request submitted by users after sending payment off-platform."""
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    receipt = models.FileField(upload_to='deposit_receipts/')
    payment_reference = models.CharField(max_length=100, blank=True, help_text="Optional reference or transaction ID from your bank transfer.")
    notes = models.TextField(blank=True, help_text="Any additional details you want the finance team to see.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-requested_at']
    
    def __str__(self):
        return f"Deposit request #{self.id} for {self.user.username} (Rs{self.amount})"
    
    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING
    
    def save(self, *args, **kwargs):
        previous_status = None
        if self.pk:
            previous_status = DepositRequest.objects.filter(pk=self.pk).values_list('status', flat=True).first()
        
        if previous_status != self.status:
            if self.status in (self.STATUS_APPROVED, self.STATUS_REJECTED):
                if not self.processed_at:
                    self.processed_at = timezone.now()
            elif self.status == self.STATUS_PENDING:
                self.processed_at = None
        
        super().save(*args, **kwargs)
        self._sync_transaction(previous_status)
    
    def _sync_transaction(self, previous_status):
        transaction = getattr(self, 'transaction', None)
        if not transaction:
            return
        
        if self.status == self.STATUS_APPROVED:
            if transaction.status != 'COMPLETED' or previous_status != self.STATUS_APPROVED:
                transaction.status = 'COMPLETED'
                transaction.description = f"Manual deposit #{self.id} approved"
                transaction.save(update_fields=['status', 'description'])
        elif self.status == self.STATUS_REJECTED:
            if transaction.status != 'CANCELLED' or previous_status != self.STATUS_REJECTED:
                transaction.status = 'CANCELLED'
                transaction.description = f"Manual deposit #{self.id} rejected"
                transaction.save(update_fields=['status', 'description'])
        else:
            if transaction.status != 'PENDING' or previous_status != self.STATUS_PENDING:
                transaction.status = 'PENDING'
                transaction.description = f"Manual deposit #{self.id} awaiting review"
                transaction.save(update_fields=['status', 'description'])
    
    def mark_approved(self, admin_notes=None):
        if self.status == self.STATUS_APPROVED:
            if admin_notes and admin_notes != (self.admin_notes or ''):
                self.admin_notes = admin_notes
                super().save(update_fields=['admin_notes'])
            return
        self.status = self.STATUS_APPROVED
        self.processed_at = timezone.now()
        if admin_notes:
            self.admin_notes = admin_notes
        self.save(update_fields=['status', 'processed_at', 'admin_notes'])
    
    def mark_rejected(self, admin_notes=None):
        if self.status == self.STATUS_REJECTED:
            if admin_notes is not None and admin_notes != (self.admin_notes or ''):
                self.admin_notes = admin_notes
                super().save(update_fields=['admin_notes'])
            return
        self.status = self.STATUS_REJECTED
        self.processed_at = timezone.now()
        if admin_notes is not None:
            self.admin_notes = admin_notes
        self.save(update_fields=['status', 'processed_at', 'admin_notes'])

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
    deposit = models.OneToOneField('DepositRequest', on_delete=models.SET_NULL, null=True, blank=True, related_name='transaction')
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate balance cache when transaction changes
        from django.core.cache import cache
        cache.delete(f'user_balance_{self.user.id}')
    
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

class BlockedUser(models.Model):
    """Model to track blocked users - prevents chat and purchases between blocked users"""
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by_users')
    blocked_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('blocker', 'blocked')
        ordering = ['-blocked_at']
    
    def __str__(self):
        return f'{self.blocker.username} blocked {self.blocked.username}'

class HeldFund(models.Model):
    """Model to track funds held for 72-hour delay before withdrawal/spending"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='held_funds')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='held_funds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    held_at = models.DateTimeField(auto_now_add=True)
    release_at = models.DateTimeField()
    is_released = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-held_at']
    
    def save(self, *args, **kwargs):
        if not self.release_at:
            # Set release time to 72 hours from now
            self.release_at = timezone.now() + datetime.timedelta(hours=72)
        super().save(*args, **kwargs)
        # Invalidate held balance cache when new held fund is created or updated
        from django.core.cache import cache
        cache.delete(f'user_held_balance_{self.user.id}')
    
    def can_be_released(self):
        """Check if the 72-hour hold period has passed"""
        return timezone.now() >= self.release_at
    
    def release_fund(self):
        """Release the held fund"""
        if self.can_be_released() and not self.is_released:
            self.is_released = True
            self.released_at = timezone.now()
            self.save()
            # Invalidate held balance cache when fund is released
            from django.core.cache import cache
            cache.delete(f'user_held_balance_{self.user.id}')
            return True
        return False
    
    def __str__(self):
        status = "Released" if self.is_released else f"Held until {self.release_at}"
        return f"HeldFund: {self.user.username} - Rs{self.amount} ({status})"

class ProcessedPaymentCallback(models.Model):
    """Model to track processed payment callbacks to prevent replay attacks"""
    transaction_ref = models.CharField(max_length=255, unique=True, db_index=True)
    response_code = models.CharField(max_length=10)
    processed_at = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-processed_at']
        indexes = [
            models.Index(fields=['transaction_ref', 'processed_at']),
        ]
    
    def __str__(self):
        return f"Callback: {self.transaction_ref} - {self.response_code}"
