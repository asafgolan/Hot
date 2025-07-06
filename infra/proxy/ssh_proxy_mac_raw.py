#!/usr/bin/env python3
"""
SSH-based E2E Testing Proxy System - Mac Side (Raw Content Transfer)
Works with raw content files instead of JSON-embedded content
Properly emulates web traffic by preserving original content format
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import socket
import threading
import os
import time
import json
import traceback
import base64
import uuid
import gzip
import logging
import ssl
import tempfile
import subprocess
from urllib.parse import urlparse

# Configuration
PORT = 8000
DEBUG = True
MAX_CONCURRENT_REQUESTS = 12  # HTTP/2-like concurrency
REQUEST_TIMEOUT = 45  # Reduced timeout for faster failure handling
FILE_POLL_INTERVAL = 0.1  # Faster polling for response files

# Browser-like optimizations
ENABLE_COMPRESSION = True  # Compress responses when possible
COMPRESSION_MIN_SIZE = 1024  # Only compress files larger than 1KB
COMPRESSION_TYPES = ['text/html', 'text/css', 'application/javascript', 'application/json', 'text/plain']

# Setup logging
LOG_FILE = os.path.expanduser("~/Hot/infra/proxy/proxy_debug.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)

# Directories - Windows will SSH into Mac to fetch these
LOCAL_BASE_DIR = os.path.expanduser("~/Hot/infra/proxy/ssh_transfer")
LOCAL_OUTGOING = os.path.join(LOCAL_BASE_DIR, "outgoing")  # Requests for Windows
LOCAL_INCOMING = os.path.join(LOCAL_BASE_DIR, "incoming")  # Responses from Windows
LOCAL_RAW_CONTENT = os.path.join(LOCAL_BASE_DIR, "raw_content")  # Raw content files

# Ensure local directories exist
for directory in [LOCAL_OUTGOING, LOCAL_INCOMING, LOCAL_RAW_CONTENT]:
    os.makedirs(directory, exist_ok=True)

# SSL Certificate paths
SSL_CERT_DIR = os.path.join(LOCAL_BASE_DIR, "ssl_certs")
SSL_CERT_FILE = os.path.join(SSL_CERT_DIR, "proxy.crt")
SSL_KEY_FILE = os.path.join(SSL_CERT_DIR, "proxy.key")

def create_ssl_certificate():
    """Create a self-signed SSL certificate for HTTPS tunneling"""
    os.makedirs(SSL_CERT_DIR, exist_ok=True)
    
    if os.path.exists(SSL_CERT_FILE) and os.path.exists(SSL_KEY_FILE):
        logger.info("SSL certificate already exists")
        return True
    
    try:
        logger.info("Creating self-signed SSL certificate...")
        
        # Create certificate using openssl
        cmd = [
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', SSL_KEY_FILE,
            '-out', SSL_CERT_FILE, '-days', '365', '-nodes', '-subj',
            '/C=US/ST=CA/L=SF/O=HotProxy/CN=*.hot.net.il'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("SSL certificate created successfully")
            return True
        else:
            logger.error(f"Failed to create SSL certificate: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating SSL certificate: {e}")
        return False

# Global dictionary to track recent requests and prevent duplicates
recent_requests = {}

# Request processing queue for better throughput
import queue
import concurrent.futures
request_queue = queue.Queue(maxsize=50)
response_cache = {}  # Cache responses to avoid duplicate processing

# Static asset cache for Mac-side caching
static_asset_cache = {}
STATIC_CACHE_MAX_SIZE = 200
STATIC_CACHE_MAX_AGE = 3600  # 1 hour for static assets

# List of domains to ignore/handle specially
IGNORED_DOMAINS = [
    "static.ess.apple.com", "ocsp.digicert.com", "suconfig.apple.com",
    "clients2.google.com", "clients4.google.com", "ocsp.apple.com",
    "valid.apple.com", "crl.apple.com", "identity.apple.com", "gstatic.com"
]

class RawContentProxyHandler(http.server.BaseHTTPRequestHandler):
    """HTTP proxy handler that uses raw content files"""
    
    def log_message(self, format, *args):
        """Override to control logging"""
        if DEBUG:
            super().log_message(format, *args)
    
    def do_GET(self):
        self._handle_request('GET')
    
    def do_POST(self):
        self._handle_request('POST')
    
    def _handle_request(self, method):
        """Handle HTTP requests by writing files for Windows to process"""
        global recent_requests
        
        url = self.path
        if not url.startswith('http'):
            url = f'http://{url}' if not url.startswith('//') else f'http:{url}'
            
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        if DEBUG:
            print(f"{method} request: {url}")
            print(f"Host: {host}")
        
        # Check if this is an ignored domain
        for ignored_domain in IGNORED_DOMAINS:
            if ignored_domain in host:
                if DEBUG:
                    print(f"Ignoring request for {host}")
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        
        # Check if this should be proxied through Windows
        if 'hot.net' in host or 'hot-qc' in host:
            self._proxy_through_windows(method, url, parsed_url, host)
        else:
            self._direct_request(method, url)
    
    def _proxy_through_windows(self, method, url, parsed_url, host):
        """Proxy request through Windows by writing files"""
        global recent_requests
        
        if DEBUG:
            print(f"Proxying {method} {url} through Windows via SSH (raw content)")
        
        # Determine if this is a resource request
        is_resource = self._is_resource_request(parsed_url.path)
        
        # Let browser handle caching - only intercept if browser explicitly allows caching
        headers = dict(self.headers)
        
        # Check if browser is asking for cached content (has If-None-Match or If-Modified-Since)
        has_cache_headers = any(h in headers for h in ['If-None-Match', 'If-Modified-Since'])
        
        # Only use Mac cache if browser is making a conditional request
        if has_cache_headers and self._is_static_asset(url):
            static_cache_key = self._get_static_cache_key(method, url, headers)
            if static_cache_key:
                cached_response = self._get_cached_static_response(static_cache_key)
                if cached_response:
                    if DEBUG:
                        print(f"⚡ Mac cache HIT for conditional request: {url}")
                    self._send_cached_static_response(cached_response)
                    return
        
        # Create unique request ID with deduplication
        request_key = f"{method}:{url}"
        current_time = time.time()
        
        if request_key in recent_requests:
            last_time = recent_requests[request_key]['time']
            if current_time - last_time < 5:  # 5 second deduplication
                request_id = recent_requests[request_key]['id']
                duplicate_request = True
                if DEBUG:
                    print(f"Using existing request ID: {request_id}")
            else:
                request_id = str(uuid.uuid4())
                duplicate_request = False
        else:
            request_id = str(uuid.uuid4())
            duplicate_request = False
        
        # Store in recent requests
        recent_requests[request_key] = {'id': request_id, 'time': current_time}
        
        # Clean up old entries
        self._cleanup_recent_requests(current_time)
        
        # Prepare and write request data if not duplicate
        if not duplicate_request:
            request_data = self._prepare_request_data(method, url, request_id, is_resource)
            success = self._write_request_file(request_data, request_id)
            if not success:
                self.send_error(500, "Failed to write request file")
                return
        
        # Add to processing queue for better concurrency
        request_item = {
            'request_id': request_id,
            'url': url,
            'is_resource': is_resource,
            'handler': self
        }
        
        try:
            request_queue.put(request_item, timeout=1)
            # Process immediately if queue is not full
            self._wait_and_process_response(request_id, url, is_resource)
        except queue.Full:
            # If queue is full, process synchronously
            self._wait_and_process_response(request_id, url, is_resource)
    
    def _is_resource_request(self, path):
        """Determine if request is for a resource (CSS, JS, image, etc.)"""
        path_lower = path.lower()
        return path_lower.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', 
                                   '.svg', '.woff', '.woff2', '.ttf', '.eot', '.ico'))
    
    def _is_static_asset(self, url):
        """Check if URL is a static asset that should be cached on Mac"""
        # Static assets that rarely change and are good candidates for Mac-side caching
        static_extensions = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', 
                           '.ico', '.woff', '.woff2', '.ttf', '.eot', '.pdf')
        return any(url.lower().endswith(ext) for ext in static_extensions)
    
    def _get_static_cache_key(self, method, url, headers):
        """Generate cache key for static assets"""
        if method != 'GET':
            return None
        if not self._is_static_asset(url):
            return None
        
        # Include relevant headers that might affect the response
        cache_headers = []
        for header in ['Accept', 'Accept-Encoding']:
            if header in headers:
                cache_headers.append(f"{header}:{headers[header]}")
        
        cache_key = f"{url}|{'|'.join(cache_headers)}"
        return cache_key
    
    def _get_cached_static_response(self, cache_key):
        """Get cached static asset response if available"""
        if cache_key in static_asset_cache:
            cached = static_asset_cache[cache_key]
            if time.time() - cached['timestamp'] < STATIC_CACHE_MAX_AGE:
                return cached['response_data']
            else:
                # Remove expired entry
                del static_asset_cache[cache_key]
        return None
    
    def _cache_static_response(self, cache_key, response_data):
        """Cache static asset response"""
        if not cache_key:
            return
            
        # Limit cache size
        if len(static_asset_cache) >= STATIC_CACHE_MAX_SIZE:
            # Remove oldest entry
            oldest_key = min(static_asset_cache.keys(), 
                           key=lambda k: static_asset_cache[k]['timestamp'])
            del static_asset_cache[oldest_key]
        
        static_asset_cache[cache_key] = {
            'response_data': response_data,
            'timestamp': time.time()
        }
        if DEBUG:
            print(f"💾 Cached static asset: {cache_key[:100]}...")
    
    def _send_cached_static_response(self, cached_response):
        """Send cached static asset response directly to browser"""
        try:
            status_code = cached_response.get('status', 200)
            headers = cached_response.get('headers', {})
            content_bytes = cached_response.get('content_bytes', b'')
            
            self.send_response(status_code)
            
            # Send headers with cache indicators
            skip_headers = {'transfer-encoding', 'content-length', 'connection'}
            for header, value in headers.items():
                if header.lower() not in skip_headers:
                    self.send_header(header, value)
            
            self.send_header('Content-Length', str(len(content_bytes)))
            self.send_header('X-Cache', 'MAC-HIT')  # Indicate Mac-side cache hit
            self.end_headers()
            
            if content_bytes:
                self.wfile.write(content_bytes)
                
            if DEBUG:
                print(f"⚡ Served from Mac cache: {status_code} ({len(content_bytes)} bytes)")
                
        except Exception as e:
            if DEBUG:
                print(f"Error sending cached static response: {e}")
            self.send_error(500, "Cache error")
    
    def _prepare_request_data(self, method, url, request_id, is_resource):
        """Prepare request data for transfer"""
        headers = dict(self.headers)
        
        # Read body for POST requests
        body = ""
        body_encoding = "utf-8"
        if method == 'POST':
            content_length = int(headers.get('Content-Length', 0))
            if content_length > 0:
                body_bytes = self.rfile.read(content_length)
                try:
                    body = body_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    body = base64.b64encode(body_bytes).decode('ascii')
                    body_encoding = "base64"
        
        # Determine if likely binary
        likely_binary = self._is_likely_binary(url)
        
        # Enhanced URL handling for hot.net domains
        final_url = self._enhance_url_for_hotnet(url, headers)
        
        return {
            "id": request_id,
            "timestamp": int(time.time()),
            "method": method,
            "url": final_url,
            "original_url": url,
            "headers": headers,
            "body": body,
            "body_encoding": body_encoding,
            "is_resource": is_resource,
            "likely_binary": likely_binary,
            "preserve_encoding": True  # Flag to preserve gzip/compression
        }
    
    def _enhance_url_for_hotnet(self, url, headers):
        """Enhance URL handling for hot.net domains, similar to original logic"""
        parsed_url = urlparse(url)
        
        # Check if URL should be HTTPS based on various factors
        use_https = parsed_url.scheme == 'https'
        
        # For hot-buzz domains, always use HTTPS
        if 'hot-buzz' in parsed_url.netloc:
            use_https = True
            if DEBUG:
                print(f"Detected hot-buzz domain, using HTTPS: {parsed_url.netloc}")
        
        # Handle relative URLs using referer
        if not url.startswith('http') and headers.get('Referer'):
            referer_parsed = urlparse(headers.get('Referer'))
            if referer_parsed.scheme == 'https':
                use_https = True
            
            base_url = f"{referer_parsed.scheme}://{referer_parsed.netloc}"
            if url.startswith('/'):
                url = f"{base_url}{url}"
            else:
                # Relative to current path
                path_parts = referer_parsed.path.split('/')
                if path_parts and path_parts[-1] and '.' in path_parts[-1]:
                    path_parts.pop()
                base_path = '/'.join(path_parts)
                url = f"{base_url}{base_path}/{url}"
            
            if DEBUG:
                print(f"Corrected relative URL using referer: {url}")
        
        # Apply HTTPS if needed
        if use_https and url.startswith('http://'):
            url = 'https://' + url[7:]
        elif use_https and not url.startswith('https://'):
            url = 'https://' + url
        
        return url
    
    def _is_likely_binary(self, url):
        """Determine if URL likely returns binary content"""
        binary_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.ico', '.pdf', 
                           '.woff', '.woff2', '.ttf', '.eot', '.zip', '.exe')
        url_lower = url.lower()
        
        # Check URL extension
        if url_lower.endswith(binary_extensions):
            return True
        
        # Check for image paths
        if '/images/' in url_lower or '/img/' in url_lower:
            return True
            
        return False
    
    def _write_request_file(self, request_data, request_id):
        """Write request file for Windows to fetch"""
        try:
            request_file = os.path.join(LOCAL_OUTGOING, f"req_{request_id}.json")
            
            with open(request_file, 'w', encoding='utf-8') as f:
                json.dump(request_data, f, indent=2, ensure_ascii=False)
            
            if DEBUG:
                print(f"Written request file: {request_file}")
            
            return True
            
        except Exception as e:
            if DEBUG:
                print(f"Error writing request file: {e}")
            return False
    
    def _wait_and_process_response(self, request_id, url, is_resource):
        """Optimized wait for response file from Windows with caching"""
        # Check response cache first
        cache_key = f"{request_id}_{url}"
        if cache_key in response_cache:
            cached_response = response_cache[cache_key]
            if time.time() - cached_response['timestamp'] < 300:  # 5 min cache
                if DEBUG:
                    print(f"Using cached response for: {url}")
                self._send_cached_response(cached_response)
                return
        
        timeout = REQUEST_TIMEOUT
        start_time = time.time()
        response_file = os.path.join(LOCAL_INCOMING, f"resp_{request_id}.json")
        
        # Optimized polling with adaptive intervals
        poll_count = 0
        while not os.path.exists(response_file) and (time.time() - start_time < timeout):
            poll_count += 1
            # Adaptive polling: faster initially, slower as time progresses
            if poll_count < 50:  # First 5 seconds
                time.sleep(FILE_POLL_INTERVAL)
            elif poll_count < 150:  # Next 20 seconds  
                time.sleep(0.2)
            else:  # After 25 seconds
                time.sleep(0.5)
        
        if os.path.exists(response_file):
            try:
                response_data = self._process_response_file(response_file, url, is_resource)
                
                # Cache successful responses for resources
                if is_resource and response_data:
                    response_cache[cache_key] = {
                        'data': response_data,
                        'timestamp': time.time()
                    }
                    # Limit cache size
                    if len(response_cache) > 100:
                        oldest_key = min(response_cache.keys(), 
                                       key=lambda k: response_cache[k]['timestamp'])
                        del response_cache[oldest_key]
                
                # Clean up response file
                os.remove(response_file)
                if DEBUG:
                    print(f"Cleaned up response file: {response_file}")
                    
            except Exception as e:
                if DEBUG:
                    print(f"Error processing response: {e}")
                    traceback.print_exc()
                
                # For static assets, return empty response instead of 500 error
                if is_resource:
                    print(f"⚠️ Static asset error for {url}, returning empty response")
                    self.send_response(200)
                    if url.endswith('.css'):
                        self.send_header('Content-Type', 'text/css')
                    elif url.endswith('.js'):
                        self.send_header('Content-Type', 'application/javascript')
                    elif url.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        self.send_header('Content-Type', 'image/png')
                    else:
                        self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', '0')
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                else:
                    self.send_error(500, f"Error processing response: {str(e)}")
        else:
            # Timeout - more graceful handling
            if DEBUG:
                print(f"Timeout waiting for response: {request_id} ({timeout}s)")
            
            if is_resource:
                # For resources, return minimal response
                self._send_empty_resource_response(url)
            else:
                self.send_error(504, "Gateway Timeout - No response from Windows")
    
    def _send_empty_resource_response(self, url):
        """Send optimized empty response for resource timeouts"""
        self.send_response(200)
        if url.endswith('.css'):
            self.send_header('Content-Type', 'text/css')
        elif url.endswith('.js'):
            self.send_header('Content-Type', 'application/javascript')
        elif url.endswith(('.png', '.jpg', '.jpeg', '.gif')):
            self.send_header('Content-Type', 'image/png')
        else:
            self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
    
    def _send_cached_response(self, cached_response):
        """Send cached response to client"""
        try:
            response_data = cached_response['data']
            status_code = response_data.get('status', 200)
            headers = response_data.get('headers', {})
            content_bytes = response_data.get('content_bytes', b'')
            
            self.send_response(status_code)
            
            # Send headers
            skip_headers = {'transfer-encoding', 'content-length', 'connection'}
            for header, value in headers.items():
                if header.lower() not in skip_headers:
                    self.send_header(header, value)
            
            self.send_header('Content-Length', str(len(content_bytes)))
            self.send_header('X-Cache', 'HIT')
            self.end_headers()
            
            if content_bytes:
                self.wfile.write(content_bytes)
                
        except Exception as e:
            if DEBUG:
                print(f"Error sending cached response: {e}")
            self.send_error(500, "Cache error")
    
    def _process_response_file(self, response_file, url, is_resource):
        """Process response file and send to client using raw content files"""
        try:
            with open(response_file, 'r', encoding='utf-8') as f:
                response_data = json.load(f)
            
            status_code = int(response_data.get('status', 500))
            headers = response_data.get('headers', {})
            raw_content_file = response_data.get('raw_content_file')
            content_size = response_data.get('content_size', 0)
            inline_content = response_data.get('content', '')
            is_binary = response_data.get('is_binary', False)
            
            # Handle 304 Not Modified
            if status_code == 304:
                if DEBUG:
                    print(f"Received 304 Not Modified response")
                self.send_response(304)
                for header, value in headers.items():
                    if header.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(header, value)
                self.end_headers()
                return
            
            # Get content bytes from raw file or inline content
            content_bytes = b''
            
            if raw_content_file:
                # Read from raw content file
                raw_content_path = os.path.join(LOCAL_RAW_CONTENT, raw_content_file)
                
                if os.path.exists(raw_content_path):
                    with open(raw_content_path, 'rb') as f:
                        content_bytes = f.read()
                    
                    if DEBUG:
                        print(f"Read {len(content_bytes)} bytes from raw content file: {raw_content_file}")
                    
                    # Clean up raw content file after reading
                    try:
                        os.remove(raw_content_path)
                        if DEBUG:
                            print(f"Cleaned up raw content file: {raw_content_file}")
                    except Exception as e:
                        if DEBUG:
                            print(f"Error cleaning up raw content file: {e}")
                else:
                    if DEBUG:
                        print(f"Raw content file not found: {raw_content_path}")
                    
                    # For static assets, return empty response instead of 500 error
                    if self._is_static_asset(url):
                        if DEBUG:
                            print(f"Returning empty response for missing static asset: {url}")
                        self.send_response(200)
                        self.send_header('Content-Type', headers.get('Content-Type', 'application/octet-stream'))
                        self.send_header('Content-Length', '0')
                        self.send_header('Cache-Control', 'no-cache')
                        self.end_headers()
                        return
                    else:
                        self.send_error(500, "Raw content file not found")
                        return
            
            elif inline_content:
                # Use inline content for small responses
                if is_binary:
                    content_bytes = base64.b64decode(inline_content)
                else:
                    content_bytes = inline_content.encode('utf-8')
            
            # Enhanced HTML URL rewriting and resource hints for better resource loading
            if not is_binary and 'text/html' in headers.get('Content-Type', ''):
                content_bytes = self._rewrite_html_urls(content_bytes, url)
                content_bytes = self._add_resource_hints(content_bytes, url)
            
            # Apply compression for browser-like performance
            original_size = len(content_bytes)
            content_bytes, compression_applied = self._apply_compression(content_bytes, headers)
            
            if compression_applied and DEBUG:
                compressed_size = len(content_bytes)
                ratio = (1 - compressed_size / original_size) * 100
                print(f"Applied compression: {original_size}→{compressed_size} bytes ({ratio:.1f}% reduction)")
            
            # Send response
            self.send_response(status_code)
            
            # Send headers (skip problematic ones)
            skip_headers = {'transfer-encoding', 'content-length', 'connection'}
            for header, value in headers.items():
                if header.lower() not in skip_headers:
                    self.send_header(header, value)
            
            self.send_header('Content-Length', str(len(content_bytes)))
            self.end_headers()
            
            # Send content
            if content_bytes:
                self.wfile.write(content_bytes)
            
            if DEBUG:
                print(f"Response sent: {status_code} ({len(content_bytes)} bytes)")
            
            # Only cache static assets that have proper cache headers and ETags
            if (self._is_static_asset(url) and status_code == 200 and 
                len(content_bytes) > 0 and len(content_bytes) < 2 * 1024 * 1024 and  # Cache up to 2MB
                headers.get('ETag') and  # Only cache if server provides ETag
                any(h in headers for h in ['Cache-Control', 'Expires'])):  # And cache headers
                
                static_cache_key = self._get_static_cache_key('GET', url, {})
                if static_cache_key:
                    cache_data = {
                        'status': status_code,
                        'headers': headers.copy(),
                        'content_bytes': content_bytes
                    }
                    self._cache_static_response(static_cache_key, cache_data)
            
            # Return response data for caching
            return {
                'status': status_code,
                'headers': headers,
                'content_bytes': content_bytes
            }
                
        except Exception as e:
            if DEBUG:
                print(f"Error processing response file: {e}")
                traceback.print_exc()
            raise
        
        return None
    
    def _rewrite_html_urls(self, content_bytes, base_url):
        """Rewrite relative URLs in HTML to be absolute"""
        try:
            content = content_bytes.decode('utf-8')
            parsed_base = urlparse(base_url)
            base_domain_url = f"{parsed_base.scheme}://{parsed_base.netloc}"
            
            import re
            
            def make_absolute(match):
                resource_url = match.group(2)
                # Skip URLs that are already absolute
                if resource_url.startswith(('http://', 'https://', '//', 'data:', 'javascript:', 'mailto:')):
                    return match.group(0)
                
                # Make relative URL absolute
                if resource_url.startswith('/'):
                    return f'{match.group(1)}{base_domain_url}{resource_url}{match.group(3)}'
                else:
                    # Relative to current path
                    path_parts = parsed_base.path.split('/')
                    if path_parts and path_parts[-1] and '.' in path_parts[-1]:
                        path_parts.pop()
                    dir_path = '/'.join(path_parts)
                    if not dir_path.endswith('/'):
                        dir_path += '/'
                    return f'{match.group(1)}{base_domain_url}{dir_path}{resource_url}{match.group(3)}'
            
            # Rewrite URLs in various HTML attributes
            content = re.sub(r'(href=["\'])([^"\']*)(["\'])', make_absolute, content)
            content = re.sub(r'(src=["\'])([^"\']*)(["\'])', make_absolute, content)
            content = re.sub(r'(url\(["\']?)([^\)"\']*)(["\']?\))', make_absolute, content)
            
            if DEBUG:
                print(f"Rewrote HTML URLs to be absolute")
            
            return content.encode('utf-8')
            
        except Exception as e:
            if DEBUG:
                print(f"Error rewriting HTML URLs: {e}")
            return content_bytes
    
    def _wait_for_file_complete(self, response_file, max_wait=5.0):
        """Wait for file to be completely written by checking size stability"""
        last_size = -1
        stable_count = 0
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                current_size = os.path.getsize(response_file)
                if current_size == 0:
                    time.sleep(0.1)
                    continue
                    
                if current_size == last_size:
                    stable_count += 1
                    if stable_count >= 3:  # Size stable for 3 checks
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
                    
                time.sleep(0.1)
            except (OSError, FileNotFoundError):
                time.sleep(0.1)
                continue
        
        return False
    
    def _read_response_file_with_retry(self, response_file, max_retries=3):
        """Read JSON file with retry logic for race conditions"""
        for attempt in range(max_retries):
            try:
                with open(response_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        if attempt < max_retries - 1:
                            logger.warning(f"🟡 RESPONSE: Empty file on attempt {attempt + 1}, retrying...")
                            time.sleep(0.2)
                            continue
                        else:
                            logger.error(f"🔴 RESPONSE: File {response_file} is empty after {max_retries} attempts")
                            return None
                    
                    return json.loads(content)
                    
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"🟡 RESPONSE: JSON decode error on attempt {attempt + 1}: {e}, retrying...")
                    time.sleep(0.2)
                    continue
                else:
                    logger.error(f"🔴 RESPONSE: JSON decode failed after {max_retries} attempts: {e}")
                    return None
            except Exception as e:
                logger.error(f"🔴 RESPONSE: File read error: {e}")
                return None
        
        return None
    
    def _apply_compression(self, content_bytes, headers):
        """Apply compression to response content for browser-like performance"""
        if not ENABLE_COMPRESSION or len(content_bytes) < COMPRESSION_MIN_SIZE:
            return content_bytes, False
        
        content_type = headers.get('Content-Type', '').lower()
        
        # Only compress text-based content types
        should_compress = any(ctype in content_type for ctype in COMPRESSION_TYPES)
        if not should_compress:
            return content_bytes, False
        
        # Check if client accepts gzip compression
        client_accepts_gzip = 'gzip' in self.headers.get('Accept-Encoding', '').lower()
        if not client_accepts_gzip:
            return content_bytes, False
        
        try:
            # Compress using gzip
            compressed_data = gzip.compress(content_bytes)
            
            # Only use compression if it actually reduces size significantly
            if len(compressed_data) < len(content_bytes) * 0.9:  # At least 10% reduction
                headers['Content-Encoding'] = 'gzip'
                headers['Vary'] = 'Accept-Encoding'
                return compressed_data, True
            else:
                return content_bytes, False
                
        except Exception as e:
            if DEBUG:
                print(f"Compression failed: {e}")
            return content_bytes, False
    
    def _add_resource_hints(self, content_bytes, base_url):
        """Add browser resource hints for better performance"""
        try:
            content = content_bytes.decode('utf-8')
            parsed_base = urlparse(base_url)
            base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
            
            # Find the </head> tag to insert resource hints
            head_end = content.find('</head>')
            if head_end == -1:
                return content_bytes
            
            # Generate resource hints based on common patterns
            hints = []
            
            # DNS prefetch for external domains
            hints.append(f'<link rel="dns-prefetch" href="{base_domain}">')
            
            # Preconnect to same origin
            hints.append(f'<link rel="preconnect" href="{base_domain}">')
            
            # Common CSS/JS preload patterns for hot.net
            if 'hot.net' in base_domain:
                hints.extend([
                    '<link rel="preload" href="/assets/css/main.css" as="style" onload="this.onload=null;this.rel=\'stylesheet\'">',
                    '<link rel="preload" href="/assets/js/app.js" as="script">',
                    '<link rel="preload" href="/assets/fonts/main.woff2" as="font" type="font/woff2" crossorigin>',
                ])
            
            # Insert hints before </head>
            hints_html = '\n' + '\n'.join(hints) + '\n'
            content = content[:head_end] + hints_html + content[head_end:]
            
            if DEBUG:
                print(f"Added {len(hints)} resource hints to HTML")
            
            return content.encode('utf-8')
            
        except Exception as e:
            if DEBUG:
                print(f"Error adding resource hints: {e}")
            return content_bytes
    
    def _direct_request(self, method, url):
        """Handle direct requests (non-proxied)"""
        try:
            if DEBUG:
                print(f"Direct {method} request: {url}")
            
            # Create request
            if method == 'POST':
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length) if content_length > 0 else None
                req = urllib.request.Request(url, data=post_data, method=method)
            else:
                req = urllib.request.Request(url, method=method)
            
            # Copy headers
            for header in self.headers:
                if header.lower() not in ('host', 'proxy-connection', 'content-length'):
                    req.add_header(header, self.headers[header])
            
            # Make request with connection handling
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    self.send_response(response.status)
                    
                    # Send headers, skip content-encoding to avoid double compression
                    for header, value in response.getheaders():
                        if header.lower() not in ('transfer-encoding', 'connection', 'content-encoding'):
                            self.send_header(header, value)
                    
                    self.end_headers()
                    self.wfile.write(response.read())
                    
            except (ConnectionResetError, BrokenPipeError) as e:
                if DEBUG:
                    print(f"Client disconnected during direct request: {e}")
                return
                
        except Exception as e:
            if DEBUG:
                print(f"Error in direct request: {e}")
            self.send_error(500, f"Error: {str(e)}")
    
    def _cleanup_recent_requests(self, current_time):
        """Clean up old entries from recent_requests"""
        global recent_requests
        to_delete = []
        for key, value in recent_requests.items():
            if current_time - value['time'] > 300:  # 5 minutes
                to_delete.append(key)
        for key in to_delete:
            del recent_requests[key]
    
    def do_CONNECT(self):
        """Handle HTTPS CONNECT requests"""
        host_port = self.path.split(':')
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 443
        
        logger.info(f"CONNECT request to: {host}:{port}")
        
        if 'hot.net' in host:
            # For hot.net domains, convert HTTPS CONNECT to HTTP processing via SSH
            logger.info(f"Converting HTTPS CONNECT to HTTP processing for hot.net domain: {host}")
            
            try:
                # Send connection established to browser
                self.send_response(200, 'Connection Established')
                self.end_headers()
                
                # Start HTTPS-to-HTTP proxy tunnel for hot.net
                self._handle_https_to_http_tunnel(host, port)
                
            except Exception as e:
                logger.error(f"Error in HTTPS-to-HTTP conversion for {host}: {e}")
                logger.error(traceback.format_exc())
                self.send_error(502, "Bad Gateway - HTTPS conversion failed")
            return
        
        # For other domains, create direct tunnel
        try:
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.connect((host, port))
            
            self.send_response(200, 'Connection Established')
            self.end_headers()
            
            client_socket = self.connection
            
            def forward_data(source, destination):
                try:
                    while True:
                        data = source.recv(4096)
                        if len(data) == 0:
                            break
                        destination.send(data)
                except:
                    pass
                finally:
                    for s in [client_socket, target_socket]:
                        try:
                            if not s._closed:
                                s.shutdown(socket.SHUT_RDWR)
                                s.close()
                        except:
                            pass
            
            threading.Thread(target=forward_data, args=(client_socket, target_socket), daemon=True).start()
            forward_data(target_socket, client_socket)
            
        except Exception as e:
            if DEBUG:
                print(f"CONNECT error: {e}")
            self.send_error(502, "Bad Gateway")
    
    def _handle_https_to_http_tunnel(self, host, port):
        """Handle HTTPS tunnel by converting requests to HTTP processing via SSH"""
        client_socket = self.connection
        
        logger.info(f"🔵 TUNNEL START: Starting SSL-terminated HTTPS tunnel for {host}:{port}")
        
        try:
            # Create SSL context and wrap the client socket
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(SSL_CERT_FILE, SSL_KEY_FILE)
            
            # Wrap the client socket with SSL
            logger.info("🔵 TUNNEL: Performing SSL handshake...")
            ssl_socket = ssl_context.wrap_socket(client_socket, server_side=True)
            logger.info("🔵 TUNNEL: SSL handshake completed successfully")
            
            request_count = 0
            while True:
                request_count += 1
                logger.info(f"🔵 TUNNEL: Waiting for request #{request_count} from browser...")
                
                # Read HTTP request from SSL-decrypted tunnel
                request_data = self._read_http_request_from_ssl_tunnel(ssl_socket)
                
                if not request_data:
                    logger.info(f"🔵 TUNNEL: No more requests, connection closed by browser")
                    break  # Connection closed
                
                # Parse the HTTP request
                method, path, headers, body = request_data
                
                # Convert to HTTPS URL for processing
                https_url = f"https://{host}{path}"
                
                logger.info(f"🔵 TUNNEL: Received request #{request_count}: {method} {https_url}")
                logger.info(f"🔵 TUNNEL: Headers: {list(headers.keys())}")
                logger.info(f"🔵 TUNNEL: Body length: {len(body)} bytes")
                
                # Process request through SSH system (similar to _proxy_through_windows)
                self._process_tunneled_request(method, https_url, headers, body, ssl_socket, host, request_count)
                
        except ssl.SSLError as e:
            logger.error(f"🔴 TUNNEL SSL ERROR: SSL handshake failed: {e}")
        except Exception as e:
            logger.error(f"🔴 TUNNEL ERROR: Error in HTTPS tunnel handling: {e}")
            logger.error(traceback.format_exc())
        finally:
            logger.info(f"🔵 TUNNEL END: Closing tunnel for {host}")
            try:
                if 'ssl_socket' in locals():
                    ssl_socket.close()
                else:
                    client_socket.close()
            except:
                pass
    
    def _read_http_request_from_ssl_tunnel(self, ssl_socket):
        """Read and parse HTTP request from SSL-decrypted tunnel"""
        try:
            logger.info("🔍 SSL TUNNEL READ: Starting to read HTTP data from SSL socket...")
            
            # Read request line and headers
            request_lines = []
            current_line = b""
            bytes_read = 0
            
            while True:
                try:
                    data = ssl_socket.recv(1)
                except ssl.SSLWantReadError:
                    continue
                except ssl.SSLError as e:
                    logger.error(f"🔍 SSL TUNNEL READ: SSL error: {e}")
                    return None
                
                if not data:
                    logger.warning(f"🔍 SSL TUNNEL READ: SSL connection closed after {bytes_read} bytes")
                    return None
                
                bytes_read += 1
                current_line += data
                
                # Log first few bytes to see what we're getting
                if bytes_read <= 20:
                    try:
                        decoded = data.decode('utf-8')
                        printable = decoded if decoded.isprintable() else 'non-printable'
                    except:
                        printable = 'non-printable'
                    logger.info(f"🔍 SSL TUNNEL READ: Byte {bytes_read}: {data.hex()} ({printable})")
                
                if current_line.endswith(b"\r\n"):
                    try:
                        line = current_line[:-2].decode('utf-8')
                        request_lines.append(line)
                        logger.info(f"🔍 SSL TUNNEL READ: Parsed line: '{line}'")
                        current_line = b""
                        
                        # Empty line indicates end of headers
                        if line == "":
                            logger.info("🔍 SSL TUNNEL READ: Found end of headers")
                            break
                    except UnicodeDecodeError as e:
                        logger.error(f"🔍 SSL TUNNEL READ: Unicode decode error: {e}")
                        logger.error(f"🔍 SSL TUNNEL READ: Raw bytes: {current_line.hex()}")
                        return None
            
            if not request_lines:
                return None
            
            # Parse request line
            request_line = request_lines[0]
            parts = request_line.split(' ')
            if len(parts) < 3:
                return None
                
            method = parts[0]
            path = parts[1]
            
            # Parse headers
            headers = {}
            for line in request_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            
            # Read body if present
            body = b""
            content_length = int(headers.get('Content-Length', 0))
            if content_length > 0:
                while len(body) < content_length:
                    chunk = ssl_socket.recv(min(4096, content_length - len(body)))
                    if not chunk:
                        break
                    body += chunk
            
            logger.info(f"🔍 SSL TUNNEL READ: Successfully parsed {method} {path} with {len(headers)} headers and {len(body)} body bytes")
            return (method, path, headers, body)
            
        except Exception as e:
            logger.error(f"🔍 SSL TUNNEL READ: Error reading HTTP request from SSL tunnel: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _read_http_request_from_tunnel(self, client_socket):
        """Read and parse HTTP request from HTTPS tunnel"""
        try:
            logger.info("🔍 TUNNEL READ: Starting to read data from browser...")
            
            # Read request line and headers
            request_lines = []
            current_line = b""
            bytes_read = 0
            
            while True:
                data = client_socket.recv(1)
                if not data:
                    logger.warning(f"🔍 TUNNEL READ: Connection closed after {bytes_read} bytes")
                    return None  # Connection closed
                
                bytes_read += 1
                current_line += data
                
                # Log first few bytes to see what we're getting
                if bytes_read <= 20:
                    try:
                        decoded = data.decode('utf-8')
                        printable = decoded if decoded.isprintable() else 'non-printable'
                    except:
                        printable = 'non-printable'
                    logger.info(f"🔍 TUNNEL READ: Byte {bytes_read}: {data.hex()} ({printable})")
                
                if current_line.endswith(b"\r\n"):
                    try:
                        line = current_line[:-2].decode('utf-8')
                        request_lines.append(line)
                        logger.info(f"🔍 TUNNEL READ: Parsed line: '{line}'")
                        current_line = b""
                        
                        # Empty line indicates end of headers
                        if line == "":
                            logger.info("🔍 TUNNEL READ: Found end of headers")
                            break
                    except UnicodeDecodeError as e:
                        logger.error(f"🔍 TUNNEL READ: Unicode decode error: {e}")
                        logger.error(f"🔍 TUNNEL READ: Raw bytes: {current_line.hex()}")
                        return None
            
            if not request_lines:
                return None
            
            # Parse request line
            request_line = request_lines[0]
            parts = request_line.split(' ')
            if len(parts) < 3:
                return None
                
            method = parts[0]
            path = parts[1]
            
            # Parse headers
            headers = {}
            for line in request_lines[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            
            # Read body if present
            body = b""
            content_length = int(headers.get('Content-Length', 0))
            if content_length > 0:
                while len(body) < content_length:
                    chunk = client_socket.recv(min(4096, content_length - len(body)))
                    if not chunk:
                        break
                    body += chunk
            
            return (method, path, headers, body)
            
        except Exception as e:
            logger.error(f"Error reading HTTP request from tunnel: {e}")
            return None
    
    def _process_tunneled_request(self, method, url, headers, body, client_socket, host, request_count):
        """Process tunneled request through SSH system and return response"""
        try:
            # Create request similar to _proxy_through_windows but for HTTPS
            parsed_url = urlparse(url)
            is_resource = self._is_resource_request(parsed_url.path)
            
            # Generate request ID
            request_id = str(uuid.uuid4())
            
            logger.info(f"🟡 PROCESS: Processing tunneled request #{request_count}: {method} {url}")
            logger.info(f"🟡 PROCESS: Request ID: {request_id}")
            logger.info(f"🟡 PROCESS: Is resource: {is_resource}")
            
            # Prepare request data for SSH processing
            request_data = {
                "id": request_id,
                "timestamp": int(time.time()),
                "method": method,
                "url": url,
                "headers": headers,
                "body": body.decode('utf-8') if body else "",
                "body_encoding": "utf-8",
                "is_resource": is_resource,
                "likely_binary": self._is_likely_binary(url),
                "preserve_encoding": True,
                "tunneled_https": True  # Flag to indicate this came from HTTPS tunnel
            }
            
            # Write request file for Windows to process
            logger.info(f"🟡 PROCESS: Writing request file for Windows...")
            success = self._write_request_file(request_data, request_id)
            if not success:
                logger.error(f"🔴 PROCESS ERROR: Failed to write request file")
                self._send_tunnel_error_response(client_socket, 500, "Failed to process request")
                return
            
            logger.info(f"🟡 PROCESS: Request file written, waiting for response...")
            
            # Wait for response and send back through tunnel
            self._wait_and_send_tunnel_response(request_id, client_socket, url, is_resource, request_count)
            
        except Exception as e:
            logger.error(f"🔴 PROCESS ERROR: Error processing tunneled request #{request_count}: {e}")
            logger.error(traceback.format_exc())
            self._send_tunnel_error_response(client_socket, 500, "Internal Server Error")
    
    def _wait_and_send_tunnel_response(self, request_id, client_socket, url, is_resource, request_count):
        """Optimized wait for SSH response and send back through HTTPS tunnel"""
        timeout = REQUEST_TIMEOUT
        start_time = time.time()
        response_file = os.path.join(LOCAL_INCOMING, f"resp_{request_id}.json")
        
        logger.info(f"🟢 RESPONSE: Waiting for response file: {response_file}")
        
        # Optimized polling with adaptive intervals
        poll_count = 0
        while not os.path.exists(response_file) and (time.time() - start_time < timeout):
            poll_count += 1
            
            # Log less frequently to reduce overhead
            if poll_count % 50 == 0:  # Log every 5-10 seconds depending on interval
                elapsed = time.time() - start_time
                logger.info(f"🟢 RESPONSE: Still waiting... ({elapsed:.1f}s)")
            
            # Adaptive polling intervals
            if poll_count < 100:  # First 10 seconds
                time.sleep(FILE_POLL_INTERVAL)
            elif poll_count < 250:  # Next 30 seconds
                time.sleep(0.2)
            else:  # After 40 seconds
                time.sleep(0.5)
        
        if os.path.exists(response_file):
            try:
                logger.info(f"🟢 RESPONSE: Found response file after {time.time() - start_time:.1f}s")
                
                # Wait for file to be completely written (fix race condition)
                if not self._wait_for_file_complete(response_file):
                    logger.error(f"🔴 RESPONSE ERROR: File {response_file} incomplete after timeout")
                    self._send_tunnel_error_response(client_socket, 500, "Incomplete response file")
                    return
                
                # Read response data with retry logic
                response_data = self._read_response_file_with_retry(response_file)
                if not response_data:
                    logger.error(f"🔴 RESPONSE ERROR: Failed to read response file {response_file}")
                    self._send_tunnel_error_response(client_socket, 500, "Response file read error")
                    return
                
                status = response_data.get('status', 'unknown')
                content_size = response_data.get('content_size', 0)
                raw_file = response_data.get('raw_content_file', 'none')
                logger.info(f"🟢 RESPONSE: Status {status}, Size {content_size}, Raw file: {raw_file}")
                
                # Send HTTP response through tunnel
                self._send_tunnel_http_response(client_socket, response_data, url, request_count)
                
                # Clean up response file
                os.remove(response_file)
                logger.info(f"🟢 RESPONSE: Sent tunnel response #{request_count} and cleaned up file")
                    
            except Exception as e:
                logger.error(f"🔴 RESPONSE ERROR: Error processing tunnel response #{request_count}: {e}")
                logger.error(traceback.format_exc())
                self._send_tunnel_error_response(client_socket, 500, "Response processing error")
        else:
            # Timeout
            logger.error(f"🔴 RESPONSE TIMEOUT: No response file found after {timeout}s for request #{request_count}")
            # Check if there are any response files at all
            incoming_files = os.listdir(LOCAL_INCOMING)
            logger.error(f"🔴 RESPONSE TIMEOUT: Files in incoming dir: {incoming_files}")
            self._send_tunnel_error_response(client_socket, 504, "Gateway Timeout")
    
    def _send_tunnel_http_response(self, client_socket, response_data, url, request_count):
        """Send HTTP response through HTTPS tunnel"""
        try:
            status_code = int(response_data.get('status', 500))
            headers = response_data.get('headers', {})
            raw_content_file = response_data.get('raw_content_file')
            inline_content = response_data.get('content', '')
            is_binary = response_data.get('is_binary', False)
            
            logger.info(f"🔵 SEND: Preparing tunnel response #{request_count} - Status {status_code}")
            logger.info(f"🔵 SEND: Raw file: {raw_content_file}, Inline content: {len(inline_content)} chars")
            
            # Get content bytes
            content_bytes = b''
            
            if raw_content_file:
                # Read from raw content file
                raw_content_path = os.path.join(LOCAL_RAW_CONTENT, raw_content_file)
                logger.info(f"🔵 SEND: Looking for raw content at: {raw_content_path}")
                
                if os.path.exists(raw_content_path):
                    with open(raw_content_path, 'rb') as f:
                        content_bytes = f.read()
                    
                    logger.info(f"🔵 SEND: Read {len(content_bytes)} bytes from raw content file")
                    
                    # Clean up raw content file
                    try:
                        os.remove(raw_content_path)
                        logger.info(f"🔵 SEND: Cleaned up raw content file")
                    except Exception as cleanup_err:
                        logger.warning(f"🟡 SEND: Could not clean up raw content file: {cleanup_err}")
                else:
                    logger.error(f"🔴 SEND ERROR: Raw content file not found!")
                        
            elif inline_content:
                logger.info(f"🔵 SEND: Using inline content ({len(inline_content)} chars, binary: {is_binary})")
                if is_binary:
                    content_bytes = base64.b64decode(inline_content)
                else:
                    content_bytes = inline_content.encode('utf-8')
            
            # Build HTTP response
            response_line = f"HTTP/1.1 {status_code} OK\r\n"
            
            # Send headers (skip problematic ones for tunneling)
            skip_headers = {'transfer-encoding', 'connection', 'content-length'}
            header_count = 0
            for header, value in headers.items():
                if header.lower() not in skip_headers:
                    response_line += f"{header}: {value}\r\n"
                    header_count += 1
            
            response_line += f"Content-Length: {len(content_bytes)}\r\n"
            response_line += "Connection: close\r\n"
            response_line += "\r\n"
            
            logger.info(f"🔵 SEND: Sending {len(response_line)} bytes of headers + {len(content_bytes)} bytes of content")
            logger.info(f"🔵 SEND: Added {header_count} headers to response")
            
            # Send response
            bytes_sent_headers = client_socket.send(response_line.encode('utf-8'))
            bytes_sent_content = 0
            
            if content_bytes:
                bytes_sent_content = client_socket.send(content_bytes)
            
            logger.info(f"🟢 SEND SUCCESS: Sent tunnel response #{request_count} - {status_code} ({bytes_sent_headers}+{bytes_sent_content} bytes)")
                
        except Exception as e:
            logger.error(f"🔴 SEND ERROR: Error sending tunnel response #{request_count}: {e}")
            logger.error(traceback.format_exc())
    
    def _send_tunnel_error_response(self, client_socket, status_code, message):
        """Send error response through HTTPS tunnel"""
        try:
            error_content = f"<html><body><h1>Error {status_code}</h1><p>{message}</p></body></html>"
            error_bytes = error_content.encode('utf-8')
            
            response = f"HTTP/1.1 {status_code} {message}\r\n"
            response += "Content-Type: text/html\r\n"
            response += f"Content-Length: {len(error_bytes)}\r\n"
            response += "Connection: close\r\n"
            response += "\r\n"
            
            client_socket.send(response.encode('utf-8'))
            client_socket.send(error_bytes)
            
        except Exception as e:
            logger.error(f"Error sending tunnel error response: {e}")

def process_request_queue():
    """Background thread to process queued requests for better concurrency"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS//2) as executor:
        while True:
            try:
                # Get request from queue with timeout
                request_item = request_queue.get(timeout=1)
                
                # Submit for async processing
                future = executor.submit(
                    request_item['handler']._wait_and_process_response,
                    request_item['request_id'],
                    request_item['url'],
                    request_item['is_resource']
                )
                
                request_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                if DEBUG:
                    print(f"Error in request queue processing: {e}")

def clear_all_caches():
    """Clear all caches (static assets and response cache)"""
    global static_asset_cache, response_cache
    static_count = len(static_asset_cache)
    response_count = len(response_cache)
    
    static_asset_cache.clear()
    response_cache.clear()
    
    print(f"🧹 Cache cleared: {static_count} static assets + {response_count} responses")
    logger.info(f"Cache manually cleared: {static_count} static assets + {response_count} responses")
    return static_count + response_count

def show_cache_stats():
    """Show current cache statistics"""
    static_count = len(static_asset_cache)
    response_count = len(response_cache)
    
    print(f"📊 Cache Stats:")
    print(f"   Static Assets: {static_count}/{STATIC_CACHE_MAX_SIZE}")
    print(f"   Response Cache: {response_count}/{response_cache.get('max_size', 100)}")
    
    if static_count > 0:
        print(f"   Static Cache Items:")
        for i, (key, data) in enumerate(list(static_asset_cache.items())[:5]):
            age = int(time.time() - data['timestamp'])
            url = key.split('|')[0]
            print(f"     {i+1}. {url[:60]}... (age: {age}s)")
        if static_count > 5:
            print(f"     ... and {static_count - 5} more")
    
    return static_count + response_count

def handle_cache_commands():
    """Handle keyboard shortcuts for cache management"""
    import sys
    import select
    
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        command = sys.stdin.readline().strip().lower()
        
        if command == 'clear' or command == 'c':
            clear_all_caches()
        elif command == 'stats' or command == 's':
            show_cache_stats()
        elif command == 'help' or command == 'h':
            print("🎛️  Cache Commands:")
            print("   c/clear  - Clear all caches")
            print("   s/stats  - Show cache statistics")
            print("   h/help   - Show this help")
        elif command and command != '':
            print(f"Unknown command: {command}. Type 'help' for available commands.")

def main():
    """Main function to run the optimized SSH proxy server with cache management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Optimized SSH proxy with dual-layer caching')
    parser.add_argument('--clear-cache', action='store_true', help='Clear all caches on startup')
    parser.add_argument('--no-static-cache', action='store_true', help='Disable static asset caching')
    parser.add_argument('--browser-cache-only', action='store_true', help='Let browser handle all caching (recommended)')
    parser.add_argument('--cache-stats', action='store_true', help='Show cache stats on startup')
    args = parser.parse_args()
    
    # Handle startup cache options
    if args.clear_cache:
        clear_all_caches()
    
    if args.no_static_cache or args.browser_cache_only:
        global STATIC_CACHE_MAX_SIZE
        STATIC_CACHE_MAX_SIZE = 0
        if args.browser_cache_only:
            print("🌐 Browser-only caching mode: Let browser handle all caching naturally")
        else:
            print("🚫 Static asset caching disabled")
    
    logger.info(f"Starting OPTIMIZED SSH-based proxy server (Mac side - Raw Content) on port {PORT}")
    logger.info(f"Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    logger.info(f"Request timeout: {REQUEST_TIMEOUT}s")
    logger.info(f"File poll interval: {FILE_POLL_INTERVAL}s")
    logger.info(f"Static cache size: {STATIC_CACHE_MAX_SIZE} entries")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Request files directory: {LOCAL_OUTGOING}")
    logger.info(f"Response files directory: {LOCAL_INCOMING}")
    logger.info(f"Raw content files directory: {LOCAL_RAW_CONTENT}")
    logger.info("Windows should SSH into this Mac to fetch request files and deliver responses")
    logger.info("Strategy: All content transferred as original raw files for proper web traffic emulation")
    logger.info("HTTPS tunnel: hot.net domains converted to HTTP processing via SSH with SSL termination")
    logger.info("Optimizations: Dual-layer caching, connection pooling, adaptive polling, concurrent processing")
    
    print("🎛️  Cache Management Commands:")
    print("   Type 'c' or 'clear' + Enter to clear all caches")
    print("   Type 's' or 'stats' + Enter to show cache statistics")
    print("   Type 'h' or 'help' + Enter for help")
    
    if args.cache_stats:
        show_cache_stats()
    
    # Create SSL certificate for HTTPS tunneling
    if not create_ssl_certificate():
        logger.error("Failed to create SSL certificate. HTTPS tunneling will not work.")
        return
    
    logger.info("Press Ctrl+C to stop")
    
    # Cleanup function for old files
    def cleanup_old_files():
        """Clean up old request/response files"""
        try:
            current_time = time.time()
            for directory in [LOCAL_OUTGOING, LOCAL_INCOMING, LOCAL_RAW_CONTENT]:
                if not os.path.exists(directory):
                    continue
                    
                for filename in os.listdir(directory):
                    file_path = os.path.join(directory, filename)
                    file_age = current_time - os.path.getmtime(file_path)
                    
                    # Remove files older than 10 minutes
                    if file_age > 600:
                        try:
                            os.remove(file_path)
                            if DEBUG:
                                print(f"Cleaned up old file: {filename}")
                        except Exception as e:
                            if DEBUG:
                                print(f"Error cleaning up {filename}: {e}")
                                
        except Exception as e:
            if DEBUG:
                print(f"Error in cleanup routine: {e}")
    
    # Start background threads
    def cleanup_thread():
        while True:
            time.sleep(120)  # Run cleanup every 2 minutes
            cleanup_old_files()
            # Also clean response cache
            current_time = time.time()
            # Clean response cache
            expired_keys = [k for k, v in response_cache.items() 
                          if current_time - v['timestamp'] > 600]  # 10 min expiry
            for key in expired_keys:
                del response_cache[key]
                
            # Clean static asset cache
            expired_static_keys = [k for k, v in static_asset_cache.items() 
                                 if current_time - v['timestamp'] > STATIC_CACHE_MAX_AGE]
            for key in expired_static_keys:
                del static_asset_cache[key]
                
            if (expired_keys or expired_static_keys) and DEBUG:
                print(f"Cleaned up {len(expired_keys)} response cache + {len(expired_static_keys)} static cache entries")
    
    cleanup = threading.Thread(target=cleanup_thread, daemon=True)
    cleanup.start()
    
    # Start request queue processor
    queue_processor = threading.Thread(target=process_request_queue, daemon=True)
    queue_processor.start()
    
    # Configure and start optimized server
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server_address = ('localhost', PORT)
    
    # Configure threading parameters for better performance
    class OptimizedThreadingTCPServer(socketserver.ThreadingTCPServer):
        daemon_threads = True
        max_children = MAX_CONCURRENT_REQUESTS
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Enable TCP keepalive for better connection management
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    
    try:
        with OptimizedThreadingTCPServer(server_address, RawContentProxyHandler) as server:
            print(f"Optimized proxy server running on {server_address[0]}:{server_address[1]}")
            print(f"Performance: {MAX_CONCURRENT_REQUESTS} max concurrent, {REQUEST_TIMEOUT}s timeout, caching enabled")
            
            # Start cache command handler in a separate thread
            def cache_command_loop():
                while True:
                    try:
                        handle_cache_commands()
                        time.sleep(0.5)  # Check for commands twice per second
                    except Exception as e:
                        if DEBUG:
                            print(f"Cache command error: {e}")
            
            cache_thread = threading.Thread(target=cache_command_loop, daemon=True)
            cache_thread.start()
            
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down optimized proxy server...")
        cleanup_old_files()  # Final cleanup
        # Clear response cache
        response_cache.clear()
        print("Cleanup completed")
    except Exception as e:
        print(f"Server error: {e}")
        logger.error(f"Server error: {e}", exc_info=True)

if __name__ == "__main__":
    main()