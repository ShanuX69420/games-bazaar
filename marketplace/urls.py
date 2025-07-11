# marketplace/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Main pages
    path('', views.home, name='home'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),

    # Auth
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    # Seller Dashboard
    path('dashboard/', views.seller_dashboard, name='seller_dashboard'),
    path('dashboard/products/create/', views.create_product, name='create_product'),

    # Order Management
    path('product/<int:pk>/buy/', views.create_order, name='create_order'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/complete/', views.complete_order, name='complete_order'),
]