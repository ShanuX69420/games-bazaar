from django.core.management.base import BaseCommand
from django.db import transaction
from marketplace.models import Order, Transaction

class Command(BaseCommand):
    help = 'Back-fills transaction records for previously completed orders.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write('Starting to back-fill transactions for completed orders...')

        completed_orders = Order.objects.filter(status='COMPLETED')
        created_count = 0

        for order in completed_orders:
            # Check if a transaction for the buyer already exists
            buyer_tx_exists = Transaction.objects.filter(order=order, user=order.buyer).exists()
            if not buyer_tx_exists:
                Transaction.objects.create(
                    user=order.buyer,
                    amount=-order.total_price,
                    transaction_type='ORDER_PURCHASE',
                    status='COMPLETED',
                    description=f"Purchase of '{order.product.listing_title}'",
                    order=order
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  + Created purchase transaction for order #{order.id}'))

            # Check if a transaction for the seller already exists
            seller_tx_exists = Transaction.objects.filter(order=order, user=order.seller).exists()
            if not seller_tx_exists:
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
                self.stdout.write(self.style.SUCCESS(f'  + Created sale transaction for order #{order.id}'))

        self.stdout.write(self.style.SUCCESS(f'\nFinished back-filling. Created {created_count} new transaction records.'))