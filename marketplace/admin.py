# marketplace/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Q, Case, When, Value, IntegerField
from django.db import models
from django.core.cache import cache
from django.urls import reverse
from .models import (
    SiteConfiguration, FlatPage, Game, Profile, Category, 
    Product, Order, Review, ReviewReply, Conversation, Message, WithdrawalRequest, DepositRequest,
    SupportTicket, Transaction, Filter, FilterOption, GameCategory, ProductImage, HeldFund
)
from . import admin_views

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
    list_display = ('get_order_id', 'get_product_title', 'buyer', 'seller', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'order_id', 'listing_title_snapshot', 'buyer__username', 'seller__username')
    readonly_fields = ('id', 'order_id', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at', 'get_product_link', 'get_buyer_profile', 'get_seller_profile', 'get_filter_options', 'get_related_conversations')
    date_hierarchy = 'created_at'
    actions = ['mark_completed', 'mark_cancelled']
    
    fieldsets = (
        ('Order Information', {
            'fields': ('id', 'order_id', 'status', 'created_at', 'updated_at')
        }),
        ('Participants', {
            'fields': ('buyer', 'get_buyer_profile', 'seller', 'get_seller_profile')
        }),
        ('Product Details (Snapshot at Purchase Time)', {
            'fields': ('get_product_link', 'listing_title_snapshot', 'description_snapshot', 'game_snapshot', 'category_snapshot', 'get_filter_options')
        }),
        ('Financial Information', {
            'fields': ('total_price', 'commission_paid')
        }),
        ('Related Communications', {
            'fields': ('get_related_conversations',),
            'description': 'Conversations between buyer and seller'
        }),
        ('Original References', {
            'fields': ('product',),
            'classes': ('collapse',),
            'description': 'Original product reference (may be deleted)'
        })
    )
    
    def get_order_id(self, obj):
        return obj.order_id or f"#{obj.id}"
    get_order_id.short_description = 'Order ID'
    
    def get_product_title(self, obj):
        return obj.listing_title_snapshot or (obj.product.listing_title if obj.product else 'Deleted Product')
    get_product_title.short_description = 'Product'
    
    def get_product_link(self, obj):
        if obj.product:
            return format_html(
                '<a href="/admin/marketplace/product/{}/change/" target="_blank" '
                'style="background: #28a745; color: white; padding: 5px 10px; text-decoration: none; '
                'border-radius: 3px;">View Original Product</a><br>'
                '<small style="color: #666; margin-top: 5px; display: block;">Product ID: {}</small>',
                obj.product.id,
                obj.product.id
            )
        return format_html('<em style="color: #dc3545;">Original product deleted or unavailable</em>')
    get_product_link.short_description = 'Original Product'
    
    def get_buyer_profile(self, obj):
        return format_html(
            '<a href="/admin/auth/user/{}/change/" target="_blank" '
            'style="background: #007cba; color: white; padding: 3px 8px; text-decoration: none; '
            'border-radius: 3px; font-size: 12px;">View Profile</a>',
            obj.buyer.id
        )
    get_buyer_profile.short_description = 'Buyer Profile'
    
    def get_seller_profile(self, obj):
        return format_html(
            '<a href="/admin/auth/user/{}/change/" target="_blank" '
            'style="background: #28a745; color: white; padding: 3px 8px; text-decoration: none; '
            'border-radius: 3px; font-size: 12px;">View Profile</a>',
            obj.seller.id
        )
    get_seller_profile.short_description = 'Seller Profile'
    
    def get_filter_options(self, obj):
        try:
            # Get filter options from the snapshot
            filter_options = obj.filter_options_snapshot.all() if hasattr(obj, 'filter_options_snapshot') else []
            if filter_options:
                options_html = []
                for option in filter_options:
                    options_html.append(
                        f'<span style="background: #f8f9fa; padding: 2px 6px; border-radius: 3px; '
                        f'margin: 2px; display: inline-block; border: 1px solid #dee2e6;">'
                        f'{option.filter.name}: {option.value}</span>'
                    )
                return format_html(
                    '<div style="margin-top: 5px;">{}</div>',
                    ''.join(options_html)
                )
            else:
                return format_html('<em style="color: #999;">No additional options selected</em>')
        except Exception as e:
            return format_html('<em style="color: #dc3545;">Error loading options: {}</em>', str(e))
    get_filter_options.short_description = 'Product Options'
    
    def get_related_conversations(self, obj):
        try:
            # Find conversations between buyer and seller
            conversations = Conversation.objects.filter(
                Q(participant1=obj.buyer, participant2=obj.seller) |
                Q(participant1=obj.seller, participant2=obj.buyer)
            ).order_by('-updated_at')
            
            if conversations.exists():
                conv_html = []
                for conv in conversations:
                    dispute_badge = '🚨 DISPUTED' if conv.is_disputed else '✅ Normal'
                    badge_color = '#dc3545' if conv.is_disputed else '#28a745'
                    
                    # Get recent message count
                    msg_count = conv.messages.count()
                    
                    conv_html.append(
                        f'<div style="border: 1px solid #dee2e6; padding: 10px; margin: 5px 0; border-radius: 5px;">'
                        f'<div style="margin-bottom: 5px;">'
                        f'<span style="background: {badge_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{dispute_badge}</span> '
                        f'<strong>{msg_count} messages</strong> • Updated {conv.updated_at.strftime("%b %d, %Y")}'
                        f'</div>'
                        f'<a href="/admin/chat/conversation/{conv.id}/chat/" target="_blank" '
                        f'style="background: #6f42c1; color: white; padding: 3px 8px; text-decoration: none; border-radius: 3px; font-size: 12px; margin-right: 5px;">View Chat</a>'
                        f'<a href="/admin/marketplace/conversation/{conv.id}/change/" target="_blank" '
                        f'style="background: #17a2b8; color: white; padding: 3px 8px; text-decoration: none; border-radius: 3px; font-size: 12px;">Manage</a>'
                        f'</div>'
                    )
                
                return format_html(''.join(conv_html))
            else:
                return format_html('<em style="color: #999;">No conversations found between buyer and seller</em>')
        except Exception as e:
            return format_html('<em style="color: #dc3545;">Error loading conversations: {}</em>', str(e))
    get_related_conversations.short_description = 'Buyer-Seller Communications'
    
    # Admin actions
    def mark_completed(self, request, queryset):
        updated = queryset.update(status='COMPLETED')
        self.message_user(request, f"{updated} orders marked as completed.")
    mark_completed.short_description = "✅ Mark selected orders as completed"
    
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status='CANCELLED')
        self.message_user(request, f"{updated} orders marked as cancelled.")
    mark_cancelled.short_description = "❌ Mark selected orders as cancelled"

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'status', 'related_record', 'created_at')
    list_filter = ('transaction_type', 'status', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'order', 'withdrawal', 'deposit')
    
    def related_record(self, obj):
        if obj.deposit:
            url = reverse('admin:marketplace_depositrequest_change', args=[obj.deposit.id])
            return format_html('<a href="{}">Deposit #{}</a>', url, obj.deposit.id)
        if obj.withdrawal:
            url = reverse('admin:marketplace_withdrawalrequest_change', args=[obj.withdrawal.id])
            return format_html('<a href="{}">Withdrawal #{}</a>', url, obj.withdrawal.id)
        if obj.order:
            url = reverse('admin:marketplace_order_change', args=[obj.order.id])
            return format_html('<a href="{}">Order #{}</a>', url, obj.order.order_id)
        return format_html('<span style="color:#6c757d;">—</span>')
    related_record.short_description = 'Linked record'

@admin.register(HeldFund)
class HeldFundAdmin(admin.ModelAdmin):
    list_display = ('user', 'order', 'amount', 'held_at', 'release_at', 'is_released', 'can_be_released_now')
    list_filter = ('is_released', 'held_at', 'release_at')
    search_fields = ('user__username', 'order__order_id')
    readonly_fields = ('held_at', 'released_at')
    date_hierarchy = 'held_at'
    actions = ['release_funds']
    
    def can_be_released_now(self, obj):
        return obj.can_be_released()
    can_be_released_now.boolean = True
    can_be_released_now.short_description = 'Can Release'
    
    def release_funds(self, request, queryset):
        released_count = 0
        for held_fund in queryset:
            if held_fund.release_fund():
                released_count += 1
        self.message_user(request, f"{released_count} funds released successfully.")
    release_funds.short_description = "Release selected funds (if eligible)"

# ==== USER MANAGEMENT ====
@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'payment_method', 'account_title', 'status', 'requested_at')
    list_filter = ('status', 'payment_method', 'requested_at')
    search_fields = ('user__username', 'account_title', 'account_number', 'iban')
    actions = ['approve_requests', 'reject_requests']
    date_hierarchy = 'requested_at'
    readonly_fields = ('requested_at',)
    
    fieldsets = (
        ('Withdrawal Information', {
            'fields': ('user', 'amount', 'status', 'requested_at', 'processed_at')
        }),
        ('Payment Details', {
            'fields': ('payment_method', 'account_title', 'account_number', 'iban')
        }),
        ('Admin Notes', {
            'fields': ('admin_notes',),
            'classes': ('collapse',)
        })
    )
    
    def approve_requests(self, request, queryset): 
        queryset.update(status='APPROVED', processed_at=timezone.now())
    approve_requests.short_description = "✅ Approve selected requests"
    
    def reject_requests(self, request, queryset): 
        queryset.update(status='REJECTED', processed_at=timezone.now())
    reject_requests.short_description = "❌ Reject selected requests"

@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'status_badge', 'payment_reference', 'requested_at', 'processed_at', 'transaction_link')
    list_filter = ('status', 'requested_at', 'processed_at')
    search_fields = ('user__username', 'payment_reference', 'notes')
    actions = ['mark_approved', 'mark_rejected']
    date_hierarchy = 'requested_at'
    readonly_fields = ('requested_at', 'processed_at', 'transaction_link', 'receipt_preview')
    list_select_related = ('user', 'transaction')
    
    fieldsets = (
        ('Deposit Summary', {
            'fields': ('user', 'amount', 'status', 'requested_at', 'processed_at', 'transaction_link')
        }),
        ('Payment Details', {
            'fields': ('payment_reference', 'receipt', 'receipt_preview')
        }),
        ('Customer Notes', {
            'fields': ('notes',)
        }),
        ('Admin Notes', {
            'fields': ('admin_notes',)
        })
    )
    
    def status_badge(self, obj):
        status_colors = {
            DepositRequest.STATUS_PENDING: '#d39e00',
            DepositRequest.STATUS_APPROVED: '#198754',
            DepositRequest.STATUS_REJECTED: '#dc3545',
        }
        color = status_colors.get(obj.status, '#6c757d')
        return format_html('<span style="font-weight:600; color:{};">{}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def receipt_preview(self, obj):
        if not obj.receipt:
            return format_html('<em>No receipt uploaded</em>')
        return format_html('<a href="{}" target="_blank" rel="noopener">View receipt</a>', obj.receipt.url)
    receipt_preview.short_description = 'Receipt'
    
    def transaction_link(self, obj):
        transaction = getattr(obj, 'transaction', None)
        if not transaction:
            return format_html('<em>Pending transaction link</em>')
        url = reverse('admin:marketplace_transaction_change', args=[transaction.id])
        return format_html('<a href="{}">Transaction #{}</a>', url, transaction.id)
    transaction_link.short_description = 'Transaction'
    
    def mark_approved(self, request, queryset):
        updated = 0
        for deposit in queryset.select_related('transaction'):
            if deposit.status != DepositRequest.STATUS_APPROVED:
                deposit.mark_approved()
                updated += 1
        self.message_user(request, f"{updated} deposit request{'s' if updated != 1 else ''} approved.")
    mark_approved.short_description = "✅ Approve selected deposits"
    
    def mark_rejected(self, request, queryset):
        updated = 0
        for deposit in queryset.select_related('transaction'):
            if deposit.status != DepositRequest.STATUS_REJECTED:
                deposit.mark_rejected()
                updated += 1
        self.message_user(request, f"{updated} deposit request{'s' if updated != 1 else ''} rejected.")
    mark_rejected.short_description = "❌ Reject selected deposits"

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'get_user_info', 'subject', 'get_category_badge', 'get_status_badge', 'created_at', 'view_actions')
    list_filter = ('status', 'user_type', 'issue_category', 'created_at')
    search_fields = ('user__username', 'subject', 'order_number')
    readonly_fields = ('user', 'subject', 'message', 'user_type', 'issue_category', 'get_order_link', 'created_at', 'updated_at', 'get_user_profile_link')
    date_hierarchy = 'created_at'
    list_per_page = 20
    
    fieldsets = (
        ('Ticket Information', {
            'fields': ('user', 'get_user_profile_link', 'subject', 'created_at', 'updated_at')
        }),
        ('Categorization', {
            'fields': ('user_type', 'issue_category', 'get_order_link')
        }),
        ('Content & Response', {
            'fields': ('message', 'status', 'admin_response')
        })
    )
    
    actions = ['mark_in_progress', 'mark_closed', 'mark_open']
    
    def get_queryset(self, request):
        # Show open tickets first, then in progress, then closed
        return super().get_queryset(request).select_related('user__profile').order_by(
            Case(
                When(status='OPEN', then=Value(1)),
                When(status='IN_PROGRESS', then=Value(2)),
                When(status='CLOSED', then=Value(3)),
                output_field=IntegerField()
            ),
            '-created_at'
        )
    
    def ticket_id(self, obj):
        return f"#{obj.id}"
    ticket_id.short_description = 'ID'
    
    def get_order_link(self, obj):
        if obj.order_number:
            try:
                # Clean the order number - ensure it has # prefix
                clean_order_id = obj.order_number.strip()
                if not clean_order_id.startswith('#'):
                    clean_order_id = '#' + clean_order_id
                
                # Look up order by order_id field (not primary key id)
                order = Order.objects.filter(order_id=clean_order_id).first()
                
                if order:
                    # Truncate description if too long for display
                    description = order.description_snapshot or 'No description'
                    if len(description) > 100:
                        description = description[:100] + '...'
                    
                    return format_html(
                        '<div style="margin-bottom: 10px;"><strong>Order {}</strong><br>'
                        '<a href="/admin/marketplace/order/{}/change/" target="_blank" '
                        'style="background: #17a2b8; color: white; padding: 5px 15px; text-decoration: none; '
                        'border-radius: 5px; display: inline-block; margin-top: 5px;">'
                        '📦 View Order Details</a><br>'
                        '<small style="color: #666; margin-top: 8px; display: block;"><strong>Product:</strong> {}</small>'
                        '<small style="color: #666; display: block;"><strong>Description:</strong> {}</small>'
                        '<small style="color: #666; display: block;"><strong>Buyer:</strong> {} | <strong>Seller:</strong> {}</small></div>',
                        clean_order_id,
                        order.id,
                        order.listing_title_snapshot or 'N/A',
                        description,
                        order.buyer.username,
                        order.seller.username
                    )
                else:
                    # If no order found, still show the order number
                    return format_html(
                        '<div><strong>Order {}</strong><br>'
                        '<small style="color: #dc3545;">⚠️ Order not found in database</small></div>',
                        clean_order_id
                    )
            except Exception as e:
                return format_html(
                    '<div><strong>Order {}</strong><br>'
                    '<small style="color: #dc3545;">⚠️ Error loading order: {}</small></div>',
                    obj.order_number, str(e)
                )
        return format_html('<em style="color: #999;">No order number provided</em>')
    get_order_link.short_description = 'Related Order'
    
    def get_user_profile_link(self, obj):
        return format_html(
            '<a href="/admin/auth/user/{}/change/" target="_blank" '
            'style="background: #28a745; color: white; padding: 5px 15px; text-decoration: none; '
            'border-radius: 5px; display: inline-block;">'
            '👤 View User Profile</a>',
            obj.user.id
        )
    get_user_profile_link.short_description = 'User Profile'
    
    def get_user_info(self, obj):
        user_type_color = '#007cba' if obj.user_type == 'BUYER' else '#28a745'
        return format_html(
            '<strong>{}</strong><br><span style="color: {}; font-size: 11px;">{}</span>',
            obj.user.username,
            user_type_color,
            obj.get_user_type_display()
        )
    get_user_info.short_description = 'User'
    
    def get_category_badge(self, obj):
        category_colors = {
            'ORDER': '#dc3545',
            'ACCOUNT': '#6f42c1', 
            'PAYMENT': '#fd7e14',
            'TECHNICAL': '#20c997',
            'GENERAL': '#6c757d',
            'BUG_REPORT': '#e83e8c',
            'FEATURE_REQUEST': '#0d6efd'
        }
        color = category_colors.get(obj.issue_category, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_issue_category_display()
        )
    get_category_badge.short_description = 'Category'
    
    def get_status_badge(self, obj):
        status_styles = {
            'OPEN': 'background-color: #dc3545; color: white; animation: pulse 2s infinite;',
            'IN_PROGRESS': 'background-color: #ffc107; color: black;',
            'CLOSED': 'background-color: #28a745; color: white;'
        }
        style = status_styles.get(obj.status, '')
        return format_html(
            '<span style="{}padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold;">{}</span>',
            style,
            obj.get_status_display()
        )
    get_status_badge.short_description = 'Status'
    
    def view_actions(self, obj):
        actions = []
        
        # Order details link if order number exists
        if obj.order_number:
            try:
                # Clean the order number - ensure it has # prefix
                clean_order_id = obj.order_number.strip()
                if not clean_order_id.startswith('#'):
                    clean_order_id = '#' + clean_order_id
                
                order = Order.objects.filter(order_id=clean_order_id).first()
                if order:
                    actions.append(
                        f'<a href="/admin/marketplace/order/{order.id}/change/" target="_blank" '
                        f'style="background: #17a2b8; color: white; padding: 3px 8px; text-decoration: none; '
                        f'border-radius: 3px; font-size: 11px; margin-right: 5px;">View Order</a>'
                    )
            except:
                pass
        
        # Chat view link
        try:
            chat = Conversation.objects.filter(
                Q(participant1=obj.user) | Q(participant2=obj.user)
            ).first()
            if chat:
                actions.append(
                    f'<a href="/admin/chat/conversation/{chat.id}/chat/" target="_blank" '
                    f'style="background: #6f42c1; color: white; padding: 3px 8px; text-decoration: none; '
                    f'border-radius: 3px; font-size: 11px; margin-right: 5px;">View Chat</a>'
                )
        except:
            pass
        
        # User profile link
        actions.append(
            f'<a href="/admin/auth/user/{obj.user.id}/change/" target="_blank" '
            f'style="background: #28a745; color: white; padding: 3px 8px; text-decoration: none; '
            f'border-radius: 3px; font-size: 11px;">User Profile</a>'
        )
        
        return format_html(''.join(actions))
    view_actions.short_description = 'Actions'
    
    # Admin actions for bulk operations
    def mark_in_progress(self, request, queryset):
        updated = queryset.update(status='IN_PROGRESS')
        self.message_user(request, f"{updated} tickets marked as In Progress.")
    mark_in_progress.short_description = "📋 Mark selected tickets as In Progress"
    
    def mark_closed(self, request, queryset):
        updated = queryset.update(status='CLOSED')
        self.message_user(request, f"{updated} tickets marked as Closed.")
    mark_closed.short_description = "✅ Mark selected tickets as Closed"
    
    def mark_open(self, request, queryset):
        updated = queryset.update(status='OPEN')
        self.message_user(request, f"{updated} tickets marked as Open.")
    mark_open.short_description = "🔄 Mark selected tickets as Open"
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        
        # Get the ticket object
        try:
            ticket = self.get_object(request, object_id)
            if ticket:
                # Get related order
                if ticket.order_number:
                    try:
                        # Clean the order number - ensure it has # prefix
                        clean_order_id = ticket.order_number.strip()
                        if not clean_order_id.startswith('#'):
                            clean_order_id = '#' + clean_order_id
                        
                        # Look up order by order_id field
                        related_order = Order.objects.filter(order_id=clean_order_id).first()
                        extra_context['related_order'] = related_order
                    except:
                        pass
                
                # Get user conversations
                conversations = Conversation.objects.filter(
                    Q(participant1=ticket.user) | Q(participant2=ticket.user)
                ).select_related('participant1', 'participant2').order_by('-updated_at')
                
                # Add recent message to each conversation
                for conv in conversations:
                    recent_msg = conv.messages.exclude(content='').order_by('-timestamp').first()
                    conv.recent_message = recent_msg.content if recent_msg else None
                
                extra_context['conversations'] = conversations
        except:
            pass
        
        return super().change_view(request, object_id, form_url, extra_context)
    
    class Media:
        css = {
            'all': ('admin/css/support_tickets.css',)
        }

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('commission_rate', 'image', 'show_listings_on_site', 'is_verified_seller')

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
admin.site.site_header = "GamesBazaar Admin"
admin.site.site_title = "GamesBazaar"
admin.site.index_title = "Welcome to GamesBazaar Administration"

# Add custom admin view for support dashboard
from django.urls import path
from django.shortcuts import redirect

def admin_index_redirect(request):
    """Custom admin index with support dashboard link"""
    return redirect('/admin/chat/support-dashboard/')

# Override admin URLs to include support dashboard
original_get_urls = admin.site.get_urls

def get_urls():
    urls = original_get_urls()
    custom_urls = [
        path('support-dashboard/', admin_views.support_dashboard, name='support_dashboard'),
    ]
    return custom_urls + urls

admin.site.get_urls = get_urls
