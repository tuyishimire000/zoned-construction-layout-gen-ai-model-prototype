import subprocess
import time
import urllib.request
import json
import threading

def stream_logs():
    with open('scratch/vlog.txt', 'w') as f:
        subprocess.run('npx vercel logs ishimusa.vercel.app', shell=True, stdout=f, stderr=subprocess.STDOUT)

t = threading.Thread(target=stream_logs, daemon=True)
t.start()

time.sleep(5)
print("Sending request...")
req = urllib.request.Request(
    'https://ishimusa.vercel.app/api/auth/register',
    data=json.dumps({'email':'test3@test.com','password':'password123','full_name':'Test User'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    urllib.request.urlopen(req)
    print("Success?")
except Exception as e:
    print(f"Failed: {e}")

time.sleep(5)
print("Done")
