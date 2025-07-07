#!/usr/bin/env python3
"""
Windows SSH Tunnel Client for Hot E2E Testing
Sets up a reverse SSH tunnel and local HTTP service to handle hot.net domain requests
"""

import argparse
import http.server
import socketserver
import threading
import logging
import sys
import os
import time
import json
import socket
import datetime
import urllib.request
import urllib.error
from urllib.parse import urlparse
from ssh_tunnel_proxy import SSHTunnelProxy

# Setup logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'windows_tunnel_client.log')
error_log_file = os.path.join(log_dir, 'windows_error_logs.json')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger('windows_tunnel_client')

# Initialize error log if it doesn't exist
if not os.path.exists(error_log_file):
    with open(error_log_file, 'w') as f:
        json.dump([], f)

# Function to log errors to JSON file
def log_error(error_type, request_info, error_message, status_code=None):
    """Log errors to a structured JSON file that can be sent to Mac"""
    try:
        # Read existing logs
        with open(error_log_file, 'r') as f:
            logs = json.load(f)
        
        # Add new log entry
        logs.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'error_type': error_type,
            'status_code': status_code,
            'request_info': request_info,
            'error_message': str(error_message)
        })
        
        # Write updated logs
        with open(error_log_file, 'w') as f:
            json.dump(logs, f, indent=2)
            
        logger.info(f"Error logged to {error_log_file}")
    except Exception as e:
        logger.error(f"Failed to log error to JSON: {e}")

# Function to send logs to Mac
def send_logs_to_mac(mac_host, mac_port=8001):
    """Send error logs to Mac for centralized monitoring"""
    try:
        if not os.path.exists(error_log_file):
            logger.warning("No error logs to send")
            return False
            
        # Read the logs
        with open(error_log_file, 'r') as f:
            logs = f.read()
            
        # Prepare request to send logs
        url = f"http://{mac_host}:{mac_port}/receive_logs"
        headers = {
            'Content-Type': 'application/json',
            'X-Log-Source': 'windows-tunnel-client'
        }
        
        # Create request
        req = urllib.request.Request(
            url=url, 
            data=logs.encode(),
            headers=headers,
            method='POST'
        )
        
        # Send logs
        with urllib.request.urlopen(req) as response:
            result = response.read().decode()
            logger.info(f"Logs sent to Mac. Response: {result}")
            
            # After successful sending, archive the log file
            archive_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_file = os.path.join(log_dir, f"windows_error_logs_{archive_time}.json")
            os.rename(error_log_file, archive_file)
            
            # Create new empty log file
            with open(error_log_file, 'w') as f:
                json.dump([], f)
                
            return True
    except Exception as e:
        logger.error(f"Failed to send logs to Mac: {e}")
        return False

class HotDomainHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for hot.net domain requests"""
    
    # Class-level counters for monitoring
    request_count = 0
    error_count = 0
    last_log_send_time = time.time()
    
    # Define supported protocols to help identify binary data
    BINARY_SIGNATURES = {
        b'\x16\x03': 'TLS handshake',
        b'\x80\x80': 'SSL handshake',
        b'\x00\x01': 'Binary data',
    }
    
    def do_GET(self):
        """Handle GET requests"""
        HotDomainHandler.request_count += 1
        self._process_request()
    
    def do_POST(self):
        """Handle POST requests"""
        HotDomainHandler.request_count += 1
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        self._process_request(post_data)
        
    def do_PUT(self):
        """Handle PUT requests"""
        HotDomainHandler.request_count += 1
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        self._process_request(post_data)
        
    def do_DELETE(self):
        """Handle DELETE requests"""
        HotDomainHandler.request_count += 1
        self._process_request()
        
    def do_OPTIONS(self):
        """Handle OPTIONS requests"""
        HotDomainHandler.request_count += 1
        self._process_request()
    
    def _process_request(self, post_data=None):
        """Process HTTP request - common handler for all methods"""
        # Track requests for log sending threshold
        HotDomainHandler.request_count += 1
        
        # First, check if this might be binary data (like a TLS handshake)
        if hasattr(self, 'raw_requestline'):
            try:
                # Check if this is binary data like SSL/TLS handshake
                for sig, protocol_name in self.BINARY_SIGNATURES.items():
                    if self.raw_requestline.startswith(sig):
                        logger.info(f"Detected binary protocol: {protocol_name}")
                        # This is likely a TLS/SSL connection attempt
                        # Log it but don't treat as error
                        request_info = {
                            'detected_protocol': protocol_name,
                            'raw_data_sample': self.raw_requestline[:20].hex()
                        }
                        
                        # Instead of 400 error, handle properly
                        self.send_response(200)
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        # Just acknowledge the binary data
                        return
            except Exception as binary_err:
                logger.info(f"Error checking for binary protocol: {binary_err}")
        
        try:
            url = self.path
            
            # Check if this is a valid HTTP request with expected headers
            try:
                if post_data and self.headers.get('Content-Type') == 'application/json':
                    try:
                        # Try to parse JSON data
                        if post_data:
                            json.loads(post_data.decode('utf-8'))
                    except json.JSONDecodeError as json_err:
                        # Log the malformed JSON issue
                        HotDomainHandler.error_count += 1
                        request_info = {
                            'url': url,
                            'method': self.command,
                            'headers': dict(self.headers.items()),
                            'data_sample': post_data[:200].decode('utf-8', errors='replace') if post_data else None
                        }
                        log_error('malformed_json', request_info, str(json_err), 400)
                        
                        self.send_error(400, f"Bad request: Malformed JSON data - {str(json_err)}")
                        return
            except Exception as format_err:
                # Don't immediately fail - try to handle it gracefully
                logger.info(f"Non-critical format issue: {format_err}")
                
            # Process the actual request for hot.net domains
            # Here you can implement your domain-specific handling
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            response = f"""
            <html>
            <head><title>Windows Proxy Response</title></head>
            <body>
                <h1>Windows SSH Tunnel Proxy</h1>
                <p>Successfully processed request for: {url}</p>
                <p>Method: {self.command}</p>
                <p>Headers: {self.headers}</p>
                <p>Post data: {post_data}</p>
            </body>
            </html>
            """
            
            self.wfile.write(response.encode())
            logger.info(f"Request for {url} processed successfully")
            
            # Periodically check if we should send logs (every 50 requests or if error threshold met)
            current_time = time.time()
            if (HotDomainHandler.error_count >= 5 or 
                HotDomainHandler.request_count >= 50 or 
                (current_time - HotDomainHandler.last_log_send_time) > 300):  # 5 minutes
                
                # Try to send logs in a non-blocking way
                threading.Thread(target=self._try_send_logs).start()
                
                # Reset counters
                HotDomainHandler.error_count = 0
                HotDomainHandler.request_count = 0
                HotDomainHandler.last_log_send_time = current_time
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            HotDomainHandler.error_count += 1
            
            # Log the general processing error
            request_info = {
                'url': url,
                'method': self.command,
                'headers': dict(self.headers.items()) if hasattr(self, 'headers') else None
            }
            log_error('request_processing_error', request_info, str(e), 500)
            
            self.send_error(500, f"Internal error: {str(e)}")
    
    def log_message(self, format, *args):
        """Override to use our logger instead of printing to stderr"""
        message = format % args
        logger.info(message)
        
        # Special handling for 400 Bad Request errors
        if '400' in message:
            HotDomainHandler.error_count += 1
            request_info = {
                'url': self.path if hasattr(self, 'path') else None,
                'method': self.command if hasattr(self, 'command') else None,
                'raw_message': message,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # Check for binary data in the raw request
            if hasattr(self, 'raw_requestline'):
                # Try to identify common binary protocols
                for sig, protocol_name in self.BINARY_SIGNATURES.items():
                    if hasattr(self.raw_requestline, 'startswith') and self.raw_requestline.startswith(sig):
                        request_info['detected_protocol'] = protocol_name
                        request_info['binary_signature'] = self.raw_requestline[:10].hex()
            
            # Directly write to log file for immediate capture
            try:
                # Force immediate write to log file
                with open(error_log_file, 'r') as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        logs = []
                
                # Add new log entry
                logs.append({
                    'timestamp': datetime.datetime.now().isoformat(),
                    'error_type': 'bad_request_format',
                    'status_code': 400,
                    'request_info': request_info,
                    'error_message': message
                })
                
                # Write updated logs
                with open(error_log_file, 'w') as f:
                    json.dump(logs, f, indent=2)
                    
                logger.info(f"400 error logged to {error_log_file}")
            except Exception as e:
                logger.error(f"Failed to log 400 error to JSON: {e}")
    
    def _try_send_logs(self):
        """Try to send logs to Mac if there are errors"""
        # Get the Mac host information from the server
        try:
            server = self.server
            if hasattr(server, 'mac_host'):
                mac_host = server.mac_host
                mac_port = getattr(server, 'mac_port', 8001)
                send_logs_to_mac(mac_host, mac_port)
        except Exception as e:
            logger.error(f"Error sending logs to Mac: {e}")


def start_http_server(port, mac_host=None, mac_port=8001):
    """Start the HTTP server for handling requests"""
    try:
        handler = HotDomainHandler
        httpd = socketserver.ThreadingTCPServer(("", port), handler)
        
        # Store Mac host info for log sending
        if mac_host:
            httpd.mac_host = mac_host
            httpd.mac_port = mac_port
        
        logger.info(f"Starting HTTP server on port {port}")
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        return httpd
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Windows SSH Tunnel Client')
    parser.add_argument('--mac-host', required=True, 
                      help='Mac host for SSH connection')
    parser.add_argument('--mac-user', required=True, 
                      help='Username for SSH connection')
    parser.add_argument('--local-port', type=int, default=8080, 
                      help='Local port for HTTP server')
    parser.add_argument('--remote-port', type=int, default=8080, 
                      help='Remote port on Mac for SSH tunnel')
    parser.add_argument('--mac-proxy-port', type=int, default=8001,
                      help='Mac proxy port for sending logs back')
    parser.add_argument('--send-logs', action='store_true',
                      help='Enable sending logs to Mac')
    
    args = parser.parse_args()
    
    # Start the HTTP server with Mac host info for log sending
    httpd = start_http_server(args.local_port, args.mac_host, args.mac_proxy_port)
    if not httpd:
        logger.error("Failed to start local HTTP server. Exiting.")
        sys.exit(1)
    
    # Create and start SSH tunnel
    tunnel = SSHTunnelProxy(
        remote_host=args.mac_host,
        remote_user=args.mac_user,
        local_port=args.local_port,
        remote_port=args.remote_port
    )
    
    if tunnel.start_tunnel():
        logger.info(f"Tunnel started successfully. Windows HTTP server on port {args.local_port} is now available on Mac at localhost:{args.remote_port}")
        
        try:
            # Send initial logs if there are any and sending is enabled
            if args.send_logs:
                logger.info("Checking for logs to send to Mac...")
                send_logs_to_mac(args.mac_host, args.mac_proxy_port)
            
            logger.info("Press Ctrl+C to stop the client")
            while True:
                # Check if tunnel is active, restart if needed
                if not tunnel.check_tunnel():
                    logger.info("Tunnel not active, restarting...")
                    tunnel.start_tunnel()
                
                # Periodically send logs if enabled
                if args.send_logs and time.time() - HotDomainHandler.last_log_send_time > 300:
                    threading.Thread(target=lambda: send_logs_to_mac(args.mac_host, args.mac_proxy_port)).start()
                    HotDomainHandler.last_log_send_time = time.time()
                    
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        finally:
            # Send final logs before shutting down
            if args.send_logs:
                logger.info("Sending final logs before shutdown...")
                send_logs_to_mac(args.mac_host, args.mac_proxy_port)
                
            # Clean up
            if tunnel:
                tunnel.stop_tunnel()
            if httpd:
                httpd.shutdown()
    else:
        logger.error("Failed to start tunnel")
        httpd.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
