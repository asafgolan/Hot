#!/usr/bin/env python3
"""
Authentication State Manager for Hot.net domains
Automatically extracts and manages all types of authentication data
"""
import json
import re
import os
import time
import threading
from urllib.parse import urlparse
from collections import defaultdict

class AuthStateManager:
    """Manages complete authentication state for hot.net domains"""
    
    # Cookies to exclude from auth management (only clear tracking/advertising cookies)
    EXCLUDED_COOKIES = {
        # Analytics and tracking cookies (safe to exclude)
        '_hjSession', '_hjSessionUser',  # Hotjar tracking
        '_ga', '_gid', '_gat', '_gcl_au',  # Google Analytics
        '_tt_enable_cookie', '_ttp',  # TikTok tracking
        'dicbo_id',  # Advertising tracking
        # Only clear redirect cookies (not session state)
        'redirect_url', 'redirect_to', 'return_url', 'return_to',
        'next_url', 'continue_url', 'target_url', 'goto_url',
        '_redirect', '_return', '_next', '_continue', '_target',
        'back_url', 'orig_url', 'original_url', 'prev_url',
        # Keep session cookies but exclude clear redirect cookies
        'hot_redirect', 'hot_nav', 'hot_route', 'hot_entry',
    }
    
    def __init__(self, auth_file_path):
        self.auth_file = auth_file_path
        self.auth_data = self.load_auth_state()
        self._lock = threading.RLock()  # Thread-safe operations
        self._save_pending = False
        self._last_save = 0
        self._min_save_interval = 5  # Minimum seconds between saves
    
    def load_auth_state(self):
        """Load existing authentication state"""
        if os.path.exists(self.auth_file):
            try:
                with open(self.auth_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading auth state: {e}")
        
        return {
            'domains': {},
            'last_updated': None
        }
    
    def save_auth_state(self, force=False):
        """Optimized save authentication state to disk with throttling"""
        with self._lock:
            current_time = time.time()
            
            # Throttle saves to avoid excessive disk I/O
            if not force and (current_time - self._last_save) < self._min_save_interval:
                self._save_pending = True
                return True
            
            try:
                self.auth_data['last_updated'] = int(current_time)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
                
                # Atomic write for safety
                temp_file = f"{self.auth_file}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.auth_data, f, indent=2, ensure_ascii=False)
                
                # Atomic rename
                os.rename(temp_file, self.auth_file)
                
                self._last_save = current_time
                self._save_pending = False
                
                print(f"Auth state saved with {len(self.auth_data['domains'])} domains")
                return True
                
            except Exception as e:
                print(f"Error saving auth state: {e}")
                return False
    
    def is_hot_net_domain(self, url):
        """Check if URL belongs to hot.net domains"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return 'hot.net' in domain
        except:
            return False
    
    def _should_exclude_cookie(self, cookie_name):
        """Check if a cookie should be excluded from auth management"""
        cookie_lower = cookie_name.lower()
        
        # Check exact matches first
        if cookie_name in self.EXCLUDED_COOKIES:
            print(f"🚫 EXCLUDED: Exact match cookie: {cookie_name}")
            return True
            
        # Check partial matches for tracking cookies
        for excluded in self.EXCLUDED_COOKIES:
            if excluded.endswith('_') and cookie_name.startswith(excluded):
                print(f"🚫 EXCLUDED: Prefix match cookie: {cookie_name} (matches {excluded})")
                return True
            elif excluded.startswith('_') and excluded.endswith('_') and excluded[1:-1] in cookie_lower:
                print(f"🚫 EXCLUDED: Contains match cookie: {cookie_name} (matches {excluded})")
                return True
        
        # Additional pattern-based exclusions for redirect-related cookies
        redirect_patterns = ['redirect', 'return', 'next', 'continue', 'target', 'goto', 'back', 'orig', 'prev']
        for pattern in redirect_patterns:
            if pattern in cookie_lower:
                print(f"🚫 EXCLUDED: Redirect pattern cookie: {cookie_name} (contains '{pattern}')")
                return True
                
        # Check for navigation/tracking patterns
        nav_patterns = ['nav', 'route', 'page', 'visit', 'journey', 'flow', 'state']
        for pattern in nav_patterns:
            if pattern in cookie_lower and ('_' in cookie_name or len(cookie_name) > 10):
                print(f"🚫 EXCLUDED: Navigation pattern cookie: {cookie_name} (contains '{pattern}')")
                return True
                
        return False
    
    def extract_domain_key(self, url):
        """Extract domain key for storage"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return None
    
    def extract_auth_from_response(self, url, response_headers, response_body, content_type):
        """Extract all authentication data from response"""
        if not self.is_hot_net_domain(url):
            return
        
        domain_key = self.extract_domain_key(url)
        if not domain_key:
            return
        
        print(f"Extracting auth data for domain: {domain_key}")
        
        # Initialize domain auth data
        if domain_key not in self.auth_data['domains']:
            self.auth_data['domains'][domain_key] = {
                'cookies': {},
                'tokens': {},
                'session_data': {},
                'csrf_tokens': {},
                'api_keys': {},
                'local_storage': {},
                'headers': {},
                'last_updated': int(time.time())
            }
        
        domain_auth = self.auth_data['domains'][domain_key]
        
        # Extract from headers
        self._extract_from_headers(response_headers, domain_auth)
        
        # Extract from response body based on content type
        if response_body:
            if 'html' in content_type.lower():
                self._extract_from_html(response_body, domain_auth)
            elif 'json' in content_type.lower():
                self._extract_from_json(response_body, domain_auth)
            elif 'javascript' in content_type.lower():
                self._extract_from_javascript(response_body, domain_auth)
        
        # Update timestamp
        domain_auth['last_updated'] = int(time.time())
        
        # Save state
        self.save_auth_state()
    
    def _extract_from_headers(self, headers, domain_auth):
        """Extract auth data from response headers"""
        auth_header_patterns = [
            'authorization', 'x-auth-token', 'x-api-key', 'x-session-id',
            'x-csrf-token', 'x-xsrf-token', 'x-user-token', 'x-access-token'
        ]
        
        for header_name, header_value in headers.items():
            header_lower = header_name.lower()
            
            # Store important auth headers
            if any(pattern in header_lower for pattern in auth_header_patterns):
                domain_auth['headers'][header_name] = header_value
                print(f"Captured auth header: {header_name}")
            
            # Extract tokens from various headers
            if 'token' in header_lower and header_value:
                domain_auth['tokens'][header_name] = header_value
                print(f"Captured token from header: {header_name}")
    
    def _extract_from_html(self, response_body, domain_auth):
        """Extract auth data from HTML responses"""
        try:
            if isinstance(response_body, bytes):
                content = response_body.decode('utf-8', errors='ignore')
            else:
                content = response_body
            
            # Extract CSRF tokens from meta tags
            csrf_patterns = [
                r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']',
                r'<meta[^>]*name=["\']_token["\'][^>]*content=["\']([^"\']+)["\']',
                r'<input[^>]*name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']',
                r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']'
            ]
            
            for pattern in csrf_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    domain_auth['csrf_tokens']['csrf_token'] = match
                    print(f"Captured CSRF token: {match[:20]}...")
            
            # Extract session IDs from hidden inputs
            session_patterns = [
                r'<input[^>]*name=["\']session_id["\'][^>]*value=["\']([^"\']+)["\']',
                r'<input[^>]*name=["\']JSESSIONID["\'][^>]*value=["\']([^"\']+)["\']',
                r'<input[^>]*name=["\']PHPSESSID["\'][^>]*value=["\']([^"\']+)["\']'
            ]
            
            for pattern in session_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    domain_auth['session_data']['session_id'] = match
                    print(f"Captured session ID: {match[:20]}...")
            
            # Extract localStorage data from inline scripts
            localstorage_patterns = [
                r'localStorage\.setItem\(["\']([^"\']+)["\'],\s*["\']([^"\']+)["\']',
                r'localStorage\[["\']([^"\']+)["\']\]\s*=\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in localstorage_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for key, value in matches:
                    domain_auth['local_storage'][key] = value
                    print(f"Captured localStorage: {key}={value[:20]}...")
            
            # Extract API keys and tokens from JavaScript variables
            token_patterns = [
                r'(?:apiKey|api_key|API_KEY)\s*[:=]\s*["\']([^"\']+)["\']',
                r'(?:authToken|auth_token|AUTH_TOKEN)\s*[:=]\s*["\']([^"\']+)["\']',
                r'(?:accessToken|access_token|ACCESS_TOKEN)\s*[:=]\s*["\']([^"\']+)["\']',
                r'(?:bearerToken|bearer_token|BEARER_TOKEN)\s*[:=]\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in token_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Use the pattern to determine token type
                    if 'api' in pattern.lower():
                        domain_auth['api_keys']['api_key'] = match
                        print(f"Captured API key: {match[:20]}...")
                    else:
                        domain_auth['tokens']['auth_token'] = match
                        print(f"Captured auth token: {match[:20]}...")
        
        except Exception as e:
            print(f"Error extracting from HTML: {e}")
    
    def _extract_from_json(self, response_body, domain_auth):
        """Extract auth data from JSON responses"""
        try:
            if isinstance(response_body, bytes):
                content = response_body.decode('utf-8', errors='ignore')
            else:
                content = response_body
            
            data = json.loads(content)
            
            # Common JSON auth field patterns
            auth_fields = [
                'token', 'auth_token', 'access_token', 'bearer_token',
                'api_key', 'session_id', 'user_token', 'jwt_token',
                'csrf_token', 'xsrf_token', 'refresh_token'
            ]
            
            def extract_recursive(obj, path=""):
                """Recursively extract auth fields from JSON"""
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        key_lower = key.lower()
                        current_path = f"{path}.{key}" if path else key
                        
                        # Check if this key contains auth data
                        if any(auth_field in key_lower for auth_field in auth_fields):
                            if isinstance(value, (str, int)):
                                if 'token' in key_lower:
                                    domain_auth['tokens'][key] = str(value)
                                    print(f"Captured JSON token: {key}={str(value)[:20]}...")
                                elif 'api' in key_lower:
                                    domain_auth['api_keys'][key] = str(value)
                                    print(f"Captured JSON API key: {key}={str(value)[:20]}...")
                                elif 'session' in key_lower:
                                    domain_auth['session_data'][key] = str(value)
                                    print(f"Captured JSON session: {key}={str(value)[:20]}...")
                                elif 'csrf' in key_lower or 'xsrf' in key_lower:
                                    domain_auth['csrf_tokens'][key] = str(value)
                                    print(f"Captured JSON CSRF: {key}={str(value)[:20]}...")
                        
                        # Recurse into nested objects
                        extract_recursive(value, current_path)
                
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        extract_recursive(item, f"{path}[{i}]")
            
            extract_recursive(data)
        
        except Exception as e:
            print(f"Error extracting from JSON: {e}")
    
    def _extract_from_javascript(self, response_body, domain_auth):
        """Extract auth data from JavaScript responses"""
        try:
            if isinstance(response_body, bytes):
                content = response_body.decode('utf-8', errors='ignore')
            else:
                content = response_body
            
            # Extract variable assignments
            variable_patterns = [
                r'(?:var|let|const)\s+(\w*(?:token|key|session|csrf)\w*)\s*=\s*["\']([^"\']+)["\']',
                r'window\.(\w*(?:token|key|session|csrf)\w*)\s*=\s*["\']([^"\']+)["\']',
                r'(\w*(?:token|key|session|csrf)\w*)\s*:\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in variable_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for var_name, value in matches:
                    var_lower = var_name.lower()
                    
                    if 'token' in var_lower:
                        domain_auth['tokens'][var_name] = value
                        print(f"Captured JS token: {var_name}={value[:20]}...")
                    elif 'key' in var_lower:
                        domain_auth['api_keys'][var_name] = value
                        print(f"Captured JS key: {var_name}={value[:20]}...")
                    elif 'session' in var_lower:
                        domain_auth['session_data'][var_name] = value
                        print(f"Captured JS session: {var_name}={value[:20]}...")
                    elif 'csrf' in var_lower:
                        domain_auth['csrf_tokens'][var_name] = value
                        print(f"Captured JS CSRF: {var_name}={value[:20]}...")
        
        except Exception as e:
            print(f"Error extracting from JavaScript: {e}")
    
    def apply_auth_to_headers(self, url, headers):
        """Apply stored authentication data to outgoing request headers (filtered)"""
        if not self.is_hot_net_domain(url):
            return headers
        
        domain_key = self.extract_domain_key(url)
        if not domain_key or domain_key not in self.auth_data['domains']:
            return headers
        
        domain_auth = self.auth_data['domains'][domain_key]
        
        # Apply stored auth headers (excluding problematic ones)
        for header_name, header_value in domain_auth.get('headers', {}).items():
            if not self._should_exclude_cookie(header_name):
                headers[header_name] = header_value
                print(f"Applied auth header: {header_name}")
        
        # Apply tokens as Authorization header if no auth header present
        if 'Authorization' not in headers and 'authorization' not in headers:
            for token_name, token_value in domain_auth.get('tokens', {}).items():
                if token_value and 'bearer' in token_name.lower():
                    headers['Authorization'] = f"Bearer {token_value}"
                    print(f"Applied Bearer token: {token_name}")
                    break
                elif token_value and 'auth' in token_name.lower():
                    headers['Authorization'] = f"Bearer {token_value}"
                    print(f"Applied auth token: {token_name}")
                    break
        
        # Apply API keys as headers
        for key_name, key_value in domain_auth.get('api_keys', {}).items():
            if key_value:
                # Common API key header patterns
                if 'x-api-key' not in headers:
                    headers['X-API-Key'] = key_value
                    print(f"Applied API key header")
                break
        
        # Apply CSRF tokens as headers
        for csrf_name, csrf_value in domain_auth.get('csrf_tokens', {}).items():
            if csrf_value:
                headers['X-CSRF-Token'] = csrf_value
                print(f"Applied CSRF token header")
                break
        
        return headers
    
    def get_auth_summary(self):
        """Get summary of stored authentication data"""
        summary = {}
        
        for domain, auth_data in self.auth_data.get('domains', {}).items():
            summary[domain] = {
                'cookies': len(auth_data.get('cookies', {})),
                'tokens': len(auth_data.get('tokens', {})),
                'session_data': len(auth_data.get('session_data', {})),
                'csrf_tokens': len(auth_data.get('csrf_tokens', {})),
                'api_keys': len(auth_data.get('api_keys', {})),
                'local_storage': len(auth_data.get('local_storage', {})),
                'headers': len(auth_data.get('headers', {})),
                'last_updated': auth_data.get('last_updated', 0)
            }
        
        return summary
    
    def cleanup_old_auth_data(self, max_age_days=30):
        """Clean up old authentication data to prevent memory bloat"""
        with self._lock:
            current_time = time.time()
            cutoff_time = current_time - (max_age_days * 24 * 3600)
            
            domains_to_remove = []
            for domain, auth_data in self.auth_data.get('domains', {}).items():
                last_updated = auth_data.get('last_updated', 0)
                if last_updated < cutoff_time:
                    domains_to_remove.append(domain)
            
            for domain in domains_to_remove:
                del self.auth_data['domains'][domain]
            
            if domains_to_remove:
                print(f"Cleaned up {len(domains_to_remove)} old auth domains")
                self.save_auth_state(force=True)
    
    def force_save(self):
        """Force save pending changes"""
        if self._save_pending:
            self.save_auth_state(force=True)