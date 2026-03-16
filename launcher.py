import subprocess
import os
import sys
import time
import socket

def kill_process_on_port(port):
    print(f"[*] Checking if port {port} is busy...")
    try:
        if os.name == 'nt': # Windows
            cmd = f"netstat -ano | findstr :{port}"
            output = subprocess.check_output(cmd, shell=True).decode()
            for line in output.strip().split('\n'):
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    print(f"[!] Killing process {pid} on port {port}...")
                    subprocess.run(f"taskkill /F /PID {pid} /T", shell=True)
                    time.sleep(1)
    except Exception:
        print(f"[OK] Port {port} is free or couldn't be checked.")

def launch():
    print("==================================================")
    print("   Lycée Al-Mansour - Failsafe Launcher")
    print("==================================================")
    
    # 1. Clear Port 5000
    kill_process_on_port(5000)
    
    # 2. Setup Paths
    root_dir = os.path.dirname(os.path.abspath(__file__))
    app_py = os.path.join(root_dir, 'server', 'app.py')
    
    if not os.path.exists(app_py):
        print(f"[ERROR] Could not find {app_py}")
        return

    # 3. Start Server
    print(f"[*] Starting server from: {app_py}")
    print("[!] IMPORTANT: Keep this window open.")
    print("[!] Visit: http://127.0.0.1:5000")
    print("--------------------------------------------------")
    
    try:
        # Use sys.executable to ensure we use the same python version
        subprocess.run([sys.executable, app_py], cwd=root_dir)
    except KeyboardInterrupt:
        print("\n[!] Server stopped by user.")
    except Exception as e:
        print(f"[ERROR] Launcher failed: {e}")

if __name__ == "__main__":
    launch()
