#!/usr/bin/env python3
"""
Test script to verify Windows logging system works
"""

import sys
import os

# Add the current directory to Python path to import the Windows module
sys.path.append('/Users/asafgolan/Hot/infra/proxy')

# Import the Windows logging functions
try:
    from ssh_raw_transfer_windows import log_to_mac, upload_logs_to_mac
    print("✅ Successfully imported Windows logging functions")
    
    # Test logging
    log_to_mac('main', 'INFO', 'TEST: Windows logging system test')
    log_to_mac('redirect', 'WARNING', 'TEST: Redirect logging test')
    log_to_mac('session', 'INFO', 'TEST: Session logging test')
    
    print("✅ Test logs queued")
    
    # Test upload (this will fail without SSH but shows if function works)
    try:
        upload_logs_to_mac()
        print("✅ Upload function executed")
    except Exception as e:
        print(f"⚠️ Upload failed (expected): {e}")
    
except ImportError as e:
    print(f"❌ Failed to import Windows functions: {e}")
except Exception as e:
    print(f"❌ Error testing logging: {e}")