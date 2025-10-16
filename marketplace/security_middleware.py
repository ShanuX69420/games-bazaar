# marketplace/security_middleware.py

import logging
import json
from datetime import datetime
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.urls import NoReverseMatch, reverse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import AnonymousUser
from marketplace.login_security import (
    LOCK_MESSAGE,
    LOCKOUT_SECONDS,
    is_ip_locked,
    is_user_locked,
    normalize_identifier,
)

logger = logging.getLogger('marketplace.security')
access_logger = logging.getLogger('marketplace.access')

class SecurityMiddleware(MiddlewareMixin):
    """Enhanced security middleware for production"""
    RATE_LIMIT_WINDOW = 3600  # seconds
    login_paths_cache = None
    admin_whitelist_cache = None

    @staticmethod
    def _get_admin_root():
        """Return the admin base path with leading slash."""
        admin_slug = settings.ADMIN_URL.strip('/')
        return f'/{admin_slug}' if admin_slug else '/admin'

    @classmethod
    def get_login_paths(cls):
        """Cache and return the set of login URLs that should enforce lockouts."""
        if cls.login_paths_cache is not None:
            return cls.login_paths_cache

        paths = set()
        for view_name in ('login', 'account_login', 'admin:login'):
            try:
                paths.add(reverse(view_name))
            except NoReverseMatch:
                continue

        # Ensure trailing slash consistency
        normalized = set()
        for path in paths:
            normalized.add(path if path.endswith('/') else f'{path}/')
        cls.login_paths_cache = normalized
        return cls.login_paths_cache

    @staticmethod
    def _extract_login_identifier(request):
        """Pull username/email from the login request for lockout checks."""
        if request.method != 'POST':
            return None

        candidates = []
        if request.content_type == 'application/json':
            try:
                payload = json.loads(request.body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            candidates.extend([
                payload.get('username'),
                payload.get('login'),
                payload.get('email'),
            ])
        else:
            candidates.extend([
                request.POST.get('username'),
                request.POST.get('login'),
                request.POST.get('email'),
            ])

        for candidate in candidates:
            normalized = normalize_identifier(candidate)
            if normalized:
                return normalized
        return None

    @staticmethod
    def lockout_response(request):
        """Return a consistent response when login is temporarily blocked."""
        context = {
            'lockout_minutes': max(1, LOCKOUT_SECONDS // 60),
            'message': LOCK_MESSAGE,
        }
        if not hasattr(request, 'user'):
            request.user = AnonymousUser()
        try:
            response = render(request, 'registration/lockout.html', context, status=429)
        except TemplateDoesNotExist:
            response = HttpResponse(LOCK_MESSAGE, status=429)
        response['Retry-After'] = str(LOCKOUT_SECONDS)
        return response

    def _increment_counter(self, key, amount=1, timeout=None):
        """Increment a cache counter without overwriting existing TTL."""
        timeout = timeout or self.RATE_LIMIT_WINDOW
        try:
            return cache.incr(key, amount)
        except ValueError:
            # Key does not exist yet; create it with the requested amount.
            if cache.add(key, amount, timeout=timeout):
                return amount
            # If another process created it concurrently, increment again.
            return cache.incr(key, amount)
    
    def process_request(self, request):
        """Process incoming requests for security checks with enhanced logging"""
        
        client_ip = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        admin_root = self._get_admin_root()
        normalized_ip = normalize_identifier(client_ip)
        normalized_path = request.path if request.path.endswith('/') else f'{request.path}/'
        admin_whitelisted = self._is_admin_whitelisted(client_ip, normalized_ip)

        # Enforce login lockouts before hitting view logic
        if normalized_path in self.get_login_paths():
            if normalized_ip and is_ip_locked(normalized_ip):
                return self.lockout_response(request)

            submitted_identifier = self._extract_login_identifier(request)
            if submitted_identifier and is_user_locked(submitted_identifier):
                return self.lockout_response(request)
        
        # Log all access attempts for sensitive endpoints
        sensitive_paths = [admin_root, '/api', '/order-confirmation', '/settings']
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

        counters = cache.get_many([cache_key, admin_cache_key, api_cache_key])
        request_count = counters.get(cache_key, 0)
        admin_count = counters.get(admin_cache_key, 0)
        api_count = counters.get(api_cache_key, 0)

        now_ts = int(datetime.now().timestamp())
        
        # Stricter rate limiting for admin endpoints
        if request.path.startswith(admin_root) and not admin_whitelisted:
            if admin_count >= 200:  # 200 admin requests per hour (3+ per minute)
                logger.critical(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'ip': client_ip,
                    'path': request.path,
                    'user_agent': user_agent[:200],
                    'event_type': 'admin_rate_limit_exceeded',
                    'request_count': admin_count
                }))
                response = HttpResponse("Admin rate limit exceeded", status=429)
                response['Retry-After'] = str(self.RATE_LIMIT_WINDOW)
                response['X-RateLimit-Limit'] = '200'
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(now_ts + self.RATE_LIMIT_WINDOW)
                return response
            self._increment_counter(admin_cache_key, timeout=self.RATE_LIMIT_WINDOW)
        
        # API rate limiting
        if '/api/' in request.path:
            if api_count >= 1000:  # 1000 API requests per hour
                logger.critical(json.dumps({
                    'timestamp': datetime.now().isoformat(),
                    'ip': client_ip,
                    'path': request.path,
                    'user_agent': user_agent[:200],
                    'event_type': 'api_rate_limit_exceeded',
                    'request_count': api_count
                }))
                response = HttpResponse("API rate limit exceeded", status=429)
                response['Retry-After'] = str(self.RATE_LIMIT_WINDOW)
                response['X-RateLimit-Limit'] = '1000'
                response['X-RateLimit-Remaining'] = '0'
                response['X-RateLimit-Reset'] = str(now_ts + self.RATE_LIMIT_WINDOW)
                return response
            self._increment_counter(api_cache_key, timeout=self.RATE_LIMIT_WINDOW)
        
        # General rate limiting
        if request_count >= 5000:  # Reduced from 8000 to 5000 for better security
            logger.critical(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'ip': client_ip,
                'path': request.path,
                'user_agent': user_agent[:200],
                'event_type': 'rate_limit_exceeded',
                'request_count': request_count
            }))
            response = HttpResponse("Rate limit exceeded", status=429)
            response['Retry-After'] = str(self.RATE_LIMIT_WINDOW)
            response['X-RateLimit-Limit'] = '5000'
            response['X-RateLimit-Remaining'] = '0'
            response['X-RateLimit-Reset'] = str(now_ts + self.RATE_LIMIT_WINDOW)
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
                self._increment_counter(cache_key, amount=10, timeout=self.RATE_LIMIT_WINDOW)  # Penalty for suspicious requests
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
            self._increment_counter(cache_key, amount=20, timeout=self.RATE_LIMIT_WINDOW)  # Heavy penalty for security scanners
            return HttpResponseBadRequest("Access denied")
        
        # Increment request counter for rate limiting
        self._increment_counter(cache_key, timeout=self.RATE_LIMIT_WINDOW)
        
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

    @classmethod
    def get_admin_whitelist(cls):
        """Return cached set of whitelisted admin IP identifiers."""
        if cls.admin_whitelist_cache is not None:
            return cls.admin_whitelist_cache

        raw_whitelist = getattr(settings, 'ADMIN_RATE_LIMIT_WHITELIST', ())
        normalized = set()
        for entry in raw_whitelist:
            sanitized = str(entry).strip().strip('"').strip("'")
            if not sanitized:
                continue
            normalized.add(sanitized)
            normalized_entry = normalize_identifier(sanitized)
            if normalized_entry:
                normalized.add(normalized_entry)
        cls.admin_whitelist_cache = normalized
        return cls.admin_whitelist_cache

    def _is_admin_whitelisted(self, client_ip, normalized_ip):
        """Determine if admin rate limiting should be skipped for the request IP."""
        whitelist = self.get_admin_whitelist()
        if not whitelist:
            return False
        if client_ip in whitelist:
            return True
        if normalized_ip and normalized_ip in whitelist:
            return True
        return False
