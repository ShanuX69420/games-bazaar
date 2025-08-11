import secrets
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings


class CSPMiddleware(MiddlewareMixin):
    """Custom CSP Middleware that properly implements Content Security Policy"""
    
    def process_request(self, request):
        """Generate a unique nonce for each request"""
        request.csp_nonce = secrets.token_urlsafe(16)
    
    def process_response(self, request, response):
        """Add CSP headers to the response"""
        if not hasattr(request, 'csp_nonce'):
            request.csp_nonce = secrets.token_urlsafe(16)
        
        nonce = request.csp_nonce
        
        # Build CSP directives
        directives = []
        
        # Default src
        if hasattr(settings, 'CSP_DEFAULT_SRC'):
            directives.append(f"default-src {' '.join(settings.CSP_DEFAULT_SRC)}")
        
        # Script src with nonce
        if hasattr(settings, 'CSP_SCRIPT_SRC'):
            script_sources = []
            for src in settings.CSP_SCRIPT_SRC:
                if src == "'nonce-{nonce}'":
                    script_sources.append(f"'nonce-{nonce}'")
                else:
                    script_sources.append(src)
            directives.append(f"script-src {' '.join(script_sources)}")
        
        # Style src with nonce  
        if hasattr(settings, 'CSP_STYLE_SRC'):
            style_sources = []
            for src in settings.CSP_STYLE_SRC:
                if src == "'nonce-{nonce}'":
                    style_sources.append(f"'nonce-{nonce}'")
                else:
                    style_sources.append(src)
            directives.append(f"style-src {' '.join(style_sources)}")
        
        # Other CSP directives
        csp_directives_map = {
            'CSP_FONT_SRC': 'font-src',
            'CSP_IMG_SRC': 'img-src', 
            'CSP_CONNECT_SRC': 'connect-src',
            'CSP_FRAME_SRC': 'frame-src',
        }
        
        for setting_name, directive_name in csp_directives_map.items():
            if hasattr(settings, setting_name):
                sources = getattr(settings, setting_name)
                directives.append(f"{directive_name} {' '.join(sources)}")
        
        # Join all directives
        csp_header = '; '.join(directives)
        
        # Use report-only mode if configured
        if getattr(settings, 'CSP_REPORT_ONLY', False):
            response['Content-Security-Policy-Report-Only'] = csp_header
        else:
            response['Content-Security-Policy'] = csp_header
        
        return response