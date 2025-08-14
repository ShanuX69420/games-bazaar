#!/bin/bash
# PM2 Management Script for GamesBazaar
# Server response time optimized from 660ms to 30ms!

case "$1" in
    status)
        echo "=== PM2 Status ==="
        pm2 list
        ;;
    logs)
        echo "=== PM2 Logs (last 20 lines) ==="
        pm2 logs games-bazaar --lines 20
        ;;
    restart)
        echo "=== Restarting GamesBazaar ==="
        pm2 restart games-bazaar
        ;;
    stop)
        echo "=== Stopping GamesBazaar ==="
        pm2 stop games-bazaar
        ;;
    start)
        echo "=== Starting GamesBazaar ==="
        pm2 start ecosystem.config.js
        ;;
    monitor)
        echo "=== PM2 Monitor ==="
        pm2 monit
        ;;
    reload)
        echo "=== Reloading GamesBazaar (zero downtime) ==="
        pm2 reload games-bazaar
        ;;
    test)
        echo "=== Performance Test ==="
        for i in {1..3}; do curl -w "Test $i: %{time_total}s\n" -o /dev/null -s 'http://gamesbazaarpk.com/'; done
        ;;
    *)
        echo "Usage: $0 {status|logs|restart|stop|start|monitor|reload|test}"
        echo ""
        echo "Commands:"
        echo "  status   - Show PM2 process status"
        echo "  logs     - Show recent logs"
        echo "  restart  - Restart the application"
        echo "  stop     - Stop the application"
        echo "  start    - Start the application"
        echo "  monitor  - Real-time monitoring"
        echo "  reload   - Zero-downtime reload"
        echo "  test     - Run performance test"
        exit 1
        ;;
esac