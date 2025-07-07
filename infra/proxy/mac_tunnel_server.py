#!/usr/bin/env python3
"""
Mac SSH Tunnel Server for Hot E2E Testing
Handles requests received through the SSH tunnel from Windows
"""

import argparse
import logging
import sys
import time
import http.server
import socketserver
import threading
from urllib.parse import urlparse
import urllib.request
import urllib.error
from ssh_tunnel_proxy import SSHTunnelProxy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('mac_tunnel_server')

class ForwardingHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that forwards hot.net domain requests to the SSH tunnel"""
    
    def do_GET(self):
        """Handle GET requests"""
        self._forward_request()
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        self._forward_request(post_data)
    
    def _forward_request(self, post_data=None):
        """Forward requests for hot.net domains through the SSH tunnel"""
        try:
            # Parse the request URL
            url = self.path
            parsed_url = urlparse(url)
            
            logger.info(f"Received request: {self.command} {url}")
            
            # Determine if this is a hot.net domain that should be forwarded
            hostname = parsed_url.netloc or self.headers.get('Host', '')
            
            if 'hot.net' in hostname:
                # Forward to Windows via the SSH tunnel
                tunnel_url = f"http://localhost:{self.server.tunnel_port}{url}"
                
                logger.info(f"Forwarding hot.net request to Windows: {tunnel_url}")
                
                # Prepare headers (exclude hop-by-hop headers)
                headers = {}
                for header, value in self.headers.items():
                    if header.lower() not in ('connection', 'keep-alive', 'proxy-authenticate', 
                                            'proxy-authorization', 'te', 'trailers', 
                                            'transfer-encoding', 'upgrade'):
                        headers[header] = value
                
                # Forward the request to the tunnel
                req = urllib.request.Request(tunnel_url)
                
                # Add headers
                for header, value in headers.items():
                    req.add_header(header, value)
                
                # Add timeout and post data if needed
                if self.command == 'POST' and post_data:
                    response = urllib.request.urlopen(req, data=post_data, timeout=30)
                else:
                    response = urllib.request.urlopen(req, timeout=30)
                
                # Return the response from Windows
                self.send_response(response.status)
                
                # Copy response headers
                for header, value in response.getheaders():
                    if header.lower() not in ('connection', 'keep-alive', 'proxy-authenticate',
                                           'proxy-authorization', 'te', 'trailers',
                                           'transfer-encoding', 'upgrade'):
                        self.send_header(header, value)
                
                self.end_headers()
                self.wfile.write(response.read())
                
                logger.info(f"Successfully forwarded response for {url}, status {response.status}")
            else:
                # Handle non-hot.net domains directly
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                response = f"""
                <html>
                <head><title>Mac Proxy Response</title></head>
                <body>
                    <h1>Mac SSH Tunnel Proxy</h1>
                    <p>This request for {hostname} would be handled directly on Mac.</p>
                    <p>In a full implementation, direct HTTP requests would go to the internet.</p>
                </body>
                </html>
                """
                
                self.wfile.write(response.encode())
                logger.info(f"Directly handled non-hot.net request for {url}")
                
        except Exception as e:
            logger.error(f"Error forwarding request: {e}")
            self.send_error(500, f"Internal error: {str(e)}")
    
    def log_message(self, format, *args):
        """Override to use our logger instead of printing to stderr"""
        logger.info(format % args)


def start_proxy_server(port, tunnel_port):
    """Start the HTTP proxy server for handling and forwarding requests"""
    try:
        handler = ForwardingHandler
        httpd = socketserver.ThreadingTCPServer(("", port), handler)
        # Store the tunnel port in the server object so handlers can access it
        httpd.tunnel_port = tunnel_port
        
        logger.info(f"Starting proxy server on port {port}, forwarding hot.net domains to port {tunnel_port}")
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        return httpd
    except Exception as e:
        logger.error(f"Failed to start proxy server: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Mac SSH Tunnel Server')
    parser.add_argument('--windows-host', required=True, 
                      help='Windows host for SSH connection')
    parser.add_argument('--windows-user', required=True, 
                      help='Username for SSH connection')
    parser.add_argument('--proxy-port', type=int, default=8000, 
                      help='Local port for proxy server')
    parser.add_argument('--tunnel-port', type=int, default=8080, 
                      help='Port for the SSH tunnel')
    parser.add_argument('--setup-tunnel', action='store_true',
                      help='Set up a forward tunnel to Windows (usually not needed with reverse tunnel)')
    
    args = parser.parse_args()
    
    # Start proxy server
    httpd = start_proxy_server(args.proxy_port, args.tunnel_port)
    if not httpd:
        logger.error("Failed to start proxy server. Exiting.")
        sys.exit(1)
    
    # Optionally create and start SSH tunnel (usually not needed with reverse tunnel)
    tunnel = None
    if args.setup_tunnel:
        tunnel = SSHTunnelProxy(
            remote_host=args.windows_host,
            remote_user=args.windows_user,
            local_port=args.tunnel_port,
            remote_port=args.tunnel_port
        )
        
        if not tunnel.start_tunnel():
            logger.error("Failed to start tunnel")
            httpd.shutdown()
            sys.exit(1)
    
    try:
        # Keep the script running
        logger.info(f"Proxy server running on port {args.proxy_port}. Press Ctrl+C to stop.")
        while True:
            time.sleep(60)  # Just keep alive
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        logger.info("Stopping proxy server...")
        httpd.shutdown()
        if tunnel:
            tunnel.stop_tunnel()


if __name__ == "__main__":
    main()
