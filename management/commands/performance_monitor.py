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
        parser.add_argument(
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
        disk = psutil.disk_usage('/')
        
        # Database metrics
        db_connections = self.get_db_connections()
        db_queries = self.get_db_query_stats()
        
        # Cache metrics
        cache_stats = self.get_cache_stats()
        
        # Application metrics
        app_stats = self.get_app_stats()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024**3),
            },
            'database': {
                'active_connections': db_connections,
                'query_count': db_queries,
            },
            'cache': cache_stats,
            'application': app_stats,
        }

    def get_db_connections(self):
        """Get database connection count"""
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                    [settings.DATABASES['default']['NAME']]
                )
                return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_db_query_stats(self):
        """Get database query statistics"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT sum(calls) as total_calls
                    FROM pg_stat_statements 
                    WHERE dbid = (SELECT oid FROM pg_database WHERE datname = %s)
                """, [settings.DATABASES['default']['NAME']])
                result = cursor.fetchone()
                return result[0] if result and result[0] else 0
        except Exception:
            return 0

    def get_cache_stats(self):
        """Get cache statistics"""
        try:
            # Redis cache stats
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("default")
            info = redis_conn.info()
            
            return {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_mb': info.get('used_memory', 0) / (1024*1024),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'hit_rate': self.calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }
        except Exception:
            return {'status': 'unavailable'}

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

    def calculate_hit_rate(self, hits, misses):
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return 0
        return round((hits / total) * 100, 2)

    def output_metrics(self, metrics, output_format):
        """Output metrics in specified format"""
        
        if output_format == 'console':
            self.output_console(metrics)
        elif output_format == 'json':
            self.stdout.write(json.dumps(metrics, indent=2))
        elif output_format == 'file':
            self.output_file(metrics)

    def output_console(self, metrics):
        """Output metrics to console in readable format"""
        timestamp = metrics['timestamp']
        sys = metrics['system']
        db = metrics['database']
        cache = metrics['cache']
        app = metrics['application']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Performance Metrics - {timestamp}")
        self.stdout.write(f"{'='*60}")
        
        # System metrics
        self.stdout.write(f"🖥️  SYSTEM:")
        self.stdout.write(f"   CPU: {sys['cpu_percent']}%")
        self.stdout.write(f"   Memory: {sys['memory_percent']}% ({sys['memory_available_gb']:.1f}GB available)")
        self.stdout.write(f"   Disk: {sys['disk_percent']}% ({sys['disk_free_gb']:.1f}GB free)")
        
        # Database metrics
        self.stdout.write(f"\n🗃️  DATABASE:")
        self.stdout.write(f"   Active Connections: {db['active_connections']}")
        self.stdout.write(f"   Total Queries: {db['query_count']}")
        
        # Cache metrics
        self.stdout.write(f"\n⚡ CACHE:")
        if 'status' in cache:
            self.stdout.write(f"   Status: {cache['status']}")
        else:
            self.stdout.write(f"   Connected Clients: {cache['connected_clients']}")
            self.stdout.write(f"   Memory Used: {cache['used_memory_mb']:.1f}MB")
            self.stdout.write(f"   Hit Rate: {cache['hit_rate']}%")
        
        # Application metrics
        self.stdout.write(f"\n📱 APPLICATION:")
        if 'status' in app:
            self.stdout.write(f"   Status: {app['status']}")
        else:
            self.stdout.write(f"   Active Products: {app['active_products']}")
            self.stdout.write(f"   Recent Orders (1h): {app['recent_orders']}")
            self.stdout.write(f"   Recent Messages (1h): {app['recent_messages']}")
            self.stdout.write(f"   Total Users: {app['total_users']}")

    def output_file(self, metrics):
        """Output metrics to file"""
        filename = f"logs/performance_{datetime.now().strftime('%Y%m%d')}.log"
        with open(filename, 'a') as f:
            f.write(json.dumps(metrics) + '\n')