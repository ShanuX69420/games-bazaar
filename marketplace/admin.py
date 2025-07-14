# marketplace/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Q

# Add SupportTicket to this import list
from .models import (
    SiteConfiguration, FlatPage, Game, Profile, Category, 
    Product, Order, Review, Conversation, Message, WithdrawalRequest, SupportTicket, Transaction
)

# --- Site Wide Settings ---
admin.site.register(SiteConfiguration)
admin.site.register(FlatPage)

# --- Model Admins ---
@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)
    filter_horizontal = ('categories',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('listing_title', 'game', 'seller', 'price', 'is_active')
    list_filter = ('game', 'category', 'is_active')
    search_fields = ('listing_title', 'game__title', 'seller__username')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'buyer', 'seller', 'status', 'total_price', 'commission_paid', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'product__listing_title', 'buyer__username', 'seller__username')

    # We will display the chat history as a read-only field
    readonly_fields = ('id', 'product', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at', 'chat_history')

    # We define the layout of the edit page here
    fields = ('id', 'product', 'status', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at', 'chat_history')

    def chat_history(self, obj):
        # Find the conversation related to this order's buyer and seller
        conversation = Conversation.objects.filter(
            (Q(participant1=obj.buyer) & Q(participant2=obj.seller)) |
            (Q(participant1=obj.seller) & Q(participant2=obj.buyer))
        ).first()

        if not conversation:
            return "No conversation found."

        messages = conversation.messages.all().order_by('timestamp')

        # Format the messages as an HTML string
        history = ""
        for message in messages:
            sender = "System" if message.is_system_message else message.sender.username
            history += f"<p><strong>{sender}</strong> ({message.timestamp.strftime('%b. %d, %Y, %I:%M %p')}):<br>{message.content}</p><hr>"

        return format_html(history)

    chat_history.short_description = "Chat History"

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'requested_at', 'processed_at')
    list_filter = ('status',)
    search_fields = ('user__username',)
    actions = ['approve_requests', 'reject_requests']

    def approve_requests(self, request, queryset):
        queryset.update(status='APPROVED', processed_at=timezone.now())
    approve_requests.short_description = "Approve selected withdrawal requests"

    def reject_requests(self, request, queryset):
        queryset.update(status='REJECTED', processed_at=timezone.now())
    reject_requests.short_description = "Reject selected withdrawal requests"

# --- NEW SUPPORT TICKET ADMIN ---
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'subject')
    # Make some fields read-only
    readonly_fields = ('user', 'subject', 'message', 'created_at', 'updated_at')
    # Define the fields to be displayed in the edit form
    fields = ('user', 'subject', 'message', 'status', 'admin_response', 'created_at', 'updated_at')


# --- User Profile Admin ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

admin.site.unregister(User.objects.model)
admin.site.register(User, UserAdmin)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'commission_rate')

# --- Other basic registrations ---
admin.site.register(Review)
admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(Transaction)