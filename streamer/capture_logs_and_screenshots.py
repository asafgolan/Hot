#!/usr/bin/env python3
"""
Capture both screenshots and logs simultaneously to ensure perfect correlation
between UI changes and log events for the Hot Streamer app.
"""

import subprocess
import time
import os
import argparse
import signal
import threading
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

class LogAndScreenshotCapture:
    """Capture both logs and screenshots simultaneously"""
    
    def __init__(self, device_id=None, output_dir="capture_session", 
                 screenshot_interval=0.2, max_duration=60):
        self.device_id = device_id
        self.output_dir = output_dir
        self.screenshot_interval = screenshot_interval
        self.max_duration = max_duration  # Maximum duration in seconds
        self.running = False
        self.start_time = None
        self.screenshot_count = 0
        self.log_file = None
        self.log_process = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.pending_tasks = []
        
        # Create output directory and subdirectories
        self.screenshot_dir = os.path.join(output_dir, "screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        
    def _execute_adb_command(self, command):
        """Execute ADB command with device ID"""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(command)
        
        try:
            return subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e}")
            return None
    
    def _capture_screenshot(self, timestamp):
        """Capture a screenshot at the specified timestamp"""
        try:
            # Format timestamp for filename with hot_ prefix to indicate these are HOT app related
            filename = "hot_" + timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".png"
            remote_path = f"/sdcard/{filename}"
            local_path = os.path.join(self.screenshot_dir, filename)
            
            # Take screenshot on device
            self._execute_adb_command(["shell", f"screencap -p {remote_path}"])
            
            # Pull to local machine
            self._execute_adb_command(["pull", remote_path, local_path])
            
            # Remove from device
            self._execute_adb_command(["shell", f"rm {remote_path}"])
            
            print(f"Screenshot: {filename}")
            return local_path
        except Exception as e:
            print(f"Screenshot error: {e}")
            return None
    
    def _start_log_capture(self):
        """Start capturing logs to a file"""
        log_path = os.path.join(self.output_dir, "session_logs.txt")
        self.log_file = open(log_path, "w")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_file.write(f"# Hot Streamer logs (HOT app filtered) - Started at {timestamp}\n")
        self.log_file.write(f"# Device: {self.device_id}\n\n")
        self.log_file.flush()
        
        # Start logcat process
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        
        # Capture logs with a two-stage approach: first capture everything, then highlight HOT app events
        cmd.extend(["logcat", "-v", "threadtime"])
        
        # Create a special marker for HOT-related logs to make them easy to identify
        # but also include all other logs except media scanner noise
        cmd = ["bash", "-c", " ".join(cmd) + " | awk '{" +
               "  if ($0 ~ /il\.net\.hot|hot|ActivityTask|input|key|touch|WebView|TvMain/i) " +
               "    print \"[HOT_EVENT] \" $0; " +
               "  else if ($0 !~ /MEDIA_SCANNER_SCAN_FILE/) " +
               "    print $0" +
               "}'"]
        print(f"Using command: {' '.join(cmd)}")
        
        print(f"Starting log capture to {log_path}")
        self.log_process = subprocess.Popen(
            cmd,
            shell=True,  # Using shell=True since we're using bash -c
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line-buffered output
        )
    
    def _stop_log_capture(self):
        """Stop the log capture process"""
        if self.log_process and self.log_process.poll() is None:
            self.log_process.terminate()
            try:
                self.log_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log_process.kill()
        
        if self.log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.log_file.write(f"\n# Logging stopped at {timestamp}\n")
            self.log_file.close()
            self.log_file = None
    
    def capture_session(self):
        """Begin a capture session with both logs and screenshots"""
        print(f"Starting capture session on device {self.device_id}")
        print(f"Output directory: {os.path.abspath(self.output_dir)}")
        print(f"Screenshot interval: {self.screenshot_interval} seconds")
        print(f"Maximum duration: {self.max_duration} seconds")
        
        # Start log capture
        self._start_log_capture()
        
        # Record start time
        self.start_time = datetime.now()
        timestamp_str = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # Create a session info file
        with open(os.path.join(self.output_dir, "session_info.txt"), "w") as f:
            f.write(f"Session started: {self.start_time}\n")
            f.write(f"Device: {self.device_id}\n")
            f.write(f"Screenshot interval: {self.screenshot_interval} seconds\n")
        
        self.running = True
        try:
            while self.running:
                # Get current timestamp
                now = datetime.now()
                elapsed = (now - self.start_time).total_seconds()
                
                # Check if we've exceeded the maximum duration
                if self.max_duration and elapsed >= self.max_duration:
                    print(f"Maximum duration ({self.max_duration}s) reached")
                    break
                
                # Submit screenshot task
                future = self.executor.submit(self._capture_screenshot, now)
                self.pending_tasks.append(future)
                self.screenshot_count += 1
                
                # Sleep for the screenshot interval
                time.sleep(self.screenshot_interval)
                
                # Clean up completed tasks
                self.pending_tasks = [f for f in self.pending_tasks if not f.done()]
                
        except KeyboardInterrupt:
            print("\nStopping capture session")
        finally:
            # Stop log capture
            self._stop_log_capture()
            
            self.running = False
            print("Waiting for remaining tasks to complete...")
            self.executor.shutdown(wait=True)
            
            print(f"Capture session completed")
            print(f"Captured {self.screenshot_count} screenshots")
            print(f"Results saved to {os.path.abspath(self.output_dir)}")
            
            # Create an HTML index for easy viewing
            self._create_html_index()
    
    def _create_html_index(self):
        """Create an HTML index of screenshots with timestamps"""
        html_file = os.path.join(self.output_dir, "index.html")
        
        # Scan for all screenshots
        screenshots = []
        for filename in sorted(os.listdir(self.screenshot_dir)):
            if filename.endswith(".png"):
                # Extract timestamp from filename
                time_parts = filename.replace(".png", "").split("_")
                if len(time_parts) >= 3:
                    time_str = f"{time_parts[0]}-{time_parts[1]}-{time_parts[2]}"
                    screenshots.append((filename, time_str))
        
        with open(html_file, "w") as f:
            f.write("<!DOCTYPE html>\n")
            f.write("<html>\n<head>\n")
            f.write(f"<title>Hot Streamer UI Capture Session (HOT App)</title>\n")
            f.write("<style>\n")
            f.write("body { font-family: Arial, sans-serif; margin: 20px; }\n")
            f.write(".screenshot { margin-bottom: 30px; border: 1px solid #ddd; padding: 10px; }\n")
            f.write(".timestamp { font-weight: bold; margin-bottom: 10px; }\n")
            f.write("img { max-width: 800px; border: 1px solid #eee; }\n")
            f.write("</style>\n")
            f.write("</head>\n<body>\n")
            f.write(f"<h1>Hot Streamer UI Capture Session (HOT App)</h1>\n")
            f.write(f"<p>Session started: {self.start_time}</p>\n")
            f.write(f"<p>Total screenshots: {len(screenshots)}</p>\n")
            f.write("<hr>\n")
            
            for filename, time_str in screenshots:
                f.write("<div class='screenshot'>\n")
                f.write(f"<div class='timestamp'>{time_str}</div>\n")
                f.write(f"<img src='screenshots/{filename}' alt='{filename}'>\n")
                f.write("</div>\n")
            
            f.write("</body>\n</html>\n")
        
        print(f"Created HTML index: {html_file}")

def handle_exit(signum, frame):
    print("\nExiting...")
    exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture both logs and screenshots simultaneously")
    parser.add_argument("--device", "-d", help="ADB device ID (default: first connected device)")
    parser.add_argument("--output", "-o", default="capture_session", help="Output directory")
    parser.add_argument("--interval", "-i", type=float, default=0.2, 
                        help="Screenshot interval in seconds (default: 0.2)")
    parser.add_argument("--duration", "-t", type=int, default=60,
                        help="Maximum duration in seconds (default: 60)")
    
    args = parser.parse_args()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # Start capture session
    capture = LogAndScreenshotCapture(
        device_id=args.device,
        output_dir=args.output,
        screenshot_interval=args.interval,
        max_duration=args.duration
    )
    
    capture.capture_session()
