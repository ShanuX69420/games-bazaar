# marketplace/security_middleware.py

import logging
import json
from datetime import datetime
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
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
        
        # Enhanced rate limiting with multiple tiers
        cache_key = f'requests_{client_ip}'
        admin_cache_key = f'admin_requests_{client_ip}'
        api_cache_key = f'api_requests_{client_ip}'
        
        request_count = cache.get(cache_key, 0)
        admin_count = cache.get(admin_cache_key, 0)
        api_count = cache.get(api_cache_key, 0)
        
        # Stricter rate limiting for admin endpoints
        if request.path.startswith('/admin'):
            if admin_count > 200:  # 200 admin requests per hour (3+ per minute)
                logger.critical(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'ip': client_ip,
                    'path': request.path,
                    'user_agent': user_agent[:200],
                    'event_type': 'admin_rate_limit_exceeded',
                    'request_count': admin_count
                }))
                response = HttpResponse("Admin rate limit exceeded", status=429)
                response['Retry-After'] = '3600'
                response['X-RateLimit-Limit'] = '200'
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(int(datetime.now().timestamp()) + 3600)
                return response
            cache.set(admin_cache_key, admin_count + 1, 3600)
        
        # API rate limiting
        if '/api/' in request.path or request.path.startswith('/jazzcash'):
            if api_count > 1000:  # 1000 API requests per hour
                logger.critical(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'ip': client_ip,
                    'path': request.path,
                    'user_agent': user_agent[:200],
                    'event_type': 'api_rate_limit_exceeded',
                    'request_count': api_count
                }))
                response = HttpResponse("API rate limit exceeded", status=429)
                response['Retry-After'] = '3600'
                response['X-RateLimit-Limit'] = '1000'
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(int(datetime.now().timestamp()) + 3600)
                return response
            cache.set(api_cache_key, api_count + 1, 3600)
        
        # General rate limiting
        if request_count > 5000:  # Reduced from 8000 to 5000 for better security
            logger.critical(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'ip': client_ip,
                'path': request.path,
                'user_agent': user_agent[:200],
                'event_type': 'rate_limit_exceeded',
                'request_count': request_count
            }))
            response = HttpResponse("Rate limit exceeded", status=429)
            response['Retry-After'] = '3600'
            response['X-RateLimit-Limit'] = '5000'
            response['X-RateLimit-Remaining'] = '0'
            response['X-RateLimit-Reset'] = str(int(datetime.now().timestamp()) + 3600)
            return response
        
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
        
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        # Align with Django settings to avoid conflicts
        response['X-Frame-Options'] = getattr(settings, 'X_FRAME_OPTIONS', 'DENY')
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Add Cross-Origin-Opener-Policy for better browser compatibility
        response['Cross-Origin-Opener-Policy'] = 'same-origin'
        
        # CSP is centrally handled by core.middleware.CSPMiddleware.
        # Do not set Content-Security-Policy here to avoid conflicts/overrides.
        
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
