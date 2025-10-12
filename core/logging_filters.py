"""
Logging filters to prevent sensitive data from being captured in logs.
"""
import logging
import re
from typing import Dict, Any


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive data from log records."""
    
    # Patterns for sensitive data
    SENSITIVE_PATTERNS = {
        'password': re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'secret_key': re.compile(r'(secret[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'api_key': re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'token': re.compile(r'(token["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'pp_password': re.compile(r'(pp_Password["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'pp_securehash': re.compile(r'(pp_SecureHash["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'integrity_salt': re.compile(r'(integrity[_-]?salt["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
        'credit_card': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        'email_password': re.compile(r'(email[_-]?password["\']?\s*[:=]\s*["\']?)([^"\'&\s]+)', re.IGNORECASE),
    }
    
    # Fields that should be completely removed from logs
    SENSITIVE_FIELDS = {
        'pp_Password', 'pp_SecureHash', 'password', 'secret_key', 'api_key',
        'token', 'integrity_salt', 'email_password', 'csrf_token'
    }
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter sensitive data from log records."""
        try:
            # Filter message content
            if hasattr(record, 'msg') and record.msg:
                record.msg = self._redact_sensitive_data(str(record.msg))
            
            # Filter arguments
            if hasattr(record, 'args') and record.args:
                if isinstance(record.args, (list, tuple)):
                    record.args = tuple(
                        self._redact_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
                elif isinstance(record.args, dict):
                    record.args = {
                        k: self._redact_sensitive_data(str(v)) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
            
            return True
        except Exception:
            # If filtering fails, allow the log but without modification
            return True
    
    def _redact_sensitive_data(self, text: str) -> str:
        """Redact sensitive data from text."""
        if not text:
            return text
        
        # Apply pattern-based redaction
        for pattern_name, pattern in self.SENSITIVE_PATTERNS.items():
            text = pattern.sub(r'\1[REDACTED]', text)
        
        return text


class PaymentCallbackFilter(logging.Filter):
    """Specialized filter for payment callback logs."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter payment callback data to prevent logging sensitive payment info."""
        try:
            if hasattr(record, 'msg') and record.msg:
                msg = str(record.msg)
                
                # Skip logging if it contains payment callback data
                if any(keyword in msg.lower() for keyword in [
                    'pp_password', 'pp_securehash', 'payment_callback'
                ]):
                    # Replace with generic message
                    record.msg = "Payment callback processed [sensitive data redacted]"
                    record.args = ()
            
            return True
        except Exception:
            return True


class AuthenticationFilter(logging.Filter):
    """Filter for authentication-related logs."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter authentication data to prevent credential leakage."""
        try:
            if hasattr(record, 'msg') and record.msg:
                msg = str(record.msg).lower()
                
                # Redact login/auth related sensitive data
                if any(keyword in msg for keyword in [
                    'login', 'authenticate', 'password', 'credential'
                ]):
                    record.msg = self._redact_auth_data(str(record.msg))
            
            return True
        except Exception:
            return True
    
    def _redact_auth_data(self, text: str) -> str:
        """Redact authentication-specific data."""
        # Remove password values but keep the fact that auth occurred
        text = re.sub(r'password["\']?\s*[:=]\s*["\']?[^"\'&\s]+', 'password=[REDACTED]', text, flags=re.IGNORECASE)
        return text


class RequestDataFilter(logging.Filter):
    """Filter for request data to prevent logging sensitive form data."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter request data logs."""
        try:
            if hasattr(record, 'msg') and record.msg:
                msg = str(record.msg)
                
                # Check if this is a request data log
                if 'request.POST' in msg or 'form data' in msg.lower():
                    # Redact the entire POST data if it might contain sensitive info
                    record.msg = "Request data processed [POST data redacted for security]"
                    record.args = ()
            
            return True
        except Exception:
            return True
