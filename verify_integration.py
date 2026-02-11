import requests
import json
import time
import sys
import uuid

# Configuration
# Users should set API_URL to their deployed endpoint or local SAM generic endpoint
API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"

print(f"Using API URL: {API_URL}")

def verify_integration():
    restaurant_id = "rest_test_01"
    
    # 1. Create Order
    print("\n[1] Creating Order...")
    order_payload = {
        "restaurant_id": restaurant_id,
        "items": [{"id": "item_1", "qty": 2, "name": "Burger"}]
    }
    
    try:
        res = requests.post(f"{API_URL}/v1/orders", json=order_payload)
        if res.status_code != 201:
            print(f"FAILED: Create Order returned {res.status_code} {res.text}")
            return
            
        order_data = res.json()
        order_id = order_data.get('order_id')
        print(f"SUCCESS: Created Order {order_id}")
        
    except Exception as e:
        print(f"ERROR: Failed to connect to API: {e}")
        return

    # 2. List Orders (Kitchen View)
    print("\n[2] Listing Restaurant Orders (Kitchen View)...")
    # Wait a moment for consistency if needed
    time.sleep(1)
    
    res = requests.get(f"{API_URL}/v1/restaurants/{restaurant_id}/orders")
    if res.status_code != 200:
        print(f"FAILED: List Orders returned {res.status_code} {res.text}")
    else:
        orders = res.json().get('orders', [])
        found = any(o['order_id'] == order_id for o in orders)
        if found:
            print(f"SUCCESS: Order {order_id} found in list")
        else:
            print(f"WARNING: Order {order_id} NOT found in list (Consistency delay?)")

    # 3. Update Status (Kitchen Move)
    print("\n[3] Updating Status to IN_PROGRESS...")
    res = requests.post(f"{API_URL}/v1/restaurants/{restaurant_id}/orders/{order_id}/status", json={"status": "IN_PROGRESS"})
    if res.status_code == 200:
        print("SUCCESS: Status updated")
    else:
        print(f"FAILED: Update Status returned {res.status_code} {res.text}")

    # 4. Verify Status
    print("\n[4] Verifying Order Status...")
    res = requests.get(f"{API_URL}/v1/orders/{order_id}")
    if res.status_code == 200:
        current_status = res.json().get('status')
        if current_status == "IN_PROGRESS":
            print(f"SUCCESS: Order status is {current_status}")
        else:
            print(f"FAILED: Expected IN_PROGRESS, got {current_status}")
    else:
        print(f"FAILED: Get Order returned {res.status_code}")

    print("\n--- Integration Verification Complete ---")
    print("Note: Real 'Kitchen Service' (backend) integration requires event plumbing which is defined as a future task.")

if __name__ == "__main__":
    verify_integration()
