from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django import template
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from marketplace.models import (
    Conversation,
    HeldFund,
    Order,
    Product,
    SupportTicket,
    Transaction,
    WithdrawalRequest,
)


register = template.Library()
ZERO_DECIMAL = Decimal("0.00")


def currency_display(value: Decimal) -> str:
    amount = (value or ZERO_DECIMAL).quantize(Decimal("0.01"))
    return f"{amount:,.2f}"


def number_display(value) -> str:
    value = value or 0
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def build_metric(label, value, fmt, hint=None):
    metric = {"label": label, "value": value, "format": fmt}
    if fmt == "currency":
        metric["display"] = currency_display(value)
        metric["prefix"] = "PKR"
    else:
        metric["display"] = number_display(value)
    if hint:
        metric["hint"] = hint
    return metric


@register.inclusion_tag("admin/partials/marketplace_overview.html", takes_context=True)
def marketplace_overview(context):
    """
    Provide aggregated marketplace metrics for the custom admin dashboard.
    """
    # Financial metrics
    total_user_balance = (
        Transaction.objects.filter(status="COMPLETED").aggregate(total=Sum("amount"))["total"]
        or ZERO_DECIMAL
    )
    held_balance = (
        HeldFund.objects.filter(is_released=False).aggregate(total=Sum("amount"))["total"]
        or ZERO_DECIMAL
    )
    available_balance = total_user_balance - held_balance

    completed_orders_qs = Order.objects.filter(status="COMPLETED")
    completed_orders = list(completed_orders_qs)

    total_revenue = sum((order.total_price or ZERO_DECIMAL) for order in completed_orders) or ZERO_DECIMAL

    total_profit = ZERO_DECIMAL
    for order in completed_orders:
        if order.commission_paid is not None:
            commission = order.commission_paid
        elif order.seller_amount:
            commission = order.total_price - order.seller_amount
        else:
            commission = order.calculate_commission()
        total_profit += commission or ZERO_DECIMAL

    # Order health
    open_orders = Order.objects.filter(
        status__in=["PENDING_PAYMENT", "PROCESSING", "DELIVERED", "DISPUTED"]
    ).count()
    closed_orders = Order.objects.filter(status__in=["COMPLETED", "CANCELLED"]).count()
    refunded_orders = Order.objects.filter(status="REFUNDED").count()
    open_disputes = Order.objects.filter(status="DISPUTED").count()
    dispute_conversations = Conversation.objects.filter(is_disputed=True).count()

    # Liquidity & support operations
    pending_withdrawals = WithdrawalRequest.objects.filter(status="PENDING").count()
    active_support_tickets = SupportTicket.objects.filter(status__in=["OPEN", "IN_PROGRESS"]).count()

    # Marketplace activity
    active_listings = Product.objects.filter(is_active=True).count()
    total_games = (
        Product.objects.filter(is_active=True).values("game_id").distinct().count()
    )
    verified_sellers = (
        Product.objects.filter(seller__profile__is_verified_seller=True)
        .values("seller_id")
        .distinct()
        .count()
    )

    User = get_user_model()
    total_users = User.objects.filter(is_active=True).count()
    new_users_7_days = User.objects.filter(
        is_active=True, date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()

    seven_days_ago = timezone.now() - timedelta(days=7)
    orders_last_7_days = Order.objects.filter(created_at__gte=seven_days_ago).count()
    revenue_last_7_days = (
        completed_orders_qs.filter(created_at__gte=seven_days_ago).aggregate(total=Sum("total_price"))[
            "total"
        ]
        or ZERO_DECIMAL
    )

    metrics = OrderedDict(
        financial=[
            build_metric("Total available balance", available_balance, "currency"),
            build_metric("Held funds", held_balance, "currency"),
            build_metric("Total revenue", total_revenue, "currency"),
            build_metric("Total profit", total_profit, "currency"),
        ],
        orders=[
            build_metric("Open orders", open_orders, "number"),
            build_metric("Closed orders", closed_orders, "number"),
            build_metric("Refunded orders", refunded_orders, "number"),
            build_metric("Open disputes", open_disputes, "number"),
            build_metric(
                "Dispute conversations",
                dispute_conversations,
                "number",
                hint="Buyer/seller chats flagged for moderator review",
            ),
        ],
        liquidity=[
            build_metric("Pending withdrawals", pending_withdrawals, "number"),
            build_metric("Active support tickets", active_support_tickets, "number"),
        ],
        marketplace=[
            build_metric("Active listings", active_listings, "number"),
            build_metric("Games with listings", total_games, "number"),
            build_metric("Verified sellers", verified_sellers, "number"),
            build_metric("Active users", total_users, "number"),
            build_metric("New users (7d)", new_users_7_days, "number"),
            build_metric("Orders (7d)", orders_last_7_days, "number"),
            build_metric("Revenue (7d)", revenue_last_7_days, "currency"),
        ],
    )

    return {"metric_groups": metrics}
