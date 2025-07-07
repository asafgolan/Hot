#!/usr/bin/env python3
"""
Monitor Windows logs that are sent from the Windows SSH handler
This script will tail the Windows log files in real-time
"""

import os
import time
import subprocess
import threading
from datetime import datetime

# Log directory where Windows logs are received
LOGS_DIR = os.path.expanduser("~/Hot/infra/proxy/ssh_transfer/logs")

# Windows log files to monitor
LOG_FILES = {
    'main': os.path.join(LOGS_DIR, "windows_main.log"),
    'redirect': os.path.join(LOGS_DIR, "windows_redirect.log"),
    'session': os.path.join(LOGS_DIR, "windows_session.log")
}

def ensure_log_dir():
    """Ensure the logs directory exists"""
    os.makedirs(LOGS_DIR, exist_ok=True)

def tail_log_file(log_type, log_file):
    """Tail a specific log file and print with prefixes"""
    if not os.path.exists(log_file):
        print(f"[{log_type.upper()}] Log file not found: {log_file}")
        return
    
    print(f"[{log_type.upper()}] Monitoring: {log_file}")
    
    try:
        # Use tail -f to follow the file
        process = subprocess.Popen(
            ['tail', '-f', log_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        for line in iter(process.stdout.readline, ''):
            if line.strip():
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"[{timestamp}] [{log_type.upper()}] {line.strip()}")
                
    except Exception as e:
        print(f"[{log_type.upper()}] Error tailing log: {e}")

def monitor_all_logs():
    """Monitor all Windows log files in parallel"""
    ensure_log_dir()
    
    print("🔍 Starting Windows log monitor...")
    print(f"📁 Monitoring logs in: {LOGS_DIR}")
    print("=" * 60)
    
    # Start a thread for each log file
    threads = []
    for log_type, log_file in LOG_FILES.items():
        thread = threading.Thread(
            target=tail_log_file, 
            args=(log_type, log_file),
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping log monitor...")

def show_recent_logs(lines=50):
    """Show recent log entries from all files"""
    ensure_log_dir()
    
    print("📖 Recent Windows log entries:")
    print("=" * 60)
    
    for log_type, log_file in LOG_FILES.items():
        if os.path.exists(log_file):
            print(f"\n[{log_type.upper()}] Last {lines} lines from {log_file}:")
            print("-" * 40)
            try:
                result = subprocess.run(
                    ['tail', '-n', str(lines), log_file],
                    capture_output=True,
                    text=True
                )
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            print(f"  {line}")
                else:
                    print(f"  (No recent entries)")
            except Exception as e:
                print(f"  Error reading log: {e}")
        else:
            print(f"\n[{log_type.upper()}] Log file not found: {log_file}")

def grep_logs(pattern, case_sensitive=False):
    """Search for a pattern in all log files"""
    ensure_log_dir()
    
    print(f"🔎 Searching for pattern: '{pattern}'")
    print("=" * 60)
    
    for log_type, log_file in LOG_FILES.items():
        if os.path.exists(log_file):
            print(f"\n[{log_type.upper()}] Searching in {log_file}:")
            print("-" * 40)
            try:
                cmd = ['grep']
                if not case_sensitive:
                    cmd.append('-i')
                cmd.extend([pattern, log_file])
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            print(f"  {line}")
                else:
                    print(f"  (No matches found)")
            except Exception as e:
                print(f"  Error searching log: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor Windows logs sent via SSH')
    parser.add_argument('--recent', type=int, metavar='N', help='Show recent N lines from all logs')
    parser.add_argument('--grep', type=str, metavar='PATTERN', help='Search for pattern in all logs')
    parser.add_argument('--case-sensitive', action='store_true', help='Case-sensitive search')
    parser.add_argument('--monitor', action='store_true', help='Monitor logs in real-time (default)')
    
    args = parser.parse_args()
    
    if args.recent:
        show_recent_logs(args.recent)
    elif args.grep:
        grep_logs(args.grep, args.case_sensitive)
    else:
        monitor_all_logs()