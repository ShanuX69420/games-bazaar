from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Sum, Q, Count, Avg
from django.db.models.functions import Lower
from django.contrib.auth.models import User
import string
from django.contrib import messages
from collections import defaultdict

from .models import (
    Game, Category, Product, Order, Review, FlatPage, 
    Conversation, Message, WithdrawalRequest, SupportTicket, SiteConfiguration, Profile, Transaction
)
from .forms import (
    ProductForm, ReviewForm, WithdrawalRequestForm, SupportTicketForm,
    ProfilePictureForm, ProfileUpdateForm
)


def live_search(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse([], safe=False)
    games = Game.objects.filter(title__istartswith=query).order_by('title').prefetch_related('categories')[:12]
    results = []
    for game in games:
        try:
            game_url = reverse_lazy('game_detail', kwargs={'pk': game.pk})
        except Exception:
            game_url = '#'
        categories_data = []
        for cat in game.categories.all():
            try:
                cat_url = reverse_lazy('listing_page', kwargs={'game_pk': game.pk, 'category_pk': cat.pk})
                categories_data.append({'name': cat.name, 'url': cat_url})
            except Exception:
                continue
        results.append({
            'name': game.title,
            'url': game_url,
            'categories': categories_data
        })
    return JsonResponse(results, safe=False)

class RegisterView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/register.html'

def home(request):
    all_games = Game.objects.prefetch_related('categories').order_by(Lower('title'))
    letters = list(string.ascii_uppercase)
    context = {'games': all_games, 'letters': letters}
    return render(request, 'marketplace/home.html', context)

def search_results(request):
    query = request.GET.get('q', '')
    if query:
        games = Game.objects.filter(title__icontains=query).prefetch_related('categories').order_by('title')
    else:
        games = Game.objects.none()
    context = {'query': query, 'games': games}
    return render(request, 'marketplace/search_results.html', context)

@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    other_user = product.seller
    if request.user.id < other_user.id:
        p1, p2 = request.user, other_user
    else:
        p1, p2 = other_user, request.user
    conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
    messages = conversation.messages.all().order_by('timestamp')
    context = {'product': product, 'other_user': other_user, 'messages': messages}
    return render(request, 'marketplace/product_detail.html', context)

def game_detail_view(request, pk):
    game = get_object_or_404(Game, pk=pk)
    categories = game.categories.all()
    context = {'game': game, 'categories': categories}
    return render(request, 'marketplace/game_detail.html', context)

def listing_page_view(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    current_category = get_object_or_404(Category, pk=category_pk)
    listings = Product.objects.filter(game=game, category=current_category, is_active=True)
    all_categories = game.categories.all().annotate(listing_count=Count('product', filter=Q(product__game=game, product__is_active=True)))
    context = {'game': game, 'current_category': current_category, 'all_categories': all_categories, 'listings': listings}
    return render(request, 'marketplace/listing_page.html', context)

def public_profile_view(request, username):
    profile_user = get_object_or_404(User, username=username)

    if request.method == 'POST' and request.user == profile_user:
        p_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user.profile)
        if p_form.is_valid():
            p_form.save()
            # You can add a success message if you want
            # messages.success(request, 'Your profile picture has been updated!')
            return redirect('public_profile', username=username)
    else:
        # This is for a normal GET request
        p_form = ProfilePictureForm(instance=request.user.profile)

    # The rest of your view's logic to get products, reviews, etc.
    products = Product.objects.filter(seller=profile_user, is_active=True).select_related('game', 'category').order_by('game__title', 'category__name')
    
    grouped_listings = defaultdict(lambda: defaultdict(list))
    for product in products:
        if product.game and product.category:
            grouped_listings[product.game][product.category].append(product)
            
    reviews = Review.objects.filter(seller=profile_user).select_related('buyer', 'order__product', 'order__product__game').order_by('-created_at')
    
    review_stats = reviews.aggregate(
        average_rating=Avg('rating'),
        review_count=Count('id')
    )
    
    other_user = profile_user
    messages = []
    if request.user.is_authenticated and request.user != other_user:
        if request.user.id < other_user.id:
            p1, p2 = request.user, other_user
        else:
            p1, p2 = other_user, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        messages = conversation.messages.all().order_by('timestamp')

    context = {
        'profile_user': profile_user,
        'grouped_listings': dict(grouped_listings),
        'reviews': reviews,
        'average_rating': review_stats['average_rating'],
        'review_count': review_stats['review_count'],
        'other_user': other_user,
        'messages': messages,
        'product': products.first(),
        'p_form': p_form
    }
    
    return render(request, 'marketplace/public_profile.html', context)

def flat_page_view(request, slug):
    page = get_object_or_404(FlatPage, slug=slug)
    return render(request, 'marketplace/flat_page.html', {'page': page})


@login_required
def select_game_for_listing(request):
    games = Game.objects.all().order_by('title')
    return render(request, 'marketplace/select_game.html', {'games': games})

@login_required
def create_product(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    category = get_object_or_404(Category, pk=category_pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.game = game
            product.category = category
            product.save()
            return redirect('seller_dashboard')
    else:
        form = ProductForm()
    context = {'form': form, 'game': game, 'category': category}
    return render(request, 'marketplace/product_form.html', context)

# This is the corrected version
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
    order_url = reverse_lazy('order_detail', kwargs={'pk': order.pk})
    return JsonResponse({'status': 'success', 'order_url': order_url})

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    # Security check: only buyer or seller can view
    if request.user != order.buyer and request.user != order.seller:
        return HttpResponseForbidden()

    # Determine who the "other user" is in the conversation
    if request.user == order.buyer:
        other_user = order.seller
    else:
        other_user = order.buyer

    # Get or create the conversation between the two users
    if request.user.id < other_user.id:
        p1, p2 = request.user, other_user
    else:
        p1, p2 = other_user, request.user
    conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
    
    # Load messages and handle review form submission
    messages = conversation.messages.all().order_by('timestamp')
    existing_review = Review.objects.filter(order=order).first()
    review_form = ReviewForm()

    if request.method == 'POST' and 'rating' in request.POST:
        if order and order.status == 'COMPLETED' and not existing_review:
            form = ReviewForm(request.POST)
            if form.is_valid():
                review = form.save(commit=False)
                review.order = order
                review.buyer = request.user
                review.seller = order.seller
                review.save()
                return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'error', 'message': 'Could not submit review.'}, status=400)

    context = {
        'order': order,
        'other_user': other_user,  # This now correctly identifies the chat partner
        'product': order.product,  # Pass product for the chat panel logic
        'messages': messages,
        'review_form': review_form,
        'existing_review': existing_review,
    }
    return render(request, 'marketplace/order_detail.html', context)

@login_required
def complete_order(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status == 'PROCESSING':
        order.status = 'COMPLETED'
        order.commission_paid = order.calculate_commission()
        order.save()
    return redirect('order_detail', pk=order.pk)

@login_required
def my_purchases(request):
    # Start with the base queryset for the logged-in user
    orders = Order.objects.filter(buyer=request.user).select_related(
        'product__game', 'product__category', 'seller__profile'
    ).order_by('-created_at')

    # Get filter values from the GET request
    order_number_query = request.GET.get('order_number', '').strip()
    seller_name_query = request.GET.get('seller_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    game_id_query = request.GET.get('game', '').strip()

    # Apply filters if they exist
    if order_number_query:
        # Filter by order ID (must be a number)
        if order_number_query.isdigit():
            orders = orders.filter(id=order_number_query)
    if seller_name_query:
        orders = orders.filter(seller__username__icontains=seller_name_query)
    if status_query:
        orders = orders.filter(status=status_query)
    if game_id_query:
        orders = orders.filter(product__game__id=game_id_query)

    # Get a distinct list of games the user has purchased items from, for the filter dropdown
    games_for_filter = Game.objects.filter(
        listings__order__buyer=request.user
    ).distinct().order_by('title')

    context = {
        'orders': orders,
        'games_for_filter': games_for_filter,
        'statuses_for_filter': Order.STATUS_CHOICES,
        'filter_values': request.GET, # Pass the GET params back to pre-fill the form
    }
    return render(request, 'marketplace/my_purchases.html', context)


@login_required
def my_sales(request):
    # Start with the base queryset for the logged-in user
    orders = Order.objects.filter(seller=request.user).select_related(
        'product__game', 'product__category', 'buyer__profile'
    ).order_by('-created_at')

    # Get filter values from the GET request
    order_number_query = request.GET.get('order_number', '').strip()
    buyer_name_query = request.GET.get('buyer_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    game_id_query = request.GET.get('game', '').strip()

    # Apply filters if they exist
    if order_number_query:
        # Filter by order ID (must be a number)
        if order_number_query.isdigit():
            orders = orders.filter(id=order_number_query)
    if buyer_name_query:
        orders = orders.filter(buyer__username__icontains=buyer_name_query)
    if status_query:
        orders = orders.filter(status=status_query)
    if game_id_query:
        orders = orders.filter(product__game__id=game_id_query)

    # Get a distinct list of games the user has sold items from, for the filter dropdown
    games_for_filter = Game.objects.filter(
        listings__order__seller=request.user
    ).distinct().order_by('title')

    context = {
        'orders': orders,
        'games_for_filter': games_for_filter,
        'statuses_for_filter': Order.STATUS_CHOICES,
        'filter_values': request.GET, # Pass the GET params back to pre-fill the form
    }
    return render(request, 'marketplace/my_sales.html', context)

@login_required
def messages_view(request, username=None):
    # Get all conversations for the logged-in user for the list on the left
    conversations = Conversation.objects.filter(
        Q(participant1=request.user) | Q(participant2=request.user)
    ).order_by('-updated_at')

    # Get the IDs of conversations with unread messages
    unread_conversation_ids = set(Message.objects.filter(
        conversation__in=conversations, is_read=False
    ).exclude(sender=request.user).values_list('conversation_id', flat=True))

    # Initialize variables
    active_conversation = None
    messages = []
    other_user = None

    if username:
        try:
            # Get the user object for the person we want to chat with
            other_user = User.objects.get(username__iexact=username)

            # --- THE CORRECTED LOGIC ---
            # Directly query for the specific conversation between the two users
            active_conversation = Conversation.objects.filter(
                participant1__in=[request.user, other_user],
                participant2__in=[request.user, other_user]
            ).first()
            # --- END CORRECTED LOGIC ---

            if active_conversation:
                # If a conversation is found, load its messages and mark them as read
                messages = active_conversation.messages.all().order_by('timestamp')
                active_conversation.messages.exclude(sender=request.user).update(is_read=True)

        except User.DoesNotExist:
            # If the user in the URL doesn't exist, do nothing.
            pass

    context = {
        'conversations': conversations,
        'active_conversation': active_conversation,
        'other_user_profile': other_user, # This now correctly passes the user object
        'messages': messages,
        'unread_conversation_ids': unread_conversation_ids,
    }
    return render(request, 'marketplace/my_messages.html', context)

@login_required
def funds_view(request):
    # Calculate balance by summing all COMPLETED transactions
    balance_data = Transaction.objects.filter(
        user=request.user, 
        status='COMPLETED'
    ).aggregate(balance=Sum('amount'))
    balance = balance_data.get('balance') or 0

    # Get all transactions for the history view
    transactions = Transaction.objects.filter(user=request.user)

    # Handle filtering from the sidebar
    filter_by = request.GET.get('filter')
    if filter_by == 'deposits':
        transactions = transactions.filter(transaction_type='DEPOSIT')
    elif filter_by == 'withdrawals':
        transactions = transactions.filter(transaction_type='WITHDRAWAL')
    elif filter_by == 'orders':
        transactions = transactions.filter(transaction_type__in=['ORDER_PURCHASE', 'ORDER_SALE'])
    elif filter_by == 'miscellaneous':
        transactions = transactions.filter(transaction_type='MISCELLANEOUS')

    # Handle the withdrawal form submission
    if request.method == 'POST':
        form = WithdrawalRequestForm(request.POST, user=request.user, balance=balance)
        if form.is_valid():
            withdrawal_request = form.save(commit=False)
            withdrawal_request.user = request.user
            withdrawal_request.save()
            return redirect('funds') # Redirect to clear the form
    else:
        # We don't need the form for this new page design, but we keep the logic
        # in case you want to add a popup for withdrawals later.
        form = WithdrawalRequestForm(user=request.user, balance=balance)
        
    context = {
        'balance': balance,
        'transactions': transactions,
        'current_filter': filter_by, # To highlight the active filter
    }
    return render(request, 'marketplace/funds.html', context)

@login_required
def settings_view(request):
    return render(request, 'marketplace/settings.html')

@login_required
def support_center_view(request):
    if request.method == 'POST':
        form = SupportTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()
            return redirect('support_center')
    else:
        form = SupportTicketForm()
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    context = {'form': form, 'tickets': tickets}
    return render(request, 'marketplace/support_center.html', context)