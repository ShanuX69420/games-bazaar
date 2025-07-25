# marketplace/urls.py
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
    path('api/live-search/', views.live_search, name='live_search'),

    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change_form.html', success_url=reverse_lazy('password_change_done')), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html', success_url=reverse_lazy('password_reset_done')), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html', success_url=reverse_lazy('password_reset_complete')), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    
    # Seller Dashboard & Listing Creation/Editing
    path('sell/', views.select_game_for_listing, name='select_game_for_listing'),
    path('sell/<int:game_pk>/<int:category_pk>/', views.create_product, name='create_product'),
    path('listing/<int:pk>/edit/', views.edit_product, name='edit_product'), # New URL for editing
    path('listing/<int:pk>/delete/', views.delete_product, name='delete_product'), # New URL for deleting
    path('sell/<int:game_pk>/<int:category_pk>/my-listings/', views.my_listings_in_category, name='my_listings_in_category'),

    # Order Management & Reviews
    path('listing/<int:pk>/buy/', views.create_order, name='create_order'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/complete/', views.complete_order, name='complete_order'),
    path('order/<int:pk>/refund/', views.refund_order, name='refund_order'),
    path('review/<int:pk>/edit/', views.edit_review, name='edit_review'),
    path('review/<int:pk>/delete/', views.delete_review, name='delete_review'),


    # User-specific pages
    path('my-sales/', views.my_sales, name='my_sales'),
    path('my-purchases/', views.my_purchases, name='my_purchases'),
    path('my-messages/', views.messages_view, name='my_messages'),
    path('my-messages/<str:username>/', views.messages_view, name='conversation_detail'),
    path('funds/', views.funds_view, name='funds'),
    path('settings/', views.settings_view, name='settings'),
    path('profile/<str:username>/', views.public_profile_view, name='public_profile'),
    path('ajax/load-more-reviews/<str:username>/', views.load_more_reviews, name='load_more_reviews'),
    path('ajax/send-message/<str:username>/', views.send_chat_message, name='send_chat_message'),
    path('ajax/update-profile-picture/', views.ajax_update_profile_picture, name='ajax_update_profile_picture'),
    path('ajax/update-listing-visibility/', views.ajax_update_listing_visibility, name='ajax_update_listing_visibility'),
    path('ajax/boost-listings/<int:game_pk>/', views.boost_listings, name='boost_listings'),
    path('support-center/', views.support_center_view, name='support_center'),
    path('ajax/load-more-purchases/', views.load_more_purchases, name='load_more_purchases'),
    path('ajax/load-more-sales/', views.load_more_sales, name='load_more_sales'),
    path('ajax/load-more-transactions/', views.load_more_transactions, name='load_more_transactions'),
    path('ajax/load-more-listings/<int:game_pk>/<int:category_pk>/', views.load_more_listings, name='load_more_listings'),
    path('jazzcash/payment/<int:product_id>/', views.jazzcash_payment, name='jazzcash_payment'),
    path('jazzcash/callback/', views.jazzcash_callback, name='jazzcash_callback'),
    path('payment-failed/', views.payment_failed_view, name='payment_failed'),
    path('order-confirmation/<int:order_id>/', views.order_confirmation_view, name='order_confirmation'),

    # The generic slug URL MUST BE LAST.
    path('<slug:slug>/', views.flat_page_view, name='flat_page'),
]