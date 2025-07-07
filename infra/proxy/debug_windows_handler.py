#!/usr/bin/env python3
"""
Debug script to test Windows handler connectivity
"""

import urllib.request
import ssl
import sys

def test_basic_connectivity():
    """Test basic HTTPS connectivity from Windows"""
    
    print("🔍 Testing Windows Handler Connectivity")
    print("=" * 50)
    
    # Test URLs
    test_urls = [
        "https://test.hot.net.il/",
        "https://www.google.com/",
        "http://test.hot.net.il/"  # Try HTTP too
    ]
    
    for url in test_urls:
        print(f"\n📡 Testing: {url}")
        try:
            # Create SSL context (like Windows handler does)
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Create request with basic headers
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Make request
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                status = response.status
                headers = dict(response.getheaders())
                content_length = len(response.read())
                
                print(f"✅ SUCCESS: {status}")
                print(f"   Content-Length: {content_length}")
                
                # Check for redirects
                if status in [301, 302, 303, 307, 308]:
                    location = headers.get('Location', 'None')
                    print(f"🔄 REDIRECT: {status} -> {location}")
                
        except Exception as e:
            print(f"❌ FAILED: {e}")
            print(f"   Error type: {type(e).__name__}")

if __name__ == "__main__":
    test_basic_connectivity()