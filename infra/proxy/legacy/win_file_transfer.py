#!/usr/bin/env python3
"""
Simple file transfer script for Mac-Windows proxy
Only handles moving files between systems - no request processing
Works alongside win_exec_bridge.py
"""
import os
import time
import subprocess
import argparse
import traceback

# Directory constants
WINDOWS_INCOMING_DIR = r"C:\WebServerTest\bt_transfer\incoming"
WINDOWS_OUTGOING_DIR = r"C:\WebServerTest\bt_transfer\outgoing"
MAC_INCOMING_DIR = "/Users/asafgolan/Hot/infra/proxy/bt_transfer/incoming"
MAC_OUTGOING_DIR = "/Users/asafgolan/Hot/infra/proxy/bt_transfer/outgoing"

# SSH configuration - these will be updated from command line args
MAC_SSH_HOST = "192.168.1.100"  # Default value, will be overridden by args
MAC_SSH_USER = "asafgolan"      # Default value, will be overridden by args
MAC_SSH_KEY_PATH = None         # Path to SSH private key file
MAC_SSH_PORT = 22               # Default SSH port

def ensure_dirs():
    """Ensure required directories exist on both Windows and Mac"""
    # Ensure Windows directories
    for directory in [WINDOWS_INCOMING_DIR, WINDOWS_OUTGOING_DIR]:
        os.makedirs(directory, exist_ok=True)
    
    # Ensure Mac directories via SSH
    for directory in [MAC_INCOMING_DIR, MAC_OUTGOING_DIR]:
        mkdir_command = f"mkdir -p {directory}"
        run_ssh_command(mkdir_command)
        print(f"Ensured directory exists: {directory}")

def run_ssh_command(command):
    """Run a command on the Mac via SSH"""
    try:
        ssh_command = ['ssh']
        if MAC_SSH_KEY_PATH:
            ssh_command.extend(['-i', MAC_SSH_KEY_PATH])
            
        ssh_command.extend([
            '-p', str(MAC_SSH_PORT),
            f"{MAC_SSH_USER}@{MAC_SSH_HOST}",
            command
        ])
        
        process = subprocess.Popen(
            ssh_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            print(f"SSH error: {stderr}")
            return None
            
        return stdout
    except Exception as e:
        print(f"SSH command execution error: {e}")
        return None

def fetch_request_files(retry_max=3):
    """Fetch request files from Mac via SSH using scp"""
    try:
        # Check if directory exists first
        check_dir_cmd = f"test -d {MAC_OUTGOING_DIR} && echo 'exists'"
        dir_check = run_ssh_command(check_dir_cmd)
        
        if not dir_check or 'exists' not in dir_check:
            print(f"Mac outgoing directory does not exist: {MAC_OUTGOING_DIR}")
            # Create directory
            mkdir_cmd = f"mkdir -p {MAC_OUTGOING_DIR}"
            run_ssh_command(mkdir_cmd)
            print(f"Created directory: {MAC_OUTGOING_DIR}")
            return []
            
        # List files in Mac outgoing directory
        list_command = f"ls -1 {MAC_OUTGOING_DIR} 2>/dev/null || echo ''"
        result = run_ssh_command(list_command)
        
        if not result:
            print("Could not list files on Mac")
            return []
            
        mac_files = result.strip().split('\n')
        request_files = [f for f in mac_files if f and f.startswith("req_") and f.endswith(".json")]
        
        if not request_files:
            return []
            
        print(f"Found {len(request_files)} request files on Mac")
        
        local_paths = []
        for filename in request_files:
            # Download the file using scp
            mac_path = os.path.join(MAC_OUTGOING_DIR, filename).replace('\\', '/')
            win_path = os.path.join(WINDOWS_INCOMING_DIR, filename)
            
            # Try up to retry_max times
            success = False
            for attempt in range(retry_max):
                try:
                    scp_command = ['scp', '-B']  # -B for binary mode
                    if MAC_SSH_KEY_PATH:
                        scp_command.extend(['-i', MAC_SSH_KEY_PATH])
                        
                    scp_command.extend([f"{MAC_SSH_USER}@{MAC_SSH_HOST}:{mac_path}", win_path])
                    
                    process = subprocess.Popen(
                        scp_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    _, stderr = process.communicate()
                    
                    if process.returncode == 0 and os.path.exists(win_path):
                        print(f"Downloaded {filename} from Mac (attempt {attempt+1})")
                        local_paths.append(win_path)
                        success = True
                        
                        # Remove the file from Mac only after successful transfer
                        rm_command = f"rm {mac_path}"
                        if run_ssh_command(rm_command):
                            print(f"Removed {filename} from Mac")
                        break
                    else:
                        print(f"Failed to download {filename} (attempt {attempt+1}): {stderr}")
                        # Short pause before retrying
                        time.sleep(0.5)
                except Exception as e:
                    print(f"Error downloading {filename} (attempt {attempt+1}): {e}")
                    time.sleep(0.5)
            
            if not success:
                print(f"Failed to download {filename} after {retry_max} attempts")
                
        return local_paths
    except Exception as e:
        print(f"Error fetching request files: {e}")
        traceback.print_exc()
        return []

def send_response_files(retry_max=3):
    """Send response files from Windows to Mac via SCP"""
    try:
        # Ensure Mac incoming directory exists
        mkdir_cmd = f"mkdir -p {MAC_INCOMING_DIR}"
        run_ssh_command(mkdir_cmd)
        
        # Find response files in Windows outgoing directory
        response_files = []
        if os.path.exists(WINDOWS_OUTGOING_DIR):
            for filename in os.listdir(WINDOWS_OUTGOING_DIR):
                if filename.startswith("resp_") and filename.endswith(".json"):
                    response_files.append(filename)
        else:
            print(f"Windows outgoing directory does not exist: {WINDOWS_OUTGOING_DIR}")
            os.makedirs(WINDOWS_OUTGOING_DIR, exist_ok=True)
            return 0
                
        if not response_files:
            return 0
            
        print(f"Found {len(response_files)} response files to send to Mac")
        
        sent_count = 0
        for filename in response_files:
            # Upload the file using scp
            win_path = os.path.join(WINDOWS_OUTGOING_DIR, filename)
            mac_path = os.path.join(MAC_INCOMING_DIR, filename).replace('\\', '/')
            
            # Try up to retry_max times
            success = False
            for attempt in range(retry_max):
                try:
                    scp_command = ['scp', '-B']  # -B for binary mode
                    if MAC_SSH_KEY_PATH:
                        scp_command.extend(['-i', MAC_SSH_KEY_PATH])
                        
                    scp_command.extend([win_path, f"{MAC_SSH_USER}@{MAC_SSH_HOST}:{mac_path}"])
                    
                    process = subprocess.Popen(
                        scp_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    _, stderr = process.communicate()
                    
                    # Verify the file was transferred correctly
                    if process.returncode == 0 and verify_file(win_path, mac_path, is_upload=True):
                        print(f"Uploaded {filename} to Mac (attempt {attempt+1})")
                        sent_count += 1
                        success = True
                        
                        # Remove the file from Windows only after successful transfer
                        try:
                            os.remove(win_path)
                            print(f"Removed {filename} from Windows")
                        except Exception as e:
                            print(f"Error removing {filename}: {e}")
                        break
                    else:
                        print(f"Failed to upload {filename} (attempt {attempt+1}): {stderr}")
                        # Short pause before retrying
                        time.sleep(0.5)
                except Exception as e:
                    print(f"Error uploading {filename} (attempt {attempt+1}): {e}")
                    time.sleep(0.5)
            
            if not success:
                print(f"Failed to upload {filename} after {retry_max} attempts")
                
        return sent_count
    except Exception as e:
        print(f"Error sending response files: {e}")
        traceback.print_exc()
        return 0

def verify_file(local_path, remote_path, is_upload=True):
    """Verify file was transferred correctly by comparing size"""
    try:
        local_size = os.path.getsize(local_path) if os.path.exists(local_path) else -1
        
        if is_upload:
            # Check remote file size
            size_cmd = f"stat -f%z {remote_path}" 
            result = run_ssh_command(size_cmd)
            if result:
                try:
                    remote_size = int(result.strip())
                    return local_size == remote_size
                except ValueError:
                    return False
            return False
        else:
            # We downloaded - check local file exists
            return os.path.exists(local_path)
    except Exception as e:
        print(f"Error verifying file: {e}")
        return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="File transfer between Mac and Windows for proxy")
    parser.add_argument('--mac-ip', type=str, required=True, help='Mac IP address')
    parser.add_argument('--mac-user', type=str, required=True, help='Mac username')
    parser.add_argument('--ssh-key', type=str, help='Path to SSH private key file')
    parser.add_argument('--interval', type=int, default=1, help='Polling interval in seconds (default: 1)')
    parser.add_argument('--ssh-port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('--retry-max', type=int, default=3, help='Maximum number of transfer retries (default: 3)')
    
    args = parser.parse_args()
    
    # Update settings from command line args
    global MAC_SSH_HOST, MAC_SSH_USER, MAC_SSH_KEY_PATH, MAC_SSH_PORT
    MAC_SSH_HOST = args.mac_ip
    MAC_SSH_USER = args.mac_user
    if args.ssh_key:
        MAC_SSH_KEY_PATH = args.ssh_key
    if args.ssh_port:
        MAC_SSH_PORT = args.ssh_port
    
    print(f"Mac-Windows File Transfer")
    print(f"=======================")
    print(f"Mac Connection Details:")
    print(f"- SSH Host: {MAC_SSH_HOST}")
    print(f"- SSH User: {MAC_SSH_USER}")
    print(f"- SSH Port: {MAC_SSH_PORT}")
    print(f"- SSH Key: {MAC_SSH_KEY_PATH or 'Using password authentication'}")
    print()
    print(f"Directory Settings:")
    print(f"- Mac Outgoing → Windows Incoming: {MAC_OUTGOING_DIR} → {WINDOWS_INCOMING_DIR}")
    print(f"- Windows Outgoing → Mac Incoming: {WINDOWS_OUTGOING_DIR} → {MAC_INCOMING_DIR}")
    print(f"- Polling Interval: {args.interval} seconds")
    print()
    
    # Ensure directories exist
    ensure_dirs()
    
    try:
        print("Starting file transfer loop. Press Ctrl+C to stop.")
        
        # First ensure directories exist
        ensure_dirs()
        print("Verified all directories exist")
        
        while True:
            # Transfer files in both directions
            req_count = len(fetch_request_files(retry_max=args.retry_max))
            resp_count = send_response_files(retry_max=args.retry_max)
            
            if req_count > 0 or resp_count > 0:
                print(f"Transferred {req_count} requests and {resp_count} responses")
                
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopping file transfer...")
    except Exception as e:
        print(f"Error in main loop: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
