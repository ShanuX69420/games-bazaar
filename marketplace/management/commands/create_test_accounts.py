from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from marketplace.models import Transaction, Profile
from decimal import Decimal
import random

class Command(BaseCommand):
    help = 'Create test accounts with fake balances for testing on production server'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=5,
            help='Number of test accounts to create (default: 5)'
        )
        parser.add_argument(
            '--min-balance',
            type=int,
            default=1000,
            help='Minimum balance for test accounts (default: 1000)'
        )
        parser.add_argument(
            '--max-balance',
            type=int,
            default=50000,
            help='Maximum balance for test accounts (default: 50000)'
        )

    def handle(self, *args, **options):
        count = options['count']
        min_balance = options['min_balance']
        max_balance = options['max_balance']
        
        self.stdout.write(f'Creating {count} test accounts with balances between {min_balance}-{max_balance}...')
        
        created_accounts = []
        
        for i in range(count):
            username = f'test_user_{i+1:03d}'
            email = f'test{i+1:03d}@example.com'
            
            # Check if user already exists
            if User.objects.filter(username=username).exists():
                self.stdout.write(f'User {username} already exists, skipping...')
                continue
            
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password='testpass123',
                first_name=f'Test',
                last_name=f'User {i+1}'
            )
            
            # Generate random balance
            balance = Decimal(str(random.randint(min_balance, max_balance)))
            
            # Create a completed deposit transaction to give the user balance
            Transaction.objects.create(
                user=user,
                amount=balance,
                transaction_type='DEPOSIT',
                status='COMPLETED',
                description=f'Test account initial balance for {username}'
            )
            
            created_accounts.append({
                'username': username,
                'email': email,
                'password': 'testpass123',
                'balance': balance
            })
            
            self.stdout.write(f'Created {username} with balance: Rs{balance}')
        
        if created_accounts:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=== TEST ACCOUNTS CREATED ==='))
            self.stdout.write('')
            for account in created_accounts:
                self.stdout.write(f'Username: {account["username"]}')
                self.stdout.write(f'Email: {account["email"]}')
                self.stdout.write(f'Password: {account["password"]}')
                self.stdout.write(f'Balance: Rs{account["balance"]}')
                self.stdout.write('---')
            
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'Successfully created {len(created_accounts)} test accounts!'))
        else:
            self.stdout.write(self.style.WARNING('No new accounts were created.'))