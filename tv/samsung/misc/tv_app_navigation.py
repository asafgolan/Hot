#!/usr/bin/env python
"""
Samsung TV App Navigation Test
Simulates remote control navigation to select and launch apps
"""
import os
import sys
import json
import time
import logging
import threading
import traceback
import ssl
from datetime import datetime
from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure
import websocket
import urllib3

# Configure logging
log_dir = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "test_results", "tv_app_navigation"
))
os.makedirs(log_dir, exist_ok=True)

# Log file with timestamp
log_file = os.path.join(log_dir, f"navigation_{time.strftime('%Y%m%d_%H%M%S')}.log")
json_file = os.path.join(log_dir, f"navigation_messages_{time.strftime('%Y%m%d_%H%M%S')}.json")

# Configure logging with both file and console output
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])
logger = logging.getLogger('tv_navigation')

# Configuration
TV_IP = "192.168.1.26"
TV_PORT = 8002
CLIENT_NAME = "HotE2ETester"
CONNECTION_TIMEOUT = 10

# List to store WebSocket messages
ws_messages = []
ws_lock = threading.Lock()

# Patch WebSocket send to capture outgoing messages
original_send = websocket.WebSocket.send

def patched_send(self, data, *args, **kwargs):
    try:
        # Try to parse as JSON for better logging
        message_type = "binary"
        message_content = data
        event_type = "unknown"
        
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                message_type = "json"
                message_content = parsed
                method = parsed.get('method', '')
                
                if method == 'ms.remote.control':
                    event_type = "remote_control"
                    key = parsed.get('params', {}).get('DataOfCmd', '')
                    logger.info(f"🎮 Remote Control: {key}")
                elif method == 'ms.channel.emit':
                    event_type = parsed.get('params', {}).get('event', 'channel_emit')
                    logger.info(f"📺 Channel event: {event_type}")
                
                with ws_lock:
                    ws_messages.append({
                        'direction': 'sent',
                        'timestamp': datetime.now().isoformat(),
                        'type': message_type,
                        'event_type': event_type,
                        'content': message_content
                    })
            except json.JSONDecodeError:
                # Not JSON data
                message_type = "text"
        
        logger.debug(f"++Sent {message_type}: {message_content}")
    except Exception as e:
        logger.debug(f"Error logging sent message: {e}")
    
    # Call original method
    return original_send(self, data, *args, **kwargs)

# Initialize Samsung TV connection
def init_tv():
    # Apply the WebSocket patch
    websocket.WebSocket.send = patched_send
    
    # Disable SSL verification for all requests
    ssl._create_default_https_context = ssl._create_unverified_context
    
    logger.info(f"Connecting to Samsung TV at {TV_IP}...")
    
    # Create TV instance
    tv = SamsungTVWS(
        host=TV_IP,
        port=TV_PORT,
        name=CLIENT_NAME,
        timeout=CONNECTION_TIMEOUT
    )
    
    # Test connection
    for attempt in range(3):
        try:
            logger.info(f"Connection attempt {attempt+1}/3...")
            response = tv.rest_device_info()
            logger.info(f"✅ TV connection successful - Device info: {response.get('name', 'Unknown')}")
            
            # Try a simple remote control command
            tv.shortcuts().home()
            logger.info("✅ Remote control working")
            return tv
        except ConnectionFailure as e:
            logger.warning(f"Connection failure on attempt {attempt+1}: {e}")
            time.sleep(2)
        except Exception as e:
            logger.error(f"❌ TV connection failed: {e}")
            logger.debug(traceback.format_exc())
            break
    
    logger.error("Failed to connect to TV after multiple attempts")
    return None

# Function to simulate navigation on the TV to select and open an app
def navigate_and_select_app(tv):
    """Use remote control commands to navigate and select an app"""
    logger.info("\n===== BEGINNING APP NAVIGATION TEST =====")
    
    try:
        # 1. First make sure we're on the home screen
        logger.info("1. Going to Home screen...")
        tv.shortcuts().home()
        time.sleep(2)  # Wait for home screen to load
        
        # 2. Navigate to the apps row (typically down a few times)
        logger.info("2. Navigating to apps row...")
        # Press down 1-2 times to reach the apps row
        for i in range(2):
            tv.send_key("KEY_DOWN")
            time.sleep(1)
        
        # 3. Navigate to the first app (should already be selected)
        logger.info("3. First app should be selected...")
        time.sleep(1)
        
        # 4. Click to open the app
        logger.info("4. Opening selected app...")
        tv.send_key("KEY_ENTER")
        
        # 5. Wait to capture messages
        logger.info("5. Waiting to capture app launch messages...")
        time.sleep(5)
        
        # 6. Return to home
        logger.info("6. Returning to home...")
        tv.shortcuts().home()
        time.sleep(2)
        
        # 7. Try with another app - navigate right first
        logger.info("7. Navigating to second app...")
        # Down to apps row again
        for i in range(2):
            tv.send_key("KEY_DOWN")
            time.sleep(1)
        
        # Move right to next app
        tv.send_key("KEY_RIGHT")
        time.sleep(1)
        
        # Open the second app
        logger.info("8. Opening second app...")
        tv.send_key("KEY_ENTER")
        time.sleep(5)
        
        # Return to home
        logger.info("9. Returning to home...")
        tv.shortcuts().home()
        
        logger.info("✅ Navigation test completed")
        return True
    except Exception as e:
        logger.error(f"❌ Navigation test failed: {e}")
        logger.debug(traceback.format_exc())
        return False

# Function to save captured messages
def save_messages():
    with ws_lock:
        if not ws_messages:
            logger.info("No messages captured")
            return
            
        # Save to JSON file
        with open(json_file, 'w') as f:
            json.dump(ws_messages, f, indent=2)
        
        logger.info(f"Saved {len(ws_messages)} WebSocket messages to {json_file}")
        
        # Analyze and print summary
        sent_count = sum(1 for m in ws_messages if m.get('direction') == 'sent')
        received_count = sum(1 for m in ws_messages if m.get('direction') == 'received')
        
        logger.info(f"\nMessage Analysis:")
        logger.info(f"Total messages: {len(ws_messages)}")
        logger.info(f"- Sent: {sent_count}")
        logger.info(f"- Received: {received_count}")
        
        # Group by event types
        event_types = {}
        for msg in ws_messages:
            event = msg.get('event_type', 'unknown')
            if event not in event_types:
                event_types[event] = 0
            event_types[event] += 1
        
        logger.info("\nEvent types:")
        for event, count in event_types.items():
            logger.info(f"- {event}: {count}")
        
        # Check for specific event types of interest
        interesting_events = ['ms.channel.ready', 'ed.apps.launch', 'ms.channel.connect']
        for event in interesting_events:
            if any(event in str(msg) for msg in ws_messages):
                logger.info(f"\nFound '{event}' events - these may contain app metadata")
        
        # Print a sample of interesting received messages
        interesting_messages = []
        for msg in ws_messages:
            if msg.get('direction') == 'received' and not msg.get('event_type') in ['ping', 'pong', 'ms.channel.timeOut']:
                interesting_messages.append(msg)
        
        if interesting_messages:
            logger.info("\nInteresting received messages:")
            for i, msg in enumerate(interesting_messages[:3]):  # Show up to 3 interesting messages
                logger.info(f"Message {i+1}:")
                logger.info(json.dumps(msg, indent=2))

# Main function
def main():
    logger.info("Samsung TV App Navigation Test")
    logger.info(f"Log file: {log_file}")
    
    # Initialize TV connection
    tv = init_tv()
    if not tv:
        return
    
    try:
        # Run the navigation test
        navigate_and_select_app(tv)
        
        # Save and analyze messages
        save_messages()
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        logger.debug(traceback.format_exc())
    
    logger.info("\nTest completed.")
    logger.info(f"Check {json_file} for detailed message logs.")

if __name__ == "__main__":
    main()
