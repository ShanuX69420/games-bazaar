from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from marketplace.models import Category, Game, Order, Product


class BalanceCacheInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.buyer = User.objects.create_user(
            username="buyer", email="buyer@example.com", password="testpass"
        )
        self.seller = User.objects.create_user(
            username="seller", email="seller@example.com", password="testpass"
        )
        self.category = Category.objects.create(
            name="Currency", commission_rate=Decimal("10.00")
        )
        self.game = Game.objects.create(title="Test Game")
        self.game.categories.add(self.category)
        self.product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Test Listing",
            description="Test Description",
            price=Decimal("500.00"),
            stock=1,
        )

        self.order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=Decimal("500.00"),
            status="PROCESSING",
            commission_paid=Decimal("0.00"),
            listing_title_snapshot=self.product.listing_title,
            description_snapshot=self.product.description,
            game_snapshot=self.product.game,
            category_snapshot=self.product.category,
        )

    def test_order_completion_clears_cached_balances(self):
        balance_cache_key = f"user_balance_{self.seller.id}"

        initial_balance = self.seller.profile.balance
        self.assertEqual(initial_balance, Decimal("0.00"))
        cached_value = cache.get(balance_cache_key)
        self.assertIsNotNone(cached_value, "Balance should be cached after first access")

        self.order.status = "COMPLETED"
        self.order.commission_paid = Decimal("50.00")
        self.order.save()

        self.assertIsNone(
            cache.get(balance_cache_key),
            "Balance cache should be cleared when order completes",
        )

        updated_balance = self.seller.profile.balance
        self.assertEqual(updated_balance, Decimal("450.00"))
        self.assertEqual(
            self.seller.profile.available_balance,
            Decimal("0.00"),
            "Available balance should not go negative after hold is applied",
        )
