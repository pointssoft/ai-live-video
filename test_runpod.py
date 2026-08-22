import os
import urllib.request
import json
import logging

try:
    with open('.env', 'r') as f:
        env = dict(line.strip().split('=', 1) for line in f if '=' in line and not line.startswith('#'))
    api_key = env.get('RUNPOD_API_KEY', '')
except:
    api_key = os.environ.get('RUNPOD_API_KEY', '')

if not api_key:
    print("No API key found")
    exit(1)

payload = {
    "query": """query { pod(input: {podId: "eps8wyc5vqnkuh"}) { 
        id desiredStatus machineId 
        runtime { uptimeInSeconds container { cpuPercent memoryPercent } } 
    } }"""
}

req = urllib.request.Request(
    f'https://api.runpod.io/graphql?api_key={api_key}',
    data=json.dumps(payload).encode(),
    headers={'content-type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
