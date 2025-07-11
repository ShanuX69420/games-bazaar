# marketplace/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import SiteConfiguration, Profile, Category, Product, Order, Review, ChatMessage

# --- Site Wide Settings ---
admin.site.register(SiteConfiguration)

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

# --- Category Admin ---
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'commission_rate')

# --- Order Admin with Chat History ---
class ChatMessagesInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('sender', 'message', 'timestamp')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'buyer', 'seller', 'status', 'total_price', 'commission_paid', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'product__title', 'buyer__username', 'seller__username')
    readonly_fields = ('id', 'product', 'buyer', 'seller', 'total_price', 'commission_paid', 'created_at', 'updated_at')
    inlines = [ChatMessagesInline]

# --- Other Model Registrations ---
# Note: We are NOT registering Order here again because the decorator does it.
admin.site.register(Product)
admin.site.register(Review)
admin.site.register(ChatMessage)