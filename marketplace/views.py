# marketplace/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Sum, Q

from .models import Product, Order, ChatMessage, Review
from .forms import ProductForm, ReviewForm

# --- AUTHENTICATION ---
class RegisterView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/register.html'

# --- MAIN PAGES ---
def home(request):
    products = Product.objects.filter(is_active=True)
    return render(request, 'marketplace/home.html', {'products': products})

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    return render(request, 'marketplace/product_detail.html', {'product': product})

# --- SELLER DASHBOARD ---
@login_required
def seller_dashboard(request):
    products = Product.objects.filter(seller=request.user)
    completed_orders = Order.objects.filter(seller=request.user, status='COMPLETED')

    sales_data = completed_orders.aggregate(
        total_sales=Sum('total_price'),
        total_commission=Sum('commission_paid')
    )

    total_sales = sales_data.get('total_sales') or 0
    total_commission = sales_data.get('total_commission') or 0
    net_earnings = total_sales - total_commission

    context = {
        'products': products,
        'completed_orders': completed_orders,
        'total_sales': total_sales,
        'total_commission': total_commission,
        'net_earnings': net_earnings,
    }
    return render(request, 'marketplace/seller_dashboard.html', context)

@login_required
def create_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.save()
            return redirect('seller_dashboard')
    else:
        form = ProductForm()
    return render(request, 'marketplace/product_form.html', {'form': form})

# --- ORDER MANAGEMENT ---
@login_required
def create_order(request, pk):
    product = get_object_or_404(Product, pk=pk)
    order = Order.objects.create(
        buyer=request.user,
        seller=product.seller,
        product=product,
        total_price=product.price,
        status='PROCESSING'
    )
    return redirect('order_detail', pk=order.pk)

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if request.user != order.buyer and request.user != order.seller:
        return HttpResponseForbidden("You do not have permission to view this order.")

    chat_messages = ChatMessage.objects.filter(order=order).order_by('timestamp')
    existing_review = Review.objects.filter(order=order).first()
    review_form = ReviewForm()

    if request.method == 'POST' and 'rating' in request.POST:
        form = ReviewForm(request.POST)
        if form.is_valid() and order.status == 'COMPLETED' and request.user == order.buyer and not existing_review:
            review = form.save(commit=False)
            review.order = order
            review.buyer = request.user
            review.seller = order.seller
            review.save()
            return redirect('order_detail', pk=order.pk)

    return render(request, 'marketplace/order_detail.html', {
        'order': order,
        'chat_messages': chat_messages,
        'review_form': review_form,
        'existing_review': existing_review,
    })

@login_required
def complete_order(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status == 'PROCESSING':
        order.status = 'COMPLETED'
        order.commission_paid = order.calculate_commission()
        order.save()
    return redirect('order_detail', pk=order.pk)


def search_results(request):
    query = request.GET.get('q', '')
    if query:
        # Search in product title and description (case-insensitive)
        results = Product.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query),
            is_active=True
        )
    else:
        results = Product.objects.none() # Return no results if query is empty

    return render(request, 'marketplace/search_results.html', {
        'query': query,
        'results': results
    })



@login_required
def my_purchases(request):
    orders = Order.objects.filter(buyer=request.user).order_by('-created_at')
    return render(request, 'marketplace/my_purchases.html', {'orders': orders})