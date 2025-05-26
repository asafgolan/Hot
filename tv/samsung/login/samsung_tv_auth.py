#!/usr/bin/env python
import websocket
import json
import time
import logging
import ssl
import argparse
import os
import getpass
import sys
import binascii
import urllib.parse
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SamsungTVAuth")

class SamsungTVAuth:
    """Samsung TV controller with proper authentication handling for E2E testing"""
    
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
            logger.info("Token saved for future sessions")
        except Exception as e:
            logger.warning(f"Failed to save token: {e}")
    
    def open(self):
        """Open the websocket connection with authentication"""
        logger.info(f"Connecting to TV at {self.url}")
        
        try:
            # Enable debugging on websocket
            websocket.enableTrace(True)
            
            print("\nConnecting to Samsung TV...")
            print("IMPORTANT: Please look at your TV screen and ACCEPT the connection request!")
            print("You may need to press the HOME button on your remote first to see the prompt.\n")
            
            # Disable SSL verification as Samsung TVs use self-signed certificates
            self.ws = websocket.create_connection(
                self.url,
                self.timeout,
                sslopt={"cert_reqs": ssl.CERT_NONE}
            )
            
            logger.info("WebSocket connection established")
            print("✅ Connection established! Now waiting for TV to respond...")
        except UnicodeDecodeError as e:
            logger.error(f"UTF-8 encoding error: {e}")
            logger.error(f"Try using ASCII characters only in client_name")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
        
        # Check if we need to authenticate
        try:
            print("\nWaiting for TV response (may take a few seconds)...")
            print("If you see a PIN code on your TV, you'll be prompted to enter it.\n")
            
            # Set a longer socket timeout for the initial response
            self.ws.sock.settimeout(20)
            response = self.ws.recv()
            logger.info(f"Initial response: {response}")
            
            # Debug raw bytes if there are encoding issues
            try:
                raw_bytes = response.encode('utf-8')
                logger.debug(f"Raw response bytes: {binascii.hexlify(raw_bytes)}")
            except Exception as e:
                logger.debug(f"Could not encode response: {e}")
        except Exception as e:
            logger.error(f"Error receiving initial response: {e}")
            return False
        
        response_data = json.loads(response)
        if response_data.get("event") == "ms.channel.connect":
            # Already authenticated
            logger.info("Connection already authorized")
            print("\n✅ TV connection AUTHORIZED! No PIN required.")
            return True
        elif response_data.get("event") == "ms.channel.ready":
            # Ready but might need PIN later
            logger.info("Channel ready - connection accepted on TV")
            print("\n✅ TV accepted the connection!")
            return True
        
        # If we have a saved token, try to use it
        if self.token:
            logger.info("Attempting to authenticate with saved token")
            if self._authenticate_with_token(self.token):
                return True
        
        # Need to authenticate with PIN
        logger.info("Authentication required. Check your TV screen for a PIN code")
        
        # In interactive mode, prompt for PIN
        if sys.stdin.isatty():
            print("\n" + "-"*50)
            print("PIN AUTHENTICATION REQUIRED")
            print("Look at your TV screen for the PIN code")
            print("-"*50 + "\n")
            pin = input("Enter the PIN displayed on your TV: ")
            # Validate PIN is digits only
            if not pin.isdigit():
                logger.error("PIN must contain only digits")
                return False
            return self._authenticate_with_token(pin)
        else:
            logger.error("PIN authentication required but running in non-interactive mode")
            return False
    
    def _authenticate_with_token(self, token):
        """Authenticate with the provided token/PIN"""
        auth_payload = {
            "method": "ms.channel.connect",
            "params": {
                "token": token,
                "data": {"clients": []}
            }
        }
        
        logger.info("Sending authentication request")
        try:
            # Ensure proper UTF-8 encoding
            auth_json = json.dumps(auth_payload, ensure_ascii=True)
            logger.debug(f"Auth payload: {auth_json}")
            self.ws.send(auth_json)
        
            # Wait for response
            response = self.ws.recv()
            logger.info(f"Auth response: {response}")
            
            # Debug raw bytes if needed
            try:
                raw_bytes = response.encode('utf-8')
                logger.debug(f"Raw response bytes: {binascii.hexlify(raw_bytes)}")
            except Exception as e:
                logger.debug(f"Could not encode response: {e}")
        except Exception as e:
            logger.error(f"Error during authentication: {e}")
            return False
        
        response_data = json.loads(response)
        if response_data.get("event") == "ms.channel.connect" and "data" in response_data:
            logger.info("Successfully authenticated")
            print("\n✅ PIN ACCEPTED! TV is now fully authenticated.")
            # Save token for future use
            self._save_token(token)
            return True
        elif "ms.error" in response_data.get("event", ""):
            logger.error(f"Authentication failed: {response}")
            print(f"\n❌ Authentication ERROR: {response_data.get('data', {}).get('message', 'Unknown error')}")
            print("Check the PIN and try again.")
            return False
        else:
            logger.error(f"Authentication failed with unexpected response: {response}")
            print(f"\n⚠️ Unexpected response from TV: {response}")
            # Some TVs might not provide the expected response format but still authenticate
            print("Connection might still be usable - attempting to continue.")
            return True
    
    def close(self):
        """Close the websocket connection"""
        if self.ws:
            self.ws.close()
            self.ws = None
            logger.info("Connection closed")
    
    def send_key(self, key):
        """Send a key command to the TV"""
        try:
            if not self.ws:
                if not self.open():
                    logger.error("Failed to open connection")
                    return False
            
            payload = {
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Click",
                    "DataOfCmd": key,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey"
                }
            }
            
            logger.info(f"Sending key: {key}")
            self.ws.send(json.dumps(payload))
            response = self.ws.recv()
            logger.info(f"Response: {response}")
            
            # Check for auth errors
            response_data = json.loads(response)
            if response_data.get("event") == "ms.error" and "No Authorized" in response_data.get("data", {}).get("message", ""):
                logger.error("Authentication required for this operation")
                # Try to authenticate and retry
                if self.open() and self.ws:
                    self.ws.send(json.dumps(payload))
                    response = self.ws.recv()
                    logger.info(f"Retry response: {response}")
                    response_data = json.loads(response)
            
            return "ms.error" not in response_data.get("event", "")
        except Exception as e:
            logger.error(f"Error sending key: {e}")
            return False
    
    def get_app_list(self):
        """Get the list of applications installed on the TV"""
        try:
            if not self.ws:
                if not self.open():
                    logger.error("Failed to open connection")
                    return None
            
            payload = {
                "method": "ms.channel.emit",
                "params": {
                    "event": "ed.installedApp.get",
                    "to": "host"
                }
            }
            
            logger.info("Getting app list")
            self.ws.send(json.dumps(payload))
            response = self.ws.recv()
            logger.info(f"Response: {response[:200]}...")
            
            # Check for auth errors
            response_data = json.loads(response)
            if response_data.get("event") == "ms.error" and "No Authorized" in response_data.get("data", {}).get("message", ""):
                logger.error("Authentication required for this operation")
                # Try to authenticate and retry
                if self.open() and self.ws:
                    self.ws.send(json.dumps(payload))
                    response = self.ws.recv()
                    logger.info(f"Retry response: {response[:200]}...")
                    response_data = json.loads(response)
            
            return response_data
        except Exception as e:
            logger.error(f"Error getting app list: {e}")
            return None

    def launch_app(self, app_id):
        """Launch an application by app ID"""
        try:
            if not self.ws:
                if not self.open():
                    logger.error("Failed to open connection")
                    return False
            
            payload = {
                "method": "ms.channel.emit",
                "params": {
                    "event": "ed.apps.launch",
                    "to": "host",
                    "data": {
                        "appId": app_id
                    }
                }
            }
            
            logger.info(f"Launching app: {app_id}")
            self.ws.send(json.dumps(payload))
            response = self.ws.recv()
            logger.info(f"Response: {response}")
            
            # Check for auth errors
            response_data = json.loads(response)
            if response_data.get("event") == "ms.error" and "No Authorized" in response_data.get("data", {}).get("message", ""):
                logger.error("Authentication required for this operation")
                # Try to authenticate and retry
                if self.open() and self.ws:
                    self.ws.send(json.dumps(payload))
                    response = self.ws.recv()
                    logger.info(f"Retry response: {response}")
                    response_data = json.loads(response)
            
            return "ms.error" not in response_data.get("event", "")
        except Exception as e:
            logger.error(f"Error launching app: {e}")
            return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Control Samsung TV with authentication handling")
    parser.add_argument("--host", default="192.168.1.26", help="TV IP address")
    parser.add_argument("--port", type=int, default=8002, help="TV port (default: 8002)")
    parser.add_argument("--name", default="HotE2ETester", help="Client name for authentication")
    parser.add_argument("--action", default="test", 
                      choices=["test", "key", "apps", "launch"], 
                      help="Action to perform")
    parser.add_argument("--value", help="Value for action (key name or app ID)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("SamsungTVAuth").setLevel(logging.DEBUG)
    
    # Use a simple ASCII name if having UTF-8 issues
    clean_name = ''.join(c for c in args.name if ord(c) < 128)
    if clean_name != args.name:
        print(f"Warning: Non-ASCII characters in name. Using '{clean_name}' instead.")
    
    tv = SamsungTVAuth(args.host, args.port, client_name=clean_name)
    
    try:
        if args.action == "test":
            # Just test connection
            if tv.open():
                print("✅ Successfully connected and authenticated to TV!")
                tv.close()
            else:
                print("❌ Failed to connect or authenticate with TV")
        
        elif args.action == "key":
            if not args.value:
                args.value = "KEY_HOME"  # Default key
            result = tv.send_key(args.value)
            print(f"Send key {args.value}: {'✅ Success' if result else '❌ Failed'}")
            tv.close()
        
        elif args.action == "apps":
            apps = tv.get_app_list()
            if apps and "ms.error" not in apps.get("event", ""):
                print("Installed apps:")
                try:
                    for app in apps.get('data', {}).get('data', []):
                        print(f"- {app.get('name')} (ID: {app.get('appId')})")
                except:
                    print(f"Raw response: {apps}")
            else:
                print("❌ Failed to get app list")
            tv.close()
        
        elif args.action == "launch":
            if not args.value:
                print("Please provide an app ID with --value")
                return
            result = tv.launch_app(args.value)
            print(f"Launch app {args.value}: {'✅ Success' if result else '❌ Failed'}")
            tv.close()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        tv.close()

if __name__ == "__main__":
    main()
