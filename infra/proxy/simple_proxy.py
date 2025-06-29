#!/usr/bin/env python3
"""
Simple HTTP/HTTPS proxy for testing connectivity
Only routes hot.net domains through Windows, direct connection for others
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import socket
import ssl
import threading
import os
import time
import json
import traceback
import base64
from urllib.parse import urlparse, parse_qs

# Global dictionary to track recent requests and prevent duplicates
recent_requests = {}

# Configuration
PORT = 8000
DEBUG = True


# List of domains to ignore/handle specially
IGNORED_DOMAINS = [
    "static.ess.apple.com",     # Apple certificate validation
    "ocsp.digicert.com",        # Certificate validation
    "suconfig.apple.com",        # Apple software update config
    "clients2.google.com",       # Google time services
    "clients4.google.com",       # Google services
    "ocsp.apple.com",           # Apple certificate services
    "valid.apple.com",          # Apple validation services
    "crl.apple.com",            # Apple certificate revocation
    "identity.apple.com",        # Apple identity validation
    "gstatic.com",              # Google static content and connectivity checks
]

class SimpleProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Access the global recent_requests dictionary
        global recent_requests
        
        url = self.path
        
        # If URL doesn't have a protocol, add it
        if not url.startswith('http'):
            url = 'http://' + url
            
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.netloc
        
        if DEBUG:
            print(f"Requested: {url}")
            print(f"Host: {host}")
            
        # Check if this is a domain we should ignore
        for ignored_domain in IGNORED_DOMAINS:
            if ignored_domain in host:
                if DEBUG:
                    print(f"Ignoring request for {host} (in ignored domains list)")
                # Return a simple 200 response immediately
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
        
        # Check if hot.net domain
        if 'hot.net' in host or 'hot-qc' in host:
            if DEBUG:
                print(f"Hot.net domain detected: {host}")
                print(f"Request headers: {dict(self.headers)}")
            
            # Check if this is a resource request (CSS, JS, image)
            is_resource = False
            path = parsed_url.path.lower()
            if path.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2')):
                is_resource = True
                if DEBUG:
                    print(f"Resource request detected: {path}")
                
            # Create a unique request ID
            import uuid
            import time
            import json
            
            # Check if we've seen this request recently
            global recent_requests
            request_key = f"{url}"
            current_time = time.time()
            
            # Check for duplicate requests within 5 seconds
            if request_key in recent_requests:
                last_time = recent_requests[request_key]['time']
                if current_time - last_time < 5:  # 5 second deduplication window
                    if DEBUG:
                        print(f"Duplicate request detected for {url}, using existing request ID")
                    request_id = recent_requests[request_key]['id']
                    duplicate_request = True
                else:
                    # If it's been more than 5 seconds, treat as new request
                    request_id = str(uuid.uuid4())
                    duplicate_request = False
            else:
                request_id = str(uuid.uuid4())
                duplicate_request = False
            
            # Store in recent requests
            recent_requests[request_key] = {
                'id': request_id, 
                'time': current_time
            }
            
            # Clean up old entries from the recent_requests dictionary
            to_delete = []
            for key, value in recent_requests.items():
                if current_time - value['time'] > 60:  # Remove entries older than 1 minute
                    to_delete.append(key)
            for key in to_delete:
                del recent_requests[key]
            
            outgoing_dir = os.path.expanduser("~/Hot/infra/proxy/bt_transfer/outgoing")
            incoming_dir = os.path.expanduser("~/Hot/infra/proxy/bt_transfer/incoming")
            
            # Ensure directories exist
            os.makedirs(outgoing_dir, exist_ok=True)
            os.makedirs(incoming_dir, exist_ok=True)
            
            # Create request file for Windows
            # Fix relative paths for resources
            final_url = url
            
            # Detect if this should be HTTPS based on URL or referer
            original_scheme = parsed_url.scheme
            use_https = original_scheme == 'https'
            
            # If URL is for hot.net, check if it should use HTTPS
            if 'hot.net' in parsed_url.netloc or 'hot-buzz' in parsed_url.netloc:
                # For hot-buzz domains, always use HTTPS on the Windows side
                if 'hot-buzz' in parsed_url.netloc:
                    use_https = True
                    if DEBUG:
                        print(f"Detected hot-buzz domain, using HTTPS: {parsed_url.netloc}")
            
            if is_resource and not url.startswith('http'):
                # This might be a relative path - reconstruct proper URL
                referer = self.headers.get('Referer')
                if referer:
                    # Extract base from referer
                    base_parts = urlparse(referer)
                    scheme = base_parts.scheme
                    
                    # If referer uses HTTPS, our request should too
                    if scheme == 'https':
                        use_https = True
                    
                    base_url = f"{scheme}://{base_parts.netloc}"
                    
                    # Handle different relative path formats
                    if url.startswith('/'):
                        # Absolute path from domain root
                        final_url = f"{base_url}{url}"
                    else:
                        # Relative to current path
                        path_parts = base_parts.path.split('/')
                        if path_parts and path_parts[-1] and '.' in path_parts[-1]:  # If last part looks like a file
                            path_parts.pop()
                        base_path = '/'.join(path_parts)
                        final_url = f"{base_url}{base_path}/{url}"
                    
                    if DEBUG:
                        print(f"Corrected relative URL: {url} -> {final_url}")
            
            # Force scheme based on use_https flag
            if use_https and not final_url.startswith('https://'):
                # Replace http:// with https:// or add https:// if needed
                if final_url.startswith('http://'):
                    final_url = 'https://' + final_url[7:]
                elif not final_url.startswith('http'):
                    final_url = 'https://' + final_url
            
            # Determine if this is likely a binary resource based on file extension
            likely_binary = False
            binary_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.ico', '.pdf', '.woff', '.woff2', '.ttf', '.eot')
            path_lower = parsed_url.path.lower()
            
            # Check both URL and path for binary extensions
            if final_url.lower().endswith(binary_extensions) or path_lower.endswith(binary_extensions):
                likely_binary = True
                
            # Special case for images in paths containing 'images' directory
            if '/images/' in path_lower or '/img/' in path_lower:
                likely_binary = True
                if DEBUG:
                    print(f"Detected likely image in path: {path_lower}")
                if DEBUG:
                    print(f"Detected likely binary resource: {parsed_url.path}")
            
            request_data = {
                "id": request_id,
                "timestamp": int(time.time()),
                "method": "GET",
                "url": final_url,
                "headers": dict(self.headers),
                "is_resource": is_resource,
                "likely_binary": likely_binary
            }
            
            # If it's not a duplicate request, write the request file
            outgoing_file = os.path.join(outgoing_dir, f"req_{request_id}.json")
            
            if not duplicate_request:
                with open(outgoing_file, "w") as f:
                    json.dump(request_data, f, indent=2)
                
                if DEBUG:
                    print(f"Created request file: {outgoing_file}")
                    print(f"Waiting for Windows to process request...")
            else:
                if DEBUG:
                    print(f"Using existing request ID {request_id} for duplicate request")
                    print(f"Checking for existing response file...")
            
            
            # Wait for a maximum of 60 seconds for the response file
            response_file = os.path.join(incoming_dir, f"resp_{request_id}.json")
            timeout = 60  # seconds
            start_time = time.time()
            
            while not os.path.exists(response_file) and (time.time() - start_time < timeout):
                time.sleep(0.2)
            
            # Process response
            if os.path.exists(response_file):                
                if DEBUG and is_resource:
                    print(f"Processing resource response for: {path}")
                try:
                    # Read response file with error handling
                    try:
                        with open(response_file, "r", encoding="utf-8") as f:
                            response_content = f.read()
                            
                        if DEBUG:
                            print(f"Response file content length: {len(response_content)} bytes")

                        # Special handling for large files that might contain multiline base64
                        if len(response_content) > 100000 and '"content": "' in response_content:
                            if DEBUG:
                                print("Large file with possible multiline base64 content detected, normalizing...")
                            import re
                            # Pattern to match the content field including multiline content
                            pattern = r'("content": ")([^"]*?)(")'
                            def normalize_base64(match):
                                # Remove all whitespace from the base64 content part
                                normalized = ''.join(match.group(2).split())
                                return match.group(1) + normalized + match.group(3)
                            
                            try:
                                # Use regex with DOTALL flag to handle newlines within the match
                                normalized_content = re.sub(pattern, normalize_base64, response_content, flags=re.DOTALL)
                                response_data = json.loads(normalized_content)
                                if DEBUG:
                                    print("Successfully parsed JSON with normalized base64 content")
                            except (json.JSONDecodeError, re.error) as e:
                                if DEBUG:
                                    print(f"Normalization failed: {e}, falling back to original content")
                                # Fall back to original parsing if normalization fails
                                response_data = json.loads(response_content)
                        else:
                            response_data = json.loads(response_content)
                            
                        response_data = json.loads(response_content)
                    except json.JSONDecodeError as json_err:
                        if DEBUG:
                            print(f"JSON decode error: {json_err}")
                            print(f"First 100 chars of file: {response_content[:100]}")
                        
                        # Try reading with different encoding
                        try:
                            with open(response_file, "r", encoding="utf-8") as f:
                                response_content = f.read()
                        except UnicodeDecodeError:
                            # If UTF-8 fails, read as binary and decode carefully
                            with open(response_file, "rb") as f:
                                response_content = f.read().decode('utf-8', errors='replace')
                                print(f"Warning: Used fallback encoding for {response_file}")
                        
                        # Parse JSON with extra error handling
                        try:
                            response_data = json.loads(response_content)
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                            print(f"First 100 chars of content: {response_content[:100]}")
                            raise ValueError(f"Invalid JSON response format: {e}")
                    try:
                        # Parse response data
                        status_code = int(response_data.get('status', 500))
                        headers = response_data.get('headers', {})
                        is_binary = response_data.get('is_binary', False)
                        
                        # Handle 304 Not Modified response - it's not an error, just a redirect to use the cached version
                        if status_code == 304:
                            if DEBUG:
                                print(f"Received 304 Not Modified response - using cached version")
                            # Just pass through the 304 response with headers
                            self.send_response(304)
                            for header, value in headers.items():
                                if header.lower() not in ("transfer-encoding", "content-length"):
                                    self.send_header(header, value)
                            self.end_headers()
                            
                            # Delete the response file before returning for 304 responses
                            try:
                                os.remove(response_file)
                                print(f"Deleted 304 response file: {response_file}")
                            except Exception as e:
                                print(f"Error deleting 304 response file: {e}")
                            return
                        
                        # Get content from either 'content' or 'body' field
                        content = response_data.get('content', response_data.get('body', ''))
                        
                        # Handle binary data if it's base64 encoded
                        content_bytes = None
                        if is_binary and content:
                            try:
                                content_bytes = base64.b64decode(content)
                                # Don't assign to content variable yet - we'll use content_bytes directly
                            except Exception as e:
                                print(f"Error decoding base64 content: {e}")
                        else:
                            content_bytes = content.encode('utf-8') if content else b''
                        
                        # Check content type and handle images properly
                        content_type = ''
                        for header_name, header_value in headers.items():
                            if header_name.lower() == 'content-type':
                                content_type = header_value.lower()
                                break
                                
                        # Force binary mode for common image types regardless of is_binary flag
                        # This handles cases where content-type might be incorrectly set
                        path_lower = parsed_url.path.lower()
                        if any(ext in path_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.ico']) or \
                           any(img_type in (content_type or '') for img_type in ['image/png', 'image/jpeg', 'image/gif', 'image/x-icon']):
                            if not is_binary:
                                print(f"Forcing binary mode for image: {parsed_url.path} ({content_type})")
                                is_binary = True
                                # Re-decode content if needed
                                if content and not content_bytes:
                                    try:
                                        content_bytes = base64.b64decode(content)
                                    except:
                                        # If not base64, treat as raw bytes
                                        content_bytes = content.encode('latin1', errors='replace')
                        
                        # If HTML content, rewrite resource URLs to be absolute
                        if not is_binary and 'text/html' in content_type and isinstance(content, str):
                            import re
                            
                            # Extract base URL (protocol + domain)
                            base_domain = urlparse(url).netloc
                            scheme = urlparse(url).scheme
                            base_url = f"{scheme}://{base_domain}"
                            
                            # Function to make URLs absolute
                            def make_absolute(match):
                                resource_url = match.group(2)
                                # Skip URLs that are already absolute
                                if resource_url.startswith('http://') or resource_url.startswith('https://') or resource_url.startswith('//'):
                                    return match.group(0)
                                # Make relative URL absolute
                                if resource_url.startswith('/'):
                                    return f'{match.group(1)}{base_url}{resource_url}{match.group(3)}'
                                else:
                                    path_parts = urlparse(url).path.split('/')
                                    if path_parts[-1] and '.' in path_parts[-1]:  # If last part looks like a file
                                        path_parts.pop()
                                    dir_path = '/'.join(path_parts)
                                    if not dir_path.endswith('/'):
                                        dir_path += '/'
                                    return f'{match.group(1)}{base_url}{dir_path}{resource_url}{match.group(3)}'
                            
                            # Rewrite URLs in various HTML attributes
                            content = re.sub(r'(href=["\'])([^"\']*)(["\'])', make_absolute, content)
                            content = re.sub(r'(src=["\'])([^"\']*)(["\'])', make_absolute, content)
                            content = re.sub(r'(url\(["\']?)([^\)"\']*)(["\']?\))', make_absolute, content)
                            
                            # Convert back to bytes
                            content_bytes = content.encode('utf-8')
                            
                            if DEBUG:
                                print(f"Rewrote HTML content with absolute URLs")
                    except Exception as e:
                        print(f"Error processing response data: {e}")
                        status_code = 500
                        headers = {"Content-Type": "text/html"}
                        content = f"<html><body><h1>Error</h1><p>Failed to process response: {str(e)}</p></body></html>"
                    else:
                        # Send response with status code
                        self.send_response(status_code)
                        
                        # Send headers
                        for header, value in headers.items():
                            if header.lower() not in ("transfer-encoding", "content-length"):
                                self.send_header(header, value)
                        
                        # Set content length based on binary data
                        self.send_header('Content-Length', str(len(content_bytes) if content_bytes else 0))
                        self.end_headers()
                        
                        # Send content if we have it
                        if content_bytes:
                            self.wfile.write(content_bytes)
                    
                    if DEBUG:
                        print(f"Response sent to browser: {status_code}")
                    
                    # Clean up - delete file after successful processing
                    try:
                        os.remove(response_file)
                        print(f"Deleted processed response file: {response_file}")
                    except Exception as e:
                        print(f"Error deleting response file: {e}")
                except Exception as e:
                    if DEBUG:
                        print(f"Error processing response file: {e}")
                        import traceback
                        traceback.print_exc()
                    self.send_error(500, f"Error processing response: {str(e)}")
                    
                    # Don't delete file on error to allow inspection
                    print(f"Keeping response file for inspection: {response_file}")
            else:
                # Timeout
                self.send_response(504)  # Gateway Timeout
                error_msg = f"<html><body><h1>504 Gateway Timeout</h1><p>No response received from Windows within {timeout} seconds.</p></body></html>"
                self.send_header("Content-Length", str(len(error_msg)))
                self.end_headers()
                self.wfile.write(error_msg.encode("utf-8"))
                if DEBUG:
                    print(f"Timeout waiting for response from Windows for URL: {url}")
                # For resource requests, just return an empty response instead of error
                if is_resource and path.endswith(('.css', '.js')):
                    self.send_response(200)
                    if path.endswith('.css'):
                        self.send_header('Content-Type', 'text/css')
                    else:
                        self.send_header('Content-Type', 'application/javascript')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    self.send_error(504, "Gateway Timeout")
        else:
            # For non-hot.net domains, fetch the content directly
            try:
                if DEBUG:
                    print(f"Direct access for: {url}")
                
                # Handle broken pipe gracefully
                try:
                    # Check if the client has disconnected before making request
                    try:
                        self.connection.settimeout(0.1)
                        check = self.connection.recv(1, socket.MSG_PEEK)
                        # If we get here without error, there's data to read, which is unexpected
                        if DEBUG:
                            print(f"Client may have sent unexpected data")
                    except (socket.timeout, BlockingIOError):
                        # This is expected - no data available means client is still connected
                        pass
                    except (ConnectionResetError, BrokenPipeError) as e:
                        # Client disconnected
                        if DEBUG:
                            print(f"Client already disconnected: {e}")
                        return
                    finally:
                        # Reset timeout
                        self.connection.settimeout(None)

                    # Make a direct request
                    req = urllib.request.Request(url)
                    # Copy headers from browser
                    for header in self.headers:
                        if header.lower() not in ('host', 'proxy-connection'):
                            req.add_header(header, self.headers[header])
                    
                    with urllib.request.urlopen(req, timeout=10) as response:
                        # Check connection again before sending response
                        try:
                            self.connection.settimeout(0.1)
                            check = self.connection.recv(1, socket.MSG_PEEK)
                        except (socket.timeout, BlockingIOError):
                            # This is good - client is still waiting
                            pass
                        except (ConnectionResetError, BrokenPipeError) as e:
                            if DEBUG:
                                print(f"Client disconnected while fetching: {e}")
                            return
                        finally:
                            self.connection.settimeout(None)
                        
                        # Send the response code
                        self.send_response(response.status)
                        
                        # Send headers
                        response_headers = response.getheaders()
                        for header, value in response_headers:
                            # Skip content-encoding if we're not actually encoding the content
                            if header.lower() == 'content-encoding' and value.lower() in ('gzip', 'deflate', 'br'):
                                if DEBUG:
                                    print(f"Skipping content-encoding header: {header}: {value}")
                                continue
                            self.send_header(header, value)
                            
                        # Set proper content type for resources
                        if 'content-type' not in [h.lower() for h in response_headers]:
                            if path.endswith('.css'):
                                self.send_header('Content-Type', 'text/css')
                            elif path.endswith('.js'):
                                self.send_header('Content-Type', 'application/javascript')
                            elif path.endswith(('.jpg', '.jpeg')):
                                self.send_header('Content-Type', 'image/jpeg')
                            elif path.endswith('.png'):
                                self.send_header('Content-Type', 'image/png')
                            elif path.endswith('.gif'):
                                self.send_header('Content-Type', 'image/gif')
                        
                        # Send body
                        self.end_headers()
                        try:
                            self.wfile.write(response.read())
                        except (BrokenPipeError, ConnectionResetError) as e:
                            if DEBUG:
                                print(f"Client disconnected while sending response: {e}")
                            return
                        
                except Exception as e:
                    try:
                        self.send_response(500)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
                    except (BrokenPipeError, ConnectionResetError):
                        # If we can't send the error because the pipe is broken, just log it
                        pass
                    
                    if DEBUG:
                        print(f"Error accessing {url}: {e}")
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
                if DEBUG:
                    print(f"Error accessing {url}: {e}")
    
    # Implement POST method that works the same way
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        
        url = self.path
        if not url.startswith('http'):
            url = 'http://' + url
            
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        if DEBUG:
            print(f"POST request to: {url}")
        
        # Check if it's an ignored domain
        if any(ignored in host for ignored in IGNORED_DOMAINS):
            if DEBUG:
                print(f"Ignoring request to {host} - returning empty response")
            
            # Return a simple successful response rather than trying to connect
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
            
        if 'hot.net' in host or 'hot-qc' in host:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(f"Would proxy POST to {url} through Windows".encode('utf-8'))
        else:
            # For non-hot.net domains, send the POST directly
            try:
                req = urllib.request.Request(url, data=post_data, method='POST')
                
                # Copy headers from browser
                for header in self.headers:
                    if header.lower() not in ('host', 'proxy-connection', 'content-length'):
                        req.add_header(header, self.headers[header])
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    self.send_response(response.status)
                    
                    for header, value in response.getheaders():
                        if header.lower() not in ('transfer-encoding', 'connection'):
                            self.send_header(header, value)
                    
                    self.end_headers()
                    self.wfile.write(response.read())
                    
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
                if DEBUG:
                    print(f"Error accessing {url}: {e}")
    
    # Implement CONNECT method for HTTPS connections
    def do_CONNECT(self):
        host_port = self.path.split(':')
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 443
        
        if DEBUG:
            print(f"CONNECT request to: {host}:{port}")
        
        if 'hot.net' in host:
            # For hot.net domains, we can't proxy HTTPS through files yet
            self.send_response(200, "Connection Established")
            self.end_headers()
            self.wfile.write(f"HTTPS tunneling for hot.net not implemented yet".encode('utf-8'))
            
            if DEBUG:
                print(f"Hot.net HTTPS connection denied: {host}:{port}")
        else:
            # For non-hot.net domains, create a direct tunnel
            try:
                if DEBUG:
                    print(f"Creating tunnel to: {host}:{port}")
                
                # Connect to the target
                target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                target_socket.connect((host, port))
                
                # Tell the client the connection is established
                self.send_response(200, 'Connection Established')
                self.end_headers()
                
                # Create a wrapper around the socket returned from server
                client_socket = self.connection
                
                # Create threads to forward data in both directions
                def forward(source, destination):
                    try:
                        source_name = 'client' if source is client_socket else 'target'
                        dest_name = 'target' if destination is target_socket else 'client'
                        
                        while True:
                            data = source.recv(4096)
                            if len(data) == 0:
                                break
                            destination.send(data)
                    except:
                        # Connection closed
                        pass
                    finally:
                        # Close both sockets when done
                        for s in [client_socket, target_socket]:
                            try:
                                if not s._closed:
                                    s.shutdown(socket.SHUT_RDWR)
                                    s.close()
                            except:
                                pass
                
                # Start forwarding threads
                threading.Thread(target=forward, args=(client_socket, target_socket), daemon=True).start()
                forward(target_socket, client_socket)
                
            except Exception as e:
                self.send_error(502)
                if DEBUG:
                    print(f"CONNECT error {host}:{port}: {str(e)}")
                    import traceback
                    traceback.print_exc()

def main():
    """Run the proxy server"""
    # Ensure bt_transfer directories exist
    base_dir = os.path.join(os.path.expanduser("~"), "Hot", "infra", "proxy", "bt_transfer")
    incoming_dir = os.path.join(base_dir, "incoming")
    outgoing_dir = os.path.join(base_dir, "outgoing")
    os.makedirs(incoming_dir, exist_ok=True)
    os.makedirs(outgoing_dir, exist_ok=True)
    
    print(f"Starting simple proxy on port {PORT}")
    print("Will direct-connect all non-hot.net domains")
    print("HTTP hot.net domains will be proxied through Windows file-based proxy")
    print(f"Using request files in: {outgoing_dir}")
    print(f"Looking for responses in: {incoming_dir}")
    print("Press Ctrl+C to stop")
    
    # Track recent requests to avoid duplicates
    recent_requests = {}

    def cleanup_old_response_files():
        """Clean up response files that are older than 2 minutes"""
        try:
            incoming_dir = os.path.join(base_dir, "bt_transfer", "incoming")
            if not os.path.exists(incoming_dir):
                return
                
            current_time = time.time()
            for filename in os.listdir(incoming_dir):
                if filename.startswith("resp_") and filename.endswith(".json"):
                    file_path = os.path.join(incoming_dir, filename)
                    file_age = current_time - os.path.getmtime(file_path)
                    
                    # If file is older than 2 minutes, delete it
                    if file_age > 120:  # 120 seconds = 2 minutes
                        try:
                            os.remove(file_path)
                            print(f"Cleaned up old response file: {filename} (age: {file_age:.1f}s)")
                        except Exception as e:
                            print(f"Error cleaning up old file {filename}: {e}")
        except Exception as e:
            print(f"Error in cleanup routine: {e}")

    def run_proxy_server():
        # Allow reuse of address to avoid 'Address already in use' errors
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        
        # Create proxy server
        server_address = ('localhost', PORT)  # Replace with your desired address and port
        proxy_server = socketserver.ThreadingTCPServer(server_address, SimpleProxyHandler)
        
        print(f"Starting proxy server on {server_address[0]}:{server_address[1]}")
        
        # Start a background thread to clean up old response files
        def cleanup_thread():
            while True:
                time.sleep(30)  # Run cleanup every 30 seconds
                cleanup_old_response_files()
                
        import threading
        cleanup = threading.Thread(target=cleanup_thread, daemon=True)
        cleanup.start()
        
        try:
            proxy_server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping proxy server")
            proxy_server.shutdown()

    run_proxy_server()

if __name__ == "__main__":
    main()
