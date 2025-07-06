#!/usr/bin/env python3
"""
user centric SSH-based Windows handler that transfers ALL content as raw files
Emulates original win_exec_bridge.py approach but with SSH file sync
All JS, CSS, images transferred as original files to preserve web traffic behavior
"""
import os
import json
import time
import subprocess
import base64
import mimetypes
import argparse
import urllib.request
import urllib.error
import ssl
import datetime
import threading
import queue
import concurrent.futures
from auth_state_manager import AuthStateManager

# SSH Configuration for Mac connection
MAC_SSH_CONFIG = {
    'host': 'mac-host',  # Mac hostname or IP
    'user': 'macuser',   # Mac username
    'remote_base': '/Users/macuser/Hot/infra/proxy/ssh_transfer',  # Mac base directory
    'key_file': None,    # SSH key file path (optional)
    'connection_pool_size': 5,  # Number of persistent connections
    'compression': True,  # Enable SSH compression
}

# Local Windows directories
WINDOWS_BASE = r"C:\WebServerTest\ssh_transfer"
INCOMING_DIR = os.path.join(WINDOWS_BASE, "incoming")  # Requests from Mac
OUTGOING_DIR = os.path.join(WINDOWS_BASE, "outgoing")  # Responses to Mac
CACHE_DIR = os.path.join(WINDOWS_BASE, "cache")
RAW_CONTENT_DIR = os.path.join(WINDOWS_BASE, "raw_content")  # Raw content files

# Mac directories (accessed via SSH)
MAC_OUTGOING = f"{MAC_SSH_CONFIG['remote_base']}/outgoing"  # Mac writes requests here
MAC_INCOMING = f"{MAC_SSH_CONFIG['remote_base']}/incoming"  # Mac reads responses from here
MAC_RAW_CONTENT = f"{MAC_SSH_CONFIG['remote_base']}/raw_content"  # Raw content files

# Cookie management
COOKIE_FILE = os.path.join(CACHE_DIR, "cookies.json")
COOKIE_JAR = {}

# Response caching for better performance
RESPONSE_CACHE = {}
CACHE_MAX_SIZE = 100
CACHE_MAX_AGE = 300  # 5 minutes

# Enhanced authentication management for hot.net domains
AUTH_STATE_FILE = os.path.join(CACHE_DIR, "auth_state.json")
auth_manager = None

# Constants - ALWAYS use raw file strategy  
RAW_CONTENT_THRESHOLD = 6291456  # 6MB - handle large CSS/JS files inline for better performance
SMALL_ASSET_THRESHOLD = 10240  # 10KB - embed small assets inline for speed
BATCH_SIZE = 50  # Process multiple files in batches (increased for browser-like speed)
CONCURRENT_TRANSFERS = 8  # Number of concurrent SSH transfers (doubled)
MAX_WORKER_THREADS = 12  # Maximum concurrent request processors (doubled)
SSH_CONNECTION_POOL_SIZE = 6  # Persistent SSH connections (doubled)

# Browser-like request prioritization
REQUEST_PRIORITIES = {
    'html': 1,      # Highest priority - HTML documents
    'css': 2,       # High priority - CSS for rendering
    'js': 3,        # Medium-high priority - JavaScript
    'font': 4,      # Medium priority - Fonts
    'image': 5,     # Lower priority - Images
    'other': 6      # Lowest priority - Other resources
}

# Resource type detection patterns
RESOURCE_PATTERNS = {
    'html': ['.html', '.htm', '.php', '.asp', '.jsp'],
    'css': ['.css'],
    'js': ['.js', '.mjs', '.ts', '.jsx', '.tsx'],
    'font': ['.woff', '.woff2', '.ttf', '.otf', '.eot'],
    'image': ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp']
}

# Global connection pool and processing queues
ssh_connection_pool = queue.Queue(maxsize=SSH_CONNECTION_POOL_SIZE)
request_processing_queue = queue.Queue(maxsize=50)
response_upload_queue = queue.Queue(maxsize=50)
processing_executor = None

# Ensure directories exist
for directory in [INCOMING_DIR, OUTGOING_DIR, CACHE_DIR, RAW_CONTENT_DIR]:
    os.makedirs(directory, exist_ok=True)

# Initialize connection pool
def init_ssh_connection_pool():
    """Initialize SSH connection pool for reuse"""
    for _ in range(SSH_CONNECTION_POOL_SIZE):
        ssh_connection_pool.put(None)  # Will be created on first use

def get_ssh_connection():
    """Get an SSH connection from the pool (placeholder for now)"""
    try:
        return ssh_connection_pool.get_nowait()
    except queue.Empty:
        return None

def return_ssh_connection(conn):
    """Return an SSH connection to the pool"""
    try:
        ssh_connection_pool.put_nowait(conn)
    except queue.Full:
        pass  # Pool is full, discard connection

def load_cookies():
    """Load cookies from disk if available"""
    global COOKIE_JAR, auth_manager
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                COOKIE_JAR = json.load(f)
                print(f"Loaded {len(COOKIE_JAR)} domains with cookies")
        except Exception as e:
            print(f"Error loading cookies: {e}")
    
    # Initialize enhanced auth manager for hot.net domains
    auth_manager = AuthStateManager(AUTH_STATE_FILE)
    print("Enhanced auth manager initialized for hot.net domains")

def save_cookies():
    """Save cookies to disk"""
    try:
        with open(COOKIE_FILE, 'w') as f:
            json.dump(COOKIE_JAR, f, indent=2)
            print(f"Saved {len(COOKIE_JAR)} domains with cookies")
    except Exception as e:
        print(f"Error saving cookies: {e}")

def extract_cookies_from_headers(headers, domain):
    """Extract cookies from response headers"""
    if not headers:
        return
        
    set_cookie_headers = []
    for header, value in headers.items():
        if header.lower() == 'set-cookie':
            if isinstance(value, list):
                set_cookie_headers.extend(value)
            else:
                set_cookie_headers.append(value)
    
    for cookie_header in set_cookie_headers:
        # Simple cookie extraction
        cookie_parts = cookie_header.split(';')[0].strip().split('=', 1)
        if len(cookie_parts) == 2:
            cookie_name, cookie_value = cookie_parts
            
            # Initialize domain in cookie jar if not present
            if domain not in COOKIE_JAR:
                COOKIE_JAR[domain] = {}
                
            # Store cookie
            COOKIE_JAR[domain][cookie_name] = cookie_value
            print(f"Stored cookie {cookie_name}={cookie_value} for {domain}")

def apply_cookies_to_headers(headers, domain):
    """Apply cookies from jar to request headers"""
    if domain in COOKIE_JAR and COOKIE_JAR[domain]:
        # Convert headers to case-insensitive dict
        lower_headers = {k.lower(): k for k in headers.keys()}
        
        # Build cookie string
        cookie_str = '; '.join([f"{k}={v}" for k, v in COOKIE_JAR[domain].items()])
        
        # Check if a cookie header already exists
        if 'cookie' in lower_headers:
            # Append to existing cookie
            original_key = lower_headers['cookie']
            headers[original_key] = headers[original_key] + '; ' + cookie_str
        else:
            # Create new cookie header
            headers['Cookie'] = cookie_str
            
        print(f"Applied {len(COOKIE_JAR[domain])} cookies to request for {domain}")
    return headers

def get_content_type(url):
    """Determine content type based on URL file extension"""
    content_type, _ = mimetypes.guess_type(url)
    if not content_type:
        # Default based on file extension
        if url.endswith('.css'):
            return 'text/css'
        elif url.endswith('.js'):
            return 'application/javascript'
        elif url.endswith('.png'):
            return 'image/png'
        elif url.endswith(('.jpg', '.jpeg')):
            return 'image/jpeg'
        elif url.endswith('.gif'):
            return 'image/gif'
        elif url.endswith('.svg'):
            return 'image/svg+xml'
        elif url.endswith('.woff'):
            return 'font/woff'
        elif url.endswith('.woff2'):
            return 'font/woff2'
        elif url.endswith('.ttf'):
            return 'font/ttf'
        elif url.endswith('.eot'):
            return 'application/vnd.ms-fontobject'
        elif url.endswith('.pdf'):
            return 'application/pdf'
        else:
            return 'application/octet-stream'
    return content_type

def get_resource_type(url):
    """Determine resource type for prioritization"""
    url_lower = url.lower()
    
    # Check for query parameters and fragments
    base_url = url_lower.split('?')[0].split('#')[0]
    
    for resource_type, patterns in RESOURCE_PATTERNS.items():
        if any(base_url.endswith(pattern) for pattern in patterns):
            return resource_type
    
    # Content-based detection for URLs without clear extensions
    if any(keyword in base_url for keyword in ['api', 'ajax', 'json']):
        return 'js'  # Treat API calls like JS
    elif any(keyword in base_url for keyword in ['style', 'theme']):
        return 'css'
    elif any(keyword in base_url for keyword in ['img', 'image', 'photo', 'pic']):
        return 'image'
    
    return 'other'

def get_request_priority(url):
    """Get browser-like priority for request"""
    resource_type = get_resource_type(url)
    return REQUEST_PRIORITIES.get(resource_type, REQUEST_PRIORITIES['other'])

def add_browser_headers(headers, url, is_resource):
    """Add realistic browser headers optimized for caching and performance"""
    # Base browser headers
    base_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br, zstd',  # Support modern compression
    }
    
    # Resource-specific headers for better caching
    if is_resource:
        if url.endswith(('.css', '.js')):
            # CSS/JS files - allow browser caching
            base_headers.update({
                'Accept': 'text/css,*/*;q=0.1' if url.endswith('.css') else 'application/javascript,*/*;q=0.8',
                'Sec-Fetch-Dest': 'style' if url.endswith('.css') else 'script',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'same-origin',
                'Cache-Control': 'max-age=3600'  # Allow 1 hour cache
            })
        elif url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
            # Images - strong caching
            base_headers.update({
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'same-origin',
                'Cache-Control': 'max-age=86400'  # Allow 24 hour cache
            })
        elif url.endswith(('.woff', '.woff2', '.ttf', '.eot')):
            # Fonts - very strong caching
            base_headers.update({
                'Accept': 'font/woff2,font/woff,*/*;q=0.1',
                'Sec-Fetch-Dest': 'font',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'Cache-Control': 'max-age=604800'  # Allow 1 week cache
            })
        else:
            # Other resources
            base_headers.update({
                'Accept': '*/*',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin'
            })
    else:
        # HTML documents - minimal caching
        base_headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
    
    # Add headers if not present
    for header, value in base_headers.items():
        if header not in headers:
            headers[header] = value
    
    return headers

def build_ssh_cmd(remote_path_or_cmd, is_command=False, use_compression=True):
    """Build Windows-compatible SSH/SCP command with basic optimizations"""
    if is_command:
        # SSH command
        cmd = ['ssh']
        if MAC_SSH_CONFIG.get('key_file'):
            cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        
        # Windows-compatible SSH options (avoiding ControlMaster which causes issues)
        cmd.extend([
            '-o', 'ConnectTimeout=10',  # More conservative timeout for Windows
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes'  # Non-interactive
        ])
        
        # Only add compression if supported and requested
        if use_compression and MAC_SSH_CONFIG.get('compression', True):
            cmd.extend(['-o', 'Compression=yes'])
            
        cmd.extend([f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}"])
        cmd.append(remote_path_or_cmd)
    else:
        # SCP command - keep it simple for Windows compatibility
        cmd = ['scp', '-r', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        
        # Windows-compatible SCP options
        cmd.extend([
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes'
        ])
        
        if use_compression and MAC_SSH_CONFIG.get('compression', True):
            cmd.extend(['-o', 'Compression=yes'])
            
        # Add source and destination
        cmd.extend([f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{remote_path_or_cmd}", "."])
    
    return cmd

def sync_request_files_fast():
    """Ultra-fast request file sync with minimal SSH calls"""
    try:
        # Single SSH command to list and count files in one go
        ssh_cmd = build_ssh_cmd(f"cd {MAC_OUTGOING} && ls req_*.json 2>/dev/null || echo 'NOFILES'", is_command=True)
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=2)
        
        if result.returncode != 0 or 'NOFILES' in result.stdout:
            return []  # No files to sync
        
        file_list = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        if not file_list:
            return []
        
        print(f"Found {len(file_list)} request files on Mac")
        
        # Change to incoming directory for SCP
        original_dir = os.getcwd()
        os.chdir(INCOMING_DIR)
        
        try:
            # Use single SCP command to get all files at once
            if len(file_list) == 1:
                scp_cmd = build_ssh_cmd(f"{MAC_OUTGOING}/{file_list[0]}", is_command=False)
            else:
                # Multiple files - use pattern or multiple file spec
                file_spec = f"{MAC_OUTGOING}/req_*.json"
                scp_cmd = build_ssh_cmd(file_spec, is_command=False)
            
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=8)
            
            if result.returncode == 0:
                # Verify what we actually got
                local_files = [f for f in os.listdir('.') if f.startswith("req_") and f.endswith(".json")]
                if local_files:
                    print(f"⚡ Fast-synced {len(local_files)} request files from Mac")
                    return local_files
                else:
                    return []
            else:
                if "No such file" not in result.stderr:
                    print(f"Fast sync failed: {result.stderr}")
                return []
        finally:
            os.chdir(original_dir)
            
    except Exception as e:
        print(f"Error in fast sync: {e}")
        return []

def cleanup_mac_request_file(filename):
    """Remove processed request file from Mac"""
    try:
        remote_file = f"{MAC_OUTGOING}/{filename}"
        ssh_cmd = build_ssh_cmd(f"rm -f {remote_file}", is_command=True)
        
        subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)
        print(f"Cleaned up request file on Mac: {filename}")
        
    except Exception as e:
        print(f"Error cleaning up Mac request file {filename}: {e}")

def cleanup_mac_request_files_batch(filenames):
    """Ultra-fast batch cleanup using single SSH command"""
    try:
        if not filenames:
            return
            
        # Ultra-efficient: cd to directory and remove files in one command
        file_list = ' '.join(filenames)  # Just filenames, not full paths
        ssh_cmd = build_ssh_cmd(f"cd {MAC_OUTGOING} && rm -f {file_list}", is_command=True)
        
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"⚡ Fast cleanup: removed {len(filenames)} files from Mac")
        else:
            print(f"Batch cleanup failed: {result.stderr}")
            # Fallback to pattern-based cleanup
            if len(filenames) > 5:
                # Use pattern for many files
                ssh_cmd = build_ssh_cmd(f"cd {MAC_OUTGOING} && rm -f req_*.json", is_command=True)
                subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)
        
    except Exception as e:
        print(f"Error in fast cleanup: {e}")

def upload_response_file(local_file, filename):
    """Windows-compatible upload response file to Mac with optimized transfers"""
    try:
        # Fast path for small response files - skip atomic operations for speed
        file_size = os.path.getsize(local_file)
        use_atomic = file_size > 50000  # Only use atomic for files > 50KB
        
        if use_atomic:
            # Use atomic file operations to prevent race conditions for large files
            temp_filename = f"{filename}.tmp"
            temp_remote_path = f"{MAC_INCOMING}/{temp_filename}"
            final_remote_path = f"{MAC_INCOMING}/{filename}"
            target_path = temp_remote_path
        else:
            # Direct upload for small files
            final_remote_path = f"{MAC_INCOMING}/{filename}"
            target_path = final_remote_path
        
        # Step 1: Upload file
        scp_cmd = ['scp', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            scp_cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        
        # Windows-compatible options - faster timeouts for small files
        connect_timeout = 10 if use_atomic else 5
        scp_cmd.extend([
            '-o', f'ConnectTimeout={connect_timeout}',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes'
        ])
        
        if MAC_SSH_CONFIG.get('compression', True):
            scp_cmd.extend(['-o', 'Compression=yes'])
            
        scp_cmd.extend([
            local_file,
            f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{target_path}"
        ])
        
        # Shorter timeout for small files
        timeout = 30 if use_atomic else 10
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode == 0:
            if use_atomic:
                # Step 2: Atomically rename to final name for large files
                ssh_cmd = build_ssh_cmd(f"mv {temp_remote_path} {final_remote_path}", is_command=True)
                rename_result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=5)
                
                if rename_result.returncode == 0:
                    print(f"Uploaded response file to Mac (atomic): {filename}")
                    return True
                else:
                    print(f"Failed to rename uploaded file: {rename_result.stderr}")
                    # Clean up temp file
                    cleanup_cmd = build_ssh_cmd(f"rm -f {temp_remote_path}", is_command=True)
                    subprocess.run(cleanup_cmd, capture_output=True, text=True, timeout=5)
                    return False
            else:
                print(f"Uploaded response file to Mac (direct): {filename} ({file_size} bytes)")
                return True
        else:
            print(f"Failed to upload response file: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error uploading response file {filename}: {e}")
        return False

def upload_raw_content_file(local_file, filename):
    """Windows-compatible upload raw content file to Mac with smart compression"""
    try:
        remote_path = f"{MAC_RAW_CONTENT}/{filename}"
        
        # Check file size for optimization decisions
        file_size = os.path.getsize(local_file)
        use_compression = file_size > 10240  # Use compression for files > 10KB
        
        # Use Windows-compatible SCP to upload raw content file
        scp_cmd = ['scp', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            scp_cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        
        # Windows-compatible options only
        scp_cmd.extend([
            '-o', 'ConnectTimeout=15',  # Longer timeout for large files
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes'
        ])
        
        # Conditional compression based on file size
        if use_compression and MAC_SSH_CONFIG.get('compression', True):
            scp_cmd.extend(['-o', 'Compression=yes'])
            
        scp_cmd.extend([
            local_file,
            f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{remote_path}"
        ])
        
        # Adjusted timeout based on file size
        timeout = min(max(file_size // 1024 + 15, 30), 180)  # 15-180 seconds based on size
        
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
        
        if result.returncode == 0:
            print(f"Uploaded raw content file to Mac: {filename} ({file_size} bytes)")
            return True
        else:
            print(f"Failed to upload raw content file: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error uploading raw content file {filename}: {e}")
        return False

def get_cache_key(url, method, headers, body):
    """Generate cache key for request"""
    # Simple cache key based on URL and method for GET requests
    if method == 'GET' and not body:
        return f"{method}:{url}"
    return None  # Don't cache POST requests or requests with body

def get_cached_response(cache_key):
    """Get cached response if available and not expired"""
    if cache_key in RESPONSE_CACHE:
        cached = RESPONSE_CACHE[cache_key]
        if time.time() - cached['timestamp'] < CACHE_MAX_AGE:
            # Verify cached response is complete and valid
            cached_data = cached['data']
            if (cached_data.get('status') == 200 and 
                ('content' in cached_data or 'raw_content_file' in cached_data)):
                return cached_data
            else:
                # Remove invalid cache entry
                del RESPONSE_CACHE[cache_key]
        else:
            # Remove expired cache entry
            del RESPONSE_CACHE[cache_key]
    return None

def cache_response(cache_key, response_data):
    """Cache response data only if it's complete and successful"""
    if (cache_key and 
        response_data.get('status') == 200 and 
        (response_data.get('content') or response_data.get('raw_content_file')) and
        response_data.get('content_size', 0) > 0):
        
        # Limit cache size
        if len(RESPONSE_CACHE) >= CACHE_MAX_SIZE:
            # Remove oldest entry
            oldest_key = min(RESPONSE_CACHE.keys(), key=lambda k: RESPONSE_CACHE[k]['timestamp'])
            del RESPONSE_CACHE[oldest_key]
        
        # Create a clean copy for caching
        cache_data = response_data.copy()
        RESPONSE_CACHE[cache_key] = {
            'data': cache_data,
            'timestamp': time.time()
        }
        print(f"💾 Cached successful response for {cache_key} ({response_data.get('content_size', 0)} bytes)")

def process_request_file(file_path):
    """Ultra-fast request processing with caching and optimizations"""
    try:
        # Read the request data
        with open(file_path, 'r', encoding='utf-8') as f:
            request_data = json.load(f)
            
        request_id = request_data.get('id')
        url = request_data.get('url', '')
        method = request_data.get('method', 'GET')
        headers = request_data.get('headers', {})
        body = request_data.get('body', '')
        body_encoding = request_data.get('body_encoding', 'utf-8')
        is_resource = request_data.get('is_resource', False)
        
        # Enhanced cache check: Use cache for fresh static assets like a real browser
        cache_key = get_cache_key(url, method, headers, body) if RESPONSE_CACHE is not None else None
        if cache_key and RESPONSE_CACHE is not None and is_resource:
            cached_response = get_cached_response(cache_key)
            if cached_response:
                # Check if browser sent conditional headers indicating it has a cached version
                if_none_match = headers.get('If-None-Match')
                if_modified_since = headers.get('If-Modified-Since')
                
                # For static assets, serve from cache if still fresh or if browser has conditional headers
                cache_control = cached_response.get('headers', {}).get('Cache-Control', '')
                etag = cached_response.get('headers', {}).get('ETag', '')
                
                # Browser is checking if content changed (conditional request)
                if (if_none_match and etag and if_none_match.strip('"') == etag.strip('"')):
                    print(f"⚡ Cache HIT: 304 Not Modified for {url}")
                    # Return 304 response
                    cached_response['status'] = 304
                    cached_response['content'] = ''
                    cached_response['content_size'] = 0
                elif not if_none_match and not if_modified_since:
                    # Direct cache hit for fresh static assets
                    print(f"⚡ Cache HIT: Fresh static asset {url}")
                else:
                    print(f"⚡ Cache HIT: Standard cache hit for {url}")
                
                # Create response file from cache
                response_file = os.path.join(OUTGOING_DIR, f"resp_{request_id}.json")
                cached_response['id'] = request_id  # Update request ID
                with open(response_file, 'w', encoding='utf-8') as f:
                    json.dump(cached_response, f, ensure_ascii=False, indent=2)
                
                # Queue for background upload
                try:
                    response_upload_queue.put_nowait((response_file, f"resp_{request_id}.json"))
                    return True
                except queue.Full:
                    # Fallback to sync upload
                    success = upload_response_file(response_file, f"resp_{request_id}.json")
                    if success:
                        os.remove(response_file)
                    return success
        
        print(f"Processing request: {url} (Resource: {is_resource})")
        
        # Extract domain
        domain = url.split('://', 1)[-1].split('/', 1)[0] if '://' in url else url.split('/', 1)[0]
        
        # Apply cookies to request headers
        headers = apply_cookies_to_headers(headers, domain)
        
        # Handle conditional requests for better caching
        if is_resource and method == 'GET':
            # Check if browser sent If-None-Match (ETag)
            if_none_match = headers.get('If-None-Match')
            if if_none_match:
                # Browser is checking if resource changed
                print(f"🔄 Conditional request for {url} with ETag {if_none_match}")
                # Keep the conditional header for the upstream server
                headers['If-None-Match'] = if_none_match
        
        # Apply enhanced authentication for hot.net domains
        if auth_manager and auth_manager.is_hot_net_domain(url):
            headers = auth_manager.apply_auth_to_headers(url, headers)
            print(f"Applied enhanced auth for hot.net domain: {domain}")
        
        # Add realistic browser headers optimized for caching
        headers = add_browser_headers(headers, url, is_resource)
        
        # Make the HTTP request
        try:
            # Create SSL context
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Prepare request body
            data = None
            if body and method != "GET":
                if body_encoding == 'base64':
                    data = base64.b64decode(body)
                else:
                    data = body.encode('utf-8')
            
            # Create the request
            req = urllib.request.Request(url, data=data, method=method)
            
            # Add headers
            for header, value in headers.items():
                req.add_header(header, value)
            
            # Make the request
            try:
                response = urllib.request.urlopen(req, context=context, timeout=30)
                response_code = response.status
                response_headers = {}
                
                for header, value in response.getheaders():
                    response_headers[header] = value
                    
            except urllib.error.HTTPError as http_err:
                # Handle HTTP errors including 304 Not Modified
                response_code = http_err.code
                response_headers = dict(http_err.headers.items())
                
                if response_code == 304:
                    response_body = b''
                    print(f"Handling 304 Not Modified response for {url}")
                else:
                    response_body = http_err.read() or b''
                    print(f"HTTP Error {response_code} for {url}")
            else:
                # Read response body
                response_body = response.read() or b''
            
            # Extract cookies from response
            extract_cookies_from_headers(response_headers, domain)
            save_cookies()
            
            # Ensure response_body is never None
            if response_body is None:
                response_body = b''
                print(f"Warning: Got None response_body for {url}, using empty bytes")
            
            # Determine content type first
            content_type = response_headers.get('Content-Type', '')
            if not content_type:
                detected_type = get_content_type(url)
                if detected_type:
                    response_headers['Content-Type'] = detected_type
                    content_type = detected_type
            
            # Extract enhanced authentication data for hot.net domains
            if auth_manager and auth_manager.is_hot_net_domain(url):
                print(f"Extracting enhanced auth data for hot.net domain: {domain}")
                auth_manager.extract_auth_from_response(url, response_headers, response_body, content_type)
                
                # Show auth summary
                summary = auth_manager.get_auth_summary()
                for auth_domain, counts in summary.items():
                    if 'hot.net' in auth_domain:
                        total_items = sum(counts.values()) - 1  # Exclude timestamp
                        print(f"Auth data for {auth_domain}: {total_items} items captured")
            
            print(f"Content type: {content_type}, Size: {len(response_body)} bytes")
            
            # Smart content handling: small static assets inline, large content as raw files
            raw_content_file = None
            content_size = len(response_body)
            
            # Fast path for small static assets (images, CSS, JS under 10KB)
            use_inline = (content_size <= SMALL_ASSET_THRESHOLD and 
                         is_resource and 
                         response_code == 200 and
                         any(ext in content_type.lower() for ext in ['image/', 'css', 'javascript']))
            
            if use_inline:
                print(f"⚡ FAST PATH: Inlining small {content_type} asset ({content_size} bytes) for speed")
            
            if not use_inline and (content_size > 0 and response_code != 304):
                # Create raw content file with appropriate extension
                file_extension = 'bin'
                if 'javascript' in content_type:
                    file_extension = 'js'
                elif 'css' in content_type:
                    file_extension = 'css'
                elif 'html' in content_type:
                    file_extension = 'html'
                elif 'json' in content_type:
                    file_extension = 'json'
                elif 'png' in content_type:
                    file_extension = 'png'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    file_extension = 'jpg'
                elif 'gif' in content_type:
                    file_extension = 'gif'
                elif 'svg' in content_type:
                    file_extension = 'svg'
                
                raw_content_file = f"content_{request_id}_{int(time.time())}.{file_extension}"
                raw_content_path = os.path.join(RAW_CONTENT_DIR, raw_content_file)
                
                print(f"Storing content as raw file: {raw_content_file}")
                
                # Write raw content exactly as received (preserving compression, encoding, etc.)
                with open(raw_content_path, 'wb') as f:
                    f.write(response_body)
                
                # Upload raw content file to Mac
                if upload_raw_content_file(raw_content_path, raw_content_file):
                    print(f"Uploaded raw content file to Mac: {raw_content_file}")
                    # Clean up local raw content file
                    os.remove(raw_content_path)
                else:
                    print(f"Failed to upload raw content file")
                    raw_content_file = None  # Mark as failed
            
            # Add proper caching headers for browser performance
            if is_resource and response_code == 200:
                if url.endswith(('.css', '.js')):
                    response_headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
                elif url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
                    response_headers['Cache-Control'] = 'public, max-age=86400'  # 24 hours
                elif url.endswith(('.woff', '.woff2', '.ttf', '.eot')):
                    response_headers['Cache-Control'] = 'public, max-age=604800'  # 1 week
                
                # Add ETag for conditional requests
                if len(response_body) > 0:
                    import hashlib
                    etag = hashlib.md5(response_body).hexdigest()[:16]
                    response_headers['ETag'] = f'"{etag}"'
                    response_headers['Last-Modified'] = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
            
            # Create minimal response JSON (just metadata, no content)
            response_data = {
                "id": request_id,
                "timestamp": int(time.time()),
                "status": response_code,
                "headers": response_headers,
                "raw_content_file": raw_content_file,  # Reference to separate content file
                "content_size": len(response_body),
                "is_resource": is_resource,
                "content_type": content_type
            }
            
            # Cache all successful resource responses (let browser handle its own caching)
            if (cache_key and response_code == 200 and is_resource and len(response_body) > 0):
                cache_response(cache_key, response_data.copy())
            
            # For small static assets, 304 responses, or when using fast inline path
            if raw_content_file is None and (use_inline or len(response_body) <= SMALL_ASSET_THRESHOLD):
                try:
                    # Try to include small content as text
                    response_data["content"] = response_body.decode('utf-8')
                    response_data["is_binary"] = False
                except UnicodeDecodeError:
                    # If it's binary, encode as base64
                    response_data["content"] = base64.b64encode(response_body).decode('ascii')
                    response_data["is_binary"] = True
            
            # Write minimal response JSON file
            response_file = os.path.join(OUTGOING_DIR, f"resp_{request_id}.json")
            with open(response_file, 'w', encoding='utf-8') as f:
                json.dump(response_data, f, ensure_ascii=False, indent=2)
                
            print(f"Response metadata file created: {response_file}")
            
            # Queue response file for background upload (faster)
            try:
                response_upload_queue.put_nowait((response_file, f"resp_{request_id}.json"))
                return True  # Don't wait for upload to complete
            except queue.Full:
                # Fallback to synchronous upload if queue is full
                if upload_response_file(response_file, f"resp_{request_id}.json"):
                    os.remove(response_file)
                    return True
                else:
                    return False
                
        except Exception as e:
            print(f"Error making request: {e}")
            import traceback
            traceback.print_exc()
            
            # Create error response
            error_response = {
                "id": request_id,
                "timestamp": int(time.time()),
                "status": 500,
                "headers": {"Content-Type": "text/plain"},
                "content": f"Error processing request: {str(e)}",
                "is_resource": is_resource,
                "is_binary": False,
                "error": True
            }
            
            # Write error response file
            response_file = os.path.join(OUTGOING_DIR, f"resp_{request_id}.json")
            with open(response_file, 'w', encoding='utf-8') as f:
                json.dump(error_response, f, ensure_ascii=False, indent=2)
            
            # Upload error response to Mac
            upload_response_file(response_file, f"resp_{request_id}.json")
            if os.path.exists(response_file):
                os.remove(response_file)
            return False
        
    except Exception as e:
        print(f"Error processing request file {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_request_async(req_file):
    """Process a single request file asynchronously with priority"""
    try:
        file_path = os.path.join(INCOMING_DIR, req_file)
        if not os.path.exists(file_path):
            return False
        
        # Read request to determine priority
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                request_data = json.load(f)
            url = request_data.get('url', '')
            priority = get_request_priority(url)
            resource_type = get_resource_type(url)
            
            print(f"Processing {resource_type} request (priority {priority}): {url}")
        except:
            priority = REQUEST_PRIORITIES['other']
            
        success = process_request_file(file_path)
        
        # Delete local file immediately after processing
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error deleting {req_file}: {e}")
        
        return success
    except Exception as e:
        print(f"Error processing {req_file}: {e}")
        return False

def check_request_files_parallel():
    """Ultra-fast parallel processing of request files"""
    try:
        # Fast sync files from Mac
        synced_files = sync_request_files_fast()
        
        if not synced_files:
            return  # No files to process
        
        print(f"⚡ Processing {len(synced_files)} requests in parallel")
        start_time = time.time()
        
        # Sort files by priority for browser-like loading
        def get_file_priority(req_file):
            try:
                file_path = os.path.join(INCOMING_DIR, req_file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    request_data = json.load(f)
                url = request_data.get('url', '')
                return get_request_priority(url)
            except:
                return REQUEST_PRIORITIES['other']
        
        # Sort by priority (lower number = higher priority) - ensure no None files
        synced_files = [f for f in synced_files if f]  # Filter out any None/empty filenames
        synced_files_prioritized = sorted(synced_files, key=get_file_priority)
        
        # Process files in parallel using thread pool with aggressive batching
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS) as executor:
            # Split into priority groups for better browser-like loading
            high_priority = [f for f in synced_files_prioritized if get_file_priority(f) <= 2]  # HTML, CSS
            medium_priority = [f for f in synced_files_prioritized if 3 <= get_file_priority(f) <= 4]  # JS, Fonts
            low_priority = [f for f in synced_files_prioritized if get_file_priority(f) > 4]  # Images, other
            
            processed_files = []
            
            # Process high priority first (like critical rendering path)
            if high_priority:
                print(f"⚡ Processing {len(high_priority)} high-priority requests first")
                future_to_file = {executor.submit(process_request_async, req_file): req_file 
                                for req_file in high_priority}
                for future in concurrent.futures.as_completed(future_to_file, timeout=30):
                    req_file = future_to_file[future]
                    try:
                        success = future.result()
                        if success:
                            processed_files.append(req_file)
                    except Exception as e:
                        print(f"Error processing high-priority {req_file}: {e}")
            
            # Process medium priority (JS, fonts)
            if medium_priority:
                print(f"⚡ Processing {len(medium_priority)} medium-priority requests")
                future_to_file = {executor.submit(process_request_async, req_file): req_file 
                                for req_file in medium_priority}
                for future in concurrent.futures.as_completed(future_to_file, timeout=45):
                    req_file = future_to_file[future]
                    try:
                        success = future.result()
                        if success:
                            processed_files.append(req_file)
                    except Exception as e:
                        print(f"Error processing medium-priority {req_file}: {e}")
            
            # Process low priority in the background (images can load after)
            if low_priority:
                print(f"⚡ Processing {len(low_priority)} low-priority requests in background")
                future_to_file = {executor.submit(process_request_async, req_file): req_file 
                                for req_file in low_priority}
                for future in concurrent.futures.as_completed(future_to_file, timeout=60):
                    req_file = future_to_file[future]
                    try:
                        success = future.result()
                        if success:
                            processed_files.append(req_file)
                    except Exception as e:
                        print(f"Error processing low-priority {req_file}: {e}")
        
        # Single batch cleanup on Mac
        if processed_files:
            cleanup_mac_request_files_batch(processed_files)
        
        elapsed = time.time() - start_time
        if processed_files:
            print(f"⚡ Processed {len(processed_files)} requests in {elapsed:.2f}s ({len(processed_files)/elapsed:.1f} req/s)")
            
    except Exception as e:
        print(f"Error in parallel processing: {e}")

def main():
    """Main function to run the ultra-fast handler"""
    parser = argparse.ArgumentParser(description='Ultra-fast SSH-syncing Windows bridge with browser-like performance')
    parser.add_argument('--no-cookies', action='store_true', help='Do not load cookies at startup')
    parser.add_argument('--reset-cookies', action='store_true', help='Reset cookie jar before starting')
    parser.add_argument('--mac-host', help='Mac SSH hostname or IP', required=True)
    parser.add_argument('--mac-user', help='Mac SSH username', required=True)
    parser.add_argument('--ssh-key', help='SSH private key file path')
    parser.add_argument('--no-cache', action='store_true', help='Disable response caching')
    parser.add_argument('--max-workers', type=int, default=6, help='Max worker threads')
    args = parser.parse_args()
    
    # Apply command line overrides
    global MAX_WORKER_THREADS, RESPONSE_CACHE
    MAX_WORKER_THREADS = args.max_workers
    if args.no_cache:
        RESPONSE_CACHE = None  # Disable caching completely
    
    # Update SSH config from command line
    MAC_SSH_CONFIG['host'] = args.mac_host
    MAC_SSH_CONFIG['user'] = args.mac_user
    if args.ssh_key:
        MAC_SSH_CONFIG['key_file'] = args.ssh_key
    
    print(f"🚀 Starting ULTRA-FAST SSH Handler at {datetime.datetime.now()}")
    print(f"⚡ Connecting to Mac: {MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}")
    print(f"📁 Mac remote directory: {MAC_SSH_CONFIG['remote_base']}")
    print(f"📦 Raw content threshold: {RAW_CONTENT_THRESHOLD} bytes")
    print(f"💨 Browser-like performance: Parallel processing, caching, optimized transfers")
    
    # Handle cookie options
    if args.reset_cookies:
        global COOKIE_JAR
        COOKIE_JAR = {}
        print("Cookie jar has been reset")
        save_cookies()
    elif not args.no_cookies:
        load_cookies()
    else:
        print("Starting with empty cookie jar (--no-cookies specified)")
    
    # Test SSH connectivity
    print("Testing SSH connectivity...")
    try:
        test_cmd = build_ssh_cmd("echo 'SSH test successful'", is_command=True)
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ SSH connectivity test successful")
        else:
            print(f"❌ SSH connectivity test failed: {result.stderr}")
            return
    except Exception as e:
        print(f"❌ SSH connectivity test failed: {e}")
        return
    
    polling_interval = 0.02  # seconds - ultra-fast polling for browser-like responsiveness (20ms)
    
    # Initialize connection pool and worker threads
    init_ssh_connection_pool()
    
    print(f"⚡ Performance optimizations enabled:")
    print(f"   - {MAX_WORKER_THREADS} parallel request processors")
    print(f"   - {SSH_CONNECTION_POOL_SIZE} SSH connection pool")
    print(f"   - {polling_interval}s polling interval")
    print(f"   - Batch size: {BATCH_SIZE}")
    
    print("Starting main polling loop...")
    print("Press Ctrl+C to stop")
    
    # Start background upload processor
    upload_thread = threading.Thread(target=upload_queue_processor, daemon=True)
    upload_thread.start()
    
    # Ultra-fast main loop with adaptive polling
    try:
        consecutive_empty = 0
        total_processed = 0
        start_time = time.time()
        
        while True:
            loop_start = time.time()
            
            # Get initial count for metrics
            initial_queue_size = response_upload_queue.qsize()
            
            # Use parallel processing
            check_request_files_parallel()
            
            # Update metrics
            total_processed += 1
            if total_processed % 100 == 0:  # Stats every 100 loops
                elapsed_total = time.time() - start_time
                cache_hits = len(RESPONSE_CACHE)
                queue_size = response_upload_queue.qsize()
                print(f"⚡ Stats: {total_processed} loops in {elapsed_total:.1f}s, {cache_hits} cached, {queue_size} queued")
            
            # Adaptive polling based on work load
            elapsed = time.time() - loop_start
            if elapsed < 0.001:  # Very fast, probably no work
                consecutive_empty += 1
                if consecutive_empty > 20:
                    time.sleep(polling_interval * 3)  # Slow down when very idle
                elif consecutive_empty > 10:
                    time.sleep(polling_interval * 2)  # Slow down when idle
                else:
                    time.sleep(polling_interval)
            else:
                consecutive_empty = 0
                # If processing took time, poll faster for next batch
                time.sleep(max(0.01, polling_interval - elapsed))
    except KeyboardInterrupt:
        print("\n🛑 Shutting down ultra-fast handler...")
        
        # Signal upload thread to stop
        response_upload_queue.put(None)
        upload_thread.join(timeout=2)
        
        # Save state
        save_cookies()
        
        # Final stats
        elapsed_total = time.time() - start_time
        cache_hits = len(RESPONSE_CACHE)
        print(f"📊 Final stats: {total_processed} loops in {elapsed_total:.1f}s, {cache_hits} responses cached")
        print("✅ Shutdown complete")
        
    except Exception as e:
        print(f"💥 Error in main loop: {e}")
        save_cookies()

# Background upload queue processor for even better performance
def upload_queue_processor():
    """Background thread to handle uploads asynchronously with batching"""
    batch_queue = []
    batch_timeout = 0.2  # Wait 200ms to batch uploads
    last_batch_time = time.time()
    
    while True:
        try:
            # Try to get an upload task
            try:
                upload_task = response_upload_queue.get(timeout=batch_timeout)
                if upload_task is None:  # Shutdown signal
                    # Process any remaining batch
                    if batch_queue:
                        process_upload_batch(batch_queue)
                    break
                    
                batch_queue.append(upload_task)
                response_upload_queue.task_done()
                
            except queue.Empty:
                # No new tasks, process batch if we have items or timeout
                if batch_queue and (time.time() - last_batch_time) > batch_timeout:
                    process_upload_batch(batch_queue)
                    batch_queue = []
                    last_batch_time = time.time()
                continue
            
            # Process batch if it's getting large or enough time has passed
            if len(batch_queue) >= 5 or (time.time() - last_batch_time) > batch_timeout:
                process_upload_batch(batch_queue)
                batch_queue = []
                last_batch_time = time.time()
                
        except Exception as e:
            print(f"Upload queue error: {e}")

def process_upload_batch(batch_queue):
    """Process a batch of uploads more efficiently"""
    if not batch_queue:
        return
        
    print(f"⚡ Processing upload batch of {len(batch_queue)} files")
    
    # Process all uploads in the batch
    for file_path, filename in batch_queue:
        if os.path.exists(file_path):
            upload_response_file(file_path, filename)
            try:
                os.remove(file_path)
            except Exception:
                pass

if __name__ == "__main__":
    main()