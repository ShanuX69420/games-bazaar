# marketplace/security_middleware.py

import logging
import json
from datetime import datetime
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('marketplace.security')
access_logger = logging.getLogger('marketplace.access')

class SecurityMiddleware(MiddlewareMixin):
    """Enhanced security middleware for production"""
    
    def process_request(self, request):
        """Process incoming requests for security checks with enhanced logging"""
        
        client_ip = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Log all access attempts for sensitive endpoints
        sensitive_paths = ['/admin', '/api', '/jazzcash', '/order-confirmation', '/settings']
        if any(path in request.path for path in sensitive_paths):
            access_logger.info(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'ip': client_ip,
                'path': request.path,
                'method': request.method,
                'user_agent': user_agent[:200],  # Truncate long user agents
                'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
                'referer': request.META.get('HTTP_REFERER', '')[:200],
                'event_type': 'sensitive_access'
            }))
        
        # Rate limiting for suspicious IPs
        cache_key = f'suspicious_requests_{client_ip}'
        request_count = cache.get(cache_key, 0)
        if request_count > 8000:  # More than 8000 requests per hour from same IP (130+ per minute)
            logger.critical(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'ip': client_ip,
                'path': request.path,
                'user_agent': user_agent[:200],
                'event_type': 'rate_limit_exceeded',
                'request_count': request_count
            }))
            return HttpResponseBadRequest("Rate limit exceeded")
        
        # Block requests with suspicious patterns
        suspicious_patterns = [
            '../', '..\\', 'etc/passwd', 'cmd.exe', '<script',
            'javascript:', 'vbscript:', 'onload=', 'onerror=',
            'eval(', 'document.cookie', 'window.location', 'union select',
            'drop table', 'insert into', 'delete from', 'update set'
        ]
        
        # Check path and query parameters
        full_path = request.get_full_path().lower()
        for pattern in suspicious_patterns:
            if pattern in full_path:
                logger.critical(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'ip': client_ip,
                    'path': request.get_full_path(),
                    'user_agent': user_agent[:200],
                    'event_type': 'suspicious_pattern_detected',
                    'pattern': pattern,
                    'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous'
                }))
                # Increment suspicious request counter
                cache.set(cache_key, request_count + 10, 3600)  # Penalty for suspicious requests
                return HttpResponseBadRequest("Invalid request")
        
        # Check user agent for security scanners
        user_agent_lower = user_agent.lower()
        blocked_agents = ['sqlmap', 'nikto', 'nmap', 'masscan', 'nuclei', 'gobuster', 'dirb', 'wpscan', 'burp']
        if any(agent in user_agent_lower for agent in blocked_agents):
            logger.critical(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'ip': client_ip,
                'path': request.path,
                'user_agent': user_agent[:200],
                'event_type': 'security_scanner_blocked',
                'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous'
            }))
            cache.set(cache_key, request_count + 20, 3600)  # Heavy penalty for security scanners
            return HttpResponseBadRequest("Access denied")
        
        # Increment request counter for rate limiting
        cache.set(cache_key, request_count + 1, 3600)
        
        return None
    
    def process_response(self, request, response):
        """Add security headers to responses"""
        
        # Add security headers (Edge-compatible)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'SAMEORIGIN'  # Changed from DENY to SAMEORIGIN for Edge compatibility
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Add Cross-Origin-Opener-Policy for better browser compatibility
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        
        # Enhanced CSP for better security
        if not settings.DEBUG:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://www.google.com https://www.gstatic.com https://accounts.google.com https://connect.facebook.net https://www.facebook.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https: blob:; "
                "frame-src 'self' https://www.google.com https://accounts.google.com https://www.facebook.com; "
                "connect-src 'self' https: wss: ws:; "
                "media-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self' https://sandbox.jazzcash.com.pk https://jazzcash.com.pk https://accounts.google.com https://www.facebook.com; "
                "upgrade-insecure-requests;"
            )
        
        return response
    
    def process_exception(self, request, exception):
        """Handle exceptions securely"""
        
        # Log security-related exceptions
        client_ip = self.get_client_ip(request)
        logger.error(f"Exception for {request.path} from {client_ip}: {str(exception)}")
        
        # Don't expose internal errors in production
        if not settings.DEBUG:
            if request.path.startswith('/api/') or request.content_type == 'application/json':
                return JsonResponse({
                    'error': 'An error occurred processing your request',
                    'code': 'INTERNAL_ERROR'
                }, status=500)
        
        return None
    
    def get_client_ip(self, request):
        """Get client IP address safely"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        return ip