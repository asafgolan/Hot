#!/usr/bin/env python3
"""
SSH-based Windows handler that transfers ALL content as raw files
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
from auth_state_manager import AuthStateManager

# SSH Configuration for Mac connection
MAC_SSH_CONFIG = {
    'host': 'mac-host',  # Mac hostname or IP
    'user': 'macuser',   # Mac username
    'remote_base': '/Users/macuser/Hot/infra/proxy/ssh_transfer',  # Mac base directory
    'key_file': None,    # SSH key file path (optional)
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

# Enhanced authentication management for hot.net domains
AUTH_STATE_FILE = os.path.join(CACHE_DIR, "auth_state.json")
auth_manager = None

# Constants - ALWAYS use raw file strategy
RAW_CONTENT_THRESHOLD = 1024  # 1KB - nearly everything goes to raw files

# Ensure directories exist
for directory in [INCOMING_DIR, OUTGOING_DIR, CACHE_DIR, RAW_CONTENT_DIR]:
    os.makedirs(directory, exist_ok=True)

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

def add_browser_headers(headers):
    """Add realistic browser headers for proper web traffic emulation"""
    browser_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }
    
    # Add browser headers if not present
    for header, value in browser_headers.items():
        if header not in headers:
            headers[header] = value
    
    return headers

def build_ssh_cmd(remote_path_or_cmd, is_command=False):
    """Build SSH/SCP command"""
    if is_command:
        # SSH command
        cmd = ['ssh']
        if MAC_SSH_CONFIG.get('key_file'):
            cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        cmd.extend([
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}"
        ])
        cmd.append(remote_path_or_cmd)
    else:
        # SCP command
        cmd = ['scp', '-r', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        cmd.extend([
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no'
        ])
        # Add source and destination
        cmd.extend([f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{remote_path_or_cmd}", "."])
    
    return cmd

def sync_request_files():
    """Sync request files from Mac to local incoming directory"""
    try:
        # Change to incoming directory for SCP
        original_dir = os.getcwd()
        os.chdir(INCOMING_DIR)
        
        try:
            # Use SCP to copy all request files from Mac
            scp_cmd = build_ssh_cmd(f"{MAC_OUTGOING}/req_*.json", is_command=False)
            
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Count files we got
                request_files = [f for f in os.listdir('.') if f.startswith("req_") and f.endswith(".json")]
                if request_files:
                    print(f"Synced {len(request_files)} request files from Mac")
                    return request_files
                else:
                    return []
            else:
                # SCP failed, might be no files (which is normal)
                if "No such file" in result.stderr:
                    return []  # No request files available
                else:
                    print(f"SCP sync failed: {result.stderr}")
                    return []
        finally:
            os.chdir(original_dir)
            
    except Exception as e:
        print(f"Error syncing request files: {e}")
        return []

def cleanup_mac_request_file(filename):
    """Remove processed request file from Mac"""
    try:
        remote_file = f"{MAC_OUTGOING}/{filename}"
        ssh_cmd = build_ssh_cmd(f"rm -f {remote_file}", is_command=True)
        
        subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
        print(f"Cleaned up request file on Mac: {filename}")
        
    except Exception as e:
        print(f"Error cleaning up Mac request file {filename}: {e}")

def upload_response_file(local_file, filename):
    """Upload response file to Mac"""
    try:
        remote_path = f"{MAC_INCOMING}/{filename}"
        
        # Use SCP to upload file
        scp_cmd = ['scp', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            scp_cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        scp_cmd.extend([
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            local_file,
            f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{remote_path}"
        ])
        
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"Uploaded response file to Mac: {filename}")
            return True
        else:
            print(f"Failed to upload response file: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error uploading response file {filename}: {e}")
        return False

def upload_raw_content_file(local_file, filename):
    """Upload raw content file to Mac"""
    try:
        remote_path = f"{MAC_RAW_CONTENT}/{filename}"
        
        # Use SCP to upload raw content file
        scp_cmd = ['scp', '-q']
        if MAC_SSH_CONFIG.get('key_file'):
            scp_cmd.extend(['-i', MAC_SSH_CONFIG['key_file']])
        scp_cmd.extend([
            '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=no',
            local_file,
            f"{MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}:{remote_path}"
        ])
        
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print(f"Uploaded raw content file to Mac: {filename}")
            return True
        else:
            print(f"Failed to upload raw content file: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Error uploading raw content file {filename}: {e}")
        return False

def process_request_file(file_path):
    """Process a single request file - store ALL content as raw files"""
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
        
        print(f"Processing request: {url} (Resource: {is_resource})")
        
        # Extract domain
        domain = url.split('://', 1)[-1].split('/', 1)[0] if '://' in url else url.split('/', 1)[0]
        
        # Apply cookies to request headers
        headers = apply_cookies_to_headers(headers, domain)
        
        # Apply enhanced authentication for hot.net domains
        if auth_manager and auth_manager.is_hot_net_domain(url):
            headers = auth_manager.apply_auth_to_headers(url, headers)
            print(f"Applied enhanced auth for hot.net domain: {domain}")
        
        # Add realistic browser headers
        headers = add_browser_headers(headers)
        
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
                    response_body = http_err.read()
                    print(f"HTTP Error {response_code} for {url}")
            else:
                # Read response body
                response_body = response.read()
            
            # Extract cookies from response
            extract_cookies_from_headers(response_headers, domain)
            save_cookies()
            
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
            
            # ALWAYS use raw file strategy for content > 1KB (everything except tiny responses)
            raw_content_file = None
            if len(response_body) > RAW_CONTENT_THRESHOLD or response_code != 304:
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
            
            # For tiny responses or 304 responses, include content inline
            if raw_content_file is None and len(response_body) <= RAW_CONTENT_THRESHOLD:
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
            
            # Upload response file to Mac
            if upload_response_file(response_file, f"resp_{request_id}.json"):
                # Clean up local response file after successful upload
                os.remove(response_file)
                return True
            else:
                print(f"Failed to upload response file")
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

def check_request_files():
    """Check for and process any request files"""
    try:
        # Sync files from Mac first
        synced_files = sync_request_files()
        
        if not synced_files:
            return  # No files to process
        
        print(f"Found {len(synced_files)} requests to process")
        
        for req_file in synced_files:
            file_path = os.path.join(INCOMING_DIR, req_file)
            
            if os.path.exists(file_path):
                success = process_request_file(file_path)
                
                # Delete the local request file after processing
                try:
                    os.remove(file_path)
                    print(f"Deleted local request file: {file_path}")
                except Exception as e:
                    print(f"Error deleting local request file: {e}")
                
                # Clean up the request file on Mac
                if success:
                    cleanup_mac_request_file(req_file)
            
    except Exception as e:
        print(f"Error checking request files: {e}")

def main():
    """Main function to run the handler"""
    parser = argparse.ArgumentParser(description='SSH-syncing Windows bridge with raw file transfer')
    parser.add_argument('--no-cookies', action='store_true', help='Do not load cookies at startup')
    parser.add_argument('--reset-cookies', action='store_true', help='Reset cookie jar before starting')
    parser.add_argument('--mac-host', help='Mac SSH hostname or IP', required=True)
    parser.add_argument('--mac-user', help='Mac SSH username', required=True)
    parser.add_argument('--ssh-key', help='SSH private key file path')
    args = parser.parse_args()
    
    # Update SSH config from command line
    MAC_SSH_CONFIG['host'] = args.mac_host
    MAC_SSH_CONFIG['user'] = args.mac_user
    if args.ssh_key:
        MAC_SSH_CONFIG['key_file'] = args.ssh_key
    
    print(f"Starting SSH Raw Content Transfer Windows handler at {datetime.datetime.now()}")
    print(f"Connecting to Mac: {MAC_SSH_CONFIG['user']}@{MAC_SSH_CONFIG['host']}")
    print(f"Mac remote directory: {MAC_SSH_CONFIG['remote_base']}")
    print(f"Raw content threshold: {RAW_CONTENT_THRESHOLD} bytes (nearly everything)")
    print("Strategy: Transfer ALL content as original raw files to emulate real web traffic")
    
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
    
    polling_interval = 1  # seconds
    
    print("Starting main polling loop...")
    print("Press Ctrl+C to stop")
    
    # Main loop
    try:
        while True:
            check_request_files()
            time.sleep(polling_interval)
    except KeyboardInterrupt:
        print("Shutting down...")
        save_cookies()
    except Exception as e:
        print(f"Error in main loop: {e}")
        save_cookies()

if __name__ == "__main__":
    main()