#!/usr/bin/env python3
"""
SSH Tunnel-based Proxy for Hot E2E Testing
Replaces the file-based proxy approach with direct SSH tunneling.
"""

import argparse
import subprocess
import socket
import sys
import time
import logging
from urllib.parse import urlparse
import os
import signal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('ssh_tunnel_proxy')

class SSHTunnelProxy:
    """Manages SSH tunnels for proxying requests between Windows and Mac"""
    
    def __init__(self, remote_host, remote_user, local_port=8080, remote_port=8080):
        self.remote_host = remote_host
        self.remote_user = remote_user
        self.local_port = local_port
        self.remote_port = remote_port
        self.tunnel_process = None
        self.is_windows = sys.platform.startswith('win')
    
    def start_tunnel(self):
        """Start an SSH tunnel based on the current platform"""
        if self.is_windows:
            return self._start_reverse_tunnel()
        else:
            return self._start_forward_tunnel()
    
    def _start_reverse_tunnel(self):
        """Start a reverse tunnel from Windows to Mac"""
        logger.info(f"Starting reverse SSH tunnel from Windows to {self.remote_host}")
        
        # Windows to Mac: Local service will be accessible on Mac at remote_port
        cmd = [
            "ssh", "-R", f"{self.remote_port}:localhost:{self.local_port}", 
            f"{self.remote_user}@{self.remote_host}", 
            "-N"  # Don't execute a remote command
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        try:
            self.tunnel_process = subprocess.Popen(cmd)
            logger.info(f"Tunnel started with PID: {self.tunnel_process.pid}")
            time.sleep(2)  # Give time for the tunnel to establish
            
            if self.tunnel_process.poll() is not None:
                logger.error(f"Tunnel failed to start, exit code: {self.tunnel_process.returncode}")
                return False
            
            logger.info(f"Tunnel active. Local port {self.local_port} is now accessible at {self.remote_host}:{self.remote_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start tunnel: {e}")
            return False
    
    def _start_forward_tunnel(self):
        """Start a forward tunnel from Mac to Windows"""
        logger.info(f"Starting forward SSH tunnel from Mac to {self.remote_host}")
        
        # Mac to Windows: Remote service will be accessible locally at local_port
        cmd = [
            "ssh", "-L", f"{self.local_port}:localhost:{self.remote_port}", 
            f"{self.remote_user}@{self.remote_host}", 
            "-N"  # Don't execute a remote command
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        try:
            self.tunnel_process = subprocess.Popen(cmd)
            logger.info(f"Tunnel started with PID: {self.tunnel_process.pid}")
            time.sleep(2)  # Give time for the tunnel to establish
            
            if self.tunnel_process.poll() is not None:
                logger.error(f"Tunnel failed to start, exit code: {self.tunnel_process.returncode}")
                return False
            
            logger.info(f"Tunnel active. Remote port {self.remote_port} is now accessible at localhost:{self.local_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start tunnel: {e}")
            return False
    
    def check_tunnel(self):
        """Check if the SSH tunnel is active"""
        if self.tunnel_process is None:
            logger.warning("No tunnel process found")
            return False
        
        # Check if process is still running
        if self.tunnel_process.poll() is not None:
            logger.warning(f"Tunnel process exited with code: {self.tunnel_process.returncode}")
            return False
        
        # Try connecting to the tunneled port
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(2)
            host = "localhost"
            port = self.local_port if not self.is_windows else self.remote_port
            
            logger.info(f"Testing connection to {host}:{port}")
            test_socket.connect((host, port))
            test_socket.close()
            logger.info("Tunnel is active and accepting connections")
            return True
        except Exception as e:
            logger.error(f"Tunnel is not accepting connections: {e}")
            return False
    
    def stop_tunnel(self):
        """Stop the SSH tunnel"""
        if self.tunnel_process:
            logger.info(f"Stopping tunnel process (PID: {self.tunnel_process.pid})")
            
            try:
                if self.is_windows:
                    # On Windows, terminate() should work
                    self.tunnel_process.terminate()
                else:
                    # On Unix, send SIGTERM
                    os.kill(self.tunnel_process.pid, signal.SIGTERM)
                
                # Wait for process to terminate
                self.tunnel_process.wait(timeout=5)
                logger.info("Tunnel stopped successfully")
                return True
            except subprocess.TimeoutExpired:
                logger.warning("Tunnel process did not terminate gracefully, forcing kill")
                try:
                    if self.is_windows:
                        self.tunnel_process.kill()
                    else:
                        os.kill(self.tunnel_process.pid, signal.SIGKILL)
                    logger.info("Tunnel process killed")
                    return True
                except Exception as e:
                    logger.error(f"Failed to kill tunnel process: {e}")
                    return False
            except Exception as e:
                logger.error(f"Error stopping tunnel: {e}")
                return False
        else:
            logger.warning("No tunnel process to stop")
            return False

class HotDomainHandler:
    """Handles traffic for hot.net domains using the SSH tunnel"""
    
    def __init__(self, tunnel_port=8080):
        self.tunnel_port = tunnel_port
        self.is_windows = sys.platform.startswith('win')
    
    def start_local_proxy(self, proxy_port=8000):
        """Start a simple HTTP proxy server to handle redirection"""
        # Implementation will depend on your specific needs
        # This is a placeholder for a more complete implementation
        pass


def main():
    parser = argparse.ArgumentParser(description='SSH Tunnel Proxy for Hot E2E Testing')
    parser.add_argument('--mode', choices=['windows', 'mac'], required=True, 
                      help='Mode to run the script in (windows or mac)')
    parser.add_argument('--remote-host', required=True, 
                      help='Remote host for SSH connection')
    parser.add_argument('--remote-user', required=True, 
                      help='Username for SSH connection')
    parser.add_argument('--local-port', type=int, default=8080, 
                      help='Local port for the tunnel')
    parser.add_argument('--remote-port', type=int, default=8080, 
                      help='Remote port for the tunnel')
    
    args = parser.parse_args()
    
    # Create and start SSH tunnel
    tunnel = SSHTunnelProxy(
        remote_host=args.remote_host,
        remote_user=args.remote_user,
        local_port=args.local_port,
        remote_port=args.remote_port
    )
    
    if tunnel.start_tunnel():
        logger.info("Tunnel started successfully")
        
        try:
            # Keep the script running while the tunnel is active
            while tunnel.check_tunnel():
                time.sleep(30)  # Check every 30 seconds
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        finally:
            tunnel.stop_tunnel()
    else:
        logger.error("Failed to start tunnel")
        sys.exit(1)


if __name__ == "__main__":
    main()
