# marketplace/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Q
from .models import (
    SiteConfiguration, FlatPage, Game, Profile, Category, 
    Product, Order, Review, Conversation, Message, WithdrawalRequest, 
    SupportTicket, Transaction, Filter, FilterOption, GameCategory, ProductImage
)

admin.site.register(SiteConfiguration)
admin.site.register(FlatPage)

# NEW: This inline editor is the core of the new admin experience
class GameCategoryInline(admin.TabularInline):
    model = GameCategory
    extra = 1 # Show one extra blank row for adding
    filter_horizontal = ('filters',) # Use a nice widget for selecting filters
    fields = ('category', 'primary_filter', 'filters', 'allows_automated_delivery')

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('title',)
    search_fields = ('title',)
    # REMOVED: filter_horizontal for categories is gone
    # NEW: The inline editor is added here
    inlines = [GameCategoryInline] 

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('listing_title', 'game', 'seller', 'price', 'is_active')
    list_filter = ('game', 'category', 'is_active')
    search_fields = ('listing_title', 'game__title', 'seller__username')
    filter_horizontal = ('filter_options',)
    inlines = [ProductImageInline]

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'buyer', 'seller', 'status', 'total_price', 'commission_paid', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'product__listing_title', 'buyer__username', 'seller__username')
    readonly_fields = ('id', 'product', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at', 'chat_history')
    fields = ('id', 'product', 'status', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at', 'chat_history')
    def chat_history(self, obj):
        conversation = Conversation.objects.filter((Q(participant1=obj.buyer) & Q(participant2=obj.seller)) | (Q(participant1=obj.seller) & Q(participant2=obj.buyer))).first()
        if not conversation: return "No conversation found."
        messages = conversation.messages.all().order_by('timestamp')
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
    def approve_requests(self, request, queryset): queryset.update(status='APPROVED', processed_at=timezone.now())
    approve_requests.short_description = "Approve selected withdrawal requests"
    def reject_requests(self, request, queryset): queryset.update(status='REJECTED', processed_at=timezone.now())
    reject_requests.short_description = "Reject selected withdrawal requests"

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'subject')
    readonly_fields = ('user', 'subject', 'message', 'created_at', 'updated_at')
    fields = ('user', 'subject', 'message', 'status', 'admin_response', 'created_at', 'updated_at')

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'commission_rate')
    search_fields = ('name',)
    # REMOVED: filter_horizontal for filters is gone from here.

class FilterOptionInline(admin.TabularInline):
    model = FilterOption
    extra = 1

@admin.register(Filter)
class FilterAdmin(admin.ModelAdmin):
    list_display = ('internal_name', 'name', 'filter_type', 'order', 'append_to_title')
    list_editable = ('order',)
    search_fields = ('internal_name', 'name')
    inlines = [FilterOptionInline]

# Register other models
admin.site.register(Review)
admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(Transaction)
admin.site.register(FilterOption)