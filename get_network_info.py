import socket
import subprocess
import platform

def get_local_ip():
    """Get the local IP address of this computer"""
    try:
        # Connect to a remote address to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def get_network_info():
    """Get detailed network information"""
    system = platform.system()
    
    if system == "Windows":
        try:
            result = subprocess.run(['ipconfig'], capture_output=True, text=True)
            return result.stdout
        except:
            return "Could not get network info"
    elif system == "Darwin":  # macOS
        try:
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            return result.stdout
        except:
            return "Could not get network info"
    else:  # Linux
        try:
            result = subprocess.run(['ip', 'addr'], capture_output=True, text=True)
            return result.stdout
        except:
            return "Could not get network info"

if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 50)
    print("🌐 NETWORK ACCESS INFORMATION")
    print("=" * 50)
    print(f"Local IP Address: {local_ip}")
    print(f"App URL: http://{local_ip}:5000")
    print()
    print("📱 To access from your phone:")
    print("1. Make sure your phone is on the same WiFi network")
    print("2. Open your phone's browser")
    print(f"3. Go to: http://{local_ip}:5000")
    print()
    print("💡 If the above doesn't work, try these IPs:")
    print("Common local IPs: 192.168.1.x, 192.168.0.x, 10.0.0.x")
    print()
    print("🔧 Detailed Network Info:")
    print("-" * 30)
    print(get_network_info())
