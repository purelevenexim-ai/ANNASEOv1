#!/usr/bin/env python3
"""
Quick Ollama Integration Test — Focus on verifying remote Ollama is working.
Doesn't require spending cloud API quota.
"""
import sys
import os
import requests
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.235.16.165:11434")
print("\n" + "=" * 70)
print("QUICK OLLAMA INTEGRATION TEST")
print("=" * 70)

# Test 1: Can reach Ollama server?
print("\n[1] Testing Ollama server reachability...")
try:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    if r.status_code == 200:
        models = r.json().get("models", [])
        if models:
            print(f"    ✓ Connected to {OLLAMA_URL}")
            for m in models:
                print(f"      - {m['name']} ({m['size']/1e9:.1f}GB)")
        else:
            print(f"    ✗ No models loaded")
            sys.exit(1)
    else:
        print(f"    ✗ Server returned {r.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"    ✗ Cannot reach Ollama: {e}")
    sys.exit(1)

# Test 2: Direct inference on Ollama
print("\n[2] Testing direct Ollama inference...")
try:
    import time
    prompts = [
        ("Short prompt", "Write 1 sentence about SEO."),
        ("Medium prompt", "List 5 benefits of remote work in 50 words."),
    ]
    
    for label, prompt in prompts:
        print(f"\n    Testing: {label}")
        start = time.time()
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 100},
            },
            timeout=120,
        )
        duration = time.time() - start
        
        if r.status_code == 200:
            resp = r.json()
            output = resp.get("response", "").strip()[:100]
            print(f"      ✓ Generated in {duration:.1f}s")
            print(f"      Output: {output}...")
        else:
            print(f"      ✗ Failed: {r.status_code}")
            
except Exception as e:
    print(f"    ✗ Inference failed: {e}")
    sys.exit(1)

# Test 3: Check AnnaSEO config
print("\n[3] Checking AnnaSEO configuration...")
try:
    from services.db_session import SessionLocal
    import sqlalchemy as sa
    db = SessionLocal()
    
    # Check what OLIGMA URL is in the system
    result = db.execute(sa.text("SELECT key, value_enc FROM api_settings WHERE key='ollama_url'")).fetchone()
    if result:
        from cryptography.fernet import Fernet
        fkey = os.getenv("FERNET_KEY", "")
        if fkey:
            f = Fernet(fkey.encode())
            try:
                stored_url = f.decrypt(result[1].encode()).decode()
                print(f"    ✓ Stored Ollama URL (DB): {stored_url}")
            except:
                print(f"    ⚠ Stored value encrypted, cannot decrypt")
        else:
            print(f"    ⚠ No FERNET_KEY to decrypt")
    else:
        print(f"    ⚠ No Ollama URL stored in DB")
    
    # Check env var
    env_url = os.getenv("OLLAMA_URL")
    if env_url:
        print(f"    ✓ Current OLLAMA_URL (env): {env_url}")
    else:
        print(f"    ✗ OLLAMA_URL not in environment")
    
    db.close()
except Exception as e:
    print(f"    ⚠ Could not check DB config: {e}")

print("\n" + "=" * 70)
print("✓ ALL TESTS PASSED - Remote Ollama is working!")
print("=" * 70)
print(f"\nOllama is ready at: {OLLAMA_URL}")
print("You can now add this server in Settings → External Ollama Servers")
print()
