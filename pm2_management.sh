#!/bin/bash
# PM2 Management Script for Games Bazaar

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
        echo "=== Restarting Games Bazaar ==="
        pm2 restart games-bazaar
        ;;
    stop)
        echo "=== Stopping Games Bazaar ==="
        pm2 stop games-bazaar
        ;;
    start)
        echo "=== Starting Games Bazaar ==="
        pm2 start games-bazaar
        ;;
    monitor)
        echo "=== PM2 Monitor ==="
        pm2 monit
        ;;
    reload)
        echo "=== Reloading Games Bazaar (zero downtime) ==="
        pm2 reload games-bazaar
        ;;
    *)
        echo "Usage: $0 {status|logs|restart|stop|start|monitor|reload}"
        echo ""
        echo "Commands:"
        echo "  status   - Show PM2 process status"
        echo "  logs     - Show recent logs"
        echo "  restart  - Restart the application"
        echo "  stop     - Stop the application"
        echo "  start    - Start the application"
        echo "  monitor  - Real-time monitoring"
        echo "  reload   - Zero-downtime reload"
        exit 1
        ;;
esac