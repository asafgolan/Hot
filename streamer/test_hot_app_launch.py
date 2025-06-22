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
            
            # Patterns to match in the logs
            app_launch_pattern = r'ActivityTaskManager: START .* pkg=il\.net\.hot\.hot cmp=il\.net\.hot\.hot/\.TvMainActivity'
            window_transition_pattern = r'WindowManagerShell: Transition requested.*il\.net\.hot\.hot'
            webview_start_pattern = r'ActivityManager: Start proc .* for  {il\.net\.hot\.hot/org\.chromium\.content\.app\.SandboxedProcessService'
            back_callback_pattern = r'CoreBackPreview: Window.* il\.net\.hot\.hot/il\.net\.hot\.hot\.TvMainActivity.*Setting back callback'
            transition_ready_pattern = r'WindowManagerShell: onTransitionReady android\.os\.BinderProxy@[\w]+'  
            initial_transition_start_pattern = r'WindowManagerShell: Playing animation for \(#(\d+)\)android\.os\.BinderProxy@[\w]+'
            initial_transition_finish_pattern = r'WindowManagerShell: Transition animation finished \(aborted=false\), notifying core \(#(\d+)\)android\.os\.BinderProxy@[\w]+'
            transition_timing_pattern = r'WindowManager: Finish Transition #(\d+): created at .* finished=(\d+\.\d+)ms'
            all_animations_finished_pattern = r'WindowManagerShell: All active transition animations finished'
            
            # For extracting important values
            proxy_pattern = r'(android\.os\.BinderProxy@[\w]+)'
            proc_thread_pattern = r'^\d+-\d+\s+\d+:\d+:\d+\.\d+\s+(\d+)\s+(\d+)'  # Format: 06-22 10:46:20.203  1030  1075
            
            log_file_path = os.path.join(self.results_dir, 'test_logs.txt')
            with open(log_file_path, 'w') as log_file:
                while not self.stop_event.is_set():
                    try:
                        line = process.stdout.readline()
                        if not line:
                            break
                        
                        # Write to log file
                        log_file.write(line)
                        log_file.flush()
                    except UnicodeDecodeError as e:
                        print(f"Warning: Skipping log line with decode error: {e}")
                        continue
                    
                    # Check for app launch event
                    if re.search(app_launch_pattern, line):
                        print("Detected HOT app launch")
                        self.log_queue.put(('app_launch', line))
                        self.event_detected['app_launch'] = True
                    
                    # Check for window transition event
                    elif re.search(window_transition_pattern, line):
                        print("Detected window transition")
                        self.log_queue.put(('window_transition', line))
                        self.event_detected['window_transition'] = True
                        
                    # Check for WebView process start event
                    elif re.search(webview_start_pattern, line):
                        print("Detected WebView process start")
                        self.log_queue.put(('webview_start', line))
                        self.event_detected['webview_start'] = True
                    
                    # Check for back callback setup event
                    elif re.search(back_callback_pattern, line):
                        print("Detected CoreBackPreview callback setup")
                        self.log_queue.put(('back_callback', line))
                        self.event_detected['back_callback'] = True
                        
                    # Check for transition ready event
                    elif re.search(transition_ready_pattern, line):
                        print("Detected transition ready")
                        self.log_queue.put(('transition_ready', line))
                        self.event_detected['transition_ready'] = True
                        
                        # Extract proxy string
                        proxy_match = re.search(proxy_pattern, line)
                        if proxy_match:
                            self.extracted_values['proxy_string'] = proxy_match.group(1)
                            print(f"Extracted proxy string: {self.extracted_values['proxy_string']}")
                        
                        # Extract process and thread IDs
                        proc_thread_match = re.search(proc_thread_pattern, line)
                        if proc_thread_match:
                            self.extracted_values['shell_process_id'] = proc_thread_match.group(1)
                            self.extracted_values['shell_thread_id'] = proc_thread_match.group(2)
                            print(f"Extracted process ID: {self.extracted_values['shell_process_id']}, thread ID: {self.extracted_values['shell_thread_id']}")
                    
                    # Check for initial transition start event
                    elif re.search(initial_transition_start_pattern, line):
                        # Only capture first occurrence as initial transition
                        if not self.event_detected['initial_transition_start']:
                            print("Detected initial loading transition start")
                            self.log_queue.put(('initial_transition_start', line))
                            self.event_detected['initial_transition_start'] = True
                            
                            # Extract transition ID for initial loading
                            transition_match = re.search(initial_transition_start_pattern, line)
                            if transition_match:
                                transition_id = transition_match.group(1)
                                self.extracted_values['initial_transition_id'] = transition_id
                                print(f"Initial loading transition ID: {transition_id}")
                        # Capture second occurrence as home page transition
                        elif not self.event_detected['home_transition_start'] and self.event_detected['initial_transition_finish']:
                            print("Detected home page transition start")
                            self.log_queue.put(('home_transition_start', line))
                            self.event_detected['home_transition_start'] = True
                            
                            # Extract transition ID for home page
                            transition_match = re.search(initial_transition_start_pattern, line)
                            if transition_match:
                                transition_id = transition_match.group(1)
                                self.extracted_values['home_transition_id'] = transition_id
                                print(f"Home page transition ID: {transition_id}")
                    
                    # Check for transition finish events
                    elif re.search(initial_transition_finish_pattern, line):
                        animation_finish_match = re.search(initial_transition_finish_pattern, line)
                        if animation_finish_match:
                            finished_transition_id = animation_finish_match.group(1)
                            # Check for initial loading transition finish
                            if (not self.event_detected['initial_transition_finish'] and 
                               'initial_transition_id' in self.extracted_values and 
                               self.extracted_values['initial_transition_id'] == finished_transition_id):
                                print(f"Initial loading transition #{finished_transition_id} finished")
                                self.log_queue.put(('initial_transition_finish', line))
                                self.event_detected['initial_transition_finish'] = True
                            # Check for home page transition finish
                            elif (self.event_detected['home_transition_start'] and 
                                 not self.event_detected['home_transition_finish'] and 
                                 'home_transition_id' in self.extracted_values and 
                                 self.extracted_values['home_transition_id'] == finished_transition_id):
                                print(f"Home page transition #{finished_transition_id} finished")
                                self.log_queue.put(('home_transition_finish', line))
                                self.event_detected['home_transition_finish'] = True
                    
                    # Check for transition timing metrics
                    elif re.search(transition_timing_pattern, line):
                        transition_finish_match = re.search(transition_timing_pattern, line)
                        if transition_finish_match:
                            finished_id = transition_finish_match.group(1)
                            finish_time_ms = transition_finish_match.group(2)
                            # Capture initial loading transition timing
                            if 'initial_transition_id' in self.extracted_values and self.extracted_values['initial_transition_id'] == finished_id:
                                self.extracted_values['initial_transition_time_ms'] = float(finish_time_ms)
                                print(f"Initial loading transition #{finished_id} completed in {finish_time_ms} ms")
                            # Capture home page transition timing
                            elif 'home_transition_id' in self.extracted_values and self.extracted_values['home_transition_id'] == finished_id:
                                self.extracted_values['home_transition_time_ms'] = float(finish_time_ms)
                                print(f"Home page transition #{finished_id} completed in {finish_time_ms} ms")
                        
            process.terminate()
        except Exception as e:
            print(f"Error in log monitoring: {str(e)}")
            
    def _capture_screenshot_on_event(self):
        """Watch for events and take screenshots"""
        try:
            while not self.stop_event.is_set():
                try:
                    event_type, log_line = self.log_queue.get(timeout=0.5)
                    if event_type in ['app_launch', 'window_transition', 'transition_ready', 'animation_start']:
                        # Take a screenshot for this event
                        screenshot_path = self._take_screenshot(event_type)
                        
                        # Save event details
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                        with open(os.path.join(self.results_dir, f"event_{event_type}_{timestamp}.txt"), 'w') as f:
                            f.write(f"Event type: {event_type}\n")
                            f.write(f"Log line: {log_line}\n")
                        
                        if screenshot_path:
                            self.screenshot_queue.put((event_type, screenshot_path))
                except queue.Empty:
                    pass  # No events in queue
                    
        except Exception as e:
            print(f"Error in screenshot capturer: {str(e)}")

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
        screenshot_thread = threading.Thread(target=self._capture_screenshot_on_event)
        
        log_thread.daemon = True
        screenshot_thread.daemon = True
        
        log_thread.start()
        screenshot_thread.start()
        
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
            print(f"Launch command output: {result.stdout}")
            
            # Force-stop the app first to ensure a clean launch
            print("Force-stopping HOT app to ensure clean launch...")
            subprocess.run(
                ["adb", "shell", "am", "force-stop", "il.net.hot.hot"],
                check=True
            )
            
            # Short delay to ensure app is fully stopped
            time.sleep(1)
            
            # Now launch the app fresh
            print("Re-launching HOT app...")
            result = subprocess.run(
                ["adb", "shell", "am", "start", "-n", "il.net.hot.hot/.TvMainActivity"],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"Re-launch command output: {result.stdout}")
            
            
            # Wait for events to be detected (max 45 seconds)
            timeout = time.time() + 45
            while time.time() < timeout and not (self.event_detected['app_launch'] and 
                                           self.event_detected['window_transition'] and
                                           self.event_detected['webview_start'] and
                                           self.event_detected['back_callback'] and
                                           self.event_detected['transition_ready'] and
                                           self.event_detected['initial_transition_start'] and
                                           self.event_detected['initial_transition_finish'] and
                                           self.event_detected['home_transition_start'] and
                                           self.event_detected['home_transition_finish']):
                time.sleep(0.5)
                
            # Generate an HTML report
            self._generate_html_report()
            
            # Assert that events were detected
            assert self.event_detected['app_launch'], "App launch event was not detected"
            assert self.event_detected['window_transition'], "Window transition event was not detected"
            assert self.event_detected['webview_start'], "WebView process start event was not detected"
            assert self.event_detected['back_callback'], "CoreBackPreview callback setup event was not detected"
            assert self.event_detected['transition_ready'], "Transition ready event was not detected"
            assert self.event_detected['initial_transition_start'], "Initial loading transition start event was not detected"
            assert self.event_detected['initial_transition_finish'], "Initial loading transition finish event was not detected"
            assert self.event_detected['home_transition_start'], "Home page transition start event was not detected"
            assert self.event_detected['home_transition_finish'], "Home page transition finish event was not detected"
            
            # Assert that important values were extracted
            assert self.extracted_values['proxy_string'], "Proxy string was not extracted"
            assert self.extracted_values['shell_process_id'], "Shell process ID was not extracted"
            assert self.extracted_values['shell_thread_id'], "Shell thread ID was not extracted"
            assert self.extracted_values['transition_id'], "Transition ID was not extracted"
            # Note: We don't assert transition_finish_time_ms as it might not always be detected in time
            
        except subprocess.CalledProcessError as e:
            pytest.fail(f"Error launching app: {str(e)}")
        finally:
            # Stop threads
            self.stop_event.set()
            
    def _generate_html_report(self):
        """Generate an HTML report with screenshots and event details"""
        html_path = os.path.join(self.results_dir, "report.html")
        
        with open(html_path, "w") as f:
            f.write("<!DOCTYPE html>\n")
            f.write("<html>\n<head>\n")
            f.write("<title>HOT App Launch Test Results</title>\n")
            f.write("<style>\n")
            f.write("body { font-family: Arial, sans-serif; margin: 20px; }\n")
            f.write(".screenshot { margin-bottom: 30px; border: 1px solid #ddd; padding: 10px; }\n")
            f.write("img { max-width: 800px; border: 1px solid #eee; }\n")
            f.write(".event { background-color: #f0f0f0; padding: 10px; margin-bottom: 10px; }\n")
            f.write("</style>\n")
            f.write("</head>\n<body>\n")
            f.write(f"<h1>HOT App Launch Test Results</h1>\n")
            f.write(f"<p>Test run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>\n")
            
            # Add event sections
            if self.event_detected['app_launch']:
                f.write("<div class='event'>\n")
                f.write("<h2>App Launch Event Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>App Launch Event Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['window_transition']:
                f.write("<div class='event'>\n")
                f.write("<h2>Window Transition Event Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Window Transition Event Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['webview_start']:
                f.write("<div class='event'>\n")
                f.write("<h2>WebView Process Start Event Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>WebView Process Start Event Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['back_callback']:
                f.write("<div class='event'>\n")
                f.write("<h2>CoreBackPreview Callback Setup Event Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>CoreBackPreview Callback Setup Event Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['transition_ready']:
                f.write("<div class='event'>\n")
                f.write("<h2>Transition Ready Event Detected ✅</h2>\n")
                f.write(f"<p>Proxy String: {self.extracted_values['proxy_string']}</p>\n")
                f.write(f"<p>WindowManagerShell Process ID: {self.extracted_values['shell_process_id']}</p>\n")
                f.write(f"<p>WindowManagerShell Thread ID: {self.extracted_values['shell_thread_id']}</p>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Transition Ready Event Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['initial_transition_start']:
                f.write("<div class='event'>\n")
                f.write("<h2>Initial Loading Transition Start Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Initial Loading Transition Start Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['initial_transition_finish']:
                f.write("<div class='event'>\n")
                f.write("<h2>Initial Loading Transition Finish Detected ✅</h2>\n")
                if 'initial_transition_time_ms' in self.extracted_values:
                    f.write(f"<p>Initial loading time: {self.extracted_values['initial_transition_time_ms']} ms</p>\n")
                if 'initial_transition_id' in self.extracted_values:
                    f.write(f"<p>Initial transition ID: {self.extracted_values['initial_transition_id']}</p>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Initial Loading Transition Finish Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['home_transition_start']:
                f.write("<div class='event'>\n")
                f.write("<h2>Home Page Transition Start Detected ✅</h2>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Home Page Transition Start Not Detected ❌</h2>\n")
                f.write("</div>\n")
                
            if self.event_detected['home_transition_finish']:
                f.write("<div class='event'>\n")
                f.write("<h2>Home Page Transition Finish Detected ✅</h2>\n")
                if 'home_transition_time_ms' in self.extracted_values:
                    f.write(f"<p>Home page transition time: {self.extracted_values['home_transition_time_ms']} ms</p>\n")
                if 'home_transition_id' in self.extracted_values:
                    f.write(f"<p>Home page transition ID: {self.extracted_values['home_transition_id']}</p>\n")
                f.write("</div>\n")
            else:
                f.write("<div class='event'>\n")
                f.write("<h2>Home Page Transition Finish Not Detected ❌</h2>\n")
                f.write("</div>\n")
            
            # Add screenshots
            f.write("<h2>Screenshots</h2>\n")
            screenshots = []
            while not self.screenshot_queue.empty():
                event_type, path = self.screenshot_queue.get()
                screenshots.append((event_type, os.path.basename(path)))
            
            for event_type, filename in screenshots:
                f.write("<div class='screenshot'>\n")
                f.write(f"<h3>Event: {event_type}</h3>\n")
                f.write(f"<img src='{filename}' alt='{event_type} screenshot'>\n")
                f.write("</div>\n")
            
            f.write("</body>\n</html>")
            
        print(f"HTML report generated: {html_path}")


if __name__ == "__main__":
    # Allow running directly (not just with pytest)
    test = TestHotAppLaunch()
    test.setup_method()
    try:
        test.test_hot_app_launch()
    finally:
        test.teardown_method()
