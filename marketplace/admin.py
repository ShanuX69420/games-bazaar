# marketplace/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Q
from django.core.cache import cache
from .models import (
    SiteConfiguration, FlatPage, Game, Profile, Category, 
    Product, Order, Review, ReviewReply, Conversation, Message, WithdrawalRequest, 
    SupportTicket, Transaction, Filter, FilterOption, GameCategory, ProductImage
)

# Site Configuration
@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    list_display = ('default_commission_rate',)
    
@admin.register(FlatPage)
class FlatPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'updated_at')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}

# ==== GAMES & CATEGORIES ====
class GameCategoryInline(admin.TabularInline):
    model = GameCategory
    extra = 0
    fields = ('category', 'allows_automated_delivery', 'primary_filter', 'filters')
    filter_horizontal = ('filters',)
    verbose_name = "Category Setup"
    verbose_name_plural = "Game Categories"

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('title', 'category_count')
    search_fields = ('title',)
    inlines = [GameCategoryInline]
    
    def category_count(self, obj):
        return obj.categories.count()
    category_count.short_description = 'Categories'
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Clear cache when games are added/modified
        cache.delete('home_games_list')
        
    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        # Clear cache when games are deleted
        cache.delete('home_games_list')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'commission_rate', 'game_count')
    search_fields = ('name',)
    list_editable = ('commission_rate',)
    
    def game_count(self, obj):
        return obj.games.count()
    game_count.short_description = 'Games Using This'
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Clear cache when categories are modified (affects game display)
        cache.delete('home_games_list') 

# ==== FILTERS SYSTEM ====
class FilterOptionInline(admin.TabularInline):
    model = FilterOption
    extra = 1
    fields = ('value',)

@admin.register(Filter)
class FilterAdmin(admin.ModelAdmin):
    list_display = ('internal_name', 'name', 'filter_type', 'order', 'append_to_title', 'option_count')
    list_editable = ('order', 'append_to_title')
    search_fields = ('internal_name', 'name')
    list_filter = ('filter_type',)
    inlines = [FilterOptionInline]
    
    def option_count(self, obj):
        return obj.options.count()
    option_count.short_description = 'Options'

# ==== PRODUCTS ====
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ('image',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('listing_title', 'game', 'category', 'seller', 'price', 'is_active', 'created_at')
    list_filter = ('is_active', 'game', 'category', 'automatic_delivery')
    search_fields = ('listing_title', 'game__title', 'seller__username')
    filter_horizontal = ('filter_options',)
    inlines = [ProductImageInline]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('seller', 'game', 'category', 'listing_title', 'description', 'price')
        }),
        ('Settings', {
            'fields': ('is_active', 'automatic_delivery', 'stock', 'stock_details', 'post_purchase_message')
        }),
        ('Filters', {
            'fields': ('filter_options',),
            'classes': ('collapse',)
        })
    )

# ==== ORDERS & TRANSACTIONS ====
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_product_title', 'buyer', 'seller', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'listing_title_snapshot', 'buyer__username', 'seller__username')
    readonly_fields = ('id', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Order Info', {
            'fields': ('id', 'buyer', 'seller', 'status', 'created_at', 'updated_at')
        }),
        ('Product Details', {
            'fields': ('product', 'listing_title_snapshot', 'total_price', 'commission_paid')
        })
    )
    
    def get_product_title(self, obj):
        return obj.listing_title_snapshot or (obj.product.listing_title if obj.product else 'Deleted Product')
    get_product_title.short_description = 'Product'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

# ==== USER MANAGEMENT ====
@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'requested_at')
    list_filter = ('status', 'requested_at')
    search_fields = ('user__username',)
    actions = ['approve_requests', 'reject_requests']
    date_hierarchy = 'requested_at'
    
    def approve_requests(self, request, queryset): 
        queryset.update(status='APPROVED', processed_at=timezone.now())
    approve_requests.short_description = "✅ Approve selected requests"
    
    def reject_requests(self, request, queryset): 
        queryset.update(status='REJECTED', processed_at=timezone.now())
    reject_requests.short_description = "❌ Reject selected requests"

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'subject')
    readonly_fields = ('user', 'subject', 'message', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Ticket Info', {
            'fields': ('user', 'subject', 'created_at', 'updated_at')
        }),
        ('Content', {
            'fields': ('message', 'status', 'admin_response')
        })
    )

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('commission_rate', 'image', 'show_listings_on_site')

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# ==== REVIEWS & COMMUNICATION ====
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'seller', 'rating', 'created_at', 'has_reply')
    list_filter = ('rating', 'created_at')
    search_fields = ('buyer__username', 'seller__username', 'comment')
    readonly_fields = ('buyer', 'seller', 'order', 'created_at')
    date_hierarchy = 'created_at'
    
    def has_reply(self, obj):
        return hasattr(obj, 'reply') and obj.reply is not None
    has_reply.boolean = True
    has_reply.short_description = 'Has Reply'

@admin.register(ReviewReply)
class ReviewReplyAdmin(admin.ModelAdmin):
    list_display = ('seller', 'get_review_info', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('seller__username', 'reply_text', 'review__comment')
    readonly_fields = ('seller', 'review', 'created_at')
    date_hierarchy = 'created_at'
    
    def get_review_info(self, obj):
        return f"Reply to {obj.review.rating}★ review by {obj.review.buyer.username}"
    get_review_info.short_description = 'Review Info'

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'get_recipient', 'timestamp', 'is_read', 'is_system_message')
    list_filter = ('is_read', 'is_system_message', 'timestamp')
    search_fields = ('sender__username', 'content')
    readonly_fields = ('sender', 'conversation', 'timestamp')
    date_hierarchy = 'timestamp'
    
    def get_recipient(self, obj):
        participants = [obj.conversation.participant1, obj.conversation.participant2]
        return next((p.username for p in participants if p != obj.sender), 'Unknown')
    get_recipient.short_description = 'To'

# Conversation management for disputes
@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('get_participants', 'is_disputed', 'moderator', 'created_at', 'message_count', 'view_chat')
    list_filter = ('is_disputed', 'created_at')
    search_fields = ('participant1__username', 'participant2__username', 'moderator__username')
    readonly_fields = ('participant1', 'participant2', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Participants', {
            'fields': ('participant1', 'participant2')
        }),
        ('Moderation', {
            'fields': ('is_disputed', 'moderator')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_participants(self, obj):
        return f"{obj.participant1.username} ↔ {obj.participant2.username}"
    get_participants.short_description = 'Participants'
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'
    
    def view_chat(self, obj):
        dispute_badge = ""
        if obj.is_disputed:
            dispute_badge = '<span style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; margin-right: 5px;">DISPUTED</span>'
        
        return format_html(
            '{}<a href="/admin/chat/conversation/{}/chat/" class="button" style="background: #007cba; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">View Chat</a>',
            dispute_badge,
            obj.id
        )
    view_chat.short_description = 'Actions'
    
    def get_queryset(self, request):
        # Show disputed conversations first
        return super().get_queryset(request).order_by('-is_disputed', '-updated_at')
    
    # Custom admin actions
    actions = ['mark_as_disputed', 'resolve_dispute', 'assign_moderator']
    
    def mark_as_disputed(self, request, queryset):
        queryset.update(is_disputed=True)
        self.message_user(request, f"{queryset.count()} conversations marked as disputed.")
    mark_as_disputed.short_description = "Mark selected conversations as disputed"
    
    def resolve_dispute(self, request, queryset):
        queryset.update(is_disputed=False, moderator=None)
        self.message_user(request, f"{queryset.count()} disputes resolved.")
    resolve_dispute.short_description = "Resolve selected disputes"
    
    def assign_moderator(self, request, queryset):
        queryset.update(moderator=request.user, is_disputed=True)
        self.message_user(request, f"You have been assigned as moderator to {queryset.count()} conversations.")
    assign_moderator.short_description = "Assign yourself as moderator"

# ==== ADMIN SITE CUSTOMIZATION ====
admin.site.site_header = "Gamers Market Admin"
admin.site.site_title = "Gamers Market"
admin.site.index_title = "Welcome to Gamers Market Administration"