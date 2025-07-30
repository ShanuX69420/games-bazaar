from django.core.management.base import BaseCommand
from django.db import connection
from django.core.cache import cache
from django.conf import settings
import psutil
import time
import json
from datetime import datetime

class Command(BaseCommand):
    help = 'Monitor application performance and traffic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=30,
            help='Monitoring interval in seconds (default: 30)'
        )
        parser. add_argument(
            '--output',
            type=str,
            default='console',
            choices=['console', 'json', 'file'],
            help='Output format'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        output_format = options['output']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting performance monitoring (interval: {interval}s)')
        )
        
        try:
            while True:
                metrics = self.collect_metrics()
                self.output_metrics(metrics, output_format)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Monitoring stopped'))

    def collect_metrics(self):
        """Collect various performance metrics"""
        
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Application metrics
        app_stats = self.get_app_stats()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
            },
            'application': app_stats,
        }

    def get_app_stats(self):
        """Get application-specific statistics"""
        from marketplace.models import Product, Order, User, Message
        
        try:
            # Recent activity (last hour)
            from datetime import datetime, timedelta
            hour_ago = datetime.now() - timedelta(hours=1)
            
            return {
                'active_products': Product.objects.filter(is_active=True).count(),
                'recent_orders': Order.objects.filter(created_at__gte=hour_ago).count(),
                'recent_messages': Message.objects.filter(timestamp__gte=hour_ago).count(),
                'total_users': User.objects.count(),
            }
        except Exception:
            return {'status': 'unavailable'}

    def output_metrics(self, metrics, output_format):
        """Output metrics in specified format"""
        
        if output_format == 'console':
            self.output_console(metrics)
        elif output_format == 'json':
            self.stdout.write(json.dumps(metrics, indent=2))

    def output_console(self, metrics):
        """Output metrics to console in readable format"""
        timestamp = metrics['timestamp']
        sys = metrics['system']
        app = metrics['application']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Performance Metrics - {timestamp}")
        self.stdout.write(f"{'='*60}")
        
        # System metrics
        self.stdout.write(f"🖥️  SYSTEM:")
        self.stdout.write(f"   CPU: {sys['cpu_percent']}%")
        self.stdout.write(f"   Memory: {sys['memory_percent']}% ({sys['memory_available_gb']:.1f}GB available)")
        
        # Application metrics
        self.stdout.write(f"\n📱 APPLICATION:")
        if 'status' in app:
            self.stdout.write(f"   Status: {app['status']}")
        else:
            self.stdout.write(f"   Active Products: {app['active_products']}")
            self.stdout.write(f"   Recent Orders (1h): {app['recent_orders']}")
            self.stdout.write(f"   Recent Messages (1h): {app['recent_messages']}")
            self.stdout.write(f"   Total Users: {app['total_users']}")