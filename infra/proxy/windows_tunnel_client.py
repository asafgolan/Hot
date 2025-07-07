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
    """HTTP handler that processes hot.net domain requests"""
    
    error_count = 0
    request_count = 0
    last_log_send_time = time.time()
    
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
        """Process incoming requests for hot.net domains"""
        try:
            # Parse the request URL
            url = self.path
            parsed_url = urlparse(url)
            
            logger.info(f"Received request: {self.command} {url}")
            
            # Check for malformed request formats
            try:
                # Attempt to parse headers to check for formatting issues
                headers_dict = dict(self.headers.items())
                
                # Check for malformed content
                if post_data and self.headers.get('Content-Type', '').startswith('application/json'):
                    try:
                        # Try to parse JSON data to check for formatting issues
                        if isinstance(post_data, bytes):
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
                # Log any formatting or parsing errors
                HotDomainHandler.error_count += 1
                request_info = {
                    'url': url,
                    'method': self.command,
                    'raw_headers': str(self.headers)
                }
                log_error('malformed_request', request_info, str(format_err), 400)
                
                self.send_error(400, f"Bad request format - {str(format_err)}")
                return
                
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
        if '400' in message and 'Bad Request' in message:
            HotDomainHandler.error_count += 1
            request_info = {
                'url': self.path if hasattr(self, 'path') else None,
                'method': self.command if hasattr(self, 'command') else None,
                'raw_message': message
            }
            log_error('bad_request', request_info, message, 400)
    
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


def start_http_server(port):
    """Start the HTTP server for handling requests"""
    try:
        handler = HotDomainHandler
        httpd = socketserver.ThreadingTCPServer(("", port), handler)
        
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
                      help='Remote port on Mac for the tunnel')
    
    args = parser.parse_args()
    
    # Start local HTTP server
    httpd = start_http_server(args.local_port)
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
            # Keep the script running
            while True:
                if not tunnel.check_tunnel():
                    logger.warning("Tunnel disconnected. Attempting to restart...")
                    tunnel.stop_tunnel()
                    if not tunnel.start_tunnel():
                        logger.error("Failed to restart tunnel. Exiting.")
                        break
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        finally:
            logger.info("Stopping HTTP server and SSH tunnel...")
            httpd.shutdown()
            tunnel.stop_tunnel()
    else:
        logger.error("Failed to start tunnel")
        httpd.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
