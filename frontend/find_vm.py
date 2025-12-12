import socket
import threading
import ipaddress
import socket
import threading
import ipaddress
import sys
import os
import time
import sys
import os
import time

# Configuration
TARGET_PORT = 8001
CLIENT_FILE = "src/api/client.ts"
ENV_FILE = ".env"

import subprocess
import re

def get_local_subnets():
    subnets = []
    try:
        # Use ip addr command
        output = subprocess.check_output(["ip", "-o", "-f", "inet", "addr", "show"], text=True)
        for line in output.splitlines():
            # Parse line like: 2: wlp1s0    inet 192.168.1.5/24 ...
            # Skip docker and bridge interfaces
            if "docker" in line or "br-" in line or "veth" in line:
                continue
                
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if match:
                ip = match.group(1)
                cidr = int(match.group(2))
                if ip.startswith("127."):
                    continue
                
                # Calculate network
                try:
                    network = ipaddress.IPv4Network(f"{ip}/{cidr}", strict=False)
                    subnets.append(network)
                except ValueError:
                    continue
    except Exception as e:
        print(f"⚠️ Error getting subnets: {e}")
        # Fallback to common subnets if ip command fails
        subnets.append(ipaddress.IPv4Network("192.168.1.0/24"))
        subnets.append(ipaddress.IPv4Network("10.0.2.0/24"))
        
    return subnets

def check_port(ip, port, result_list):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5) # Fast timeout
    try:
        result = sock.connect_ex((str(ip), port))
        if result == 0:
            result_list.append(str(ip))
    except:
        pass
    finally:
        sock.close()

def scan_network():
    print("🔍 Scanning network for DGIS Backend (Port 8000)...")
    subnets = get_local_subnets()
    found_ips = []
    threads = []

    for subnet in subnets:
        print(f"   Scanning subnet: {subnet}")
        # Scan all hosts in subnet
        for ip in subnet.hosts():
            t = threading.Thread(target=check_port, args=(ip, TARGET_PORT, found_ips))
            t.start()
            threads.append(t)
            
            # Limit concurrent threads to avoid OS limits
            if len(threads) > 200:
                for t in threads:
                    t.join()
                threads = []
    
    # Join remaining
    for t in threads:
        t.join()

    return found_ips

def update_files(ip):
    base_url = f"http://{ip}:{TARGET_PORT}/api"
    print(f"✅ FOUND VM IP: {ip}")
    print(f"📝 Updating configuration to: {base_url}")

    # 1. Update client.ts
    if os.path.exists(CLIENT_FILE):
        with open(CLIENT_FILE, 'r') as f:
            lines = f.readlines()
        
        with open(CLIENT_FILE, 'w') as f:
            for line in lines:
                if "const BASE_URL =" in line:
                    f.write(f"const BASE_URL = '{base_url}';\n")
                else:
                    f.write(line)
        print(f"   Updated {CLIENT_FILE}")
    else:
        print(f"   ❌ Error: {CLIENT_FILE} not found")

    # 2. Update .env
    with open(ENV_FILE, 'w') as f:
        f.write(f"VITE_API_URL={base_url}\n")
    print(f"   Updated {ENV_FILE}")

def main():
    # 1. Try to find IP
    ips = scan_network()
    
    if not ips:
        print("❌ Could not find any device on port 8000.")
        print("   Ensure the VM is running and Network Adapter 2 (Bridge) is connected.")
        sys.exit(1)
    
    # Filter out own IPs
    local_ips = []
    try:
        output = subprocess.check_output(["ip", "-o", "-f", "inet", "addr", "show"], text=True)
        for line in output.splitlines():
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
            if match:
                local_ips.append(match.group(1))
    except:
        pass

    # Remove local IPs from results (usually we want the VM, not ourselves)
    final_ips = [ip for ip in ips if ip not in local_ips]
    
    if not final_ips:
        if ips:
            print(f"⚠️  Only found local IPs {ips}. Assuming Backend is running locally.")
            final_ips = ips
        else:
            print("⚠️  No IPs found via scan. Falling back to localhost.")
            final_ips = ["localhost"]
            # sys.exit(1)  <-- Removed exit to allow fallback

        
    target_ip = final_ips[0]
    if len(final_ips) > 1:
        print(f"⚠️  Multiple remote IPs found: {final_ips}. Using {target_ip}")
    
    # 2. Update config
    update_files(target_ip)
    print("🚀 Configuration updated successfully.")

if __name__ == "__main__":
    main()
