# mac_proxy_server.py
import http.server
import socketserver
import urllib.request
import urllib.parse
import threading
import argparse
import socket
import ssl
import select
import http.client

# List of domains that should be proxied through the tunnel
# All other domains will be connected to directly
PROXY_DOMAINS = [
    'hot.net',
    'hot.net.il',
    'selfservicetest.hot.net.il',
    'hot-qc11-01:8080'
    # Add any other domains you want to proxy here
]

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests by forwarding them through the tunnel"""
        print(f"GET request to {self.path}")
        self._process_request()
        
    def do_POST(self):
        """Handle POST requests by forwarding them through the tunnel"""
        print(f"POST request to {self.path}")
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None
        self._process_request(post_data)
        
    def do_PUT(self):
        """Handle PUT requests by forwarding them through the tunnel"""
        print(f"PUT request to {self.path}")
        content_length = int(self.headers.get('Content-Length', 0))
        put_data = self.rfile.read(content_length) if content_length > 0 else None
        self._process_request(put_data)
        
    def do_DELETE(self):
        """Handle DELETE requests by forwarding them through the tunnel"""
        print(f"DELETE request to {self.path}")
        self._process_request()
        
    def do_HEAD(self):
        """Handle HEAD requests by forwarding them through the tunnel"""
        print(f"HEAD request to {self.path}")
        self._process_request()
        
    def do_OPTIONS(self):
        """Handle OPTIONS requests by forwarding them through the tunnel"""
        print(f"OPTIONS request to {self.path}")
        self._process_request()
        
    def do_CONNECT(self):
        """Handle HTTPS CONNECT requests"""
        host_port = self.path.split(':')
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 443
        
        print(f"CONNECT request to {host}:{port}")
        
        # Check if this domain should be proxied through the tunnel
        should_proxy = False
        for domain in PROXY_DOMAINS:
            if domain in host or host in domain:
                should_proxy = True
                break
        
        if should_proxy:
            print(f"Proxying domain through tunnel: {host}")
            # Continue with proxy connection below
        else:
            print(f"Direct connection for domain: {host}")
            self._direct_connect(host, port)
            return
        
        try:
            # Try to forward through tunnel first
            tunnel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tunnel_socket.settimeout(5)  # 5 second timeout
            
            try:
                print(f"Attempting to connect to tunnel at localhost:{self.server.tunnel_port}")
                tunnel_socket.connect(('localhost', self.server.tunnel_port))
                print(f"Successfully connected to tunnel for {host}:{port}")
                
                # Tell the client we're ready to tunnel
                self.send_response(200, 'Connection Established')
                self.send_header('Connection', 'close')
                self.end_headers()
                
                # Create a thread to forward data between client and tunnel
                self._tunnel_data(self.connection, tunnel_socket)
                
            except socket.timeout:
                print(f"Timeout connecting to tunnel at localhost:{self.server.tunnel_port}")
                self.send_error(504, f"Tunnel connection timeout")
                return
            except ConnectionRefusedError:
                print(f"Connection refused to tunnel at localhost:{self.server.tunnel_port}")
                print(f"Is the SSH tunnel established from Windows to Mac?")
                self.send_error(502, f"Cannot connect to tunnel - connection refused")
                return
                
        except Exception as e:
            print(f"CONNECT error: {e}")
            self.send_error(500, f"CONNECT error: {str(e)}")
    
    def _direct_connect(self, host, port):
        """Create a direct connection to the target host for reCAPTCHA domains"""
        try:
            # Create a socket to the actual target server
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(10)  # 10 second timeout
            
            print(f"Opening direct connection to {host}:{port}")
            target_socket.connect((host, port))
            print(f"Successfully connected directly to {host}:{port}")
            
            # Tell the client we're ready to tunnel
            self.send_response(200, 'Connection Established')
            self.send_header('Connection', 'close')
            self.end_headers()
            
            # Create a thread to forward data between client and target
            self._tunnel_data(self.connection, target_socket)
            
        except socket.timeout:
            print(f"Timeout connecting directly to {host}:{port}")
            self.send_error(504, f"Direct connection timeout")
        except ConnectionRefusedError:
            print(f"Connection refused when connecting directly to {host}:{port}")
            self.send_error(502, f"Cannot connect directly - connection refused")
        except Exception as e:
            print(f"Direct connection error: {e}")
            self.send_error(500, f"Direct connection error: {str(e)}")
    
    def _tunnel_data(self, client_conn, tunnel_conn):
        """Forward data between client and tunnel connections"""
        sockets = [client_conn, tunnel_conn]
        print("Starting data tunneling between client and proxy")
        
        client_bytes = 0
        tunnel_bytes = 0
        
        try:
            while True:
                # Use select to monitor both connections for data
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                
                # If we have any exceptional conditions, break the loop
                if exceptional:
                    print(f"Exceptional condition on sockets: {exceptional}")
                    break
                
                if not readable:
                    print("Timeout waiting for data - no activity for 60 seconds")
                    break
                
                for sock in readable:
                    # Get data from the source socket
                    try:
                        data = sock.recv(4096)
                        
                        if not data:
                            # If no data received, the connection is closed
                            if sock is client_conn:
                                print("Client closed connection")
                            else:
                                print("Tunnel closed connection")
                            return
                        
                        # Figure out the destination socket (the other one)
                        if sock is client_conn:
                            print(f"Client → Tunnel: {len(data)} bytes")
                            client_bytes += len(data)
                            tunnel_conn.sendall(data)
                        else:
                            print(f"Tunnel → Client: {len(data)} bytes")
                            tunnel_bytes += len(data)
                            client_conn.sendall(data)
                            
                    except socket.error as e:
                        print(f"Socket error during tunneling: {e}")
                        return
                    except Exception as e:
                        print(f"Error during tunneling: {e}")
                        return
        finally:
            print(f"Tunnel closed. Total bytes: Client→Tunnel: {client_bytes}, Tunnel→Client: {tunnel_bytes}")
        
        # Close both sockets
        try:
            client_conn.close()
            tunnel_conn.close()
        except:
            pass
    
    def _process_request(self, post_data=None):
        """Process HTTP requests by forwarding them through the tunnel"""
        # Parse the request URL
        url = self.path
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.netloc
        
        # Check if this domain should be proxied through the tunnel
        should_proxy = False
        if host:
            for domain in PROXY_DOMAINS:
                if domain in host or host in domain:
                    should_proxy = True
                    break
        
        # Direct connection for non-proxied domains
        if host and not should_proxy:
            self._direct_http_request(post_data)
            return
            
        try:
            print(f"Forwarding {self.command} request to {url} via tunnel on port {self.server.tunnel_port}")
            
            # Connect to the tunnel
            conn = http.client.HTTPConnection('localhost', self.server.tunnel_port, timeout=30)
            
            # Forward the request with the same headers and body
            headers = {}
            for k, v in self.headers.items():
                if k.lower() not in ('connection', 'keep-alive', 'proxy-connection', 'proxy-authenticate'):
                    headers[k] = v
            
            try:
                conn.request(
                    method=self.command,
                    url=url,
                    body=post_data,
                    headers=headers
                )
                
                # Get the response from the tunnel
                response = conn.getresponse()
                print(f"Received response: {response.status} {response.reason} for {url}")
                
                # Read the response body
                response_body = response.read()
                
                # Forward the response back to the client
                self.send_response(response.status, response.reason)
                
                # Forward the response headers
                for header, value in response.getheaders():
                    if header.lower() not in ('connection', 'transfer-encoding'):
                        self.send_header(header, value)
                
                # Set content length for proper response handling
                self.send_header('Content-Length', str(len(response_body)))
                self.end_headers()
                
                # Forward the response body
                if response_body:
                    self.wfile.write(response_body)
                
            except http.client.HTTPException as he:
                print(f"HTTP error forwarding request: {he}")
                self.send_error(502, f"HTTP error: {str(he)}")
            finally:
                conn.close()
            
        except socket.error as se:
            print(f"Socket error processing request: {se}")
            self.send_error(504, f"Gateway Timeout: {str(se)}")
        except Exception as e:
            print(f"Error processing request: {e}")
            self.send_error(500, f"Error: {str(e)}")
            self.end_headers()
            self.wfile.write(str(e).encode())
    
    def _direct_http_request(self, post_data=None):
        """Handle HTTP requests directly without tunneling for non-Hot domains"""
        parsed_url = urllib.parse.urlparse(self.path)
        protocol = parsed_url.scheme
        host = parsed_url.netloc
        path = parsed_url.path
        if parsed_url.query:
            path += '?' + parsed_url.query
            
        print(f"Direct HTTP connection for: {host} ({self.command})")
        
        try:
            # Create the appropriate connection based on the protocol
            if protocol == 'https':
                conn = http.client.HTTPSConnection(host, timeout=30)
            else:
                conn = http.client.HTTPConnection(host, timeout=30)
                
            # Prepare headers - remove hop-by-hop headers
            headers = {}
            for k, v in self.headers.items():
                if k.lower() not in ('connection', 'keep-alive', 'proxy-connection', 'proxy-authenticate'):
                    headers[k] = v
            
            # Send the request
            conn.request(
                method=self.command,
                url=path,
                body=post_data,
                headers=headers
            )
            
            # Get the response
            response = conn.getresponse()
            print(f"Received direct response: {response.status} {response.reason} for {self.path}")
            
            # Read response body
            response_body = response.read()
            
            # Forward response to client
            self.send_response(response.status, response.reason)
            
            # Forward headers
            for header, value in response.getheaders():
                if header.lower() not in ('connection', 'transfer-encoding'):
                    self.send_header(header, value)
            
            self.send_header('Content-Length', str(len(response_body)))
            self.end_headers()
            
            # Send response body
            if response_body:
                self.wfile.write(response_body)
                
        except http.client.HTTPException as he:
            print(f"HTTP error in direct connection: {he}")
            self.send_error(502, f"HTTP error: {str(he)}")
        except socket.error as se:
            print(f"Socket error in direct connection: {se}")
            self.send_error(504, f"Gateway Timeout: {str(se)}")
        except Exception as e:
            print(f"Error in direct connection: {e}")
            self.send_error(500, f"Error: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

def check_tunnel(tunnel_port):
    """Check if tunnel is accessible"""
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(2)
        test_socket.connect(('localhost', tunnel_port))
        test_socket.close()
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    except Exception as e:
        print(f"Error checking tunnel: {e}")
        return False

def run_server(listen_port, tunnel_port):
    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        pass
    
    server = ThreadedHTTPServer(("0.0.0.0", listen_port), ProxyHandler)
    server.tunnel_port = tunnel_port
    
    # Check if tunnel is accessible
    tunnel_available = check_tunnel(tunnel_port)
    if not tunnel_available:
        print(f"WARNING: Cannot connect to tunnel at localhost:{tunnel_port}")
        print(f"Is the SSH tunnel established from Windows to Mac?")
        print(f"On Windows, run: ssh -R {tunnel_port}:localhost:{tunnel_port} your-username@your-mac-ip -N")
        print(f"Starting anyway, but expect connection errors unless tunnel is established...")
    else:
        print(f"Tunnel connection verified at localhost:{tunnel_port}")
    
    print(f"Starting proxy server on port {listen_port}, forwarding to tunnel on port {tunnel_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down proxy server")
        server.shutdown()

def main():
    parser = argparse.ArgumentParser(description="Mac proxy server for mitmproxy tunnel")
    parser.add_argument("--listen-port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--tunnel-port", type=int, default=8080, help="Port for the SSH tunnel")
    
    args = parser.parse_args()
    
    run_server(args.listen_port, args.tunnel_port)

if __name__ == "__main__":
    main()