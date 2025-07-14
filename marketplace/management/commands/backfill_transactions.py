from django.core.management.base import BaseCommand
from django.db import transaction
from marketplace.models import Order, Transaction

class Command(BaseCommand):
    help = 'Back-fills transaction records for previously completed or processing orders.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write('Starting to back-fill transactions for existing orders...')

        # Find orders that should have transactions but might not
        orders_to_check = Order.objects.filter(status__in=['PROCESSING', 'COMPLETED'])
        created_count = 0

        for order in orders_to_check:
            # --- Handle PROCESSING orders ---
            if order.status == 'PROCESSING':
                # Check if a transaction for the buyer already exists
                if not Transaction.objects.filter(order=order, user=order.buyer).exists():
                    Transaction.objects.create(
                        user=order.buyer,
                        amount=-order.total_price,
                        transaction_type='ORDER_PURCHASE',
                        status='PROCESSING',
                        description=f"Purchase of '{order.product.listing_title}'",
                        order=order
                    )
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  + Created PROCESSING purchase transaction for order #{order.id}'))

                # Check if a transaction for the seller already exists
                if not Transaction.objects.filter(order=order, user=order.seller).exists():
                    Transaction.objects.create(
                        user=order.seller,
                        amount=order.total_price,
                        transaction_type='ORDER_SALE',
                        status='PROCESSING',
                        description=f"Sale of '{order.product.listing_title}'",
                        order=order
                    )
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  + Created PROCESSING sale transaction for order #{order.id}'))

            # --- Handle COMPLETED orders ---
            elif order.status == 'COMPLETED':
                # Check for buyer's transaction
                if not Transaction.objects.filter(order=order, user=order.buyer).exists():
                    Transaction.objects.create(
                        user=order.buyer,
                        amount=-order.total_price,
                        transaction_type='ORDER_PURCHASE',
                        status='COMPLETED',
                        description=f"Purchase of '{order.product.listing_title}'",
                        order=order
                    )
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  + Created COMPLETED purchase transaction for order #{order.id}'))

                # Check for seller's transaction
                if not Transaction.objects.filter(order=order, user=order.seller).exists():
                    net_earning = order.total_price - (order.commission_paid or 0)
                    Transaction.objects.create(
                        user=order.seller,
                        amount=net_earning,
                        transaction_type='ORDER_SALE',
                        status='COMPLETED',
                        description=f"Sale of '{order.product.listing_title}'",
                        order=order
                    )
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  + Created COMPLETED sale transaction for order #{order.id}'))

        self.stdout.write(self.style.SUCCESS(f'\nFinished back-filling. Created {created_count} new transaction records.'))