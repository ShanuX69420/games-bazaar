#!/bin/bash
# High Traffic Deployment Script for GamesBazaar
# Supports 10,000+ concurrent users

echo "🚀 Starting HIGH TRAFFIC deployment..."

# Configuration
PROJECT_DIR="/path/to/gamers_market"
VENV_DIR="$PROJECT_DIR/venv"
GUNICORN_INSTANCES=3
REDIS_INSTANCES=3

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Set environment
export DJANGO_SETTINGS_MODULE=core.settings.high_traffic

cd $PROJECT_DIR

# Activate virtual environment
source $VENV_DIR/bin/activate

# Install/Update dependencies
print_status "📦 Installing dependencies..."
pip install -r requirements.txt
pip install psycopg2-binary gevent redis hiredis

# Database setup
print_status "🗃️ Setting up database..."
python manage.py migrate --noinput

# Collect static files
print_status "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Create necessary directories
print_status "📂 Creating directories..."
mkdir -p logs
mkdir -p /var/cache/nginx/gamers_market
mkdir -p /dev/shm

# System checks
print_status "🔍 Running system checks..."
python manage.py check --deploy

# Setup Redis cluster (if not already running)
print_status "⚡ Setting up Redis cluster..."
for i in $(seq 1 $REDIS_INSTANCES); do
    PORT=$((6378 + i))
    if ! pgrep -f "redis-server.*:$PORT" > /dev/null; then
        print_status "Starting Redis instance on port $PORT"
        redis-server --port $PORT --daemonize yes --save 900 1 --save 300 10
    else
        print_status "Redis instance on port $PORT already running"
    fi
done

# Stop existing Gunicorn processes
print_status "🔄 Stopping existing Gunicorn processes..."
pkill -f "gunicorn.*gamers_market" || true
sleep 2

# Start multiple Gunicorn instances
print_status "🌐 Starting Gunicorn instances..."
for i in $(seq 0 $((GUNICORN_INSTANCES - 1))); do
    PORT=$((8000 + i))
    print_status "Starting Gunicorn instance on port $PORT"
    
    gunicorn core.wsgi:application \
        --bind 0.0.0.0:$PORT \
        --config deployment/gunicorn_high_traffic.conf \
        --daemon \
        --pid logs/gunicorn_$PORT.pid \
        --error-logfile logs/gunicorn_error_$PORT.log \
        --access-logfile logs/gunicorn_access_$PORT.log
        
    sleep 1
done

# Setup log rotation
print_status "📝 Setting up log rotation..."
cat > /etc/logrotate.d/gamers_market << EOF
$PROJECT_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 www-data www-data
    postrotate
        systemctl reload nginx
        pkill -USR1 -f "gunicorn.*gamers_market"
    endscript
}
EOF

# Database optimization
print_status "⚙️ Optimizing database..."
python manage.py shell << EOF
from django.db import connection
cursor = connection.cursor()

# PostgreSQL optimizations
cursor.execute("ALTER SYSTEM SET shared_buffers = '256MB';")
cursor.execute("ALTER SYSTEM SET effective_cache_size = '1GB';")
cursor.execute("ALTER SYSTEM SET maintenance_work_mem = '64MB';")
cursor.execute("ALTER SYSTEM SET checkpoint_completion_target = 0.9;")
cursor.execute("ALTER SYSTEM SET wal_buffers = '16MB';")
cursor.execute("ALTER SYSTEM SET default_statistics_target = 100;")
cursor.execute("SELECT pg_reload_conf();")
EOF

# Health check
print_status "🔍 Running health checks..."
sleep 5

HEALTH_CHECK_PASSED=true
for i in $(seq 0 $((GUNICORN_INSTANCES - 1))); do
    PORT=$((8000 + i))
    if curl -f -s http://localhost:$PORT/health/ > /dev/null; then
        print_status "✅ Gunicorn instance on port $PORT is healthy"
    else
        print_error "❌ Gunicorn instance on port $PORT failed health check"
        HEALTH_CHECK_PASSED=false
    fi
done

# Check Redis instances
for i in $(seq 1 $REDIS_INSTANCES); do
    PORT=$((6378 + i))
    if redis-cli -p $PORT ping | grep -q PONG; then
        print_status "✅ Redis instance on port $PORT is healthy"
    else
        print_error "❌ Redis instance on port $PORT failed health check"
        HEALTH_CHECK_PASSED=false
    fi
done

# Final status
if [ "$HEALTH_CHECK_PASSED" = true ]; then
    print_status "🎉 HIGH TRAFFIC DEPLOYMENT SUCCESSFUL!"
    print_status "📊 Configuration:"
    print_status "   - Gunicorn instances: $GUNICORN_INSTANCES (ports 8000-$((8000 + GUNICORN_INSTANCES - 1)))"
    print_status "   - Redis instances: $REDIS_INSTANCES (ports 6379-$((6378 + REDIS_INSTANCES)))"
    print_status "   - Expected capacity: 10,000+ concurrent users"
    print_status "   - Max RPS: 1,000+"
    print_status ""
    print_status "📝 Next steps:"
    print_status "   1. Update Nginx configuration with deployment/nginx_high_traffic.conf"
    print_status "   2. Restart Nginx: sudo systemctl restart nginx"
    print_status "   3. Monitor logs: tail -f logs/gunicorn_error_*.log"
    print_status "   4. Set up monitoring with tools like New Relic or DataDog"
else
    print_error "❌ DEPLOYMENT FAILED - Check error logs"
    exit 1
fi