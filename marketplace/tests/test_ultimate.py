from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone

from marketplace.models import (
    Category,
    Game,
    GameCategory,
    HeldFund,
    Order,
    Product,
    SiteConfiguration,
    Transaction,
    Conversation,
    Message,
    BlockedUser,
)
from marketplace.forms import (
    CustomUserCreationForm,
    ProductForm,
    WithdrawalRequestForm,
    DepositRequestForm,
)
from marketplace.templatetags.safe_html import (
    safe_system_html,
    safe_user_html,
    unescape_for_preview,
)


class UltimateMarketplaceFlowTests(TestCase):
    """
    High-value regression tests that exercise the core marketplace flow. These
    tests focus on model-level behaviours so they remain fast, deterministic,
    and safe to run before every deployment.
    """

    def setUp(self) -> None:
        cache.clear()

        SiteConfiguration.objects.create(default_commission_rate=Decimal("11.00"))

        self.seller = User.objects.create_user(
            username="ultimate_seller", email="seller@example.com", password="password123"
        )
        self.buyer = User.objects.create_user(
            username="ultimate_buyer", email="buyer@example.com", password="password123"
        )
        self.category = Category.objects.create(
            name="Ultimate Gear", commission_rate=Decimal("12.00")
        )
        self.game = Game.objects.create(title="Ultimate Adventure")
        self.game_category_link = GameCategory.objects.create(
            game=self.game,
            category=self.category,
            allows_automated_delivery=False,
        )

        self.product = self._create_manual_product(
            title="Starter Pack", price=Decimal("100.00"), stock=3
        )

    def _create_manual_product(
        self, title: str, price: Decimal, stock: int, description: str = "Manual delivery item"
    ) -> Product:
        product = Product(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title=title,
            description=description,
            price=price,
            automatic_delivery=False,
            stock=stock,
            stock_details="",
        )
        product.full_clean()
        product.save()
        return product

    def _create_order(self, product: Product, total_price: Decimal | None = None) -> Order:
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=product,
            total_price=total_price or product.price,
            status="PROCESSING",
            commission_paid=Decimal("0.00"),
            listing_title_snapshot=product.listing_title,
            description_snapshot=product.description,
            game_snapshot=self.game,
            category_snapshot=self.category,
        )

    def test_product_validation_and_stock_count(self) -> None:
        auto_product = Product(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Auto Delivery Pack",
            description="Two instant delivery codes",
            price=Decimal("59.99"),
            automatic_delivery=True,
            stock=None,
            stock_details="CODE-1\nCODE-2\n",
        )
        auto_product.full_clean()
        auto_product.save()
        self.assertEqual(auto_product.stock_count, 2)

        manual_product = Product(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Manual Pack",
            description="Ships manually",
            price=Decimal("19.99"),
            automatic_delivery=False,
            stock=5,
            stock_details="",
        )
        manual_product.full_clean()
        manual_product.save()
        self.assertEqual(manual_product.stock_count, 5)

        with self.assertRaises(ValidationError):
            invalid_auto = Product(
                seller=self.seller,
                game=self.game,
                category=self.category,
                listing_title="Invalid Auto",
                description="Missing codes",
                price=Decimal("9.99"),
                automatic_delivery=True,
                stock=1,
                stock_details="",
            )
            invalid_auto.full_clean()

        with self.assertRaises(ValidationError):
            invalid_manual = Product(
                seller=self.seller,
                game=self.game,
                category=self.category,
                listing_title="Invalid Manual",
                description="Extra stock details",
                price=Decimal("24.99"),
                automatic_delivery=False,
                stock=5,
                stock_details="SHOULD-NOT-BE-HERE",
            )
            invalid_manual.full_clean()

    def test_order_commission_priority_and_id_generation(self) -> None:
        order = self._create_order(self.product, total_price=Decimal("100.00"))

        self.assertRegex(
            order.order_id,
            r"^#[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$",
            "Order IDs should use the secure UUID-based format",
        )
        self.assertEqual(order.clean_order_id, order.order_id.lstrip("#"))

        self.seller.profile.commission_rate = Decimal("7.50")
        self.seller.profile.save(update_fields=["commission_rate"])
        commission = order.calculate_commission()
        self.assertEqual(commission.quantize(Decimal("0.01")), Decimal("7.50"))

        self.seller.profile.commission_rate = None
        self.seller.profile.save(update_fields=["commission_rate"])
        self.category.commission_rate = Decimal("12.00")
        self.category.save(update_fields=["commission_rate"])
        commission = order.calculate_commission()
        self.assertEqual(commission.quantize(Decimal("0.01")), Decimal("12.00"))

        self.category.commission_rate = None
        self.category.save(update_fields=["commission_rate"])
        commission = order.calculate_commission()
        self.assertEqual(commission.quantize(Decimal("0.01")), Decimal("11.00"))

        second_order = self._create_order(self.product, total_price=Decimal("25.00"))
        self.assertNotEqual(
            order.order_id,
            second_order.order_id,
            "generate_unique_order_id should produce unique identifiers",
        )

    def test_transaction_cache_and_held_funds_flow(self) -> None:
        order = self._create_order(self.product, total_price=Decimal("150.00"))

        Transaction.objects.create(
            user=self.seller,
            amount=Decimal("150.00"),
            transaction_type="ORDER_SALE",
            status="COMPLETED",
            description="Order payout",
            order=order,
        )

        profile = self.seller.profile
        self.assertEqual(profile.balance, Decimal("150.00"))

        Transaction.objects.create(
            user=self.seller,
            amount=Decimal("-25.00"),
            transaction_type="WITHDRAWAL",
            status="COMPLETED",
            description="Withdrawal processed",
        )

        self.assertEqual(
            profile.balance,
            Decimal("125.00"),
            "Balance cache should invalidate when new transactions arrive",
        )

        hold = HeldFund.objects.create(
            user=self.seller,
            order=order,
            amount=Decimal("60.00"),
            release_at=timezone.now() + datetime.timedelta(hours=1),
        )

        self.assertEqual(profile.held_balance, Decimal("60.00"))
        self.assertEqual(profile.available_balance, Decimal("65.00"))

        hold.release_at = timezone.now() - datetime.timedelta(minutes=1)
        hold.save(update_fields=["release_at"])
        hold.refresh_from_db()
        self.assertTrue(hold.can_be_released())

        self.assertEqual(
            profile.available_balance,
            Decimal("125.00"),
            "Auto-release should free held funds once the hold period passes",
        )
        hold.refresh_from_db()
        self.assertTrue(hold.is_released)

    def test_profile_signal_and_online_state(self) -> None:
        fresh_user = User.objects.create_user(
            username="signal_user", email="signal@example.com", password="password123"
        )
        self.assertTrue(hasattr(fresh_user, "profile"), "Profile signal should create profile")
        profile = fresh_user.profile
        self.assertFalse(profile.is_online)
        profile.last_seen = timezone.now()
        profile.save(update_fields=["last_seen"])
        self.assertTrue(profile.is_online)
        fresh_user.is_staff = True
        fresh_user.save(update_fields=["is_staff"])
        profile.refresh_from_db()
        self.assertTrue(profile.can_moderate)

    def test_custom_user_creation_form_validation(self) -> None:
        form = CustomUserCreationForm(
            data={
                "username": "newplayer1",
                "email": "newplayer@example.com",
                "password": "strongpass9",
            }
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        new_user = form.save()
        self.assertTrue(new_user.check_password("strongpass9"))

        bad_form = CustomUserCreationForm(
            data={
                "username": "bad user!",
                "email": "newplayer@example.com",
                "password": "short",
            }
        )
        self.assertFalse(bad_form.is_valid())
        self.assertIn("username", bad_form.errors)
        self.assertIn("password", bad_form.errors)

    def test_product_form_enforces_filters_and_stock(self) -> None:
        from marketplace.models import Filter, FilterOption

        filter_obj = Filter.objects.create(
            internal_name="Region",
            name="Region",
            filter_type="dropdown",
            order=1,
        )
        option = FilterOption.objects.create(filter=filter_obj, value="NA")
        self.game_category_link.filters.add(filter_obj)

        base_data = {
            "listing_title": "Filtered Product",
            "description": "With metadata",
            "post_purchase_message": "Thanks",
            "price": "55.00",
            "stock": "5",
            "stock_details": "",
        }

        form_missing_filter = ProductForm(
            data=base_data,
            game_category_link=self.game_category_link,
        )
        self.assertNotIn("automatic_delivery", form_missing_filter.fields)
        self.assertFalse(form_missing_filter.is_valid())
        self.assertIn(f"filter_{filter_obj.id}", form_missing_filter.errors)

        valid_data = {**base_data, f"filter_{filter_obj.id}": str(option.pk)}
        form_with_filter = ProductForm(
            data=valid_data,
            game_category_link=self.game_category_link,
        )
        self.assertTrue(form_with_filter.is_valid(), form_with_filter.errors.as_json())

        zero_stock_data = valid_data.copy()
        zero_stock_data["stock"] = "0"
        form_zero_stock = ProductForm(
            data=zero_stock_data,
            game_category_link=self.game_category_link,
        )
        self.assertFalse(form_zero_stock.is_valid())
        self.assertIn("stock", form_zero_stock.errors)

    def test_messaging_conversation_and_cache_invalidation(self) -> None:
        moderator = User.objects.create_user(
            username="mod", email="mod@example.com", password="password123", is_staff=True
        )
        conversation = Conversation.objects.create(
            participant1=self.seller,
            participant2=self.buyer,
            moderator=moderator,
        )
        cache_key = f"conversation_message_count_{conversation.id}"
        cache.set(cache_key, 10)
        message = Message.objects.create(
            conversation=conversation,
            sender=self.buyer,
            content="Hello there!",
        )
        self.assertIsNone(cache.get(cache_key))
        self.assertIn(moderator, conversation.get_participants())
        self.assertTrue(conversation.is_participant(self.seller))
        self.assertFalse(message.is_system_message)

        BlockedUser.objects.create(blocker=self.buyer, blocked=self.seller)
        with self.assertRaises(IntegrityError):
            BlockedUser.objects.create(blocker=self.buyer, blocked=self.seller)

    def test_withdrawal_request_form_validations(self) -> None:
        Transaction.objects.create(
            user=self.seller,
            amount=Decimal("300.00"),
            transaction_type="ORDER_SALE",
            status="COMPLETED",
            description="Sale payout",
        )
        cache.clear()

        form = WithdrawalRequestForm(
            data={
                "amount": "150.00",
                "payment_method": "bank_transfer",
                "account_title": "Ultimate Seller",
                "iban": "PK" + "0" * 22,
            },
            user=self.seller,
            balance=self.seller.profile.available_balance,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

        invalid_form = WithdrawalRequestForm(
            data={
                "amount": "0",
                "payment_method": "bank_transfer",
                "account_title": "A",
                "iban": "INVALID",
            },
            user=self.seller,
            balance=self.seller.profile.available_balance,
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("amount", invalid_form.errors)
        self.assertIn("account_title", invalid_form.errors)
        self.assertIn("iban", invalid_form.errors)

    def test_deposit_request_form_file_validation(self) -> None:
        valid_file = SimpleUploadedFile(
            "receipt.png",
            b"x" * 2048,
            content_type="image/png",
        )
        form = DepositRequestForm(
            data={
                "amount": "1500.00",
                "payment_reference": "REF123",
                "notes": "All good",
            },
            files={"receipt": valid_file},
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

        small_file = SimpleUploadedFile(
            "receipt.gif",
            b"x" * 100,
            content_type="image/gif",
        )
        invalid_form = DepositRequestForm(
            data={
                "amount": "500.00",
                "payment_reference": "REF123",
                "notes": "Too small",
            },
            files={"receipt": small_file},
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("amount", invalid_form.errors)
        self.assertIn("receipt", invalid_form.errors)

        bad_ext_file = SimpleUploadedFile(
            "receipt.exe",
            b"x" * 2048,
            content_type="application/octet-stream",
        )
        invalid_type_form = DepositRequestForm(
            data={
                "amount": "1500.00",
                "payment_reference": "REF123",
                "notes": "Bad type",
            },
            files={"receipt": bad_ext_file},
        )
        self.assertFalse(invalid_type_form.is_valid())
        self.assertIn("receipt", invalid_type_form.errors)

    def test_safe_html_filters(self) -> None:
        system_html = '<script>alert("xss")</script><a href="/help/" class="link">Help</a>'
        rendered = safe_system_html(system_html)
        rendered_str = str(rendered)
        self.assertNotIn("<script>", rendered_str)
        self.assertIn('<a href="/help/" class="link">Help</a>', rendered_str)

        user_html = safe_user_html('<b>bold</b>\nsecond line')
        self.assertIn("<br>", str(user_html))
        self.assertIn("<b>bold</b>", str(user_html))

        preview = unescape_for_preview('<strong>Safe</strong> &amp; Sound')
        self.assertEqual(preview, "Safe & Sound")
