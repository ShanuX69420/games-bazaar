# marketplace/views.py
import json
import requests
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, Http404
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib.auth import forms as auth_forms
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q, Count, Avg, F, OuterRef, Subquery
from django.db.models.functions import Lower
from django.contrib.auth.models import User
import string
from django.contrib import messages
from itertools import groupby
from operator import attrgetter
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.core.exceptions import ValidationError

def validate_quantity(quantity_str, max_quantity=1000):
    """
    Securely validate quantity input with proper bounds checking.
    Returns validated quantity or raises ValidationError.
    """
    try:
        quantity = int(quantity_str)
        if quantity < 1:
            raise ValidationError("Quantity must be at least 1")
        if quantity > max_quantity:
            raise ValidationError(f"Quantity cannot exceed {max_quantity}")
        return quantity
    except (ValueError, TypeError):
        raise ValidationError("Invalid quantity format")

def validate_uploaded_file(uploaded_file, max_size_mb=5, allowed_types=None):
    """
    Enhanced secure validation for uploaded files.
    Returns True if valid, raises ValidationError if not.
    """
    if allowed_types is None:
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    
    # Check file size
    max_size = max_size_mb * 1024 * 1024  # Convert to bytes
    if uploaded_file.size > max_size:
        raise ValidationError(f"File size cannot exceed {max_size_mb}MB")
    
    # Check for minimum file size (prevent empty files)
    if uploaded_file.size < 100:  # Minimum 100 bytes
        raise ValidationError("File is too small to be a valid image")
    
    # Strict filename validation
    if not uploaded_file.name or len(uploaded_file.name) > 255:
        raise ValidationError("Invalid filename")
    
    # Check for dangerous filenames
    dangerous_patterns = ['..', '/', '\\', '<', '>', ':', '"', '|', '?', '*', '\x00']
    if any(pattern in uploaded_file.name for pattern in dangerous_patterns):
        raise ValidationError("Filename contains dangerous characters")
    
    # Check file extension (stricter validation)
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    file_ext = uploaded_file.name.lower().split('.')[-1] if '.' in uploaded_file.name else ''
    if f'.{file_ext}' not in allowed_extensions:
        raise ValidationError(f"File extension .{file_ext} not allowed")
    
    # Check MIME type matches extension
    mime_ext_mapping = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/gif': ['.gif'],
        'image/webp': ['.webp']
    }
    
    if uploaded_file.content_type in mime_ext_mapping:
        if f'.{file_ext}' not in mime_ext_mapping[uploaded_file.content_type]:
            raise ValidationError("File extension doesn't match content type")
    
    # Enhanced magic byte validation
    uploaded_file.seek(0)
    file_start = uploaded_file.read(16)  # Read more bytes for better detection
    uploaded_file.seek(0)
    
    # Comprehensive image signatures
    image_signatures = [
        b'\xff\xd8\xff',  # JPEG
        b'\x89PNG\r\n\x1a\n',  # PNG
        b'GIF87a',  # GIF87a
        b'GIF89a',  # GIF89a
        b'RIFF',  # WebP (check WEBP in content too)
    ]
    
    if not any(file_start.startswith(sig) for sig in image_signatures):
        raise ValidationError("File content does not match expected image format")
    
    # Additional WebP validation
    if uploaded_file.content_type == 'image/webp':
        if b'WEBP' not in file_start:
            raise ValidationError("Invalid WebP file format")
    
    # Check for embedded scripts in image metadata (basic check)
    file_content_lower = file_start.lower()
    script_patterns = [b'<script', b'javascript:', b'vbscript:', b'onload=', b'onerror=']
    if any(pattern in file_content_lower for pattern in script_patterns):
        raise ValidationError("File contains potentially malicious content")
    
    return True

def check_rate_limit(request, action, limit=10, period=300):
    """
    Simple rate limiting using Django cache.
    Returns True if action is allowed, False if rate limit exceeded.
    
    Args:
        request: Django request object
        action: String identifying the action (e.g., 'login', 'message', 'order')
        limit: Number of allowed actions per period
        period: Time period in seconds (default: 5 minutes)
    """
    # Use IP address for rate limiting
    user_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not user_ip:
        user_ip = request.META.get('REMOTE_ADDR', '')
    
    # Create cache key
    if request.user.is_authenticated:
        cache_key = f'rate_limit_{action}_{request.user.id}_{user_ip}'
    else:
        cache_key = f'rate_limit_{action}_{user_ip}'
    
    # Get current count
    current_count = cache.get(cache_key, 0)
    
    if current_count >= limit:
        return False
    
    # Increment counter
    cache.set(cache_key, current_count + 1, period)
    return True

def sanitize_user_input(text, max_length=10000):
    """
    Sanitize user input to prevent XSS and other injection attacks.
    Returns cleaned text with HTML characters escaped.
    """
    if not text:
        return text
    
    # Truncate to max length
    text = str(text)[:max_length]
    
    # Escape HTML characters to prevent XSS - this is safer than removing content
    from django.utils.html import escape
    text = escape(text)
    
    # Remove null bytes and control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in ['\n', '\r', '\t'])
    
    return text.strip()

def get_cached_message_count(conversation):
    """Get message count with caching to avoid repeated count() queries"""
    cache_key = f'conversation_message_count_{conversation.id}'
    count = cache.get(cache_key)
    if count is None:
        count = conversation.messages.count()
        cache.set(cache_key, count, 300)  # Cache for 5 minutes
    return count

def get_cached_review_stats(seller):
    """Get review statistics with caching to avoid repeated aggregate queries"""
    cache_key = f'review_stats_{seller.id}'
    stats = cache.get(cache_key)
    if stats is None:
        from django.db.models import Avg, Count
        stats = Review.objects.filter(seller=seller).aggregate(
            average_rating=Avg('rating'), 
            review_count=Count('id')
        )
        # Cache for 10 minutes - reviews don't change very frequently
        cache.set(cache_key, stats, 600)
    return stats
from .jazzcash_utils import get_jazzcash_payment_params, verify_jazzcash_response
from django.conf import settings

from .models import (
    Game, Category, Product, Order, Review, ReviewReply, FlatPage,
    Conversation, Message, WithdrawalRequest, SupportTicket, SiteConfiguration, Profile, Transaction, GameCategory, UserGameBoost, ProductImage, BlockedUser
)
from .forms import (
    ProductForm, ReviewForm, ReviewReplyForm, WithdrawalRequestForm, SupportTicketForm,
    ProfilePictureForm, ProfileUpdateForm, CustomUserCreationForm
)


def live_search(request):
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 1:
        return JsonResponse([], safe=False)

    cache_key = f'search_{query.lower()}'
    cached_results = cache.get(cache_key)

    if cached_results is not None:
        return JsonResponse(cached_results, safe=False)

    # DEV NOTE: For a more scalable solution at a larger scale,
    # a dedicated search index (e.g., Elasticsearch or PostgreSQL's trigram index)
    # on the 'title' field of the Game model is recommended.
    games = Game.objects.filter(title__istartswith=query).prefetch_related('categories')[:6]
    
    results = []
    for game in games:
        try:
            game_url = reverse_lazy('game_detail', kwargs={'pk': game.pk})
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
        except Exception:
            continue

    cache.set(cache_key, results, 120)  # Cache for 2 minutes
    return JsonResponse(results, safe=False)

class RegisterView(generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/register.html'

def form_valid(self, form):
        recaptcha_response = self.request.POST.get('g-recaptcha-response')
        if not recaptcha_response:
            messages.error(self.request, 'Please complete the reCAPTCHA.')
            return self.form_invalid(form)

        data = {
            'secret': settings.RECAPTCHA_PRIVATE_KEY,
            'response': recaptcha_response
        }
        r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
        result = r.json()

        if not result.get('success'):
            messages.error(self.request, 'Invalid reCAPTCHA. Please try again.')
            return self.form_invalid(form)

        messages.success(self.request, 'Registration successful! You can now log in.')
        return super().form_valid(form)

def home(request):
    # Cache games for 10 minutes since they don't change frequently
    cache_key = 'home_games_list'
    all_games = cache.get(cache_key)

    if all_games is None:
        all_games = list(Game.objects.prefetch_related('categories').order_by(Lower('title')))
        cache.set(cache_key, all_games, 600)  # 10 minutes

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

def product_detail(request, pk):
    product = get_object_or_404(Product.objects.with_full_details(), pk=pk)
    seller = product.seller
    messages = []
    active_conversation = None
    is_blocked = False


    if request.user.is_authenticated and request.user != seller:
        # Check if users have blocked each other
        is_blocked = BlockedUser.objects.filter(
            Q(blocker=request.user, blocked=seller) |
            Q(blocker=seller, blocked=request.user)
        ).exists()
        if request.user.id < seller.id:
            p1, p2 = request.user, seller
        else:
            p1, p2 = seller, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        active_conversation = conversation
        # MODIFIED: Fetch the last 100 messages initially for better infinite scroll
        message_manager = conversation.messages
        message_count = get_cached_message_count(conversation)
        messages = message_manager.order_by('timestamp')[max(0, message_count - 100):]
        has_more_messages = message_count > 100
    all_reviews = Review.objects.with_full_details().by_seller(seller).recent_first()
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else:
        reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = get_cached_review_stats(seller)

    ordered_filter_options = product.filter_options.select_related('filter').order_by('filter__order')

    # Efficient random selection: get total count, then use random offset
    similar_products_query = Product.objects.filter(game=product.game, is_active=True).exclude(pk=pk)
    total_count = similar_products_query.count()
    if total_count > 0:
        # Get up to 5 random products using efficient offset method
        import random
        max_items = min(5, total_count)
        random_offset = random.randint(0, max(0, total_count - max_items))
        similar_products = similar_products_query[random_offset:random_offset + max_items]
    else:
        similar_products = []
    context = {
        'product': product,
        'similar_products': similar_products,
        'messages': messages,
        'active_conversation': active_conversation,
        'reviews': page_obj,
        'average_rating': review_stats['average_rating'],
        'review_count': review_stats['review_count'],
        'current_rating_filter': rating_filter,
        'profile_user': seller,
        'ordered_filter_options': ordered_filter_options,
        'has_more_messages': has_more_messages if 'has_more_messages' in locals() else False,
        'is_blocked': is_blocked,
    }
    return render(request, 'marketplace/product_detail.html', context)

def game_detail_view(request, pk):
    # Cache game details for 5 minutes
    cache_key = f'game_detail_{pk}'
    cached_data = cache.get(cache_key)

    if cached_data is None:
        game = get_object_or_404(Game, pk=pk)
        categories = list(game.categories.all())
        cached_data = {'game': game, 'categories': categories}
        cache.set(cache_key, cached_data, 300)  # 5 minutes

    context = cached_data
    return render(request, 'marketplace/game_detail.html', context)



def listing_page_view(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    current_category = get_object_or_404(Category, pk=category_pk)

    game_category_link = get_object_or_404(GameCategory, game=game, category=current_category)

    filter_online_only = request.GET.get('online_only')
    filter_auto_delivery = request.GET.get('auto_delivery_only')
    filter_q = request.GET.get('q', '').strip()
    sort_order = request.GET.get('sort', '')

    from django.db.models import OuterRef, Subquery

    boost_subquery = UserGameBoost.objects.filter(
        user=OuterRef('seller'),
        game=OuterRef('game')
    ).order_by('-boosted_at').values('boosted_at')[:1]

    listings_query = Product.objects.with_full_details().filter(
        game=game,
        category=current_category,
        is_active=True,
        seller__profile__show_listings_on_site=True
    ).annotate(
        seller_avg_rating=Avg('seller__reviews__rating'),
        seller_review_count=Count('seller__reviews__id'),
        boost_time=Subquery(boost_subquery)
    )

    if filter_online_only == 'on':
        ten_seconds_ago = timezone.now() - timedelta(seconds=10)
        listings_query = listings_query.filter(seller__profile__last_seen__gte=ten_seconds_ago)

    if filter_auto_delivery == 'on':
        listings_query = listings_query.filter(automatic_delivery=True)

    if filter_q:
        # Only search if query is meaningful length to reduce DB load
        if len(filter_q.strip()) >= 2:
            listings_query = listings_query.filter(listing_title__icontains=filter_q)

    if sort_order == 'price_asc':
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), 'price')
    elif sort_order == 'price_desc':
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), '-price')
    else:
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), '-created_at')


    category_filters = game_category_link.filters.all().prefetch_related('options')
    active_filters = {}

    for f in category_filters:
        param_name = f'filter_{f.id}'
        param_value = request.GET.get(param_name)
        if param_value and param_value.isdigit():
            listings_query = listings_query.filter(filter_options=int(param_value))
            active_filters[f.id] = int(param_value)

    paginator = Paginator(listings_query, 20)
    page_number = request.GET.get('page')
    listings = paginator.get_page(page_number)

    all_categories = game.categories.all().annotate(
        listing_count=Count('product', filter=Q(
            product__game=game,
            product__is_active=True,
            product__seller__profile__show_listings_on_site=True
        ))
    )

    context = {
        'game': game,
        'current_category': current_category,
        'all_categories': all_categories,
        'listings': listings,
        'filter_values': request.GET,
        'category_filters': category_filters,
        'active_filters': active_filters,
        'game_category_link': game_category_link,
        'sort_order': sort_order,
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string(
            'marketplace/_listings_partial.html',
            {
                'listings': listings,
                'game_category_link': game_category_link
            }
        )
        response = HttpResponse(html)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

    return render(request, 'marketplace/listing_page.html', context)

def load_more_listings(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    current_category = get_object_or_404(Category, pk=category_pk)
    game_category_link = get_object_or_404(GameCategory, game=game, category=current_category)

    filter_online_only = request.GET.get('online_only')
    filter_auto_delivery = request.GET.get('auto_delivery_only')
    filter_q = request.GET.get('q', '').strip()
    sort_order = request.GET.get('sort', '')

    boost_subquery = UserGameBoost.objects.filter(
        user=OuterRef('seller'),
        game=OuterRef('game')
    ).order_by('-boosted_at').values('boosted_at')[:1]

    listings_query = Product.objects.filter(
        game=game,
        category=current_category,
        is_active=True,
        seller__profile__show_listings_on_site=True
    ).select_related('seller__profile', 'game', 'category').prefetch_related(
        'filter_options__filter',
        'images'
    ).annotate(
        seller_avg_rating=Avg('seller__reviews__rating'),
        seller_review_count=Count('seller__reviews__id'),
        boost_time=Subquery(boost_subquery)
    )

    if filter_online_only == 'on':
        ten_seconds_ago = timezone.now() - timedelta(seconds=10)
        listings_query = listings_query.filter(seller__profile__last_seen__gte=ten_seconds_ago)

    if filter_auto_delivery == 'on':
        listings_query = listings_query.filter(automatic_delivery=True)

    if filter_q:
        # Only search if query is meaningful length to reduce DB load
        if len(filter_q.strip()) >= 2:
            listings_query = listings_query.filter(listing_title__icontains=filter_q)

    if sort_order == 'price_asc':
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), 'price')
    elif sort_order == 'price_desc':
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), '-price')
    else:
        listings_query = listings_query.order_by(F('boost_time').desc(nulls_last=True), '-created_at')

    category_filters = game_category_link.filters.all().prefetch_related('options')
    active_filters = {}

    for f in category_filters:
        param_name = f'filter_{f.id}'
        param_value = request.GET.get(param_name)
        if param_value and param_value.isdigit():
            listings_query = listings_query.filter(filter_options=int(param_value))
            active_filters[f.id] = int(param_value)

    paginator = Paginator(listings_query, 20)
    page_number = request.GET.get('page')
    listings = paginator.get_page(page_number)

    html = render_to_string(
        'marketplace/_listings_partial.html',
        {'listings': listings, 'game_category_link': game_category_link}
    )
    return JsonResponse({'html': html, 'has_next': listings.has_next()})

def public_profile_view(request, username):
    profile_user = get_object_or_404(User, username=username)
    p_form = None

    if request.user == profile_user:
        if request.method == 'POST':
            p_form = ProfilePictureForm(request.POST, request.FILES, instance=request.user.profile)
            if p_form.is_valid():
                p_form.save()
                messages.success(request, 'Your profile picture has been updated!')
                return redirect('public_profile', username=username)
        else:
            p_form = ProfilePictureForm(instance=request.user.profile)

    products_qs = Product.objects.filter(
        seller=profile_user, is_active=True, game__isnull=False, category__isnull=False
    ).select_related('game', 'category', 'seller__profile').prefetch_related(
        'filter_options__filter',
        'images'
    ).order_by('game__title', 'category__name')

    # Efficiently fetch GameCategory objects
    game_cat_pks = products_qs.values_list('game_id', 'category_id').distinct()
    game_category_links = GameCategory.objects.filter(
        game_id__in=[pk[0] for pk in game_cat_pks],
        category_id__in=[pk[1] for pk in game_cat_pks]
    ).select_related('primary_filter')

    game_category_map = {
        (gc.game_id, gc.category_id): gc for gc in game_category_links
    }

    # Group listings and attach the GameCategory link
    grouped_listings = []
    for game, game_products_iterator in groupby(products_qs, key=attrgetter('game')):
        for category, cat_products_iterator in groupby(list(game_products_iterator), key=attrgetter('category')):
            products_list = list(cat_products_iterator)
            game_category_link = game_category_map.get((game.id, category.id))
            grouped_listings.append({
                'game': game,
                'category': category,
                'products': products_list,
                'game_category_link': game_category_link
            })

    all_reviews = Review.objects.filter(seller=profile_user).select_related(
        'buyer__profile',
        'order__product__game',
        'order__game_snapshot',
        'order__category_snapshot'
    ).prefetch_related('reply').order_by('-created_at')

    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else:
        reviews_to_display = all_reviews

    paginator = Paginator(reviews_to_display, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = get_cached_review_stats(profile_user)

    # Calculate rating breakdown for the bar chart
    rating_breakdown = all_reviews.values('rating').annotate(count=Count('rating')).order_by('-rating')
    ratings = {item['rating']: item['count'] for item in rating_breakdown}
    total_reviews = review_stats['review_count']
    rating_percentages = {
        star: (ratings.get(star, 0) / total_reviews * 100) if total_reviews > 0 else 0
        for star in range(5, 0, -1)
    }

    other_user = profile_user
    chat_messages = []
    has_more_messages = False
    is_blocked = False

    if request.user.is_authenticated and request.user != other_user:
        # Check if users have blocked each other
        is_blocked = BlockedUser.objects.filter(
            Q(blocker=request.user, blocked=other_user) |
            Q(blocker=other_user, blocked=request.user)
        ).exists()
        if request.user.id < other_user.id:
            p1, p2 = request.user, other_user
        else:
            p1, p2 = other_user, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        message_manager = conversation.messages
        message_count = get_cached_message_count(conversation)
        chat_messages = message_manager.order_by('timestamp')[max(0, message_count - 100):]
        has_more_messages = message_count > 100

    context = {
        'profile_user': profile_user,
        'reviews': page_obj,
        'average_rating': review_stats['average_rating'],
        'review_count': total_reviews,
        'ratings': ratings,
        'rating_percentages': rating_percentages,
        'other_user': other_user,
        'messages': chat_messages,
        'p_form': p_form,
        'grouped_listings': grouped_listings,
        'current_rating_filter': rating_filter,
        'has_more_messages': has_more_messages,
        'is_blocked': is_blocked,
    }
    return render(request, 'marketplace/public_profile.html', context)


@login_required
def my_listings_in_category(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    category = get_object_or_404(Category, pk=category_pk)

    # NEW: Fetch the GameCategory link
    game_category_link = get_object_or_404(GameCategory, game=game, category=category)

    listings = Product.objects.filter(
        seller=request.user,
        game=game,
        category=category,
        is_active=True
    ).prefetch_related('filter_options__filter').order_by('-created_at') # MODIFIED: added prefetch

    user_has_listings_in_game = Product.objects.filter(seller=request.user, game=game, is_active=True).exists()

    context = {
        'game': game,
        'category': category,
        'listings': listings,
        'user_has_listings_in_game': user_has_listings_in_game,
        'game_category_link': game_category_link, # NEW: Add to context
    }
    return render(request, 'marketplace/my_listings.html', context)


def flat_page_view(request, slug):
    page = get_object_or_404(FlatPage, slug=slug)
    return render(request, 'marketplace/flat_page.html', {'page': page})

def privacy_policy_view(request):
    return render(request, 'marketplace/privacy_policy.html')

def cookie_policy_view(request):
    return render(request, 'marketplace/cookie_policy.html')

def terms_of_service_view(request):
    return render(request, 'marketplace/terms_of_service.html')

def rules_view(request):
    return render(request, 'marketplace/rules.html')

@csrf_exempt
def facebook_data_deletion(request):
    """
    Facebook data deletion callback endpoint for app review compliance.
    """
    if request.method == 'POST':
        # For production, you would handle actual data deletion here
        # For now, just acknowledge the request
        return JsonResponse({
            'url': f'https://gamesbazaarpk.com/accounts/facebook/data-deletion/',
            'confirmation_code': 'deletion_requested'
        })
    elif request.method == 'GET':
        # Show styled deletion information page
        return render(request, 'marketplace/data_deletion.html')
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def select_game_for_listing(request):
    games = Game.objects.all().order_by('title')
    return render(request, 'marketplace/select_game.html', {'games': games})

@login_required
def create_product(request, game_pk, category_pk):
    game = get_object_or_404(Game, pk=game_pk)
    category = get_object_or_404(Category, pk=category_pk)
    game_category_link = get_object_or_404(GameCategory, game=game, category=category)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, game_category_link=game_category_link)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user
            product.game = game
            product.category = category
            product.save()

            for f in request.FILES.getlist('images'):
                try:
                    validate_uploaded_file(f, max_size_mb=5)
                    ProductImage.objects.create(product=product, image=f)
                except ValidationError as e:
                    messages.error(request, f"Image upload error: {str(e)}")
                    return redirect('product_form', game_pk=game_pk, category_pk=category_pk)

            filter_options_to_add = []
            for name, value in form.cleaned_data.items():
                if name.startswith('filter_'):
                    filter_options_to_add.append(value)

            if filter_options_to_add:
                product.filter_options.set(filter_options_to_add)

            return redirect('my_listings_in_category', game_pk=game.pk, category_pk=category.pk)
    else:
        form = ProductForm(game_category_link=game_category_link)

    context = {
        'form': form,
        'game': game,
        'category': category,
    }
    return render(request, 'marketplace/product_form.html', context)

@login_required
def edit_product(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    game_category_link = get_object_or_404(GameCategory, game=product.game, category=product.category)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, game_category_link=game_category_link)
        if form.is_valid():
            updated_product = form.save()

            # Handle deleting specific existing images
            images_to_delete = request.POST.getlist('delete_images')
            if images_to_delete:
                ProductImage.objects.filter(
                    product=updated_product,
                    id__in=images_to_delete
                ).delete()
            
            # Add new images if uploaded
            if 'images' in request.FILES and request.FILES.getlist('images'):
                for f in request.FILES.getlist('images'):
                    try:
                        validate_uploaded_file(f, max_size_mb=5)
                        ProductImage.objects.create(product=updated_product, image=f)
                    except ValidationError as e:
                        messages.error(request, f"Image upload error: {str(e)}")
                        return redirect('edit_product', pk=pk)

            filter_options_to_add = []
            for name, value in form.cleaned_data.items():
                if name.startswith('filter_'):
                    filter_options_to_add.append(value)

            if filter_options_to_add:
                updated_product.filter_options.set(filter_options_to_add)

            messages.success(request, 'Your listing has been updated.')
            return redirect('product_detail', pk=updated_product.pk)
    else:
        form = ProductForm(instance=product, game_category_link=game_category_link)

    context = {
        'form': form,
        'game': product.game,
        'category': product.category,
        'product': product,
        'is_editing': True
    }
    return render(request, 'marketplace/product_form.html', context)

@login_required
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    if request.method == 'POST':
        game_pk = product.game.pk
        category_pk = product.category.pk
        product.delete()
        messages.success(request, 'Your listing has been successfully deleted.')
        return redirect('my_listings_in_category', game_pk=game_pk, category_pk=category_pk)
    # Redirect if accessed via GET, or for some other reason
    return redirect('product_detail', pk=pk)

@login_required
def create_order(request, pk):
    """Redirect to checkout page with payment method and quantity"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('product_detail', pk=pk)

    product = get_object_or_404(Product, pk=pk, is_active=True)

    if product.seller == request.user:
        messages.error(request, 'You cannot purchase your own listing.')
        return redirect('product_detail', pk=pk)

    # Check if users have blocked each other
    if BlockedUser.objects.filter(
        Q(blocker=request.user, blocked=product.seller) | 
        Q(blocker=product.seller, blocked=request.user)
    ).exists():
        messages.error(request, 'You cannot purchase from this seller.')
        return redirect('product_detail', pk=pk)

    try:
        quantity = validate_quantity(request.POST.get('quantity', '1'), max_quantity=100)
    except ValidationError as e:
        messages.error(request, f"Invalid quantity: {str(e)}")
        return redirect('product_detail', pk=pk)

    payment_method = request.POST.get('payment_method', '')
    
    # Validate payment method - only allow specific values
    valid_payment_methods = ['Jazzcash', 'Easypaisa', 'balance', '']
    if payment_method not in valid_payment_methods:
        messages.error(request, 'Invalid payment method selected.')
        return redirect('product_detail', pk=pk)
    
    # Check for Easypaisa and show message, then continue with JazzCash
    if payment_method == 'Easypaisa':
        # Store info message for checkout page
        request.session['easypaisa_message'] = 'Easypaisa payment is coming soon! Continuing with JazzCash for now.'
        payment_method = 'Jazzcash'
    
    # Calculate pricing to check if payment method is required
    total_price = product.price * quantity
    user_balance = request.user.profile.available_balance
    
    from decimal import Decimal
    user_balance = Decimal(str(user_balance))
    total_price = Decimal(str(total_price))
    
    # If total price exceeds balance and no payment method selected, show error
    if total_price > user_balance and not payment_method:
        messages.error(request, 'Please select a payment method for the amount that exceeds your balance.')
        return redirect('product_detail', pk=pk)
    
    # If user has sufficient balance and no payment method, set to balance
    if total_price <= user_balance and not payment_method:
        payment_method = 'balance'
    
    # Store data in session and redirect to checkout
    request.session['checkout_data'] = {
        'product_id': product.id,
        'quantity': quantity,
        'payment_method': payment_method,
        'total_price': float(total_price)
    }
    
    return redirect('checkout', pk=product.pk)

@login_required
def order_detail(request, order_id):
    # Secure IDOR fix: Check authorization BEFORE fetching order details
    try:
        # Add # prefix if not present (for clean URL support)
        if not order_id.startswith('#'):
            order_id = f'#{order_id}'
        order = Order.objects.with_full_details().get(order_id=order_id)
        # Immediate authorization check
        if request.user != order.buyer and request.user != order.seller:
            return HttpResponseForbidden("You don't have permission to view this order.")
    except Order.DoesNotExist:
        raise Http404("Order not found.")

    ordered_filter_options = order.filter_options_snapshot.select_related('filter').order_by('filter__order')

    other_user = order.seller if request.user == order.buyer else order.buyer
    p1, p2 = sorted((request.user.id, other_user.id))
    conversation, created = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)

    message_manager = conversation.messages
    message_count = message_manager.count()
    messages = message_manager.order_by('timestamp')[max(0, message_count - 100):]
    has_more_messages = message_count > 100

    existing_review = Review.objects.filter(order=order).first()
    review_form = ReviewForm()

    if request.method == 'POST' and 'rating' in request.POST:
        if request.user != order.buyer: return JsonResponse({'status': 'error', 'message': 'Only the buyer can leave a review.'}, status=403)

        if order.status not in ['PROCESSING', 'COMPLETED']:
            return JsonResponse({'status': 'error', 'message': 'Reviews can only be left for orders that are processing or completed.'}, status=403)

        if existing_review: return JsonResponse({'status': 'error', 'message': 'A review for this order already exists.'}, status=403)

        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False); review.order = order; review.buyer = request.user; review.seller = order.seller
            review.save()
            review_html = render_to_string('marketplace/partials/_my_review_display.html', {'review': review, 'user': request.user})
            return JsonResponse({'status': 'success', 'review_html': review_html})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid form data.', 'errors': form.errors}, status=400)

    all_reviews = Review.objects.filter(seller=order.seller).select_related('buyer__profile', 'order__product__game', 'order__product__category').prefetch_related('reply').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else:
        reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = get_cached_review_stats(order.seller)
    
    # Find the specific delivery message for this order by looking at message sequence
    delivery_message = None
    if order.product and order.product.automatic_delivery:
        # Get all auto-reply delivery messages (not post-purchase messages) in chronological order
        all_delivery_messages = conversation.messages.filter(
            sender=order.seller,
            is_auto_reply=True,
            is_system_message=False,
        ).exclude(
            content=order.product.post_purchase_message if order.product.post_purchase_message else ''
        ).order_by('timestamp')
        
        # Get all orders between these users for this product, ordered by creation time
        all_orders = Order.objects.filter(
            buyer=order.buyer,
            seller=order.seller,
            product=order.product
        ).order_by('created_at')
        
        # Find the position of current order in the sequence
        order_list = list(all_orders)
        try:
            order_position = order_list.index(order)
            # Get the delivery message at the same position
            delivery_messages_list = list(all_delivery_messages)
            if order_position < len(delivery_messages_list):
                delivery_message = delivery_messages_list[order_position]
        except (ValueError, IndexError):
            pass
            
    elif not order.product:
        # For deleted products, try to find by timestamp with tight window
        delivery_message = conversation.messages.filter(
            sender=order.seller,
            is_auto_reply=True,
            is_system_message=False,
            timestamp__gte=order.created_at - timezone.timedelta(seconds=10),
            timestamp__lte=order.created_at + timezone.timedelta(seconds=10)
        ).exclude(
            content__icontains='thank you'
        ).exclude(
            content__icontains='purchase'
        ).first()
    
    # Check if users have blocked each other
    is_blocked = (
        BlockedUser.objects.filter(blocker=request.user, blocked=other_user).exists() or
        BlockedUser.objects.filter(blocker=other_user, blocked=request.user).exists()
    )
    
    context = { 'order': order, 'other_user': other_user, 'messages': messages, 'active_conversation': conversation, 'review_form': review_form, 'existing_review': existing_review, 'reviews': page_obj, 'average_rating': review_stats['average_rating'], 'review_count': review_stats['review_count'], 'current_rating_filter': rating_filter, 'profile_user': order.seller, 'ordered_filter_options': ordered_filter_options, 'has_more_messages': has_more_messages, 'delivery_message': delivery_message, 'is_blocked': is_blocked, }
    return render(request, 'marketplace/order_detail.html', context)

@login_required
def complete_order(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status == 'PROCESSING':
        order.status = 'COMPLETED'
        order.commission_paid = order.calculate_commission()
        order.save()
    return redirect('order_detail', order_id=order.clean_order_id)

@login_required
@transaction.atomic
def refund_order(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()

    order = get_object_or_404(Order, pk=pk)

    # Security check: only the seller can refund
    if request.user != order.seller:
        return HttpResponseForbidden()

    # Business logic check: only processing or completed orders can be refunded
    if order.status not in ['PROCESSING', 'COMPLETED']:
        messages.error(request, 'This order cannot be refunded.')
        return redirect('order_detail', order_id=order.clean_order_id)

    # Find and delete the review if one exists
    Review.objects.filter(order=order).delete()

    # Update the order status
    order.status = 'REFUNDED'
    order.save()

    messages.success(request, f'Order {order.order_id} has been successfully refunded to the buyer.')
    return redirect('order_detail', order_id=order.clean_order_id)

@login_required
def edit_review(request, pk):
    review = get_object_or_404(Review, pk=pk, buyer=request.user)
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            review_html = render_to_string('marketplace/partials/_my_review_display.html', {'review': review})
            return JsonResponse({'status': 'success', 'review_html': review_html})
        else:
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    data = {'rating': review.rating, 'comment': review.comment}
    return JsonResponse(data)


@login_required
def delete_review(request, pk):
    review = get_object_or_404(Review, pk=pk, buyer=request.user)
    if request.method == 'POST':
        order_pk = review.order.pk
        review.delete()
        review_form = ReviewForm()
        # Render the form part specifically for replacement
        form_html = render_to_string('marketplace/partials/_review_form.html', {'review_form': review_form, 'order': {'pk': order_pk}}, request=request)
        return JsonResponse({'status': 'success', 'form_html': form_html})
    return HttpResponseForbidden()

@login_required
def create_review_reply(request, review_pk):
    """Allow sellers to reply to reviews on their products"""
    review = get_object_or_404(Review, pk=review_pk, seller=request.user)

    # Check if reply already exists
    if hasattr(review, 'reply'):
        return JsonResponse({'status': 'error', 'message': 'You have already replied to this review.'}, status=400)

    if request.method == 'POST':
        form = ReviewReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.review = review
            reply.seller = request.user
            reply.save()

            # Render the reply HTML for immediate display
            reply_html = render_to_string('marketplace/partials/_review_reply.html', {
                'reply': reply,
                'request': request
            })

            return JsonResponse({
                'status': 'success',
                'reply_html': reply_html,
                'message': 'Your reply has been posted successfully.'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Please check your reply and try again.',
                'errors': form.errors
            }, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def edit_review_reply(request, reply_pk):
    """Allow sellers to edit their review replies"""
    reply = get_object_or_404(ReviewReply, pk=reply_pk, seller=request.user)

    if request.method == 'POST':
        form = ReviewReplyForm(request.POST, instance=reply)
        if form.is_valid():
            updated_reply = form.save()

            # Render the updated reply HTML
            reply_html = render_to_string('marketplace/partials/_review_reply.html', {
                'reply': updated_reply,
                'request': request
            })

            return JsonResponse({
                'status': 'success',
                'reply_html': reply_html,
                'message': 'Your reply has been updated successfully.'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Please check your reply and try again.',
                'errors': form.errors
            }, status=400)

    # Return current reply data for editing
    return JsonResponse({
        'status': 'success',
        'reply_text': reply.reply_text
    })

@login_required
def delete_review_reply(request, reply_pk):
    """Allow sellers to delete their review replies"""
    reply = get_object_or_404(ReviewReply, pk=reply_pk, seller=request.user)

    if request.method == 'POST':
        reply.delete()
        return JsonResponse({
            'status': 'success',
            'message': 'Your reply has been deleted successfully.'
        })

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def _filter_orders(request, queryset):
    """Helper function to filter orders based on request parameters."""
    order_number_query = request.GET.get('order_number', '').strip()
    status_query = request.GET.get('status', '').strip()
    
    # Differentiate between buyer and seller name based on the view
    seller_name_query = request.GET.get('seller_name', '').strip()
    buyer_name_query = request.GET.get('buyer_name', '').strip()

    if order_number_query and order_number_query.isdigit():
        queryset = queryset.filter(id=order_number_query)
    if seller_name_query:
        queryset = queryset.filter(seller__username__icontains=seller_name_query)
    if buyer_name_query:
        queryset = queryset.filter(buyer__username__icontains=buyer_name_query)
    if status_query:
        queryset = queryset.filter(status=status_query)
        
    return queryset

@login_required
def my_purchases(request):
    orders_list = Order.objects.with_full_details().filter(buyer=request.user).recent_first()
    orders_list = _filter_orders(request, orders_list)
    
    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = { 
        'orders': page_obj, 
        'statuses_for_filter': Order.STATUS_CHOICES, 
        'filter_values': request.GET, 
    }
    return render(request, 'marketplace/my_purchases.html', context)

def load_more_purchases(request):
    orders_list = Order.objects.filter(buyer=request.user).select_related(
        'product__game', 'product__category', 'seller__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    orders_list = _filter_orders(request, orders_list)
    
    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    html_list = [render_to_string('marketplace/partials/purchase_row.html', {'order': order}) for order in page_obj]
    html = "".join(html_list)
    
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def my_sales(request):
    orders_list = Order.objects.with_full_details().filter(seller=request.user).recent_first()
    orders_list = _filter_orders(request, orders_list)

    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = { 
        'orders': page_obj, 
        'statuses_for_filter': Order.STATUS_CHOICES, 
        'filter_values': request.GET, 
    }
    return render(request, 'marketplace/my_sales.html', context)

def load_more_sales(request):
    orders_list = Order.objects.filter(seller=request.user).select_related(
        'product__game', 'product__category', 'buyer__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    orders_list = _filter_orders(request, orders_list)

    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    html_list = [render_to_string('marketplace/partials/sale_row.html', {'order': order}) for order in page_obj]
    html = "".join(html_list)
    
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})


@login_required
def messages_view(request, username=None):
    if username and username.lower() == request.user.username.lower():
        return redirect('my_messages')

    conversations = Conversation.objects.filter(Q(participant1=request.user) | Q(participant2=request.user)).annotate(message_count=Count('messages')).filter(message_count__gt=0).exclude(participant1=F('participant2')).order_by('-updated_at')
    unread_conversation_ids = set(Message.objects.filter(conversation__in=conversations, is_read=False).exclude(sender=request.user).values_list('conversation_id', flat=True))
    active_conversation, messages, other_user = None, [], None
    if username:
        try:
            other_user = User.objects.get(username__iexact=username)
            active_conversation = Conversation.objects.filter((Q(participant1=request.user) & Q(participant2=other_user)) | (Q(participant1=other_user) & Q(participant2=request.user))).first()
            if active_conversation:
                # MODIFIED: Fetch the last 100 messages in a template-safe way.
                message_manager = active_conversation.messages
                message_count = get_cached_message_count(active_conversation)
                messages = message_manager.order_by('timestamp')[max(0, message_count - 100):]
                has_more_messages = message_count > 100
                active_conversation.messages.exclude(sender=request.user).update(is_read=True)
                if active_conversation.id in unread_conversation_ids: unread_conversation_ids.remove(active_conversation.id)
        except User.DoesNotExist: pass
    context = { 'conversations': conversations, 'active_conversation': active_conversation, 'other_user_profile': other_user, 'messages': messages, 'unread_conversation_ids': unread_conversation_ids, 'has_more_messages': has_more_messages if 'has_more_messages' in locals() else False, }
    return render(request, 'marketplace/my_messages.html', context)


@login_required
def funds_view(request):
    # Get total balance, available balance and held balance
    total_balance = request.user.profile.balance
    available_balance = request.user.profile.available_balance
    held_balance = request.user.profile.held_balance
    held_funds_summary = request.user.profile.get_held_funds_summary()
    
    # Only get detailed breakdown if specifically requested and limit to recent ones
    show_details = request.GET.get('show_held_details') == '1'
    held_funds_details = None
    if show_details:
        held_funds_details = request.user.profile.get_held_funds_details()[:20]  # Limit to 20 most recent
    
    transactions_list = Transaction.objects.filter(user=request.user)
    filter_by = request.GET.get('filter')
    if filter_by == 'deposits': transactions_list = transactions_list.filter(transaction_type='DEPOSIT')
    elif filter_by == 'withdrawals': transactions_list = transactions_list.filter(transaction_type='WITHDRAWAL')
    elif filter_by == 'orders': transactions_list = transactions_list.filter(transaction_type__in=['ORDER_PURCHASE', 'ORDER_SALE'])
    elif filter_by == 'miscellaneous': transactions_list = transactions_list.filter(transaction_type='MISCELLANEOUS')
    paginator = Paginator(transactions_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = WithdrawalRequestForm(request.POST, user=request.user, balance=available_balance)
        if form.is_valid():
            withdrawal_request = form.save(commit=False)
            withdrawal_request.user = request.user
            withdrawal_request.save()
            messages.success(request, 
                f'Your withdrawal request of Rs{withdrawal_request.amount:.2f} via {withdrawal_request.get_payment_method_display()} has been received! '
                f'It will be processed within 24-48 hours. You will receive the funds in your {withdrawal_request.account_title} account.'
            )
            return redirect('funds')
    else:
        form = WithdrawalRequestForm(user=request.user, balance=available_balance)
    context = {
        'balance': total_balance,
        'available_balance': available_balance,
        'held_balance': held_balance,
        'held_funds_summary': held_funds_summary,
        'held_funds_details': held_funds_details,
        'show_details': show_details,
        'transactions': page_obj,
        'withdrawal_form': form,
        'current_filter': filter_by,
    }
    return render(request, 'marketplace/funds.html', context)

def load_more_transactions(request):
    transactions_list = Transaction.objects.filter(user=request.user)
    filter_by = request.GET.get('filter')
    if filter_by == 'deposits': transactions_list = transactions_list.filter(transaction_type='DEPOSIT')
    elif filter_by == 'withdrawals': transactions_list = transactions_list.filter(transaction_type='WITHDRAWAL')
    elif filter_by == 'orders': transactions_list = transactions_list.filter(transaction_type__in=['ORDER_PURCHASE', 'ORDER_SALE'])
    elif filter_by == 'miscellaneous': transactions_list = transactions_list.filter(transaction_type='MISCELLANEOUS')
    paginator = Paginator(transactions_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    html_list = [render_to_string('marketplace/partials/transaction_row.html', {'tx': tx}) for tx in page_obj]
    html = "".join(html_list)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def settings_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your settings have been updated.')
            return redirect('settings')
    else: form = ProfileUpdateForm(instance=profile)
    password_form = auth_forms.PasswordChangeForm(request.user)
    
    # Get connected social accounts
    from allauth.socialaccount.models import SocialAccount
    social_accounts = SocialAccount.objects.filter(user=request.user)
    
    context = { 
        'form': form, 
        'password_form': password_form,
        'social_accounts': social_accounts,
    }
    return render(request, 'marketplace/settings.html', context)

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
        # Check if reporting a user
        report_user = request.GET.get('report_user')
        initial_data = {}
        if report_user:
            initial_data = {
                'subject': f'Report User: {report_user}',
                'message': f'I would like to report user "{report_user}" for the following reason:\n\n[Please describe the issue in detail]',
                'issue_category': 'GENERAL'
            }
        form = SupportTicketForm(initial=initial_data)
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    context = {'form': form, 'tickets': tickets}
    return render(request, 'marketplace/support_center.html', context)

def load_more_reviews(request, username):
    profile_user = get_object_or_404(User, username=username)
    all_reviews = Review.objects.filter(seller=profile_user).select_related('buyer__profile', 'order__product__game', 'order__product__category').prefetch_related('reply').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5: reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else: reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    template_to_render = 'marketplace/partials/_profile_review_item.html' if request.user.is_authenticated and request.user == profile_user else 'marketplace/partials/_public_review_item.html'
    html_list = [render_to_string(template_to_render, {'review': review}) for review in page_obj]
    html = "".join(html_list)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def send_chat_message(request, username):
    if request.method == 'POST':
        # Rate limiting: 30 messages per minute
        if not check_rate_limit(request, 'send_message', limit=30, period=60):
            return JsonResponse({'status': 'error', 'message': 'Too many messages. Please slow down.'}, status=429)
        
        other_user = get_object_or_404(User, username=username)
        
        # Check if users have blocked each other
        if BlockedUser.objects.filter(
            Q(blocker=request.user, blocked=other_user) | 
            Q(blocker=other_user, blocked=request.user)
        ).exists():
            return JsonResponse({'status': 'error', 'message': 'You cannot send messages to this user.'}, status=403)
        
        message_content = sanitize_user_input(request.POST.get('message', ''), max_length=2000)
        image_file = request.FILES.get('image')
        
        # Validate image file if provided
        if image_file:
            try:
                validate_uploaded_file(image_file, max_size_mb=3)
            except ValidationError as e:
                return JsonResponse({'status': 'error', 'message': f'Image upload error: {str(e)}'}, status=400)
        
        if not message_content and not image_file: 
            return JsonResponse({'status': 'error', 'message': 'Cannot send an empty message.'}, status=400)
        
        if request.user.id < other_user.id: p1, p2 = request.user, other_user
        else: p1, p2 = other_user, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        Message.objects.create(conversation=conversation, sender=request.user, content=message_content, image=image_file)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def load_older_messages(request, username):
    """Load older messages for infinite scroll in chat"""
    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    other_user = get_object_or_404(User, username=username)

    # Get the conversation
    if request.user.id < other_user.id:
        p1, p2 = request.user, other_user
    else:
        p1, p2 = other_user, request.user

    try:
        conversation = Conversation.objects.get(participant1=p1, participant2=p2)
    except Conversation.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Conversation not found.'}, status=404)

    # Get query parameters
    try:
        offset = int(request.GET.get('offset', '0'))
        limit = int(request.GET.get('limit', '50'))
    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid query parameters.'}, status=400)

    # Fetch messages in reverse chronological order using the offset
    messages_qs = conversation.messages.select_related('sender__profile').order_by('-timestamp')

    # Slice the queryset to get the next batch of older messages
    older_messages = list(messages_qs[offset:offset + limit])

    # Render messages HTML
    messages_html = []
    for message in older_messages:
        message_html = render_to_string('marketplace/partials/message.html', {
            'message': message,
            'request': request
        })
        messages_html.append(message_html)

    # Check if there are more messages to load after this batch
    total_messages = get_cached_message_count(conversation) # Use cached count
    has_more = (offset + len(older_messages)) < total_messages
    new_offset = offset + len(older_messages)

    return JsonResponse({
        'status': 'success',
        'messages_html': messages_html,
        'has_more': has_more,
        'new_offset': new_offset,
    })

@login_required
def ajax_update_profile_picture(request):
    if request.method == 'POST':
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return JsonResponse({'status': 'success', 'image_url': request.user.profile.image_url})
        else:
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def ajax_update_listing_visibility(request):
    if request.method == 'POST':
        show_listings = request.POST.get('show_listings_on_site') == 'True'
        profile = request.user.profile
        if profile.show_listings_on_site != show_listings:
            profile.show_listings_on_site = show_listings
            profile.save(update_fields=['show_listings_on_site'])
        return JsonResponse({'status': 'success', 'message': 'Setting updated successfully.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@login_required
def boost_listings(request, game_pk):
    game = get_object_or_404(Game, pk=game_pk)
    last_boost = UserGameBoost.objects.filter(user=request.user, game=game).first()

    cooldown = timedelta(hours=4)

    if last_boost and timezone.now() < last_boost.boosted_at + cooldown:
        next_boost_time = last_boost.boosted_at + cooldown
        remaining_time = next_boost_time - timezone.now()

        hours, remainder = divmod(remaining_time.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        error_message = f"Please wait {hours}h {minutes}m until you can boost again."
        messages.error(request, error_message)
    else:
        UserGameBoost.objects.update_or_create(
            user=request.user,
            game=game,
            defaults={'boosted_at': timezone.now()}
        )
        success_message = f"Your listings for {game.title} have been boosted!"
        messages.success(request, success_message)

    return redirect(request.META.get('HTTP_REFERER', reverse_lazy('game_detail', kwargs={'pk': game_pk})))

@login_required
@transaction.atomic
def jazzcash_payment(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    # Get data from session (either from checkout or direct POST)
    checkout_data = request.session.get('checkout_data')
    
    if request.method == 'POST':
        # Calculate payment details from POST data
        try:
            quantity = validate_quantity(request.POST.get('quantity', '1'), max_quantity=100)
        except ValidationError as e:
            messages.error(request, f"Invalid quantity: {str(e)}")
            return redirect('product_detail', pk=product.pk)
    elif checkout_data and checkout_data.get('product_id') == product.id:
        # Get data from checkout session
        quantity = checkout_data.get('quantity', 1)
    else:
        return redirect('product_detail', pk=product.pk)

    total_price = product.price * quantity
    user_balance = request.user.profile.available_balance
    amount_from_balance = min(user_balance, total_price)
    payment_amount = total_price - amount_from_balance
    
    # Store order details in session for later creation
    request.session['pending_order'] = {
        'product_id': product.id,
        'quantity': quantity,
        'total_price': float(total_price),
        'amount_from_balance': float(amount_from_balance),
        'payment_amount': float(payment_amount)
    }
    
    # Generate unique reference ID for this payment attempt
    import time
    payment_ref = f"{request.user.id}_{product.id}_{int(time.time())}"
    
    jazzcash_params = get_jazzcash_payment_params(payment_amount, payment_ref)

    context = {
        'jazzcash_params': jazzcash_params,
        'JAZZCASH_TRANSACTION_URL': settings.JAZZCASH_TRANSACTION_URL,
        'product': product,
        'payment_amount': payment_amount,
        'total_price': total_price,
        'amount_from_balance': amount_from_balance
    }
    return render(request, 'marketplace/jazzcash_payment_form.html', context)

@csrf_exempt  # Only exempt for external JazzCash callbacks, with additional security
@transaction.atomic
def jazzcash_callback(request):
    """
    Secure JazzCash payment callback handler.
    Uses signature verification and additional security checks instead of CSRF for external callbacks.
    """
    # Additional security validation for callback
    if request.method != 'POST':
        return HttpResponseBadRequest("Only POST requests allowed")
    
    # Validate request size to prevent DoS
    if len(request.body) > 10000:  # 10KB limit
        return HttpResponseBadRequest("Request too large")
    
    # Basic rate limiting check (simplified)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if 'bot' in user_agent.lower() or 'crawler' in user_agent.lower():
        return HttpResponseForbidden("Bots not allowed")
    
    response_data = request.POST.dict()
    
    # Extract transaction reference for replay attack prevention
    transaction_ref = response_data.get('pp_TxnRefNo', '')
    if not transaction_ref:
        return HttpResponseBadRequest("Missing transaction reference")
    
    # Check for replay attacks - ensure this callback hasn't been processed before
    from .models import ProcessedPaymentCallback
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not client_ip:
        client_ip = request.META.get('REMOTE_ADDR', '')
    
    if ProcessedPaymentCallback.objects.filter(transaction_ref=transaction_ref).exists():
        # This is a replay attack or duplicate callback
        return HttpResponseBadRequest("Transaction already processed")
    
    # Validate JazzCash signature - this is our primary security check
    if verify_jazzcash_response(response_data):
        pp_ResponseCode = response_data.get('pp_ResponseCode')
        payment_ref = response_data.get('pp_BillReference')
        
        # Record this callback as processed to prevent replay attacks
        ProcessedPaymentCallback.objects.create(
            transaction_ref=transaction_ref,
            response_code=pp_ResponseCode,
            client_ip=client_ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]  # Truncate user agent
        )

        if pp_ResponseCode == '000':
            # Payment successful - create order now
            pending_order_data = request.session.get('pending_order')
            
            if not pending_order_data:
                messages.error(request, "Order session expired. Please try again.")
                return redirect('payment_failed')
            
            try:
                from decimal import Decimal
                product = Product.objects.select_for_update().get(id=pending_order_data['product_id'])
                quantity = pending_order_data['quantity']
                total_price = Decimal(str(pending_order_data['total_price']))
                amount_from_balance = Decimal(str(pending_order_data['amount_from_balance']))
                payment_amount = Decimal(str(pending_order_data['payment_amount']))
                
                # Check stock availability again before creating order
                item_to_deliver = None
                if product.automatic_delivery:
                    stock_items = [item for item in product.stock_details.splitlines() if item.strip()]
                    if len(stock_items) < quantity:
                        messages.error(request, f"Sorry, stock became unavailable during payment. Only {len(stock_items)} left.")
                        return redirect('payment_failed')

                    items_to_deliver_list = stock_items[:quantity]
                    product.stock_details = "\n".join(stock_items[quantity:])
                    item_to_deliver = "\n".join(items_to_deliver_list)

                    if not product.stock_details.strip():
                        product.is_active = False
                    product.save()
                else:
                    if product.stock is not None:
                        if product.stock >= quantity:
                            product.stock -= quantity
                            if product.stock == 0:
                                product.is_active = False
                            product.save()
                        else:
                            messages.error(request, "Sorry, stock became unavailable during payment.")
                            return redirect('payment_failed')
                
                # Create order with PROCESSING status
                order = Order.objects.create(
                    buyer=request.user,
                    seller=product.seller,
                    product=product,
                    total_price=total_price,
                    status='PROCESSING',
                    amount_paid_from_balance=amount_from_balance,
                    amount_paid_via_payment_method=payment_amount,
                    # Snapshot fields
                    listing_title_snapshot=product.listing_title,
                    description_snapshot=product.description,
                    game_snapshot=product.game,
                    category_snapshot=product.category
                )
                order.filter_options_snapshot.set(product.filter_options.all())
                
                # Handle automatic delivery and messages
                p1, p2 = sorted((order.buyer.id, order.seller.id))
                conversation, created = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)

                if product.automatic_delivery and item_to_deliver:
                    Message.objects.create(
                        conversation=conversation,
                        sender=product.seller,
                        content=item_to_deliver,
                        is_system_message=False,
                        is_auto_reply=True
                    )

                if product.post_purchase_message:
                    Message.objects.create(
                        conversation=conversation,
                        sender=product.seller,
                        content=product.post_purchase_message,
                        is_system_message=False,
                        is_auto_reply=True
                    )
                
                # Clear session data
                del request.session['pending_order']
                
                messages.success(request, "Payment successful!")
                return redirect('order_confirmation', order_id=order.order_id)
                
            except Exception as e:
                messages.error(request, "Error creating order. Please contact support.")
                return redirect('payment_failed')
        else:
            # Payment failed
            error_message = response_data.get('pp_ResponseMessage', 'An unknown error occurred.')
            messages.error(request, f"Payment failed: {error_message}")
            
            # Clear session data
            if 'pending_order' in request.session:
                del request.session['pending_order']
                
            return redirect('payment_failed')
    else:
        messages.error(request, "Invalid response from Jazzcash. Payment could not be verified.")
        return redirect('payment_failed')

@login_required
def payment_failed_view(request):
    # You can pass more context here if needed, like an error message
    return render(request, 'marketplace/payment_failed.html')

@login_required
def order_confirmation_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, buyer=request.user)
    return render(request, 'marketplace/order_confirmation.html', {'order': order})

@login_required
def report_dispute(request, conversation_id):
    """Allow users to report a conversation as disputed"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        # Secure IDOR fix: Check user is participant in the query itself
        from django.db.models import Q
        conversation = Conversation.objects.filter(
            id=conversation_id
        ).filter(
            Q(participant1=request.user) | Q(participant2=request.user) | Q(moderator=request.user)
        ).first()
        
        if not conversation:
            return JsonResponse({'success': False, 'error': 'Conversation not found or access denied'})

        if conversation.is_disputed:
            return JsonResponse({'success': False, 'error': 'This conversation is already reported as disputed'})

        # Mark as disputed
        conversation.is_disputed = True
        conversation.save()

        # Send system message
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=f"{request.user.username} has reported this conversation as a dispute. An admin will review the conversation shortly.",
            is_system_message=True
        )

        return JsonResponse({'success': True})

    except Conversation.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Conversation not found'})

@login_required
def checkout_view(request, pk):
    """Display checkout confirmation page with selected payment method"""
    product = get_object_or_404(Product, pk=pk, is_active=True)
    
    if product.seller == request.user:
        messages.error(request, 'You cannot purchase your own listing.')
        return redirect('product_detail', pk=product.pk)
    
    # Check if users have blocked each other
    if BlockedUser.objects.filter(
        Q(blocker=request.user, blocked=product.seller) | 
        Q(blocker=product.seller, blocked=request.user)
    ).exists():
        messages.error(request, 'You cannot purchase from this seller.')
        return redirect('product_detail', pk=product.pk)
    
    # Get data from session
    checkout_data = request.session.get('checkout_data')
    if not checkout_data or checkout_data.get('product_id') != product.id:
        return redirect('product_detail', pk=product.pk)
    
    quantity = checkout_data.get('quantity', 1)
    payment_method = checkout_data.get('payment_method', '')
    
    # Calculate pricing
    total_price = product.price * quantity
    user_balance = request.user.profile.available_balance
    
    from decimal import Decimal
    user_balance = Decimal(str(user_balance))
    total_price = Decimal(str(total_price))
    
    amount_from_balance = min(user_balance, total_price)
    remaining_amount = total_price - amount_from_balance
    can_pay_from_balance = user_balance >= total_price
    
    # Get ordered filter options for display
    ordered_filter_options = product.filter_options.select_related('filter').order_by('filter__order')
    
    # Check for Easypaisa message from session
    easypaisa_message = None
    if 'easypaisa_message' in request.session:
        easypaisa_message = request.session.pop('easypaisa_message')
    
    context = {
        'product': product,
        'quantity': quantity,
        'total_price': total_price,
        'user_balance': user_balance,
        'amount_from_balance': amount_from_balance,
        'remaining_amount': remaining_amount,
        'can_pay_from_balance': can_pay_from_balance,
        'ordered_filter_options': ordered_filter_options,
        'payment_method': payment_method,
        'easypaisa_message': easypaisa_message,
    }
    
    return render(request, 'marketplace/checkout.html', context)

@login_required
@transaction.atomic
def process_checkout(request, pk):
    """Process the checkout form submission"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('product_detail', pk=pk)
    
    # Rate limiting: 10 orders per hour
    if not check_rate_limit(request, 'create_order', limit=10, period=3600):
        messages.error(request, 'Too many order attempts. Please try again later.')
        return redirect('product_detail', pk=pk)
    
    product = get_object_or_404(Product.objects.select_for_update(), pk=pk)
    
    if product.seller == request.user:
        messages.error(request, 'You cannot purchase your own listing.')
        return redirect('product_detail', pk=product.pk)
    
    # Check if users have blocked each other
    if BlockedUser.objects.filter(
        Q(blocker=request.user, blocked=product.seller) | 
        Q(blocker=product.seller, blocked=request.user)
    ).exists():
        messages.error(request, 'You cannot purchase from this seller.')
        return redirect('product_detail', pk=product.pk)
    
    try:
        quantity = validate_quantity(request.POST.get('quantity', '1'), max_quantity=100)
    except ValidationError as e:
        messages.error(request, f"Invalid quantity: {str(e)}")
        return redirect('product_detail', pk=product.pk)
    
    payment_method = request.POST.get('payment_method')
    
    # Validate payment method on checkout processing too
    valid_payment_methods = ['Jazzcash', 'Easypaisa', 'balance']
    if payment_method not in valid_payment_methods:
        messages.error(request, 'Invalid payment method.')
        return redirect('product_detail', pk=pk)
    
    total_price = product.price * quantity
    
    # Get user's current available balance
    user_balance = request.user.profile.available_balance
    
    from decimal import Decimal
    user_balance = Decimal(str(user_balance))
    total_price = Decimal(str(total_price))
    
    # Calculate payment split
    amount_from_balance = min(user_balance, total_price)
    remaining_amount = total_price - amount_from_balance
    
    # If user has sufficient balance, always use balance only (regardless of selected payment method)
    if user_balance >= total_price:
        # Process order immediately using balance only
        return create_order_with_balance(request, product, quantity, total_price)
    
    # If payment method requires external payment (only when balance is insufficient)
    elif payment_method.lower() in ['jazzcash', 'easypaisa']:
        # Store checkout data in session for later use
        request.session['checkout_data'] = {
            'product_id': product.id,
            'quantity': quantity,
            'total_price': float(total_price),
            'payment_method': payment_method
        }
        
        # Redirect to payment gateway
        return redirect('jazzcash_payment', product_id=product.id)
    
    else:
        # Don't add error message for invalid payment methods to prevent it showing on other pages
        return redirect('product_detail', pk=product.pk)

def create_order_with_balance(request, product, quantity, total_price):
    """Helper function to create order using balance only"""
    from decimal import Decimal
    
    # Check stock availability
    order_status = 'PROCESSING'
    item_to_deliver = None
    
    if product.automatic_delivery:
        stock_items = [item for item in product.stock_details.splitlines() if item.strip()]
        if len(stock_items) < quantity:
            messages.error(request, f'Not enough stock available. Only {len(stock_items)} left.')
            return redirect('checkout', pk=product.pk)
        
        items_to_deliver_list = stock_items[:quantity]
        product.stock_details = "\n".join(stock_items[quantity:])
        item_to_deliver = "\n".join(items_to_deliver_list)
        
        if not product.stock_details.strip():
            product.is_active = False
        product.save()
    else:
        # For non-auto-delivery, only check stock if it's specified
        if product.stock is not None:
            if product.stock >= quantity:
                product.stock -= quantity
                if product.stock == 0:
                    product.is_active = False
                product.save()
            else:
                messages.error(request, 'Not enough stock available.')
                return redirect('checkout', pk=product.pk)
    
    # Create order
    order = Order.objects.create(
        buyer=request.user,
        seller=product.seller,
        product=product,
        total_price=total_price,
        status=order_status,
        amount_paid_from_balance=total_price,
        amount_paid_via_payment_method=Decimal('0.00'),
        # Snapshot fields
        listing_title_snapshot=product.listing_title,
        description_snapshot=product.description,
        game_snapshot=product.game,
        category_snapshot=product.category
    )
    order.filter_options_snapshot.set(product.filter_options.all())
    
    # Create conversation and messages
    p1, p2 = sorted((order.buyer.id, order.seller.id))
    conversation, created = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)
    
    if product.automatic_delivery and item_to_deliver:
        Message.objects.create(
            conversation=conversation,
            sender=product.seller,
            content=item_to_deliver,
            is_system_message=False,
            is_auto_reply=True
        )
    
    # Send the post-purchase message if it exists
    if product.post_purchase_message:
        Message.objects.create(
            conversation=conversation,
            sender=product.seller,
            content=product.post_purchase_message,
            is_system_message=False,
            is_auto_reply=True
        )
    
    return redirect('order_detail', order_id=order.clean_order_id)

@login_required
def block_user(request, user_id):
    """Block a user - prevents chat and purchases"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        user_to_block = User.objects.get(id=user_id)
        
        # Can't block yourself
        if user_to_block == request.user:
            return JsonResponse({'success': False, 'error': 'You cannot block yourself'})
        
        # Check if already blocked
        if BlockedUser.objects.filter(blocker=request.user, blocked=user_to_block).exists():
            return JsonResponse({'success': False, 'error': 'User is already blocked'})
        
        # Create block relationship
        BlockedUser.objects.create(blocker=request.user, blocked=user_to_block)
        
        # Get updated status
        i_blocked_them = True
        they_blocked_me = BlockedUser.objects.filter(blocker=user_to_block, blocked=request.user).exists()
        
        return JsonResponse({
            'success': True, 
            'message': f'You have blocked {user_to_block.username}',
            'is_blocked': True,
            'i_blocked_them': i_blocked_them,
            'they_blocked_me': they_blocked_me,
            'mutual_block': i_blocked_them and they_blocked_me
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})

@login_required
def unblock_user(request, user_id):
    """Unblock a user - allows chat and purchases again"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        user_to_unblock = User.objects.get(id=user_id)
        
        # Find and delete block relationship
        blocked_user = BlockedUser.objects.filter(blocker=request.user, blocked=user_to_unblock).first()
        
        if not blocked_user:
            return JsonResponse({'success': False, 'error': 'User is not blocked'})
        
        blocked_user.delete()
        
        # Get updated status
        i_blocked_them = False
        they_blocked_me = BlockedUser.objects.filter(blocker=user_to_unblock, blocked=request.user).exists()
        
        return JsonResponse({
            'success': True, 
            'message': f'You have unblocked {user_to_unblock.username}',
            'is_blocked': False,
            'i_blocked_them': i_blocked_them,
            'they_blocked_me': they_blocked_me,
            'mutual_block': i_blocked_them and they_blocked_me
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})

@login_required
def check_user_blocked_status(request, user_id):
    """Check if a user is blocked"""
    try:
        user_to_check = User.objects.get(id=user_id)
        i_blocked_them = BlockedUser.objects.filter(blocker=request.user, blocked=user_to_check).exists()
        they_blocked_me = BlockedUser.objects.filter(blocker=user_to_check, blocked=request.user).exists()
        
        return JsonResponse({
            'success': True,
            'is_blocked': i_blocked_them,
            'i_blocked_them': i_blocked_them,
            'they_blocked_me': they_blocked_me,
            'mutual_block': i_blocked_them and they_blocked_me,
            'username': user_to_check.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})




def cdn_proxy_view(request, path):
    """
    Proxy CDN requests to Google Cloud Storage
    This makes images appear to come from your domain instead of Google's
    """
    from django.conf import settings
    
    # Construct the Google Storage URL
    storage_url = f"https://storage.googleapis.com/{settings.GS_BUCKET_NAME}/{path}"
    
    try:
        # Fetch the image from Google Storage
        response = requests.get(storage_url, stream=True, timeout=10)
        
        if response.status_code == 200:
            # Return the image with proper headers
            django_response = HttpResponse(
                response.content,
                content_type=response.headers.get('content-type', 'application/octet-stream')
            )
            # Add caching headers
            django_response['Cache-Control'] = 'public, max-age=3600'
            return django_response
        else:
            raise Http404("Image not found")
            
    except requests.RequestException:
        raise Http404("Image not available")
