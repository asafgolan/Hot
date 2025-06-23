#!/usr/bin/env python3
import os
import re
import time
import pytest
import subprocess
from datetime import datetime
import threading
import queue

class TestHotAppLaunch:
    """Test class for launching HOT app and capturing events"""
    
    def setup_method(self):
        """Setup before each test method"""
        self.log_queue = queue.Queue()
        self.screenshot_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.event_detected = {
            'app_launch': False,
            'window_transition': False,
            'webview_start': False,
            'back_callback': False,
            'transition_ready': False,
            'initial_transition_start': False,
            'initial_transition_finish': False,
            'home_transition_start': False,
            'home_transition_finish': False
        }
        
        # For extracted values
        self.extracted_values = {
            'proxy_string': None,
            'shell_process_id': None,
            'shell_thread_id': None,
            'transition_id': None,
            'transition_finish_time_ms': None
        }
        
        # Create results directory
        self.results_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'test_results',
            f'run_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        os.makedirs(self.results_dir, exist_ok=True)
        print(f"Results will be saved to: {self.results_dir}")

    def teardown_method(self):
        """Cleanup after each test method"""
        self.stop_event.set()
        if hasattr(self, 'log_thread') and self.log_thread.is_alive():
            self.log_thread.join(timeout=2)
        if hasattr(self, 'screenshot_thread') and self.screenshot_thread.is_alive():
            self.screenshot_thread.join(timeout=2)

    def _monitor_logs(self):
        """Thread function to monitor logs for specific events"""
        try:
            # Start adb logcat process - no need to clear logs here as it's done in the main test method
            cmd = ["adb", "logcat", "-v", "threadtime"]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            

            # Process logs without writing to file, filtering out noisy entries
            while not self.stop_event.is_set():
                try:
                    line = process.stdout.readline()
                    if not line:
                        break
                    
                    # Display logs with V level for WindowManagerShell and I level for ActivityManager and ActivityTaskManager
                    if re.search(r'\s+V\s+WindowManagerShell', line):
                        print(f"DEBUG LOG V: {line.strip()}")
                    elif re.search(r'\s+I\s+ActivityManager', line):
                        print(f"DEBUG LOG I: {line.strip()}")
                    elif re.search(r'\s+I\s+ActivityTaskManager', line):
                        print(f"DEBUG LOG I: {line.strip()}")
                except UnicodeDecodeError as e:
                    try:
                        # Try to read the raw bytes and decode with replacement characters
                        raw_line = process.stdout.buffer.raw.readline()
                        decoded_line = raw_line.decode('utf-8', errors='replace')
                        print(f"Recovered log line (with replacements): {decoded_line.strip()}")
                        
                        # Check if it matches our filter and print it
                        if 'WindowManagerShell' in decoded_line and ' V ' in decoded_line:
                            print(f"DEBUG LOG V (recovered): {decoded_line.strip()}")
                        elif 'ActivityManager' in decoded_line and ' I ' in decoded_line:
                            print(f"DEBUG LOG I (recovered): {decoded_line.strip()}")
                        elif 'ActivityTaskManager' in decoded_line and ' I ' in decoded_line:
                            print(f"DEBUG LOG I (recovered): {decoded_line.strip()}")
                    except Exception as inner_e:
                        print(f"Warning: Could not recover log line: {str(e)} -> {str(inner_e)}")
                    continue
                    
            process.terminate()
        except Exception as e:
            print(f"Error in log monitoring: {str(e)}")

    def _take_screenshot(self, event_type):
        """Take a screenshot"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        screenshot_base_name = f"hot_event_{event_type}_{timestamp}"
        device_screenshot_path = f"/sdcard/{screenshot_base_name}.png"
        host_screenshot_path = os.path.join(self.results_dir, f"{screenshot_base_name}.png")

        # Take screenshot on device
        try:
            # Add extracted values to the screenshot filename if available
            if event_type in ['transition_ready', 'animation_start'] and self.extracted_values['proxy_string']:
                proxy_id = self.extracted_values['proxy_string'].split('@')[1] if '@' in self.extracted_values['proxy_string'] else 'unknown'
                device_screenshot_path = f"/sdcard/{screenshot_base_name}_proxy{proxy_id}.png"
                host_screenshot_path = os.path.join(self.results_dir, f"{screenshot_base_name}_proxy{proxy_id}.png")
                
            subprocess.run(["adb", "shell", "screencap", "-p", device_screenshot_path], 
                           check=True, capture_output=True)
            subprocess.run(["adb", "pull", device_screenshot_path, host_screenshot_path],
                           check=True, capture_output=True)
            print(f"Captured screenshot for {event_type} event: {host_screenshot_path}")
            return host_screenshot_path
        except subprocess.CalledProcessError as e:
            print(f"Failed to capture screenshot: {str(e)}")
            return None

    def test_hot_app_launch(self):
        """Test launching HOT app and capturing screenshots on key events"""
        # Clear logs before beginning the test
        print("Clearing Android logs before starting test...")
        try:
            subprocess.run(["adb", "logcat", "-c"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to clear logs: {e}")
        
        # Start log monitoring and screenshot threads
        print("Starting log monitoring...")
        log_thread = threading.Thread(target=self._monitor_logs)
        #screenshot_thread = threading.Thread(target=self._capture_screenshot_on_event)
        
        log_thread.daemon = True
        #screenshot_thread.daemon = True
        
        log_thread.start()
        #screenshot_thread.start()
        
        # Short pause to make sure monitoring is active before launching app
        time.sleep(2)
        
        try:
            # Launch the HOT app using adb
            print("Launching HOT app...")
            result = subprocess.run(
                ["adb", "shell", "am", "start", "-n", "il.net.hot.hot/.TvMainActivity"],
                check=True,
                capture_output=True,
                text=True
            )
            launch_output = result.stdout
            print(f"Launch command output: {launch_output}")
            
            #wait 10 seconds and run next line
            time.sleep(20)

            # Force-stop the app first to ensure a clean launch
            print("Force-stopping HOT app to ensure clean launch...")
            subprocess.run(
                ["adb", "shell", "am", "force-stop", "il.net.hot.hot"],
                check=True
            )
            
            # Short delay to ensure app is fully stopped
            time.sleep(1)
            
        except subprocess.CalledProcessError as e:
            pytest.fail(f"Error launching app: {str(e)}")
        finally:
            # Stop threads
            self.stop_event.set()
            
if __name__ == "__main__":
    # Allow running directly (not just with pytest)
    test = TestHotAppLaunch()
    test.setup_method()
    try:
        test.test_hot_app_launch()
    finally:
        test.teardown_method()
