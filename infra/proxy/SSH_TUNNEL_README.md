# SSH Tunnel Proxy for Hot E2E Testing

This system replaces the file-based proxy approach with direct SSH tunneling for better performance and simpler implementation.

## Overview

The SSH tunnel proxy consists of three main components:

1. **SSH Tunnel Base Class** (`ssh_tunnel_proxy.py`)
   - Handles SSH tunnel creation and management
   - Works on both Windows and Mac

2. **Windows Client** (`windows_tunnel_client.py`) 
   - Runs on your Windows machine
   - Sets up a local HTTP server to handle requests
   - Creates a reverse SSH tunnel to your Mac
   - Makes Windows-side services accessible from Mac

3. **Mac Server** (`mac_tunnel_server.py`)
   - Runs on your Mac
   - Acts as a proxy to intercept hot.net domain requests
   - Forwards hot.net requests through the SSH tunnel to Windows
   - Handles other domains directly

## Advantages Over File-Based Approach

1. **Direct Connection**: No need to serialize/deserialize requests between platforms
2. **Real-Time Communication**: No delay waiting for file operations
3. **Simpler Implementation**: Eliminates complex file transfer logic
4. **Better Performance**: Avoids file I/O overhead and JSON parsing issues
5. **HTTPS Support**: Works with both HTTP and HTTPS traffic
6. **More Reliable**: Fewer points of failure

## Setup Instructions

### Windows Side

1. Ensure Python is installed (no additional packages required as we use only native Python libraries)

2. Run the Windows client:
   ```
   python windows_tunnel_client.py --mac-host <mac-ip-address> --mac-user <mac-username> --local-port 8080 --remote-port 8080
   ```

### Mac Side

1. Ensure Python is installed (no additional packages required as we use only native Python libraries)

2. Run the Mac server:
   ```
   python mac_tunnel_server.py --windows-host <windows-ip-address> --windows-user <windows-username> --proxy-port 8000 --tunnel-port 8080
   ```

3. Configure your browser or tests to use `localhost:8000` as the proxy

## How It Works

1. Your E2E tests connect to the Mac proxy server (port 8000)
2. The Mac proxy determines if the request is for a hot.net domain
3. If it's a hot.net domain, the request is forwarded through the SSH tunnel to Windows (port 8080)
4. The Windows server processes the request and sends the response back through the tunnel
5. The Mac proxy forwards the response to your E2E tests

## Troubleshooting

- **Check SSH Connection**: Make sure you can SSH between the machines normally
- **Verify Ports**: Ensure the specified ports are open and not blocked by firewalls
- **Check Logs**: Both scripts provide detailed logging for troubleshooting
- **Test Tunnel**: Use `curl localhost:<port>` to test if the tunnel is working

## Advanced Configuration

You can modify the HTTP handlers in both `windows_tunnel_client.py` and `mac_tunnel_server.py` to implement your specific domain handling logic from your previous file-based proxy system.
