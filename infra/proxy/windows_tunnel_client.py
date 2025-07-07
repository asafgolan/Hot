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
    
    def do_GET(self):
        """Handle GET requests"""
        self._process_request()
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        self._process_request(post_data)
    
    def _process_request(self, post_data=None):
        """Process incoming requests for hot.net domains"""
        try:
            # Parse the request URL
            url = self.path
            parsed_url = urlparse(url)
            
            logger.info(f"Received request: {self.command} {url}")
            
            # Here you can implement your domain-specific handling
            # For hot.net domains that previously used the file-based proxy
            
            # Example response
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
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            self.send_error(500, f"Internal error: {str(e)}")
    
    def log_message(self, format, *args):
        """Override to use our logger instead of printing to stderr"""
        logger.info(format % args)


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
