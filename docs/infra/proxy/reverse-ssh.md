# Reverse SSH Tunnel Proxy Setup

This document describes how to set up the reverse SSH tunnel between Mac and Windows machines for proxying web traffic through mitmproxy.

## Overview

Our proxy infrastructure uses an SSH reverse tunnel to forward traffic from a Mac machine (running tests) to a Windows machine (running mitmproxy). This allows us to:

1. Capture and analyze all HTTP/HTTPS traffic to the Hot application
2. Modify requests/responses for testing edge cases
3. Selectively route only Hot domains through the proxy
4. Bypass proxy for non-Hot domains to avoid CAPTCHA and certificate issues

## Setup Instructions

### On Windows Machine

1. Start mitmproxy in regular proxy mode:

```powershell
.\mitmproxy.exe --mode regular --listen-host 0.0.0.0 --listen-port 8080 --ssl-insecure
```

2. In a second terminal, establish the SSH reverse tunnel to the Mac machine:

```powershell
ssh -v -R 8081:localhost:8080 asafgolan@<Mac-IP> -N
```

This forwards Windows port 8080 (mitmproxy) to Mac port 8081.

### On Mac Machine

Run the custom proxy server that selectively routes traffic:

```bash
python mac_proxy_server.py --listen-port 8000 --tunnel-port 8081
```

## Browser/Test Configuration

Configure your browser or Playwright tests to use `localhost:8000` as the proxy server. The Mac proxy will:

- Forward all Hot domain traffic through the tunnel to mitmproxy
- Connect directly to non-Hot domains to avoid CAPTCHA and certificate issues

## Troubleshooting

- If you see "Connection refused" errors, ensure the SSH tunnel is established properly
- For certificate errors with Hot domains, install the mitmproxy CA certificate in your system trust store
- For more details, see the [Mac Proxy Server documentation](mac-proxy-server.md)
