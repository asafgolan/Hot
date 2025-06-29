#!/usr/bin/env python3
"""
Windows-side handler using mitmproxy executable directly to enhance
v 3 file-based proxy with cookies and browser state
"""
import os
import json
import time
import subprocess
import threading
import tempfile
import re
import datetime
import base64
import mimetypes
import argparse

# Constants
INCOMING_DIR = r"C:\WebServerTest\bt_transfer\incoming"
OUTGOING_DIR = r"C:\WebServerTest\bt_transfer\outgoing"
CACHE_DIR = r"C:\WebServerTest\bt_transfer\cache"
FLOW_DIR = r"C:\WebServerTest\bt_transfer\flows"
MITM_EXEC = r"mitmdump.exe"  # Executable name (must be in PATH or same directory)
COOKIE_FILE = os.path.join(FLOW_DIR, "cookies.json")

# Cookie jar to maintain state
COOKIE_JAR = {}

# Ensure directories exist
for directory in [INCOMING_DIR, OUTGOING_DIR, CACHE_DIR, FLOW_DIR]:
    os.makedirs(directory, exist_ok=True)

def load_cookies():
    """Load cookies from disk if available"""
    global COOKIE_JAR
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                COOKIE_JAR = json.load(f)
                print(f"Loaded {len(COOKIE_JAR)} domains with cookies")
        except Exception as e:
            print(f"Error loading cookies: {e}")

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

def record_flow_with_mitmdump(url, flow_file):
    """Use mitmdump to record a single request flow"""
    try:
        # Run mitmdump with a script to capture traffic
        script_content = f'''
import sys
from mitmproxy import http

class CaptureAllRelatedResources:
    def __init__(self):
        self.base_url = "{url}"
        self.base_domain = self.extract_domain("{url}")
        self.captured_main = False
        self.capture_counter = 0
        self.max_captures = 20  # Limit the number of captures to prevent endless processing
        self.timeout = time.time() + 15  # 15-second timeout
        
    def extract_domain(self, url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
        
    def request(self, flow):
        current_domain = self.extract_domain(flow.request.url)
        
        # Log all requests we're seeing
        print(f"Seeing request for: {flow.request.url} [domain: {current_domain}]")
        
        # If this is our target URL, mark it as captured
        if self.base_url in flow.request.url and not self.captured_main:
            self.captured_main = True
            self.capture_counter += 1
            print(f"[{self.capture_counter}] Capturing main request: {flow.request.url}")
        
        # If this is from the same domain, also process it
        elif current_domain == self.base_domain and self.capture_counter < self.max_captures:
            self.capture_counter += 1
            print(f"[{self.capture_counter}] Capturing related resource: {flow.request.url}")
        
        # Otherwise kill the flow
        else:
            print(f"Ignoring unrelated request: {flow.request.url}")
            flow.kill()
            
    def response(self, flow):
        if self.captured_main and time.time() > self.timeout:
            print(f"Timeout reached after capturing {self.capture_counter} resources")
            ctx.master.shutdown()
        print(f"Response captured with status {flow.response.status_code} for {flow.request.url}")

addons = [CaptureAllRelatedResources()]
'''
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
            f.write(script_content)
            script_file = f.name
        
        # Use subprocess to run mitmdump with our script
        cmd = [MITM_EXEC, '-w', flow_file, '-s', script_file, '--mode', 'transparent']
        process = subprocess.Popen(cmd)
        
        # Wait for process to finish or timeout
        process.wait(timeout=60)
        return True
    except Exception as e:
        print(f"Error recording flow: {e}")
        return False

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
        elif url.endswith('.jpg') or url.endswith('.jpeg'):
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

def process_request_file(file_path):
    """Process a single request file using mitmdump if possible"""
    try:
        # Read the request data
        with open(file_path, 'r') as f:
            request_data = json.load(f)
            
        request_id = request_data.get('id')
        url = request_data.get('url', '')
        method = request_data.get('method', 'GET')
        headers = request_data.get('headers', {})
        body = request_data.get('body', '')
        is_resource = request_data.get('is_resource', False)
        likely_binary = request_data.get('likely_binary', False)
        
        print(f"Processing request: {url} (Resource: {is_resource})")
        
        # Extract domain
        domain = url.split('://', 1)[-1].split('/', 1)[0] if '://' in url else url.split('/', 1)[0]
        
        # Apply cookies to request headers
        headers = apply_cookies_to_headers(headers, domain)
        request_data['headers'] = headers
        
        # Update the request file with cookies
        with open(file_path, 'w') as f:
            json.dump(request_data, f, indent=2)
        
        try:
            # Try to use mitmdump to handle the request
            flow_file = os.path.join(FLOW_DIR, f"req_{request_id}.flow")
            
            # This doesn't work consistently with the executable
            # Just use the standard library instead
            use_urllib = True
            
            if not use_urllib:
                if record_flow_with_mitmdump(url, flow_file):
                    # Process the recorded flow - extract response and cookies
                    print("Flow recorded, extracting response...")
                    # This would require parsing the flow file format
                    # Instead we'll make direct request below
            
            # Make the request directly
            import urllib.request
            import urllib.error
            import ssl
            import base64
            
            # Create a context for HTTPS requests
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Create the request
            req = urllib.request.Request(url, method=method)
            
            # Add headers
            for header, value in headers.items():
                req.add_header(header, value)
            
            # Add body if it exists
            data = None
            if body and method != "GET":
                data = body.encode('utf-8')
            
            # Make the request
            try:
                try:
                    response = urllib.request.urlopen(req, data=data, context=context, timeout=30)
                    
                    # Read response data
                    response_body = response.read()
                    response_code = response.status
                    response_headers = {}
                    
                    for header, value in response.getheaders():
                        response_headers[header] = value
                        
                except urllib.error.HTTPError as http_err:
                    # Handle HTTP errors including 304 Not Modified
                    response_code = http_err.code
                    response_headers = dict(http_err.headers.items())
                    
                    # For 304 Not Modified, we don't need body content
                    if response_code == 304:
                        response_body = b''
                        print(f"Handling 304 Not Modified response for {url}")
                    else:
                        # For other errors, get the error body
                        response_body = http_err.read()
                        print(f"HTTP Error {response_code} for {url}: {http_err}")
                
                # Check if response is binary
                is_binary = likely_binary  # Start with the request hint
                
                # Get content type from headers or detect from URL
                content_type = response_headers.get('Content-Type', '')
                if not content_type:
                    detected_type = get_content_type(url)
                    if detected_type:
                        response_headers['Content-Type'] = detected_type
                        content_type = detected_type
                else:
                    # Log the actual content type for debugging
                    print(f"Server returned Content-Type: {content_type} for {url}")
                
                # Determine if content is binary based on content type or previous hint
                if not is_binary and content_type:
                    binary_types = ['image/', 'audio/', 'video/', 'application/pdf', 'application/octet-stream', 'font/']
                    is_binary = any(content_type.startswith(bt) for bt in binary_types)
                
                if is_resource:
                    print(f"Resource {url} fetched with Content-Type: {response_headers.get('Content-Type')}")
                
                # Extract cookies from response
                extract_cookies_from_headers(response_headers, domain)
                
                # Save updated cookies
                save_cookies()
                
                # Special handling for 304 Not Modified response
                if response_code == 304:
                    # 304 responses typically don't have a body
                    content_str = ""
                    is_binary = False  # Force non-binary for 304
                    print(f"304 Not Modified response for {url}")
                # Process response body based on binary flag
                elif is_binary:
                    # Encode binary content as base64
                    content_str = base64.b64encode(response_body).decode('ascii')
                    print(f"Encoded binary content as base64 ({len(content_str)} chars)")
                else:
                    # Try to decode as text
                    try:
                        content_str = response_body.decode('utf-8')
                    except UnicodeDecodeError:
                        # If decode fails, it's likely binary - use base64
                        is_binary = True
                        content_str = base64.b64encode(response_body).decode('ascii')
                        print(f"Content couldn't be decoded as UTF-8, treating as binary")
                
                # Create response json - ALWAYS use 'content' as the field name for consistency
                response_data = {
                    "id": request_id,
                    "timestamp": int(time.time()),
                    "status": response_code,
                    "headers": response_headers,
                    "content": content_str,  # Standardize on 'content' field
                    "is_resource": is_resource,
                    "is_binary": is_binary
                }
                
                # Write response file
                response_file = os.path.join(OUTGOING_DIR, f"resp_{request_id}.json")
                with open(response_file, 'w', encoding='utf-8') as f:
                    json.dump(response_data, f, ensure_ascii=False, indent=2)
                    
                print(f"Response file created: {response_file}")
                return True
                
            except Exception as e:
                print(f"Error making request: {e}")
                
                # Create error response
                response_data = {
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
                    json.dump(response_data, f, ensure_ascii=False, indent=2)
                    
                print(f"Error response file created: {response_file}")
                return False
        
        except Exception as e:
            print(f"Error processing request: {e}")
            
            # Create error response
            error_data = {
                "id": request_id,
                "timestamp": int(time.time()),
                "status": 500,
                "headers": {"Content-Type": "text/plain"},
                "content": f"Error: {str(e)}",
                "is_binary": False
            }
            
            # Write error response file
            response_file = os.path.join(OUTGOING_DIR, f"resp_{request_id}.json")
            with open(response_file, "w", encoding="utf-8") as f:
                json.dump(error_data, f, ensure_ascii=False)
        
        # Remove processed request file
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        print(f"Error processing request file {file_path}: {e}")

def check_request_files():
    """Check for and process any request files"""
    try:
        request_files = [f for f in os.listdir(INCOMING_DIR) if f.startswith("req_") and f.endswith(".json")]
        
        if request_files:
            print(f"Found {len(request_files)} requests to process")
            
        for req_file in request_files:
            file_path = os.path.join(INCOMING_DIR, req_file)
            success = process_request_file(file_path)
            
            # Delete the request file after successful processing
            if success and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted processed request file: {file_path}")
                except Exception as e:
                    print(f"Error deleting request file: {e}")
            
    except Exception as e:
        print(f"Error checking request files: {e}")

def main():
    """Main function to run the handler"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Windows bridge for file-based proxy')
    parser.add_argument('--no-cookies', action='store_true', help='Do not load cookies at startup')
    parser.add_argument('--reset-cookies', action='store_true', help='Reset cookie jar before starting')
    args = parser.parse_args()
    
    print(f"Starting Windows mitmproxy bridge handler at {datetime.datetime.now()}")
    
    # Handle cookie options
    if args.reset_cookies:
        global COOKIE_JAR
        COOKIE_JAR = {}
        print("Cookie jar has been reset")
        save_cookies()  # Save empty cookie jar to file
    elif not args.no_cookies:
        # Load any stored cookies if not disabled
        load_cookies()
    else:
        print("Starting with empty cookie jar (--no-cookies specified)")
    
    polling_interval = 1  # seconds
    
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
