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
import urllib.request
import urllib.error
from urllib.parse import urlparse
from ssh_tunnel_proxy import SSHTunnelProxy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('windows_tunnel_client')

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
