from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('search/', views.search_results, name='search_results'),
    path('game/<int:pk>/', views.game_detail_view, name='game_detail'),
    path('game/<int:game_pk>/category/<int:category_pk>/', views.listing_page_view, name='listing_page'),
    path('listing/<int:pk>/', views.product_detail, name='product_detail'),

    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change_form.html', success_url=reverse_lazy('password_change_done')), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),
    
    # Seller Dashboard & Listing Creation
    path('dashboard/', views.seller_dashboard, name='seller_dashboard'),
    path('sell/', views.select_game_for_listing, name='select_game_for_listing'),
    path('sell/<int:game_pk>/<int:category_pk>/', views.create_product, name='create_product'),

    # Order Management
    path('listing/<int:pk>/buy/', views.create_order, name='create_order'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/complete/', views.complete_order, name='complete_order'),

    # User-specific pages
    path('my-purchases/', views.my_purchases, name='my_purchases'),
    path('my-messages/', views.messages_view, name='my_messages'),
    path('my-messages/<str:username>/', views.messages_view, name='conversation_detail'),
    path('funds/', views.funds_view, name='funds'),
    path('settings/', views.settings_view, name='settings'),
    path('profile/<str:username>/', views.public_profile_view, name='public_profile'),
    path('support-center/', views.support_center_view, name='support_center'),

    # The generic slug URL MUST BE LAST.
    path('<slug:slug>/', views.flat_page_view, name='flat_page'),
]