# marketplace/management/commands/release_held_funds.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from marketplace.models import HeldFund

class Command(BaseCommand):
    help = 'Release held funds that have passed the 72-hour delay period (Note: Funds are auto-released when users check their balance, so this command is optional)'

    def handle(self, *args, **options):
        # Get all unreleased funds that can be released
        releasable_funds = HeldFund.objects.filter(
            is_released=False,
            release_at__lte=timezone.now()
        )
        
        released_count = 0
        total_amount = 0
        
        for held_fund in releasable_funds:
            if held_fund.release_fund():
                released_count += 1
                total_amount += held_fund.amount
                self.stdout.write(
                    f"Released Rs{held_fund.amount} for {held_fund.user.username} "
                    f"from order {held_fund.order.order_id}"
                )
        
        if released_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully released {released_count} funds totaling Rs{total_amount}"
                )
            )
        else:
            self.stdout.write("No funds eligible for release at this time")