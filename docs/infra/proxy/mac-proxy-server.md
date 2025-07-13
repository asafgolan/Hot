# Mac Proxy Server

This document explains the Mac proxy server component of our E2E testing infrastructure.

## Overview

The Mac proxy server (`mac_proxy_server.py`) is a custom HTTP/HTTPS proxy that selectively routes traffic:
- Hot domain traffic is forwarded through an SSH tunnel to a Windows machine running mitmproxy
- All other domains bypass the proxy with direct connections

This approach resolves common issues with reCAPTCHA and certificate validation that often occur when proxying all traffic.

## Key Features

1. **Domain-Specific Routing**
   - Only forwards specified domains through the proxy tunnel (currently Hot domains)
   - Configurable list of domains to proxy at the top of the file:
     ```python
     PROXY_DOMAINS = [
         'hot.net',
         'hot.net.il',
         'selfservicetest.hot.net.il',
         # Add more domains as needed
     ]
     ```

2. **HTTPS CONNECT Support**
   - Handles HTTPS traffic through CONNECT method tunneling
   - Performs direct SSL/TLS connections for non-Hot domains
   - Prevents certificate errors for most websites

3. **HTTP Request Forwarding**
   - Forwards HTTP requests to either the tunnel or directly based on domain
   - Maintains headers and request bodies
   - Proper error handling and status code forwarding

## Usage

Run the proxy server with:

```bash
python mac_proxy_server.py --listen-port 8000 --tunnel-port 8081
```

Where:
- `--listen-port` is the port your browser or tests should connect to
- `--tunnel-port` is the port where the SSH tunnel forwards to Windows mitmproxy

## Integration with E2E Tests

In your Playwright test configuration, set the proxy to:

```python
context = browser.new_context(
    proxy={"server": "localhost:8000"}
)
```

## Troubleshooting

- **Connection Refused**: Make sure the SSH tunnel is active
- **Slow Performance**: Check that direct connections are working for non-Hot domains
- **HTTPS Errors**: For Hot domains, make sure the mitmproxy CA certificate is installed
- **Domain Not Proxied**: Check the `PROXY_DOMAINS` list and add missing domains
