# marketplace/views.py
import json
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
import hmac
import hashlib
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.contrib.auth import forms as auth_forms
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction
from django.db.models import Sum, Q, Count, Avg, F
from django.db.models.functions import Lower
from django.contrib.auth.models import User
import string
from django.contrib import messages
from collections import defaultdict
from itertools import groupby
from operator import attrgetter
from django.core.paginator import Paginator
from django.template.loader import render_to_string

from .models import (
    Game, Category, Product, Order, Review, FlatPage,
    Conversation, Message, WithdrawalRequest, SupportTicket, SiteConfiguration, Profile, Transaction, GameCategory, UserGameBoost, ProductImage
)
from .forms import (
    ProductForm, ReviewForm, WithdrawalRequestForm, SupportTicketForm,
    ProfilePictureForm, ProfileUpdateForm, CustomUserCreationForm
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

def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('seller__profile', 'game', 'category').prefetch_related('filter_options__filter'), pk=pk)
    seller = product.seller
    messages = []
    active_conversation = None
    if request.user.is_authenticated and request.user != seller:
        if request.user.id < seller.id:
            p1, p2 = request.user, seller
        else:
            p1, p2 = seller, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        active_conversation = conversation
        # MODIFIED: Fetch the last 50 messages in a template-safe way.
        message_manager = conversation.messages
        message_count = message_manager.count()
        messages = message_manager.order_by('timestamp')[max(0, message_count - 50):]
    all_reviews = Review.objects.filter(seller=seller).select_related('buyer__profile', 'order__product__game', 'order__product__category').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else:
        reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = all_reviews.aggregate(average_rating=Avg('rating'), review_count=Count('id'))

    ordered_filter_options = product.filter_options.select_related('filter').order_by('filter__order')

    similar_products = Product.objects.filter(game=product.game).exclude(pk=pk).order_by('?')[:5]
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
    }
    return render(request, 'marketplace/product_detail.html', context)

def game_detail_view(request, pk):
    game = get_object_or_404(Game, pk=pk)
    categories = game.categories.all()
    context = {'game': game, 'categories': categories}
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

    listings_query = Product.objects.filter(
        game=game,
        category=current_category,
        is_active=True,
        seller__profile__show_listings_on_site=True
    ).select_related('seller__profile').prefetch_related('filter_options').annotate(
        seller_avg_rating=Avg('seller__reviews__rating'),
        seller_review_count=Count('seller__reviews__id'),
        boost_time=Subquery(boost_subquery)
    )

    if filter_online_only == 'on':
        thirty_seconds_ago = timezone.now() - timedelta(seconds=30)
        listings_query = listings_query.filter(seller__profile__last_seen__gte=thirty_seconds_ago)

    if filter_auto_delivery == 'on':
        listings_query = listings_query.filter(automatic_delivery=True)

    if filter_q:
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

    paginator = Paginator(listings_query, 200)
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

    listings_query = Product.objects.filter(
        game=game,
        category=current_category,
        is_active=True,
        seller__profile__show_listings_on_site=True
    ).select_related('seller__profile').prefetch_related('filter_options').annotate(
        seller_avg_rating=Avg('seller__reviews__rating'),
        seller_review_count=Count('seller__reviews__id')
    )

    if filter_online_only == 'on':
        thirty_seconds_ago = timezone.now() - timedelta(seconds=30)
        listings_query = listings_query.filter(seller__profile__last_seen__gte=thirty_seconds_ago)

    if filter_auto_delivery == 'on':
        listings_query = listings_query.filter(automatic_delivery=True)

    if filter_q:
        listings_query = listings_query.filter(listing_title__icontains=filter_q)

    if sort_order == 'price_asc':
        listings_query = listings_query.order_by('price')
    elif sort_order == 'price_desc':
        listings_query = listings_query.order_by('-price')

    category_filters = game_category_link.filters.all().prefetch_related('options')
    active_filters = {}

    for f in category_filters:
        param_name = f'filter_{f.id}'
        param_value = request.GET.get(param_name)
        if param_value and param_value.isdigit():
            listings_query = listings_query.filter(filter_options=int(param_value))
            active_filters[f.id] = int(param_value)

    paginator = Paginator(listings_query, 100)
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
    ).select_related('game', 'category').prefetch_related('filter_options__filter').order_by('game__title', 'category__name')

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

    all_reviews = Review.objects.filter(seller=profile_user).select_related('buyer__profile', 'order__product__game', 'order__product__category').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else: reviews_to_display = all_reviews
    
    paginator = Paginator(reviews_to_display, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = all_reviews.aggregate(average_rating=Avg('rating'), review_count=Count('id'))
    
    other_user = profile_user
    chat_messages = []
    if request.user.is_authenticated and request.user != other_user:
        if request.user.id < other_user.id: p1, p2 = request.user, other_user
        else: p1, p2 = other_user, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        message_manager = conversation.messages
        message_count = message_manager.count()
        chat_messages = message_manager.order_by('timestamp')[max(0, message_count - 50):]

    context = {
        'profile_user': profile_user,
        'reviews': page_obj,
        'average_rating': review_stats['average_rating'],
        'review_count': review_stats['review_count'],
        'other_user': other_user,
        'messages': chat_messages,
        'p_form': p_form,
        'grouped_listings': grouped_listings,
        'current_rating_filter': rating_filter,
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
                ProductImage.objects.create(product=product, image=f)

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

            if 'images' in request.FILES and request.FILES.getlist('images'):
                updated_product.images.all().delete()
                for f in request.FILES.getlist('images'):
                    ProductImage.objects.create(product=updated_product, image=f)

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
@transaction.atomic
def start_jazzcash_payment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()

    product = get_object_or_404(Product.objects.select_for_update(), pk=pk)

    if product.seller == request.user:
        return HttpResponseForbidden()

    try:
        quantity = int(request.POST.get('quantity', 1))
        if quantity < 1:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    total_price = product.price * quantity

    order = Order.objects.create(
        buyer=request.user,
        seller=product.seller,
        product=product,
        total_price=total_price,
        status='PENDING_PAYMENT',
        payment_method='Jazzcash',
        listing_title_snapshot=product.listing_title,
        description_snapshot=product.description,
        game_snapshot=product.game,
        category_snapshot=product.category,
    )
    order.filter_options_snapshot.set(product.filter_options.all())

    txn_ref = f"ORDER{order.id}"
    now = timezone.now()
    params = {
        'pp_Version': '1.1',
        'pp_TxnType': 'MWALLET',
        'pp_Language': 'EN',
        'pp_MerchantID': settings.JAZZCASH_MERCHANT_ID,
        'pp_Password': settings.JAZZCASH_PASSWORD,
        'pp_TxnRefNo': txn_ref,
        'pp_Amount': str(int(total_price * 100)),
        'pp_TxnDateTime': now.strftime('%Y%m%d%H%M%S'),
        'pp_TxnExpiryDateTime': (now + timedelta(hours=1)).strftime('%Y%m%d%H%M%S'),
        'pp_ReturnURL': settings.JAZZCASH_RETURN_URL,
        'pp_SecureHash': '',
        'pp_SubMerchantID': '',
        'pp_BillReference': str(order.id),
        'pp_Description': product.listing_title,
    }

    # Calculate secure hash
    sorted_pairs = [(k, params[k]) for k in sorted(params.keys()) if k != 'pp_SecureHash']
    hash_string = '&'.join(str(v) for k, v in sorted_pairs)
    digest = hmac.new(
        settings.JAZZCASH_INTEGRITY_SALT.encode('utf-8'),
        hash_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    params['pp_SecureHash'] = digest

    return render(request, 'marketplace/jazzcash_redirect.html', {
        'gateway_url': settings.JAZZCASH_POST_URL,
        'params': params,
    })

@login_required
@transaction.atomic
def create_order(request, pk):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    product = get_object_or_404(Product.objects.select_for_update(), pk=pk)

    if product.seller == request.user:
        return JsonResponse({'status': 'error', 'message': 'You cannot purchase your own listing.'}, status=403)

    try:
        quantity = int(request.POST.get('quantity', 1))
        if quantity < 1:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    total_price = product.price * quantity
    order_status = 'PROCESSING'
    item_to_deliver = None

    if product.automatic_delivery:
        stock_items = [item for item in product.stock_details.splitlines() if item.strip()]
        if len(stock_items) < quantity:
            return JsonResponse({'status': 'error', 'message': f'Not enough stock available. Only {len(stock_items)} left.'}, status=400)

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
                return JsonResponse({'status': 'error', 'message': 'Not enough stock available.'}, status=400)
        # If product.stock is None, proceed without stock check


    order = Order.objects.create(
        buyer=request.user,
        seller=product.seller,
        product=product,
        total_price=total_price,
        status=order_status,
        # Snapshot fields
        listing_title_snapshot=product.listing_title,
        description_snapshot=product.description,
        game_snapshot=product.game,
        category_snapshot=product.category
    )
    order.filter_options_snapshot.set(product.filter_options.all())


    p1, p2 = sorted((order.buyer.id, order.seller.id))
    conversation, created = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)

    if product.automatic_delivery and item_to_deliver:
        message_content = (
            f"Order #{order.id}: Your automatically delivered item{'s are' if quantity > 1 else ' is'} available below.\n\n"
            f"---\n{item_to_deliver}\n---"
        )
        Message.objects.create(
            conversation=conversation,
            sender=product.seller,
            content=message_content,
            is_system_message=True
        )

    # Send the post-purchase message if it exists
    if product.post_purchase_message:
        Message.objects.create(
            conversation=conversation,
            sender=product.seller,
            content=product.post_purchase_message,
            is_system_message=False # This is a message from the seller, not the system
        )

    order_url = reverse_lazy('order_detail', kwargs={'pk': order.pk})
    return JsonResponse({'status': 'success', 'order_url': order_url})


@transaction.atomic
def jazzcash_return(request):
    data = request.POST if request.method == 'POST' else request.GET
    order_id = data.get('pp_BillReference')
    order = get_object_or_404(Order, pk=order_id, status='PENDING_PAYMENT')

    # verify secure hash
    received_hash = data.get('pp_SecureHash', '')
    params = {k: v for k, v in data.items() if k != 'pp_SecureHash'}
    sorted_pairs = [(k, params[k]) for k in sorted(params.keys())]
    hash_string = '&'.join(str(v) for k, v in sorted_pairs)
    digest = hmac.new(
        settings.JAZZCASH_INTEGRITY_SALT.encode('utf-8'),
        hash_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if digest == received_hash and data.get('pp_ResponseCode') == '000':
        product = order.product
        quantity = 1
        try:
            quantity = int(data.get('quantity', 1))
        except (ValueError, TypeError):
            pass

        item_to_deliver = None
        if product.automatic_delivery:
            stock_items = [item for item in product.stock_details.splitlines() if item.strip()]
            if len(stock_items) >= quantity:
                items_to_deliver_list = stock_items[:quantity]
                product.stock_details = "\n".join(stock_items[quantity:])
                item_to_deliver = "\n".join(items_to_deliver_list)
                if not product.stock_details.strip():
                    product.is_active = False
                product.save()
        else:
            if product.stock is not None and product.stock >= quantity:
                product.stock -= quantity
                if product.stock == 0:
                    product.is_active = False
                product.save()

        order.status = 'PROCESSING'
        order.save()

        p1, p2 = sorted((order.buyer.id, order.seller.id))
        conversation, _ = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)

        if product.automatic_delivery and item_to_deliver:
            message_content = (
                f"Order #{order.id}: Your automatically delivered item{'s are' if quantity > 1 else ' is'} available below.\n\n"
                f"---\n{item_to_deliver}\n---"
            )
            Message.objects.create(
                conversation=conversation,
                sender=product.seller,
                content=message_content,
                is_system_message=True
            )

        if product.post_purchase_message:
            Message.objects.create(
                conversation=conversation,
                sender=product.seller,
                content=product.post_purchase_message,
                is_system_message=False
            )

        return redirect('order_detail', pk=order.pk)
    else:
        order.status = 'CANCELLED'
        order.save()
        messages.error(request, 'Payment verification failed.')
        return redirect('product_detail', pk=order.product.pk)

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('buyer__profile', 'seller__profile', 'product__game', 'product__category', 'game_snapshot', 'category_snapshot'), pk=pk)
    if request.user != order.buyer and request.user != order.seller: return HttpResponseForbidden()

    ordered_filter_options = order.filter_options_snapshot.select_related('filter').order_by('filter__order')
    
    other_user = order.seller if request.user == order.buyer else order.buyer
    p1, p2 = sorted((request.user.id, other_user.id))
    conversation, created = Conversation.objects.get_or_create(participant1_id=p1, participant2_id=p2)
    
    message_manager = conversation.messages
    message_count = message_manager.count()
    messages = message_manager.order_by('timestamp')[max(0, message_count - 50):]
    
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

    all_reviews = Review.objects.filter(seller=order.seller).select_related('buyer__profile', 'order__product__game', 'order__product__category').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5:
        reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else:
        reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    review_stats = all_reviews.aggregate(average_rating=Avg('rating'), review_count=Count('id'))
    context = { 'order': order, 'other_user': other_user, 'messages': messages, 'active_conversation': conversation, 'review_form': review_form, 'existing_review': existing_review, 'reviews': page_obj, 'average_rating': review_stats['average_rating'], 'review_count': review_stats['review_count'], 'current_rating_filter': rating_filter, 'profile_user': order.seller, 'ordered_filter_options': ordered_filter_options, }
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
        return redirect('order_detail', pk=order.pk)

    # Find and delete the review if one exists
    Review.objects.filter(order=order).delete()

    # Update the order status
    order.status = 'REFUNDED'
    order.save()

    messages.success(request, f'Order #{order.id} has been successfully refunded to the buyer.')
    return redirect('order_detail', pk=order.pk)

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
def my_purchases(request):
    orders_list = Order.objects.filter(buyer=request.user).select_related(
        'product__game', 'product__category', 'seller__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    order_number_query = request.GET.get('order_number', '').strip()
    seller_name_query = request.GET.get('seller_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    if order_number_query and order_number_query.isdigit(): orders_list = orders_list.filter(id=order_number_query)
    if seller_name_query: orders_list = orders_list.filter(seller__username__icontains=seller_name_query)
    if status_query: orders_list = orders_list.filter(status=status_query)
    paginator = Paginator(orders_list, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = { 'orders': page_obj, 'statuses_for_filter': Order.STATUS_CHOICES, 'filter_values': request.GET, }
    return render(request, 'marketplace/my_purchases.html', context)

def load_more_purchases(request):
    orders_list = Order.objects.filter(buyer=request.user).select_related(
        'product__game', 'product__category', 'seller__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    order_number_query = request.GET.get('order_number', '').strip()
    seller_name_query = request.GET.get('seller_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    if order_number_query and order_number_query.isdigit(): orders_list = orders_list.filter(id=order_number_query)
    if seller_name_query: orders_list = orders_list.filter(seller__username__icontains=seller_name_query)
    if status_query: orders_list = orders_list.filter(status=status_query)
    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    html_list = [render_to_string('marketplace/partials/purchase_row.html', {'order': order}) for order in page_obj]
    html = "".join(html_list)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def my_sales(request):
    orders_list = Order.objects.filter(seller=request.user).select_related(
        'product__game', 'product__category', 'buyer__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    order_number_query = request.GET.get('order_number', '').strip()
    buyer_name_query = request.GET.get('buyer_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    if order_number_query and order_number_query.isdigit(): orders_list = orders_list.filter(id=order_number_query)
    if buyer_name_query: orders_list = orders_list.filter(buyer__username__icontains=buyer_name_query)
    if status_query: orders_list = orders_list.filter(status=status_query)
    paginator = Paginator(orders_list, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = { 'orders': page_obj, 'statuses_for_filter': Order.STATUS_CHOICES, 'filter_values': request.GET, }
    return render(request, 'marketplace/my_sales.html', context)

def load_more_sales(request):
    orders_list = Order.objects.filter(seller=request.user).select_related(
        'product__game', 'product__category', 'buyer__profile', 
        'game_snapshot', 'category_snapshot'
    ).order_by('-created_at')
    order_number_query = request.GET.get('order_number', '').strip()
    buyer_name_query = request.GET.get('buyer_name', '').strip()
    status_query = request.GET.get('status', '').strip()
    if order_number_query and order_number_query.isdigit(): orders_list = orders_list.filter(id=order_number_query)
    if buyer_name_query: orders_list = orders_list.filter(buyer__username__icontains=buyer_name_query)
    if status_query: orders_list = orders_list.filter(status=status_query)
    paginator = Paginator(orders_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    html_list = [render_to_string('marketplace/partials/sale_row.html', {'order': order}) for order in page_obj]
    html = "".join(html_list)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def messages_view(request, username=None):
    if username and username.lower() == request.user.username.lower(): return redirect('my_messages')
    conversations = Conversation.objects.filter(Q(participant1=request.user) | Q(participant2=request.user)).annotate(message_count=Count('messages')).filter(message_count__gt=0).exclude(participant1=F('participant2')).order_by('-updated_at')
    unread_conversation_ids = set(Message.objects.filter(conversation__in=conversations, is_read=False).exclude(sender=request.user).values_list('conversation_id', flat=True))
    active_conversation, messages, other_user = None, [], None
    if username:
        try:
            other_user = User.objects.get(username__iexact=username)
            active_conversation = Conversation.objects.filter((Q(participant1=request.user) & Q(participant2=other_user)) | (Q(participant1=other_user) & Q(participant2=request.user))).first()
            if active_conversation:
                # MODIFIED: Fetch the last 50 messages in a template-safe way.
                message_manager = active_conversation.messages
                message_count = message_manager.count()
                messages = message_manager.order_by('timestamp')[max(0, message_count - 50):]
                active_conversation.messages.exclude(sender=request.user).update(is_read=True)
                if active_conversation.id in unread_conversation_ids: unread_conversation_ids.remove(active_conversation.id)
        except User.DoesNotExist: pass
    context = { 'conversations': conversations, 'active_conversation': active_conversation, 'other_user_profile': other_user, 'messages': messages, 'unread_conversation_ids': unread_conversation_ids, }
    return render(request, 'marketplace/my_messages.html', context)

@login_required
def funds_view(request):
    balance_data = Transaction.objects.filter(user=request.user, status='COMPLETED').aggregate(balance=Sum('amount'))
    balance = balance_data.get('balance') or 0
    transactions_list = Transaction.objects.filter(user=request.user)
    filter_by = request.GET.get('filter')
    if filter_by == 'deposits': transactions_list = transactions_list.filter(transaction_type='DEPOSIT')
    elif filter_by == 'withdrawals': transactions_list = transactions_list.filter(transaction_type='WITHDRAWAL')
    elif filter_by == 'orders': transactions_list = transactions_list.filter(transaction_type__in=['ORDER_PURCHASE', 'ORDER_SALE'])
    elif filter_by == 'miscellaneous': transactions_list = transactions_list.filter(transaction_type='MISCELLANEOUS')
    paginator = Paginator(transactions_list, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = WithdrawalRequestForm(request.POST, user=request.user, balance=balance)
        if form.is_valid():
            withdrawal_request = form.save(commit=False)
            withdrawal_request.user = request.user
            withdrawal_request.save()
            messages.success(request, 'Your withdrawal request has been submitted.')
            return redirect('funds')
    else:
        form = WithdrawalRequestForm(user=request.user, balance=balance)
    context = {
        'balance': balance,
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
    context = { 'form': form, 'password_form': password_form, }
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
    else: form = SupportTicketForm()
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    context = {'form': form, 'tickets': tickets}
    return render(request, 'marketplace/support_center.html', context)

def load_more_reviews(request, username):
    profile_user = get_object_or_404(User, username=username)
    all_reviews = Review.objects.filter(seller=profile_user).select_related('buyer__profile', 'order__product__game', 'order__product__category').order_by('-created_at')
    rating_filter = request.GET.get('rating')
    if rating_filter and rating_filter.isdigit() and 1 <= int(rating_filter) <= 5: reviews_to_display = all_reviews.filter(rating=int(rating_filter))
    else: reviews_to_display = all_reviews
    paginator = Paginator(reviews_to_display, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    template_to_render = 'marketplace/partials/_profile_review_item.html' if request.user.is_authenticated and request.user == profile_user else 'marketplace/partials/_public_review_item.html'
    html_list = [render_to_string(template_to_render, {'review': review}) for review in page_obj]
    html = "".join(html_list)
    return JsonResponse({'html': html, 'has_next': page_obj.has_next()})

@login_required
def send_chat_message(request, username):
    if request.method == 'POST':
        other_user = get_object_or_404(User, username=username)
        message_content = request.POST.get('message', '').strip()
        image_file = request.FILES.get('image')
        if not message_content and not image_file: return JsonResponse({'status': 'error', 'message': 'Cannot send an empty message.'}, status=400)
        if request.user.id < other_user.id: p1, p2 = request.user, other_user
        else: p1, p2 = other_user, request.user
        conversation, created = Conversation.objects.get_or_create(participant1=p1, participant2=p2)
        Message.objects.create(conversation=conversation, sender=request.user, content=message_content, image=image_file)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

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