#!/usr/bin/env python
"""
Samsung TV Navigation Script
This script connects to the Samsung TV and performs a specific navigation sequence:
1. Go to HOME screen
2. Navigate RIGHT once
3. Navigate DOWN twice
4. Click ENTER to select
"""
import websocket
import json
import time
import logging
import ssl
import argparse
import sys
import urllib.parse
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SamsungTVNav")

class SamsungTVNavigator:
    """Samsung TV controller with navigation sequences for E2E testing"""
    
    def __init__(self, host, port=8002, timeout=15, client_name="HotE2ETester"):
        self.host = host
        self.port = port
        self.timeout = timeout
        # Ensure client_name is properly encoded
        self.client_name = client_name
        self.ws = None
        self.token_file = Path.home() / ".samsung_tv_token"
        self.token = self._load_token()
        
        # URL encode the name parameter to prevent UTF-8 issues
        encoded_name = urllib.parse.quote(client_name)
        self.url = f"wss://{host}:{port}/api/v2/channels/samsung.remote.control?name={encoded_name}"
        logger.debug(f"URL encoded name: {encoded_name}")
        
    def _load_token(self):
        """Load saved token if exists"""
        if self.token_file.exists():
            try:
                with open(self.token_file, 'r') as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")
        return None
    
    def _save_token(self, token):
        """Save token for future use"""
        try:
            with open(self.token_file, 'w') as f:
                f.write(token)
            logger.debug("Token saved successfully")
        except Exception as e:
            logger.warning(f"Failed to save token: {e}")
    
    def open(self):
        """Open a WebSocket connection to the TV"""
        logger.info(f"Connecting to TV at {self.url}")
        
        print("\nConnecting to Samsung TV...")
        print("IMPORTANT: Please look at your TV screen and ACCEPT the connection request!")
        print("You may need to press the HOME button on your remote first to see the prompt.\n")
        
        try:
            self.ws = websocket.create_connection(self.url, self.timeout, sslopt={"cert_reqs": ssl.CERT_NONE})
            logger.info("WebSocket connection established")
            print("✅ Connection established! Now waiting for TV to respond...")
            print("\nWaiting for TV response (may take a few seconds)...")
            print("If you see a PIN code on your TV, you'll be prompted to enter it.\n")
            
            response = self.ws.recv()
            logger.debug(f"Initial response: {response}")
            
            # Process the initial response
            return self._handle_response(response)
        except Exception as e:
            logger.error(f"Failed to connect to TV: {e}")
            print(f"❌ Connection failed: {e}")
            return False
    
    def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            self.ws.close()
            logger.info("Connection closed")
    
    def _handle_response(self, response):
        """Handle the response from the TV"""
        try:
            response_data = json.loads(response)
            
            if response_data.get("event") == "ms.channel.connect":
                data = response_data.get("data", {})
                token = data.get("token")
                connection_id = data.get("id")
                
                if token and connection_id:
                    logger.info("Connection already authorized")
                    print("\n✅ TV connection AUTHORIZED! No PIN required.")
                    self._save_token(token)
                    return True
                elif connection_id:
                    logger.info("Connection established, but PIN may be required")
                    # Wait for PIN request or successful auth
                    return self._wait_for_pin_request()
                else:
                    logger.error("Failed to authenticate: Invalid response")
                    print("\n❌ Failed to authenticate: Invalid response from TV")
                    return False
            else:
                logger.warning(f"Unexpected response: {response}")
                print(f"\n⚠️ Unexpected response from TV: {response}")
                return False
        except json.JSONDecodeError:
            logger.error(f"Failed to parse response: {response}")
            print(f"\n❌ Failed to parse TV response: {response}")
            return False
 
    def send_key(self, key, delay=0.5):
        """Send a key command to the TV"""
        if not self.ws:
            logger.error("Not connected to TV")
            return False
        
        logger.info(f"Sending key: {key}")
        
        try:
            key_data = {
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Click",
                    "DataOfCmd": key,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey"
                }
            }
            
            self.ws.send(json.dumps(key_data))
            time.sleep(delay)  # Wait a bit for the TV to process
            return True
        except Exception as e:
            logger.error(f"Failed to send key {key}: {e}")
            return False
                
    def navigate_to_home(self, delay_between_keys=1.0):
        """
        Navigate to the downloaded apps section on the Samsung TV
        """
        print("\n🔍 Navigating to downloaded apps section...")
        
        # Go to HOME screen first
        print("1. Going to HOME screen...")
        if not self.send_key("KEY_HOME", delay=delay_between_keys*2):
            print("❌ Failed to send HOME key")
            return False
            
        # Give the HOME screen time to load completely
        time.sleep(delay_between_keys*2)
        
        return True
        
    def find_and_launch_hot_app(self, delay_between_keys=1.0):
        """
        Find and launch the HOT app from the apps section
        This uses a search pattern to locate the app
        """
        print("\n🔍 Looking for HOT app...")
        
        # First, make sure we're in the apps section
        self.navigate_to_home(delay_between_keys)
        time.sleep(delay_between_keys*2)  # Give time for apps to load
        
        # Search patterns - try multiple methods to find the HOT app
        methods = [
            self._search_method_1
        ]
        
        for i, method in enumerate(methods, 1):
            print(f"\nTrying search method {i}...")
            if method(delay_between_keys):
                print("✅ HOT app found and launched!")
                return True
            
        print("❌ Could not find HOT app after trying all methods")
        return False
        
    def _search_method_1(self, delay_between_keys):
        """Method 1: Look for HOT app in recently used apps row"""
        print("METHOD 1: Looking in recently used apps...")
        
        # First row is usually recently used apps
        # Look through first 6 apps
        for i in range(6):
            # Select the app
            self.send_key("KEY_ENTER", delay=delay_between_keys*3)
            
            # Check if this is the right app (wait to see if HOT loads)
            time.sleep(delay_between_keys*3)
            
            # Ask user if this is the HOT app
            response = input("❓ Is this the HOT app? (y/n): ").lower()
            if response == 'y' or response == 'yes':
                return True
                
            # If not, go back and try the next app
            self.send_key("KEY_RETURN", delay=delay_between_keys*2)
            self.send_key("KEY_RIGHT", delay=delay_between_keys)
            
        return False

def main():
    parser = argparse.ArgumentParser(description="Navigate Samsung TV through a specific sequence")
    parser.add_argument("--host", required=True, help="IP address of the TV")
    parser.add_argument("--port", type=int, default=8002, help="Port number (default: 8002)")
    parser.add_argument("--timeout", type=int, default=15, help="Connection timeout in seconds (default: 15)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between key presses in seconds (default: 1.0)")
    
    args = parser.parse_args()
    
    tv = SamsungTVNavigator(
        host=args.host,
        port=args.port,
        timeout=args.timeout
    )
    
    try:
        if not tv.open():
            print("❌ Failed to connect to TV")
            sys.exit(1)  
       
        tv.find_and_launch_hot_app(delay_between_keys=args.delay)
        
    except KeyboardInterrupt:
        print("\n⚠️ Operation interrupted by user")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
    finally:
        tv.close()

if __name__ == "__main__":
    main()
