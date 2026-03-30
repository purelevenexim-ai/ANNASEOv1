#!/usr/bin/env python3
"""
Start backend and run comprehensive tests
"""
import subprocess
import time
import os
import sys
import signal

# Kill any existing uvicorn
os.system("pkill -9 -f uvicorn 2>/dev/null")
time.sleep(2)

# Start backend
print("[*] Starting uvicorn backend...")
backend_proc = subprocess.Popen(
    ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
    cwd="/root/ANNASEOv1",
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)
print(f"[*] Backend PID: {backend_proc.pid}")

# Wait for startup
time.sleep(5)

# Run test
print("[*] Running comprehensive test suite...")
os.system("cd /root/ANNASEOv1 && python3 test_all_issues.py")

# Keep backend running
print("\n[*] Backend running (press Ctrl+C to stop)")
try:
    backend_proc.wait()
except KeyboardInterrupt:
    print("\n[*] Shutting down...")
    backend_proc.terminate()
    backend_proc.wait(timeout=5)
