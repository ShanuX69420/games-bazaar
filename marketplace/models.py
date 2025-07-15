from django.utils import timezone
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from model_utils import FieldTracker

class SiteConfiguration(models.Model):
    default_commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Default site-wide commission rate in % (e.g., 10.00).")
    def __str__(self): return "Site Configuration"

class FlatPage(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, help_text="The URL-friendly version of the title, e.g., 'support-center'")
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.title

class Game(models.Model):
    title = models.CharField(max_length=200, unique=True)
    categories = models.ManyToManyField('Category', related_name='games')
    def __str__(self): return self.title

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Custom commission rate in % (e.g., 15.00).")
    def __str__(self): return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Custom commission for this seller in % (e.g., 7.00).")
    last_seen = models.DateTimeField(null=True, blank=True)
    # Use a default image that actually exists in MEDIA_ROOT. The current
    # default.jpg lives directly under MEDIA_ROOT, so reference it here
    # without the `profile_pics/` prefix to avoid broken links when a user
    # hasn't uploaded a custom picture.
    image = models.ImageField(upload_to='profile_pics', default='default.jpg')
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_online(self):
        if self.last_seen:
            # A user is "online" if their last seen time was within the last 30 seconds.
            # This reduces the chance of showing "Online" for a user who has just disconnected.
            return timezone.now() < self.last_seen + datetime.timedelta(seconds=30)
        return False

    def __str__(self): 
        return f'{self.user.username} Profile'

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        try:
            instance.profile.save()
        except Profile.DoesNotExist:
            Profile.objects.create(user=instance)

class Product(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='listings')
    listing_title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    is_virtual = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return f'{self.game.title} - {self.listing_title}'

class Order(models.Model):
    STATUS_CHOICES = [('PENDING_PAYMENT', 'Pending Payment'), ('PROCESSING', 'Processing'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('DISPUTED', 'Disputed'), ('REFUNDED', 'Refunded'), ('CANCELLED', 'Cancelled')]
    buyer = models.ForeignKey(User, related_name='purchases', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='sales', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_PAYMENT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    commission_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tracker = FieldTracker()
    def __str__(self): return f"Order #{self.id} for {self.product.listing_title}"
    def calculate_commission(self):
        from .models import SiteConfiguration
        if self.seller.profile.commission_rate is not None: rate = self.seller.profile.commission_rate
        elif self.product.category and self.product.category.commission_rate is not None: rate = self.product.category.commission_rate
        else:
            config = SiteConfiguration.objects.first()
            rate = config.default_commission_rate if config else 10.00
        return (self.total_price * rate) / 100

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
    content = models.TextField()
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
    
    def __str__(self):
        return f"Withdrawal request for {self.user.username} of Rs{self.amount}"

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
    TRANSACTION_TYPE_CHOICES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('ORDER_PURCHASE', 'Order Purchase'),
        ('ORDER_SALE', 'Order Sale'),
        ('MISCELLANEOUS', 'Miscellaneous'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Positive for income, negative for expense.")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    # These fields will link to the original source of the transaction, if any.
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    withdrawal = models.ForeignKey(WithdrawalRequest, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.amount} for {self.user.username}"

    class Meta:
        ordering = ['-created_at']