import requests
import json

API_KEY = "admin_97375e28712d7627e7cea67c8c86d60d"
BIN_ID = "6a511a2f02866d9b1850deec"
API_ENDPOINT = "https://jsonbinbro.onrender.com/api"

# The data structure we want to store
data = {
    "users": [],
    "buildings": [],
    "properties": [],
    "tenants": [],
    "payments": [],
    "complaints": [],
    "chats": [],
    "agreements": [],
    "agents": []
}

print("=" * 60)
print("Resetting Database...")
print("=" * 60)

# Try different approaches to save data

# Approach 1: Direct PUT with data
url = f"{API_ENDPOINT}/bins/{BIN_ID}?api_key={API_KEY}"
print(f"\nApproach 1: Direct PUT")
print(f"URL: {url}")
print(f"Data: {json.dumps(data, indent=2)}")

response = requests.put(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Approach 2: PUT with data wrapped in "data" field
print(f"\nApproach 2: PUT with 'data' wrapper")
wrapped_data = {"data": data}
response = requests.put(url, json=wrapped_data)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")

# Approach 3: Create a new bin and delete the old one
print(f"\nApproach 3: Create new bin")
create_url = f"{API_ENDPOINT}/bins?api_key={API_KEY}"
response = requests.post(create_url, json=data)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"New bin created: {json.dumps(result, indent=2)}")
    print(f"New Bin ID: {result.get('id')}")
    print("\nUpdate your .env file with this new Bin ID")
else:
    print(f"Failed to create new bin: {response.text}")

# Verify current state
print("\n" + "=" * 60)
print("Verifying Current State")
print("=" * 60)

verify_response = requests.get(url)
print(f"Verify Status: {verify_response.status_code}")
verify_data = verify_response.json()
print(f"Verify Response: {json.dumps(verify_data, indent=2)}")

if verify_data.get('data') is not None:
    print("\n✅ DATA IS NOT NULL! Database is working!")
else:
    print("\n❌ DATA IS STILL NULL. Please use the new Bin ID from Approach 3.")